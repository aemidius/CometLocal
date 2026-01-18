"""
Helper para generar evidencias automáticas en errores.

SPRINT C2.16: Evidencias automáticas (screenshot, HTML, log) incluso si evidence_dir es None.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
import time
import os
import json
import traceback
from datetime import datetime


def ensure_evidence_dir(evidence_dir: Optional[Path], run_id: Optional[str] = None, tenant_id: str = "default") -> Path:
    """
    Asegura que existe un directorio de evidencias.
    
    Si evidence_dir es None, crea un directorio temporal bajo data/tenants/<tenant_id>/runs/tmp_<timestamp>/
    
    Args:
        evidence_dir: Directorio de evidencias (puede ser None)
        run_id: ID del run (opcional, para naming)
        tenant_id: ID del tenant (default "default")
    
    Returns:
        Path al directorio de evidencias (nunca None)
    """
    if evidence_dir is not None:
        evidence_dir = Path(evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        return evidence_dir
    
    # Crear directorio temporal
    from backend.config import DATA_DIR
    from backend.shared.tenant_paths import tenant_runs_root, ensure_write_dir
    timestamp = int(time.time())
    runs_root = tenant_runs_root(DATA_DIR, tenant_id)
    tmp_dir = runs_root / f"tmp_{timestamp}"
    if run_id:
        tmp_dir = runs_root / f"tmp_{run_id}_{timestamp}"
    ensure_write_dir(tmp_dir)
    print(f"[EVIDENCE] evidence_dir era None, creado directorio temporal: {tmp_dir}")
    return tmp_dir


def generate_error_evidence(
    page: Any,
    phase: str,
    attempt: int,
    error: Exception,
    evidence_dir: Optional[Path],
    context: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """
    Genera evidencias automáticas en caso de error.
    
    Args:
        page: Página de Playwright (puede ser None)
        phase: Fase donde ocurrió el error
        attempt: Número de intento (1-indexed)
        error: Excepción capturada
        evidence_dir: Directorio de evidencias (puede ser None)
        context: Contexto adicional (selector, URL, etc.)
        run_id: ID del run (opcional)
    
    Returns:
        Dict con paths de evidencias generadas:
        {
            "evidence_dir": str,
            "screenshot_fullpage": str | None,
            "screenshot_phase": str | None,
            "html_snippet": str | None,
            "error_log": str,
        }
    """
    context = context or {}
    
    # Asegurar que existe evidence_dir
    evidence_dir = ensure_evidence_dir(evidence_dir, run_id, tenant_id)
    
    # Crear subdirectorio por fase e intento
    phase_evidence_dir = evidence_dir / phase / f"attempt_{attempt}"
    phase_evidence_dir.mkdir(parents=True, exist_ok=True)
    
    evidence_paths = {
        "evidence_dir": str(phase_evidence_dir),
        "screenshot_fullpage": None,
        "screenshot_phase": None,
        "html_snippet": None,
        "error_log": str(phase_evidence_dir / "error_log.txt"),
    }
    
    # 1) Screenshot fullpage
    if page:
        try:
            screenshot_path = phase_evidence_dir / "screenshot_fullpage.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            evidence_paths["screenshot_fullpage"] = str(screenshot_path)
            print(f"[EVIDENCE] Screenshot fullpage guardado: {screenshot_path}")
        except Exception as e:
            print(f"[EVIDENCE] ⚠️ Error guardando screenshot fullpage: {e}")
    
    # 2) Screenshot específico de la fase (si hay selector/context)
    if page and context.get("selector"):
        try:
            screenshot_path = phase_evidence_dir / f"screenshot_{phase}.png"
            selector = context.get("selector")
            if selector:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        element.screenshot(path=str(screenshot_path))
                        evidence_paths["screenshot_phase"] = str(screenshot_path)
                        print(f"[EVIDENCE] Screenshot de fase guardado: {screenshot_path}")
                except Exception:
                    # Si falla el selector, intentar screenshot de la página completa
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    evidence_paths["screenshot_phase"] = str(screenshot_path)
        except Exception as e:
            print(f"[EVIDENCE] ⚠️ Error guardando screenshot de fase: {e}")
    
    # 3) HTML snippet del contenedor relevante
    if page:
        try:
            html_path = phase_evidence_dir / "html_snippet.html"
            html_content = ""
            
            # Intentar obtener HTML del contenedor relevante según la fase
            if phase == "grid_load" and context.get("grid_selector"):
                try:
                    grid_html = page.locator(context["grid_selector"]).first.inner_html()
                    html_content = f"<!-- Grid HTML (selector: {context['grid_selector']}) -->\n{grid_html}"
                except Exception:
                    html_content = page.content()
            elif phase == "upload" and context.get("upload_form_selector"):
                try:
                    form_html = page.locator(context["upload_form_selector"]).first.inner_html()
                    html_content = f"<!-- Upload form HTML (selector: {context['upload_form_selector']}) -->\n{form_html}"
                except Exception:
                    html_content = page.content()
            else:
                # Fallback: HTML completo de la página
                html_content = page.content()
            
            html_path.write_text(html_content, encoding="utf-8")
            evidence_paths["html_snippet"] = str(html_path)
            print(f"[EVIDENCE] HTML snippet guardado: {html_path}")
        except Exception as e:
            print(f"[EVIDENCE] ⚠️ Error guardando HTML snippet: {e}")
    
    # 4) Error log textual
    try:
        error_log_path = phase_evidence_dir / "error_log.txt"
        log_content = f"""Error Evidence Report
========================
Timestamp: {datetime.utcnow().isoformat()}
Phase: {phase}
Attempt: {attempt}
Error Type: {type(error).__name__}
Error Message: {str(error)}

Context:
{json.dumps(context, indent=2, default=str) if context else "No context provided"}

Traceback:
{traceback.format_exc()}
"""
        error_log_path.write_text(log_content, encoding="utf-8")
        print(f"[EVIDENCE] Error log guardado: {error_log_path}")
    except Exception as e:
        print(f"[EVIDENCE] ⚠️ Error guardando error log: {e}")
    
    return evidence_paths


def generate_timeout_evidence(
    page: Any,
    phase: str,
    timeout_s: float,
    evidence_dir: Optional[Path],
    context: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """
    Genera evidencias automáticas en caso de timeout.
    
    Args:
        page: Página de Playwright (puede ser None)
        phase: Fase donde ocurrió el timeout
        timeout_s: Timeout en segundos que se excedió
        evidence_dir: Directorio de evidencias (puede ser None)
        context: Contexto adicional
        run_id: ID del run (opcional)
    
    Returns:
        Dict con paths de evidencias generadas
    """
    # Crear excepción simulada para reutilizar generate_error_evidence
    from backend.shared.phase_timeout import PhaseTimeoutError
    timeout_error = PhaseTimeoutError(phase, timeout_s, f"Timeout in phase '{phase}' after {timeout_s}s")
    return generate_error_evidence(
        page=page,
        phase=phase,
        attempt=1,  # Timeout es siempre el primer intento
        error=timeout_error,
        evidence_dir=evidence_dir,
        context={**(context or {}), "timeout_s": timeout_s},
        run_id=run_id,
        tenant_id=tenant_id,
    )
