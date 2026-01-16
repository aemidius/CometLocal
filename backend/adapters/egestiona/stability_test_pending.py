"""
Stability test para validar consistencia en detección de pendientes.

Ejecuta el mismo flujo READ-ONLY múltiples veces y valida que los resultados son consistentes.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.adapters.egestiona.match_pending_headful import run_match_pending_documents_readonly_headful
from backend.repository.data_bootstrap_v1 import ensure_data_layout


def compute_screen_signature(
    page_url: str,
    title: str,
    breadcrumbs: List[str],
    listado_link_count: int,
    has_grid_container: bool,
    first_items_text: List[str],
) -> str:
    """
    Calcula una firma determinista de la pantalla.
    
    Args:
        page_url: URL de la página
        title: Título de la página
        breadcrumbs: Lista de breadcrumbs visibles
        listado_link_count: Número de anchors listado_link encontrados
        has_grid_container: Si hay grid container
        first_items_text: Texto de los 3 primeros items (si existen)
    
    Returns:
        Hash SHA256 corto (primeros 16 caracteres)
    """
    # Normalizar y construir string base
    breadcrumbs_str = "|".join(breadcrumbs)
    items_str = "|".join(first_items_text[:3])
    
    base_string = f"{page_url}|{title}|{breadcrumbs_str}|{listado_link_count}|{has_grid_container}|{items_str}"
    
    # Hash
    hash_obj = hashlib.sha256(base_string.encode('utf-8'))
    return hash_obj.hexdigest()[:16]


def run_stability_test_pending_readonly(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    company_key: str,
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    iterations: int = 5,
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.5,
) -> Dict[str, Any]:
    """
    Ejecuta stability test: N iteraciones del mismo flujo READ-ONLY.
    
    Returns:
        Dict con resumen de todas las iteraciones y resultado (PASS/FAIL)
    """
    base_dir = Path(base_dir)
    ensure_data_layout()
    
    # Crear directorio para el stability test
    stability_dir = base_dir / "stability_tests" / f"pending_{coordination}_{company_key}_{int(time.time())}"
    stability_dir.mkdir(parents=True, exist_ok=True)
    
    results: List[Dict[str, Any]] = []
    all_counts: List[int] = []
    all_signatures: List[str] = []
    
    print(f"[STABILITY_TEST] Iniciando stability test: {iterations} iteraciones")
    print(f"[STABILITY_TEST] Coord: {coordination}, Company: {company_key}, Person: {person_key}")
    
    for i in range(iterations):
        print(f"\n[STABILITY_TEST] === Iteración {i + 1}/{iterations} ===")
        iteration_start = time.time()
        
        try:
            # Ejecutar el flujo normal
            run_id = run_match_pending_documents_readonly_headful(
                base_dir=base_dir,
                platform=platform,
                coordination=coordination,
                company_key=company_key,
                person_key=person_key,
                limit=limit,
                only_target=only_target,
                slow_mo_ms=slow_mo_ms,
                viewport=viewport,
                wait_after_login_s=wait_after_login_s,
            )
            
            # Leer resultados del run
            run_dir = base_dir / "runs" / run_id
            evidence_dir = run_dir / "evidence"
            
            # Leer pending_items.json
            pending_items_path = evidence_dir / "pending_items.json"
            pending_items = []
            if pending_items_path.exists():
                try:
                    pending_data = json.loads(pending_items_path.read_text(encoding="utf-8"))
                    pending_items = pending_data.get("items", [])
                except Exception as e:
                    print(f"[STABILITY_TEST] Error al leer pending_items.json: {e}")
            
            count = len(pending_items)
            all_counts.append(count)
            
            # Leer diagnostic info si existe (priorizar diagnostic_info.json, luego diagnostic_zero_case.json)
            diagnostic_info = {}
            diagnostic_path = evidence_dir / "diagnostic_info.json"
            if diagnostic_path.exists():
                try:
                    diagnostic_info = json.loads(diagnostic_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            # Si no hay diagnostic_info.json, intentar diagnostic_zero_case.json
            if not diagnostic_info:
                diagnostic_path = evidence_dir / "diagnostic_zero_case.json"
                if diagnostic_path.exists():
                    try:
                        diagnostic_info = json.loads(diagnostic_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            
            # Leer screen signature si existe
            screen_signature = diagnostic_info.get("screen_signature", "unknown")
            all_signatures.append(screen_signature)
            
            # Leer frame info
            frame_url = diagnostic_info.get("main_frame_url", "unknown")
            page_url = diagnostic_info.get("page_url", "unknown")
            
            iteration_result = {
                "iteration": i + 1,
                "run_id": run_id,
                "count_pendings": count,
                "page_url": page_url,
                "frame_url": frame_url,
                "screen_signature": screen_signature,
                "duration_ms": int((time.time() - iteration_start) * 1000),
                "success": True,
            }
            
            results.append(iteration_result)
            print(f"[STABILITY_TEST] Iteración {i + 1}: {count} pendientes, signature: {screen_signature[:8]}...")
            
        except Exception as e:
            print(f"[STABILITY_TEST] Error en iteración {i + 1}: {e}")
            iteration_result = {
                "iteration": i + 1,
                "run_id": None,
                "count_pendings": 0,
                "page_url": "error",
                "frame_url": "error",
                "screen_signature": "error",
                "duration_ms": int((time.time() - iteration_start) * 1000),
                "success": False,
                "error": str(e),
            }
            results.append(iteration_result)
            all_counts.append(0)
        
        # Esperar un poco entre iteraciones para evitar rate limiting
        if i < iterations - 1:
            time.sleep(2.0)
    
    # Análisis de resultados
    unique_counts = set(all_counts)
    unique_signatures = set([s for s in all_signatures if s != "unknown" and s != "error"])
    
    # Criterio de éxito
    passed = True
    failure_reasons = []
    
    # 1. Si hay diferentes conteos (y no todos son 0)
    if len(unique_counts) > 1:
        non_zero_counts = [c for c in all_counts if c > 0]
        if len(non_zero_counts) > 0:
            passed = False
            failure_reasons.append(f"Inconsistencia en conteos: {unique_counts} (algunos >0, algunos 0)")
    
    # 2. Si todas son 0 pero debería haber pendientes (validar manualmente)
    if len(unique_counts) == 1 and list(unique_counts)[0] == 0:
        failure_reasons.append("Todas las iteraciones devolvieron 0 (validar manualmente si hay pendientes reales)")
        # No marcamos como FAIL automáticamente, requiere validación manual
    
    # 3. Si hay diferentes signatures (indica diferentes pantallas)
    if len(unique_signatures) > 1:
        passed = False
        failure_reasons.append(f"Inconsistencia en screen signatures: {unique_signatures}")
    
    # Guardar resumen
    summary = {
        "test_type": "stability_test_pending_readonly",
        "coordination": coordination,
        "company_key": company_key,
        "person_key": person_key,
        "iterations": iterations,
        "results": results,
        "analysis": {
            "unique_counts": list(unique_counts),
            "unique_signatures": list(unique_signatures),
            "all_counts": all_counts,
            "all_signatures": all_signatures,
            "min_count": min(all_counts) if all_counts else 0,
            "max_count": max(all_counts) if all_counts else 0,
            "avg_count": sum(all_counts) / len(all_counts) if all_counts else 0,
        },
        "passed": passed,
        "failure_reasons": failure_reasons,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    
    summary_path = stability_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n[STABILITY_TEST] === RESUMEN ===")
    print(f"[STABILITY_TEST] Conteos únicos: {unique_counts}")
    print(f"[STABILITY_TEST] Signatures únicos: {len(unique_signatures)}")
    print(f"[STABILITY_TEST] Resultado: {'PASS' if passed else 'FAIL'}")
    if failure_reasons:
        print(f"[STABILITY_TEST] Razones de fallo: {failure_reasons}")
    
    return summary

