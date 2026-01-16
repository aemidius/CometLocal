"""
Runner para ejecutar conectores.

Ejecuta el flujo completo de un conector:
1. Login
2. Navegación a pendientes
3. Extracción de requisitos
4. Matching con repositorio
5. Subida de documentos
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from backend.connectors.registry import get_connector
from backend.connectors.models import RunContext, PendingRequirement, UploadResult


def _generate_report(
    evidence_dir: Path,
    run_id: str,
    platform_id: str,
    tenant_id: Optional[str],
    reqs: List[PendingRequirement],
    match_results: Dict[str, Dict],
    dry_run: bool,
) -> None:
    """
    Genera informe final (JSON + Markdown).
    
    PASO 6: Generar informe determinista.
    """
    # Contar matches
    matched_count = sum(1 for r in match_results.values() if r.get("decision") == "match")
    no_match_count = len(reqs) - matched_count
    
    # Generar report.json
    report_json = {
        "run_id": run_id,
        "platform": platform_id,
        "tenant": tenant_id,
        "dry_run": dry_run,
        "timestamp": datetime.now().isoformat(),
        "counts": {
            "total_requirements": len(reqs),
            "matched": matched_count,
            "no_match": no_match_count,
        },
        "requirements": [
            {
                "id": req.id,
                "doc_type_hint": req.doc_type_hint,
                "subject_type": req.subject_type,
                "subject_id": req.subject_id,
                "period": req.period,
                "status": req.status,
            }
            for req in reqs
        ],
        "matches": [
            {
                "requirement_id": req_id,
                "matched_type_id": result.get("matched_type_id"),
                "chosen_doc_id": result.get("chosen_doc_id"),
                "decision": result.get("decision"),
                "decision_reason": result.get("decision_reason", ""),
            }
            for req_id, result in match_results.items()
        ],
        "no_matches": [
            {
                "requirement_id": req_id,
                "doc_type_hint": next((r.doc_type_hint for r in reqs if r.id == req_id), ""),
                "decision_reason": result.get("decision_reason", ""),
                "suggestion": _suggest_fix(result),
            }
            for req_id, result in match_results.items()
            if result.get("decision") == "no_match"
        ],
    }
    
    with open(evidence_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump(report_json, f, indent=2, ensure_ascii=False)
    
    # Generar report.md
    report_md_lines = [
        f"# Informe de Dry-Run - {platform_id}",
        "",
        f"**Run ID:** `{run_id}`",
        f"**Plataforma:** {platform_id}",
        f"**Tenant:** {tenant_id or 'N/A'}",
        f"**Dry-Run:** {'Sí' if dry_run else 'No'}",
        f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Resumen",
        "",
        f"- **Total de pendientes encontrados:** {len(reqs)}",
        f"- **Con match:** {matched_count}",
        f"- **Sin match:** {no_match_count}",
        "",
        "## Tabla de Resumen",
        "",
        "| Tipo Documento | Subject | Matched Type | Chosen Doc ID | Estado |",
        "|----------------|---------|--------------|---------------|--------|",
    ]
    
    for req in reqs:
        match_result = match_results.get(req.id, {})
        matched_type = match_result.get("matched_type_id") or "-"
        chosen_doc = match_result.get("chosen_doc_id") or "-"
        decision = match_result.get("decision", "no_match")
        status_emoji = "✅" if decision == "match" else "❌"
        
        report_md_lines.append(
            f"| {req.doc_type_hint} | {req.subject_id or '-'} | {matched_type} | {chosen_doc} | {status_emoji} |"
        )
    
    report_md_lines.extend([
        "",
        "## Pendientes sin Match",
        "",
    ])
    
    no_matches = [r for r in reqs if match_results.get(r.id, {}).get("decision") == "no_match"]
    if no_matches:
        for req in no_matches:
            match_result = match_results.get(req.id, {})
            reason = match_result.get("decision_reason", "No se encontró documento coincidente")
            suggestion = _suggest_fix(match_result)
            
            report_md_lines.extend([
                f"### {req.doc_type_hint}",
                "",
                f"- **Subject:** {req.subject_id or 'N/A'}",
                f"- **Razón:** {reason}",
                f"- **Sugerencia:** {suggestion}",
                "",
            ])
    else:
        report_md_lines.append("No hay pendientes sin match.")
    
    report_md_lines.extend([
        "",
        "---",
        f"*Generado automáticamente el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ])
    
    with open(evidence_dir / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_md_lines))


def _suggest_fix(match_result: Dict) -> str:
    """Genera sugerencia de cómo arreglar un no-match."""
    reason = match_result.get("decision_reason", "").lower()
    
    if "alias" in reason or "tipo" in reason:
        return "Añadir alias al tipo de documento en el repositorio"
    elif "documento" in reason or "doc" in reason:
        return "Añadir documento al repositorio"
    elif "subject" in reason or "empresa" in reason or "trabajador" in reason:
        return "Verificar mapping de subject (empresa/trabajador)"
    else:
        return "Revisar configuración del repositorio y reglas de matching"


async def run_connector(
    platform_id: str,
    tenant_id: Optional[str] = None,
    headless: bool = True,
    max_items: int = 5,
    base_url: Optional[str] = None,
    evidence_base_dir: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Ejecuta un conector completo.
    
    Args:
        platform_id: ID de la plataforma (ej "egestiona")
        tenant_id: ID del tenant/empresa (opcional)
        headless: Si ejecutar en modo headless
        max_items: Máximo número de items a procesar
        base_url: URL base del portal (opcional)
        evidence_base_dir: Directorio base para evidencias (opcional)
    
    Returns:
        Resumen JSON con counts y results
    
    Raises:
        ValueError: Si el conector no está registrado
        Exception: Si hay errores durante la ejecución
    """
    # Crear contexto de ejecución
    run_id = RunContext.create_run_id()
    
    # Crear directorio de evidencias
    if evidence_base_dir:
        evidence_dir = Path(evidence_base_dir) / run_id
    else:
        evidence_dir = Path("data") / "connectors" / "evidence" / run_id
    
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    ctx = RunContext(
        run_id=run_id,
        base_url=base_url,
        platform_id=platform_id,
        tenant_id=tenant_id,
        headless=headless,
        dry_run=dry_run,
        evidence_dir=str(evidence_dir),
    )
    
    # Obtener conector
    connector = get_connector(platform_id, ctx)
    if not connector:
        raise ValueError(f"Connector for platform '{platform_id}' not found")
    
    # Inicializar Playwright
    playwright = await async_playwright().start()
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    
    results: List[Dict[str, Any]] = []
    counts = {
        "total_requirements": 0,
        "matched": 0,
        "uploaded": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    try:
        # Lanzar navegador
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        # 1. Login
        try:
            await connector.login(page)
            await page.screenshot(path=str(evidence_dir / "01_login.png"), full_page=True)
        except Exception as e:
            error_msg = f"Login failed: {str(e)}"
            return {
                "run_id": run_id,
                "platform_id": platform_id,
                "error": error_msg,
                "counts": counts,
                "results": results,
            }
        
        # 2. Navegar a pendientes
        try:
            await connector.navigate_to_pending(page)
            await page.screenshot(path=str(evidence_dir / "02_pending.png"), full_page=True)
        except Exception as e:
            error_msg = f"Navigation to pending failed: {str(e)}"
            return {
                "run_id": run_id,
                "platform_id": platform_id,
                "error": error_msg,
                "counts": counts,
                "results": results,
            }
        
        # 3. Extraer requisitos pendientes
        try:
            reqs = await connector.extract_pending(page)
            counts["total_requirements"] = len(reqs)
            
            # Guardar requisitos extraídos
            reqs_data = [
                {
                    "id": req.id,
                    "subject_type": req.subject_type,
                    "subject_id": req.subject_id,
                    "doc_type_hint": req.doc_type_hint,
                    "period": req.period,
                    "due_date": req.due_date,
                    "status": req.status,
                }
                for req in reqs
            ]
            with open(evidence_dir / "requirements.json", "w", encoding="utf-8") as f:
                json.dump(reqs_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            error_msg = f"Extraction failed: {str(e)}"
            return {
                "run_id": run_id,
                "platform_id": platform_id,
                "error": error_msg,
                "counts": counts,
                "results": results,
            }
        
        # 4. Matching con repositorio
        match_results = {}
        try:
            match_results = await connector.match_repository(reqs)
            # match_results es dict[req_id] -> {decision, chosen_doc_id, ...}
            counts["matched"] = sum(1 for r in match_results.values() if r.get("decision") == "match")
        except Exception as e:
            error_msg = f"Matching failed: {str(e)}"
            return {
                "run_id": run_id,
                "platform_id": platform_id,
                "error": error_msg,
                "counts": counts,
                "results": results,
            }
        
        # 5. Subir documentos (solo si NO es dry_run)
        if not dry_run:
            reqs_to_process = reqs[:max_items]
            for req in reqs_to_process:
                match_result = match_results.get(req.id, {})
                doc_id = match_result.get("chosen_doc_id")
                
                if not doc_id:
                    counts["skipped"] += 1
                    results.append({
                        "requirement_id": req.id,
                        "status": "skipped",
                        "reason": "no_match",
                    })
                    continue
                
                try:
                    upload_result = await connector.upload_one(page, req, doc_id)
                    
                    if upload_result.success:
                        counts["uploaded"] += 1
                    else:
                        counts["failed"] += 1
                    
                    results.append({
                        "requirement_id": req.id,
                        "uploaded_doc_id": upload_result.uploaded_doc_id,
                        "portal_reference": upload_result.portal_reference,
                        "success": upload_result.success,
                        "error": upload_result.error,
                        "evidence": upload_result.evidence,
                    })
                    
                    # Screenshot después de cada subida
                    if page:
                        screenshot_path = evidence_dir / f"upload_{req.id[:8]}.png"
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        if upload_result.evidence:
                            upload_result.evidence["screenshot"] = str(screenshot_path)
                except Exception as e:
                    counts["failed"] += 1
                    results.append({
                        "requirement_id": req.id,
                        "status": "error",
                        "error": str(e),
                    })
        else:
            # En dry_run, solo registrar resultados de matching
            for req in reqs[:max_items]:
                match_result = match_results.get(req.id, {})
                results.append({
                    "requirement_id": req.id,
                    "status": "dry_run",
                    "decision": match_result.get("decision", "no_match"),
                    "chosen_doc_id": match_result.get("chosen_doc_id"),
                    "decision_reason": match_result.get("decision_reason", ""),
                })
        
        # Generar informe final (JSON + Markdown)
        _generate_report(evidence_dir, run_id, platform_id, tenant_id, reqs, match_results, dry_run)
        
        # Guardar resumen final
        summary = {
            "run_id": run_id,
            "platform_id": platform_id,
            "tenant_id": tenant_id,
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
            "counts": counts,
            "results": results,
            "evidence_dir": str(evidence_dir),
        }
        
        with open(evidence_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        return summary
    
    finally:
        # Cerrar navegador
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        await playwright.stop()
