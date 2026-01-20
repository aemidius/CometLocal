from __future__ import annotations

import json as jsonlib
import time
import uuid
import hashlib
import hmac
import os
from datetime import date as dt_date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.document_matcher_v1 import (
    DocumentMatcherV1,
    PendingItemV1,
    normalize_text,
)
from backend.shared.document_repository_v1 import DocumentStatusV1
from backend.shared.person_matcher import match_person_in_element
from backend.shared.text_normalizer import normalize_text, normalize_company_name, text_contains, extract_company_code
from backend.adapters.egestiona.grid_extract import extract_dhtmlx_grid, canonicalize_row
from backend.adapters.egestiona.pagination_helper import (
    detect_pagination_controls,
    wait_for_page_change,
    click_pagination_button,
)
from backend.adapters.egestiona.upload_policy import evaluate_upload_policy
from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS, _safe_write_json
from backend.adapters.egestiona.match_pending_headful import (
    _parse_date_from_cell,
    run_match_pending_documents_readonly_headful,
)


def _format_date_for_portal(d: Optional[dt_date]) -> Optional[str]:
    """Formatea fecha como DD/MM/YYYY para el portal."""
    if not d:
        return None
    return d.strftime("%d/%m/%Y")


def _evaluate_submission_guardrails(
    match_result: Dict[str, Any],
    today: dt_date,
    only_target: bool,
    match_count: int,
    doc_type: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Evalúa guardrails deterministas para decidir si se puede auto-enviar.
    
    Retorna:
    {
        "action": "AUTO_SUBMIT_OK" | "REVIEW_REQUIRED" | "NO_MATCH",
        "confidence": float,
        "reasons": List[str],
        "blocking_issues": List[str]
    }
    """
    best_doc = match_result.get("best_doc")
    confidence = match_result.get("confidence", 0.0)
    reasons = match_result.get("reasons", [])
    
    decision = {
        "action": "NO_MATCH",
        "confidence": confidence,
        "reasons": reasons.copy(),
        "blocking_issues": []
    }
    
    # Si no hay match -> NO_MATCH
    if not best_doc:
        decision["reasons"].append("No matching document found")
        return decision
    
    doc_status = best_doc.get("status")
    # Usar validity_from/validity_to del matcher (ya incluye override si existe)
    valid_from_str = best_doc.get("validity_from")
    valid_to_str = best_doc.get("validity_to")
    
    # Parsear fechas si son strings
    valid_from = None
    valid_to = None
    if isinstance(valid_from_str, str):
        try:
            valid_from = datetime.strptime(valid_from_str, "%Y-%m-%d").date()
        except ValueError:
            valid_from = None
    elif isinstance(valid_from_str, dt_date):
        valid_from = valid_from_str
    
    if isinstance(valid_to_str, str):
        try:
            valid_to = datetime.strptime(valid_to_str, "%Y-%m-%d").date()
        except ValueError:
            valid_to = None
    elif isinstance(valid_to_str, dt_date):
        valid_to = valid_to_str
    
    # Inicializar como REVIEW_REQUIRED (más seguro por defecto)
    decision["action"] = "REVIEW_REQUIRED"
    
    # Regla 1: Si match.confidence < 0.75 -> REVIEW_REQUIRED
    if confidence < 0.75:
        decision["blocking_issues"].append(f"confidence={confidence:.2f} < 0.75")
        decision["reasons"].append(f"Low confidence match ({confidence:.2f})")
        return decision
    
    # Regla 2: Si doc.status == draft -> REVIEW_REQUIRED
    if doc_status == "draft":
        decision["blocking_issues"].append("doc.status=draft")
        decision["reasons"].append("Document is in draft status")
        return decision
    
    # Regla 3: Si today NOT in [valid_from, valid_to + grace_days/late_submission_max_days] -> REVIEW_REQUIRED
    from datetime import timedelta
    
    # Obtener grace_days y late_submission_max_days del tipo
    grace_days = 0
    allow_late_submission = False
    late_submission_max_days = 0
    
    if doc_type:
        # Obtener grace_days del monthly config si existe
        if doc_type.validity_policy.monthly:
            grace_days = doc_type.validity_policy.monthly.grace_days or 0
        
        allow_late_submission = doc_type.allow_late_submission or False
        late_submission_max_days = doc_type.late_submission_max_days
        
        # Si late_submission_max_days es None, usar grace_days
        if late_submission_max_days is None:
            late_submission_max_days = grace_days
    
    if valid_from and valid_to:
        # Determinar fecha límite según política
        if allow_late_submission:
            # Permitir envío tardío hasta valid_to + late_submission_max_days
            valid_until = valid_to + timedelta(days=late_submission_max_days)
            decision["reasons"].append(f"Late submission allowed: valid_to + {late_submission_max_days} days")
        else:
            # Solo permitir dentro del período o con grace_days si hoy está dentro del período
            valid_until = valid_to
            if grace_days > 0 and valid_from <= today <= valid_to:
                # Si hoy está dentro del período, permitir grace_days después de valid_to
                valid_until = valid_to + timedelta(days=grace_days)
                decision["reasons"].append(f"Grace period: valid_to + {grace_days} days (today within period)")
            elif grace_days > 0:
                # Si hoy está fuera del período, no aplicar grace_days
                valid_until = valid_to
                decision["reasons"].append(f"Grace days ({grace_days}) not applied (today outside period)")
        
        if today < valid_from:
            decision["blocking_issues"].append(f"today ({today}) < valid_from ({valid_from})")
            decision["reasons"].append(f"Validity period starts in the future ({valid_from})")
            return decision
        elif today > valid_until:
            decision["blocking_issues"].append(f"today ({today}) > valid_until ({valid_until})")
            decision["reasons"].append(f"Validity period expired ({valid_until})")
            return decision
        else:
            decision["reasons"].append(f"Today ({today}) is within validity period ({valid_from} to {valid_until})")
    else:
        decision["blocking_issues"].append("validity dates missing")
        decision["reasons"].append("Document validity dates are missing")
        return decision
    
    # Regla 4: Si matches != 1 para only_target -> hard-stop
    if only_target and match_count != 1:
        decision["blocking_issues"].append(f"match_count={match_count} != 1 (only_target=True)")
        decision["reasons"].append(f"Expected exactly 1 match for only_target, got {match_count}")
        return decision
    
    # Si pasó todos los guardrails -> AUTO_SUBMIT_OK
    decision["action"] = "AUTO_SUBMIT_OK"
    decision["reasons"].append("All guardrails passed, ready for auto-submit")
    
    return decision


def run_build_submission_plan_readonly_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    company_key: str,
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.5,
    return_plan_only: bool = False,  # Si True, devuelve plan directamente sin crear run
    max_pages: int = 10,  # SPRINT C2.14.1: Límite de páginas para paginación
    max_items: int = 200,  # SPRINT C2.14.1: Límite de items totales
) -> str | Dict[str, Any]:
    """
    HEADFUL / READ-ONLY:
    1) Login y obtiene listado de pendientes (reutiliza lógica de matching).
    2) Para cada pendiente, hace matching con repo.
    3) Evalúa guardrails y genera plan de envío.
    4) Genera evidence: pending_items.json, match_results.json, submission_plan.json, meta.json.
    """
    # HOTFIX C2.13.7: Logging de trace al inicio de la función
    print(f"[CAE][READONLY][TRACE] run_build_submission_plan_readonly_headful ENTRADA: platform={platform} coordination={coordination} company_key={company_key} person_key={person_key} limit={limit} only_target={only_target} return_plan_only={return_plan_only}")
    
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)
    repo_store = DocumentRepositoryStoreV1(base_dir=base)
    matcher = DocumentMatcherV1(repo_store, base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        print(f"[CAE][READONLY][TRACE] BRANCH: early_return_platform_not_found reason=platform '{platform}' not found")
        raise ValueError(f"platform not found: {platform}")
    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        print(f"[CAE][READONLY][TRACE] BRANCH: early_return_coordination_not_found reason=coordination '{coordination}' not found")
        raise ValueError(f"coordination not found: {coordination}")

    client_code = (coord.client_code or "").strip()
    username = (coord.username or "").strip()
    password_ref = (coord.password_ref or "").strip()
    password = secrets.get_secret(password_ref) if password_ref else None
    if not client_code or not username or not password:
        print(f"[CAE][READONLY][TRACE] BRANCH: early_return_missing_credentials reason=client_code={bool(client_code)} username={bool(username)} password={bool(password)}")
        raise ValueError("Missing credentials: client_code/username/password_ref")
    
    print(f"[CAE][READONLY][TRACE] Credenciales OK, iniciando Playwright...")

    # HOTFIX C2.12.6: Si return_plan_only=True, NO crear run ni tocar filesystem
    # SPRINT C2.18A: Pero aún así necesitamos evidence_dir para matching_debug
    if return_plan_only:
        # No crear run_id ni directorios principales, pero sí un temp para matching_debug
        run_id = None
        run_dir = None
        # SPRINT C2.18A: Crear evidence_dir temporal para matching_debug
        # Este se copiará al plan_dir final cuando se genere el plan_id
        from tempfile import mkdtemp
        temp_evidence = Path(mkdtemp(prefix="plan_evidence_"))
        evidence_dir = temp_evidence
        evidence_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_id = f"r_{uuid.uuid4().hex}"
        run_dir = Path(base) / "runs" / run_id
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Variable para almacenar storage_state_path
    storage_state_path = None

    # Evidence paths (solo si NO es return_plan_only)
    if not return_plan_only:
        shot_01 = evidence_dir / "01_dashboard_tiles.png"
        shot_02 = evidence_dir / "02_listado_grid.png"
        pending_items_path = evidence_dir / "pending_items.json"
        match_results_path = evidence_dir / "match_results.json"
        submission_plan_path = evidence_dir / "submission_plan.json"
        meta_path = evidence_dir / "meta.json"
    else:
        shot_01 = None
        shot_02 = None
        pending_items_path = None
        match_results_path = None
        submission_plan_path = None
        meta_path = None

    started = time.time()
    today = dt_date.today()
    
    # HOTFIX C2.13.9a: Inicializar instrumentation al inicio para evitar UnboundLocalError
    instrumentation: Dict[str, Any] = {}

    # Reutilizar lógica de extracción de pendientes
    # (copiamos el código de match_pending_headful pero añadimos evaluación de guardrails)
    try:
        from playwright.sync_api import sync_playwright
        print(f"[CAE][READONLY][TRACE] Playwright import OK, lanzando browser...")
    except Exception as e:
        print(f"[CAE][READONLY][TRACE] BRANCH: playwright_import_failed reason={type(e).__name__}: {str(e)}")
        raise RuntimeError("Playwright sync_api not available") from e

    pending_items: List[Dict[str, Any]] = []
    match_results: List[Dict[str, Any]] = []
    submission_plan: List[Dict[str, Any]] = []

    print(f"[CAE][READONLY][TRACE] Iniciando contexto Playwright (headless=False)...")
    with sync_playwright() as p:
        print(f"[CAE][READONLY][TRACE] Lanzando browser Chromium (headless=False)...")
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(
            viewport=viewport or {"width": 1600, "height": 1000},
        )
        page = context.new_page()
        print(f"[CAE][READONLY][TRACE] Browser lanzado, navegando a login...")

        # 1) Login (reutilizar lógica existente)
        print(f"[CAE][READONLY][TRACE] Navegando a: {LOGIN_URL_PREVIOUS_SUCCESS}")
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)
        print(f"[CAE][READONLY][TRACE] Página de login cargada, rellenando credenciales...")
        page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
        page.locator('input[name="Username"]').fill(username, timeout=20000)
        page.locator('input[name="Password"]').fill(password, timeout=20000)
        print(f"[CAE][READONLY][TRACE] Credenciales rellenadas, haciendo click en submit...")
        page.locator('button[type="submit"]').click(timeout=20000)

        print(f"[CAE][READONLY][TRACE] Esperando redirección a default_contenido.asp...")
        page.wait_for_url("**/default_contenido.asp", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass
        print(f"[CAE][READONLY][TRACE] Login completado, esperando {wait_after_login_s}s...")
        time.sleep(wait_after_login_s)
        print(f"[CAE][READONLY][TRACE] Continuando con navegación a listado de pendientes...")

        # Guardar storage_state tras login exitoso (para reutilizar sesión) - solo si NO es return_plan_only
        if not return_plan_only:
            storage_state_path = run_dir / "storage_state.json"
            try:
                context.storage_state(path=str(storage_state_path))
                print(f"[submission_plan] Storage state guardado en: {storage_state_path}")
            except Exception as e:
                print(f"[WARNING] No se pudo guardar storage_state: {e}")
                storage_state_path = None
        else:
            storage_state_path = None

        # Cerrar todos los overlays DHTMLX bloqueantes (pipeline completo)
        # IMPORTANTE: Este helper ya fue probado y funciona. Debe ejecutarse después del login.
        try:
            from backend.adapters.egestiona.priority_comms_headful import dismiss_all_dhx_blockers, PriorityCommsModalNotDismissed, DhxBlockerNotDismissed
            print(f"[submission_plan] Invocando dismiss_all_dhx_blockers (timeout=30s)...")
            dismiss_all_dhx_blockers(page, evidence_dir if not return_plan_only else None, timeout_seconds=30)
            print(f"[submission_plan] dismiss_all_dhx_blockers completado exitosamente")
            # Esperar un poco más para asegurar que el modal se cerró completamente
            time.sleep(1.0)
        except (PriorityCommsModalNotDismissed, DhxBlockerNotDismissed) as e:
            # Re-lanzar como RuntimeError para que el endpoint lo capture
            print(f"[submission_plan] ERROR: No se pudo cerrar modal DHTMLX: {e}")
            if not return_plan_only:
                page.screenshot(path=str(evidence_dir / "dhx_blocker_failed.png"), full_page=True)
            raise RuntimeError(f"DHX_BLOCKER_NOT_DISMISSED: {e}") from e
        except Exception as e:
            # Si falla, guardar evidence pero continuar (no romper el flujo)
            print(f"[WARNING] Error inesperado al cerrar overlays DHTMLX: {e}")
            import traceback
            traceback.print_exc()
            if not return_plan_only:
                try:
                    page.screenshot(path=str(evidence_dir / "dhx_blocker_error.png"), full_page=True)
                except Exception:
                    pass

        # Esperar frame nm_contenido
        t_deadline = time.time() + 25.0
        frame = None
        while time.time() < t_deadline:
            frame = page.frame(name="nm_contenido")
            if frame and frame.url:
                break
            time.sleep(0.25)
        if not frame:
            if not return_plan_only:
                page.screenshot(path=str(shot_01), full_page=True)
            raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")

        if not return_plan_only:
            page.screenshot(path=str(shot_01), full_page=True)

        # Cerrar overlays DHTMLX también justo antes del primer click importante (por si aparecen tarde)
        # Esto es una medida de seguridad adicional
        try:
            from backend.adapters.egestiona.priority_comms_headful import dismiss_all_dhx_blockers, PriorityCommsModalNotDismissed, DhxBlockerNotDismissed
            print(f"[submission_plan] Verificación adicional de overlays DHTMLX antes del click...")
            dismiss_all_dhx_blockers(page, evidence_dir if not return_plan_only else None, timeout_seconds=10)
            print(f"[submission_plan] Verificación adicional completada")
        except (PriorityCommsModalNotDismissed, DhxBlockerNotDismissed) as e:
            # Re-lanzar como RuntimeError para que el endpoint lo capture
            print(f"[submission_plan] ERROR: Overlay DHTMLX detectado antes del click: {e}")
            if not return_plan_only:
                page.screenshot(path=str(evidence_dir / "dhx_blocker_before_click.png"), full_page=True)
            raise RuntimeError(f"DHX_BLOCKER_NOT_DISMISSED: {e}") from e
        except Exception as e:
            print(f"[WARNING] Error inesperado al cerrar overlays DHTMLX antes del click: {e}")
            # No romper el flujo, solo loguear

        # 2) Click tile Enviar Doc. Pendiente
        tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
        tile = frame.locator(tile_sel)
        tile.first.wait_for(state="visible", timeout=20000)
        tile.first.click(timeout=20000)

        # 3) Esperar grid (reutilizar lógica existente)
        def _find_list_frame() -> Any:
            fr = page.frame(name="f3")
            if fr:
                return fr
            for fr2 in page.frames:
                u = (fr2.url or "").lower()
                if ("buscador.asp" in u) and ("apartado_id=3" in u):
                    return fr2
            return None

        def _frame_has_grid(fr) -> bool:
            try:
                return fr.locator("table.obj.row20px").count() > 0
            except Exception:
                return False

        list_frame = None
        t_deadline = time.time() + 15.0
        while time.time() < t_deadline:
            list_frame = _find_list_frame()
            if list_frame and _frame_has_grid(list_frame):
                break
            time.sleep(0.25)

        if not (list_frame and _frame_has_grid(list_frame)):
            try:
                btn_buscar = frame.get_by_text("Buscar", exact=True)
                if btn_buscar.count() > 0:
                    btn_buscar.first.click(timeout=10000)
            except Exception:
                pass
            t_deadline = time.time() + 20.0
            while time.time() < t_deadline:
                list_frame = _find_list_frame()
                if list_frame and _frame_has_grid(list_frame):
                    break
                time.sleep(0.25)

        if not (list_frame and _frame_has_grid(list_frame)):
            if not return_plan_only:
                page.screenshot(path=str(shot_02), full_page=True)
            raise RuntimeError("GRID_NOT_FOUND")

        list_frame.locator("table.hdr").first.wait_for(state="attached", timeout=15000)
        list_frame.locator("table.obj.row20px").first.wait_for(state="attached", timeout=15000)

        if not return_plan_only:
            try:
                list_frame.locator("body").screenshot(path=str(shot_02))
            except Exception:
                page.screenshot(path=str(shot_02), full_page=True)

        # 3.5) Esperar a que el grid esté estable (sin "Loading...") antes de validar
        from backend.adapters.egestiona.page_contract_validator import (
            validate_pending_page_contract,
            PageContractError,
            wait_for_grid_stable,
        )
        
        loading_info = wait_for_grid_stable(list_frame, timeout=25.0)
        
        # 3.5) Validar "page contract" antes de extraer
        try:
            validate_pending_page_contract(
                page=page,
                list_frame=list_frame,
                evidence_dir=evidence_dir if not return_plan_only else None,
            )
        except PageContractError as e:
            # La excepción ya tiene toda la información estructurada
            # Solo añadir timestamp y guardar JSON adicional si es necesario
            if not return_plan_only:
                error_dump_path = evidence_dir / f"{e.error_code}_error.json"
                _safe_write_json(error_dump_path, {
                    "error_code": e.error_code,
                    "message": e.message,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "details": e.details,
                    "evidence_paths": e.evidence_paths,
                    "loading_info": loading_info,  # Añadir info de loading
                })
            # Re-lanzar la excepción para que flows.py la capture
            raise

        # 3.6) SPRINT C2.13.0: Auto-disparar búsqueda si grid está vacío
        from backend.adapters.egestiona.grid_search_helper import ensure_results_loaded
        
        print(f"[CAE][READONLY][TRACE] Llamando ensure_results_loaded para verificar grid...")
        search_result = ensure_results_loaded(
            list_frame=list_frame,
            evidence_dir=evidence_dir if not return_plan_only else None,
            timeout_seconds=60.0,
            max_retries=1,
            page=page,  # HOTFIX C2.13.9: Pasar page para validar pestaña correcta
        )
        
        # Guardar resultado de búsqueda en instrumentación
        if not return_plan_only:
            search_result_path = evidence_dir / "search_result.json"
            _safe_write_json(search_result_path, search_result)
        
        print(f"[submission_plan] Search result: clicked={search_result.get('search_clicked')}, "
              f"rows_before={search_result.get('rows_before')}, rows_after={search_result.get('rows_after')}")

        # SPRINT C2.14.1: 4) Extraer grid con soporte de paginación completa
        print(f"[CAE][READONLY][PAGINATION] Iniciando extracción de grid con paginación (max_pages={max_pages}, max_items={max_items})...")
        
        # Detectar paginación
        pagination_info = detect_pagination_controls(list_frame)
        has_pagination = pagination_info.get("has_pagination", False)
        
        # Inicializar estructuras para acumulación
        seen_keys = set()
        all_raw_rows = []
        pages_processed = 0
        next_clicks = 0
        pagination_truncated = False
        
        # Ir a primera página si existe control "first"
        if has_pagination and pagination_info.get("first_button"):
            first_btn = pagination_info["first_button"]
            if first_btn.get("isVisible") and first_btn.get("isEnabled"):
                print(f"[CAE][READONLY][PAGINATION] Navegando a primera página...")
                if click_pagination_button(list_frame, first_btn, evidence_dir if not return_plan_only else None):
                    time.sleep(1.0)  # Esperar a que cargue la primera página
        
        # Loop de paginación
        while pages_processed < max_pages:
            pages_processed += 1
            print(f"[CAE][READONLY][PAGINATION] Procesando página {pages_processed}...")
            
            # Extraer grid de la página actual
            extracted = extract_dhtmlx_grid(list_frame)
            
            # Guardar debug info si hay warnings (solo si NO es return_plan_only y primeras 3 páginas o última)
            if extracted.get("warnings") and not return_plan_only and (pages_processed <= 3 or not has_pagination):
                grid_debug_path = evidence_dir / f"grid_debug_page_{pages_processed}.json"
                _safe_write_json(grid_debug_path, {
                    "page": pages_processed,
                    "warnings": extracted.get("warnings", []),
                    "headers": extracted.get("headers", []),
                    "mapping_debug": extracted.get("mapping_debug", {}),
                    "raw_rows_preview": extracted.get("raw_rows_preview", []),
                    "debug": extracted.get("debug", {})
                })
                if pages_processed == 1:
                    print(f"WARNING: Grid extraction issues detected. Debug saved to {grid_debug_path}")
                    for warning in extracted.get("warnings", []):
                        print(f"  - {warning}")
            
            # Capturar screenshot de primeras 3 páginas + última (si hay paginación)
            if not return_plan_only and evidence_dir and (pages_processed <= 3 or (has_pagination and pages_processed == max_pages)):
                try:
                    screenshot_path = evidence_dir / f"grid_page_{pages_processed}.png"
                    list_frame.locator("body").screenshot(path=str(screenshot_path))
                except Exception as e:
                    print(f"[CAE][READONLY][PAGINATION] Error al guardar screenshot página {pages_processed}: {e}")
            
            # Procesar filas de esta página
            page_rows = extracted.get("rows") or []
            items_before_dedupe = len(all_raw_rows)
            
            for row in page_rows:
                # Canonicalizar para obtener pending_item_key
                canonical = canonicalize_row(row)
                pending_item_key = canonical.get("pending_item_key")
                
                # Deduplicación por pending_item_key
                if pending_item_key and pending_item_key not in seen_keys:
                    seen_keys.add(pending_item_key)
                    all_raw_rows.append(row)
                    
                    # Verificar límite de items
                    if len(all_raw_rows) >= max_items:
                        pagination_truncated = True
                        print(f"[CAE][READONLY][PAGINATION] ⚠️ Límite de items alcanzado ({max_items}), deteniendo paginación")
                        break
            
            items_after_dedupe = len(all_raw_rows)
            print(f"[CAE][READONLY][PAGINATION] Página {pages_processed}: {len(page_rows)} filas extraídas, {items_after_dedupe - items_before_dedupe} nuevas (total acumulado: {items_after_dedupe})")
            
            # Si se alcanzó el límite de items, salir
            if pagination_truncated:
                break
            
            # Si no hay paginación o no hay botón "next" habilitado, salir
            if not has_pagination:
                break
            
            next_button = pagination_info.get("next_button")
            if not next_button or not next_button.get("isVisible") or not next_button.get("isEnabled"):
                print(f"[CAE][READONLY][PAGINATION] No hay botón 'next' disponible, finalizando paginación")
                break
            
            # Guardar firma de la primera fila antes del click
            initial_signature = None
            initial_row_count = None
            if all_raw_rows:
                try:
                    first_row = all_raw_rows[0]
                    initial_signature = " | ".join([
                        str(first_row.get("tipo_doc", "")),
                        str(first_row.get("elemento", "")),
                        str(first_row.get("empresa", ""))
                    ])[:100]
                except Exception:
                    pass
            
            try:
                initial_row_count = list_frame.locator("table.obj.row20px tbody tr").count()
            except Exception:
                pass
            
            # Hacer click en "next"
            print(f"[CAE][READONLY][PAGINATION] Haciendo click en botón 'next'...")
            if click_pagination_button(list_frame, next_button, evidence_dir if not return_plan_only else None):
                next_clicks += 1
                # Esperar a que cambie la página
                page_changed = wait_for_page_change(
                    list_frame,
                    initial_signature=initial_signature,
                    initial_row_count=initial_row_count,
                    timeout_seconds=10.0,
                )
                if not page_changed:
                    print(f"[CAE][READONLY][PAGINATION] ⚠️ No se detectó cambio de página después del click, finalizando paginación")
                    break
                time.sleep(0.5)  # Pequeña pausa adicional
            else:
                print(f"[CAE][READONLY][PAGINATION] ⚠️ No se pudo hacer click en botón 'next', finalizando paginación")
                break
        
        # Guardar información de paginación en diagnostics
        pagination_diagnostics = {
            "has_pagination": has_pagination,
            "pages_detected": pagination_info.get("page_info", {}).get("total") if pagination_info.get("page_info") else None,
            "pages_processed": pages_processed,
            "items_before_dedupe": len(all_raw_rows),
            "items_after_dedupe": len(all_raw_rows),
            "next_clicks": next_clicks,
            "truncated": pagination_truncated,
            "max_pages": max_pages,
            "max_items": max_items,
        }
        
        if pagination_info.get("page_info"):
            pagination_diagnostics["page_info"] = pagination_info["page_info"]
        
        instrumentation["pagination"] = pagination_diagnostics
        print(f"[CAE][READONLY][PAGINATION] Paginación completada: {pages_processed} páginas procesadas, {len(all_raw_rows)} items únicos")
        
        # Usar todas las filas acumuladas
        raw_rows = all_raw_rows
        
        # HOTFIX C2.13.9a: Inicializar variables para grid_parse_mismatch
        counter_text_found = None
        counter_count_found = None
        
        # HOTFIX C2.13.9: TAREA C - Detectar grid real y contar filas reales
        rows_data_count = len(raw_rows)
        first_row_text = None
        if rows_data_count > 0:
            first_row = raw_rows[0]
            # Extraer texto de las primeras columnas para sanity check
            first_row_text = " | ".join([
                str(first_row.get("tipo_doc", "")),
                str(first_row.get("elemento", "")),
                str(first_row.get("empresa", ""))
            ])[:100]
        
        instrumentation["rows_data_count"] = rows_data_count
        instrumentation["first_row_text"] = first_row_text
        
        print(f"[CAE][READONLY][TRACE] Grid extraído: rows_data_count={rows_data_count} first_row_text={first_row_text}")
        
        # HOTFIX C2.13.9: Si rows_data_count==0 después de búsqueda, capturar evidencia
        # HOTFIX C2.13.9a: TAREA C - Validar grid_parse_mismatch si contador muestra >0 pero rows_data_count==0
        if rows_data_count == 0:
            if not return_plan_only and evidence_dir:
                try:
                    screenshot_path = evidence_dir / "02_zero_rows.png"
                    list_frame.locator("body").screenshot(path=str(screenshot_path))
                    print(f"[CAE][READONLY][TRACE] Screenshot de grid vacío guardado: {screenshot_path}")
                except Exception as e:
                    print(f"[CAE][READONLY][TRACE] Error al guardar screenshot de grid vacío: {e}")
            
            # HOTFIX C2.13.9a: Validar si hay texto "X Registros" con X>0 en la UI
            try:
                body_text = list_frame.evaluate("() => document.body.innerText")
                body_text_lower = body_text.lower() if body_text else ""
                
                # Buscar patrón de contador
                import re
                counter_patterns = [
                    r'(\d+)\s+registros?',
                    r'(\d+)\s+registro\(s\)',
                    r'registros?:\s*(\d+)',
                    r'total:\s*(\d+)',
                ]
                
                for pattern in counter_patterns:
                    match = re.search(pattern, body_text_lower, re.IGNORECASE)
                    if match:
                        counter_text_found = match.group(0)
                        counter_count_found = int(match.group(1))
                        if counter_count_found > 0:
                            print(f"[CAE][READONLY][TRACE] ⚠️ GRID_PARSE_MISMATCH: UI muestra '{counter_text_found}' ({counter_count_found} registros) pero rows_data_count=0")
                            instrumentation["grid_parse_mismatch"] = True
                            instrumentation["counter_text_found"] = counter_text_found
                            instrumentation["counter_count_found"] = counter_count_found
                            instrumentation["rows_data_count"] = rows_data_count
                            break
            except Exception as e:
                print(f"[CAE][READONLY][TRACE] Error al validar grid_parse_mismatch: {e}")
            
            # Si se intentó búsqueda y sigue vacío, incluir diagnostics pero NO error (ya se maneja más abajo)
            if search_result.get("search_clicked"):
                print(f"[CAE][READONLY][TRACE] ⚠️ Grid sigue vacío después de búsqueda: rows_data_count=0")
        
        # HOTFIX C2.13.9a: Asegurar que instrumentation existe antes de usarlo
        if not isinstance(instrumentation, dict):
            instrumentation = {}
        
        # Instrumentación: guardar contadores intermedios + loading/empty-state info
        # SPRINT C2.13.0: Incluir información de búsqueda automática
        # HOTFIX C2.13.9a: Actualizar instrumentation existente en lugar de reemplazarlo
        instrumentation.update({
            "rows_detected": len(raw_rows),
            "headers_detected": len(extracted.get("headers", [])),
            "current_url": page.url,
            "frame_url": list_frame.url if hasattr(list_frame, 'url') else None,
            "loading_overlay_detected": loading_info.get("loading_overlay_detected", False),
            "loading_overlay_text": loading_info.get("loading_overlay_text"),
            "loading_duration_ms": loading_info.get("loading_duration_ms", 0),
        })
        
        # SPRINT C2.13.0: Añadir información de búsqueda automática
        if 'search_result' in locals():
            instrumentation["search_clicked"] = search_result.get("search_clicked", False)
            instrumentation["search_rows_before"] = search_result.get("rows_before", 0)
            instrumentation["search_rows_after"] = search_result.get("rows_after", 0)
            instrumentation["search_counter_before"] = search_result.get("counter_text_before")
            instrumentation["search_counter_after"] = search_result.get("counter_text_after")
        
        # SPRINT C2.13.1: Inicializar contadores de matches para instrumentación
        instrumentation["matches_found"] = 0
        instrumentation["local_docs_considered"] = 0
        
        # Intentar detectar tenant/client label desde la UI
        try:
            tenant_info = page.evaluate("""() => {
                const userMenu = document.querySelector('[class*="user"], [id*="user"], [class*="usuario"]');
                const clientLabel = document.querySelector('[class*="client"], [id*="client"], [class*="cliente"]');
                return {
                    userMenuText: userMenu ? userMenu.innerText.substring(0, 50) : null,
                    clientLabelText: clientLabel ? clientLabel.innerText.substring(0, 50) : null
                };
            }""")
            instrumentation["detected_tenant"] = tenant_info.get("clientLabelText") or tenant_info.get("userMenuText")
        except Exception:
            pass
        
        # Canonicalizar filas
        canonical_rows = []
        for row in raw_rows:
            canonical = canonicalize_row(row)
            # Solo incluir filas que tengan al menos tipo_doc o elemento
            if canonical.get("tipo_doc") or canonical.get("elemento"):
                canonical_rows.append(canonical)
        
        instrumentation["requirements_parsed"] = len(canonical_rows)
        
        # Si no hay filas después de canonicalizar, pero el extractor encontró filas,
        # puede ser que estemos en una página incorrecta
        if len(canonical_rows) == 0 and len(raw_rows) > 0:
            print(f"WARNING: Se encontraron {len(raw_rows)} filas pero ninguna tiene tipo_doc o elemento válidos")
            # Guardar evidencia adicional (solo si NO es return_plan_only)
            if not return_plan_only:
                grid_debug_path = evidence_dir / "grid_debug.json"
                _safe_write_json(grid_debug_path, {
                    "error": "No rows with tipo_doc or elemento",
                    "total_raw_rows": len(raw_rows),
                    "sample_raw_row": raw_rows[0] if raw_rows else None,
                    "headers": extracted.get("headers", []),
                    "raw_rows_preview": extracted.get("raw_rows_preview", []),
                    "instrumentation": instrumentation,
                })
        
        # Si no hay filas Y no hay tabla renderizada, verificar empty-state robusto
        # SPRINT C2.13.0: Si se hizo búsqueda y sigue vacío, incluir diagnostics
        if len(canonical_rows) == 0 and len(raw_rows) == 0:
            # Verificar si realmente es empty-state o si es un error de navegación
            has_empty_state = False
            empty_state_text_sample = None
            
            try:
                body_text = list_frame.evaluate("() => document.body.innerText")
                body_text_lower = body_text.lower() if body_text else ""
                
                # Patrones robustos de empty-state (incluyendo "0 Registros")
                import re
                empty_state_patterns = [
                    r"0\s+registros?",  # "0 Registros", "0 registros"
                    r"0\s+registro\(s\)",  # "0 Registro(s)"
                    r"no hay",
                    r"sin resultados",
                    r"sin datos",
                    r"no se encontraron",
                    r"lista vacía",
                    r"ningún resultado",
                    r"sin registros",
                ]
                
                for pattern in empty_state_patterns:
                    matches = re.search(pattern, body_text_lower, re.IGNORECASE)
                    if matches:
                        has_empty_state = True
                        # Extraer muestra del texto alrededor del match
                        start = max(0, matches.start() - 20)
                        end = min(len(body_text), matches.end() + 60)
                        empty_state_text_sample = body_text[start:end].strip()[:100]
                        break
                
                # También buscar en elementos específicos del grid/paginador
                if not has_empty_state:
                    empty_selectors = [
                        '.empty-state',
                        '.no-results',
                        '.sin-resultados',
                        '[class*="empty"]',
                        '[class*="no-data"]',
                    ]
                    for selector in empty_selectors:
                        try:
                            empty_elem = list_frame.locator(selector)
                            if empty_elem.count() > 0 and empty_elem.first().is_visible():
                                has_empty_state = True
                                empty_state_text_sample = empty_elem.first().text_content()[:100] if empty_elem.first().text_content() else None
                                break
                        except Exception:
                            continue
            except Exception:
                pass
            
            # Añadir empty_state a instrumentación
            instrumentation["empty_state_detected"] = has_empty_state
            instrumentation["empty_state_text_sample"] = empty_state_text_sample
            
            # Si headers existen y empty_state_detected es true y rows=0 => NO error
            # SPRINT C2.13.0: Si se hizo búsqueda y sigue vacío, incluir diagnostics pero NO error
            if has_empty_state and len(extracted.get("headers", [])) > 0:
                # Es un empty-state real, no un error
                print(f"[submission_plan] Empty-state real detectado: {empty_state_text_sample}")
                
                # SPRINT C2.13.0: Si se hizo búsqueda, añadir diagnostics
                # HOTFIX C2.13.9: Si rows_data_count==0 después de búsqueda, incluir error_code
                if search_result.get("search_clicked"):
                    instrumentation["search_attempted"] = True
                    instrumentation["search_result"] = search_result
                    instrumentation["diagnostics"] = {
                        "reason": "no_rows_after_search",
                        "frame_url": search_result.get("frame_url"),
                        "counter_text": search_result.get("counter_text_after") or search_result.get("counter_text_before"),
                        "rows_before": search_result.get("rows_before", 0),
                        "rows_after": search_result.get("rows_after", 0),
                        "rows_data_count": rows_data_count,  # HOTFIX C2.13.9: Incluir conteo real de filas de datos
                        "fallback_used": search_result.get("diagnostics", {}).get("fallback_used"),  # HOTFIX C2.13.9
                    }
                    
                    # HOTFIX C2.13.9: Si rows_data_count==0 después de búsqueda, NO es status ok silencioso
                    # Se maneja más abajo en el código que construye el resultado
                
                # Continuar normalmente (no lanzar error)
            elif not has_empty_state:
                # No es empty-state real, es un error
                from backend.adapters.egestiona.page_contract_validator import PageContractError
                if not return_plan_only:
                    error_dump_path = evidence_dir / "pending_list_not_loaded_error.json"
                    _safe_write_json(error_dump_path, {
                        "error_code": "pending_list_not_loaded",
                        "message": "No se encontraron filas y no hay empty-state válido. Posible error de navegación.",
                        "instrumentation": instrumentation,
                        "extracted": {
                            "headers": extracted.get("headers", []),
                            "rows_count": len(raw_rows),
                            "warnings": extracted.get("warnings", []),
                        }
                    })
                    evidence_paths = {
                        "error_json": str(error_dump_path.relative_to(evidence_dir.parent.parent.parent)) if (error_dump_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
                    }
                else:
                    evidence_paths = {}
                raise PageContractError(
                    error_code="pending_list_not_loaded",
                    message="No se encontraron filas y no hay empty-state válido. Posible error de navegación.",
                    details={
                        "instrumentation": instrumentation,
                        "extracted": {
                            "headers": extracted.get("headers", []),
                            "rows_count": len(raw_rows),
                            "warnings": extracted.get("warnings", []),
                        }
                    },
                    evidence_paths=evidence_paths
                )
        
        raw_rows = canonical_rows
        
        # Guardar instrumentación (solo si NO es return_plan_only)
        # SPRINT C2.13.1: Asegurar que instrumentation siempre tiene contadores de matches
        if 'instrumentation' not in locals():
            instrumentation = {}
        instrumentation.setdefault("matches_found", 0)
        instrumentation.setdefault("local_docs_considered", 0)
        
        if not return_plan_only:
            instrumentation_path = evidence_dir / "instrumentation.json"
            _safe_write_json(instrumentation_path, instrumentation)

        # 5) Cargar información de persona si person_key está presente
        person_data = None
        if person_key and only_target:
            try:
                people = store.load_people()
                person_data = next((p for p in people.people if p.worker_id == person_key), None)
                if not person_data:
                    # Log warning pero continuar (puede que el person_key sea un DNI o nombre)
                    print(f"WARNING: person_key '{person_key}' no encontrado en people.json. Usando matching simple.")
            except Exception as e:
                print(f"WARNING: Error al cargar people.json: {e}. Usando matching simple.")

        # 6) Filtrar si only_target (las filas ya están canonicalizadas)
        def _row_matches_target(r: Dict[str, Any]) -> bool:
            """Filtra por company_key y person_key si only_target=True. Usa matching robusto normalizado."""
            if not only_target:
                return True
            
            empresa_raw = r.get("empresa") or ""
            elemento_raw = r.get("elemento") or ""
            
            # Matching robusto de empresa
            # company_key puede ser tax_id (ej: "F63161988") o nombre de empresa
            empresa_match = True
            if company_key and empresa_raw:
                # Primero intentar buscar por código fiscal (tax_id) en paréntesis
                company_code = extract_company_code(empresa_raw)
                if company_code:
                    # Si hay código en la empresa, comparar directamente
                    company_key_upper = company_key.strip().upper().replace(' ', '')
                    if company_key_upper == company_code:
                        empresa_match = True
                    else:
                        # Si no coincide por código, intentar por nombre
                        empresa_norm = normalize_company_name(empresa_raw)
                        company_key_norm = normalize_text(company_key)
                        empresa_match = text_contains(empresa_norm, company_key_norm)
                else:
                    # No hay código en la empresa, buscar por nombre normalizado
                    empresa_norm = normalize_company_name(empresa_raw)
                    company_key_norm = normalize_text(company_key)
                    empresa_match = text_contains(empresa_norm, company_key_norm)
            
            # Matching robusto de persona si tenemos person_data
            if person_data and elemento_raw:
                elemento_match = match_person_in_element(person_data, elemento_raw)
            else:
                # Fallback a matching simple normalizado si no hay person_data
                elemento_norm = normalize_text(elemento_raw)
                person_key_norm = normalize_text(person_key) if person_key else ""
                elemento_match = text_contains(elemento_norm, person_key_norm) if person_key else True
            
            return empresa_match and elemento_match

        target_rows = [r for r in raw_rows if _row_matches_target(r)][:limit]
        
        # Log si no se encontraron filas pero había person_key
        if only_target and person_key and len(target_rows) == 0 and len(raw_rows) > 0:
            print(f"WARNING: No se encontraron filas para person_key='{person_key}' con only_target=True.")
            print(f"  Total filas en grid: {len(raw_rows)}")
            print(f"  Ejemplo de 'Elemento' en grid: {raw_rows[0].get('Elemento', 'N/A') if raw_rows else 'N/A'}")
            if person_data:
                print(f"  Persona buscada: {person_data.full_name} (DNI: {person_data.tax_id})")

        # 7) Convertir a PendingItemV1, hacer matching y generar plan
        # Las filas ya están canonicalizadas
        print(f"[CAE][READONLY][TRACE] Procesando {len(target_rows)} filas target para matching...")
        for row in target_rows:
            tipo_doc = row.get("tipo_doc") or ""
            elemento = row.get("elemento") or ""
            empresa = row.get("empresa") or ""
            
            fecha_inicio = _parse_date_from_cell(row.get("inicio") or "")
            fecha_fin = _parse_date_from_cell(row.get("fin") or "")

            pending = PendingItemV1(
                tipo_doc=tipo_doc,
                elemento=elemento,
                empresa=empresa,
                trabajador=elemento,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                raw_data=row.get("_raw_row", row)  # Mantener raw para debug
            )

            pending_dict = pending.to_dict()
            pending_items.append(pending_dict)

            # Hacer matching (con platform y coord para reglas)
            # SPRINT C2.18A: Generar debug report estructurado
            # Siempre pasar evidence_dir si está disponible (incluso en return_plan_only)
            match_result = matcher.match_pending_item(
                pending,
                company_key=company_key,
                person_key=person_key,
                platform_key=platform,
                coord_label=coordination,
                evidence_dir=evidence_dir,  # SPRINT C2.18A: Siempre pasar evidence_dir si está disponible
                generate_debug_report=True,  # SPRINT C2.18A: Siempre generar reporte estructurado
            )

            match_results.append({
                "pending_item": pending_dict,
                "match_result": match_result
            })

            # SPRINT C2.13.1: Instrumentación de matches
            best_doc = match_result.get("best_doc")
            match_count = 1 if best_doc else 0
            
            # Actualizar contadores de instrumentación
            if best_doc:
                instrumentation["matches_found"] = instrumentation.get("matches_found", 0) + 1
            
            # SPRINT C2.18A: Usar local_docs_considered del debug_report si está disponible
            matching_debug_report = match_result.get("matching_debug_report")
            if matching_debug_report and isinstance(matching_debug_report, dict):
                local_docs_considered_from_report = matching_debug_report.get("outcome", {}).get("local_docs_considered", 0)
                instrumentation["local_docs_considered"] = instrumentation.get("local_docs_considered", 0) + local_docs_considered_from_report
            elif match_result.get("candidates") and isinstance(match_result.get("candidates"), list):
                # Fallback legacy
                instrumentation["local_docs_considered"] = instrumentation.get("local_docs_considered", 0) + len(match_result.get("candidates"))
            
            # Obtener tipo de documento para guardrails
            doc_type = None
            if best_doc:
                type_id = best_doc.get("type_id")
                if type_id:
                    doc_type = repo_store.get_type(type_id)
            
            # Evaluar guardrails
            decision = _evaluate_submission_guardrails(
                match_result,
                today,
                only_target,
                match_count,
                doc_type=doc_type
            )

            # Dedupe: verificar si ya fue enviado
            from backend.repository.submission_history_store_v1 import SubmissionHistoryStoreV1
            from backend.repository.submission_history_utils import compute_pending_fingerprint
            
            history_store = SubmissionHistoryStoreV1(base_dir=base)
            pending_dict_for_fp = pending.to_dict()
            fingerprint = compute_pending_fingerprint(
                platform_key=platform,
                coord_label=coordination,
                pending_item_dict=pending_dict_for_fp
            )
            
            # Verificar si ya fue enviado
            existing_submitted = history_store.find_by_fingerprint(
                fingerprint=fingerprint,
                action="submitted"
            )
            
            if existing_submitted:
                # Ya fue enviado -> SKIP
                decision = {
                    "action": "SKIP_ALREADY_SUBMITTED",
                    "confidence": 1.0,
                    "reasons": [
                        f"Already submitted in run {existing_submitted.run_id}",
                        f"Previous record: {existing_submitted.record_id}",
                        f"Submitted at: {existing_submitted.submitted_at or existing_submitted.created_at}"
                    ],
                    "blocking_issues": ["Duplicate submission detected"]
                }
            
            # Verificar si ya está planificado (self-test o dry-run previo)
            existing_planned = history_store.find_by_fingerprint(
                fingerprint=fingerprint,
                action="planned"
            )
            
            if existing_planned and not existing_submitted:
                # Ya está planificado pero no enviado -> SKIP o REVIEW
                decision = {
                    "action": "SKIP_ALREADY_PLANNED",
                    "confidence": 1.0,
                    "reasons": [
                        f"Already planned in run {existing_planned.run_id}",
                        f"Previous record: {existing_planned.record_id}",
                        f"Planned at: {existing_planned.created_at}"
                    ],
                    "blocking_issues": ["Duplicate plan detected"]
                }

            # Construir plan item
            # SPRINT C2.14.1: Incluir pending_item_key en pending_ref para re-localización robusta
            pending_item_key = row.get("pending_item_key")
            plan_item: Dict[str, Any] = {
                "pending_ref": {
                    "tipo_doc": tipo_doc,
                    "elemento": elemento,
                    "empresa": empresa,
                    "row_index": len(pending_items) - 1,  # Mantener para compatibilidad
                    "pending_item_key": pending_item_key,  # SPRINT C2.14.1: ID estable
                },
                "pending_item_key": pending_item_key,  # SPRINT C2.14.1: También en nivel superior para fácil acceso
                "expected_doc_type_text": f"{tipo_doc} {elemento}",
                "matched_doc": None,
                "proposed_fields": {
                    "fecha_inicio_vigencia": None,
                    "fecha_fin_vigencia": None
                },
                "decision": decision,
                "pending_fingerprint": fingerprint,  # Añadir fingerprint para dedupe
                "rule_form": None,  # Se llenará si match vino de regla
                "debug_report": match_result.get("matching_debug_report_c234"),  # SPRINT C2.34: Reporte de debug simplificado
            }
            
            # Si el match vino de regla, añadir rule.form al plan item
            matched_rule = match_result.get("matched_rule")
            if matched_rule:
                plan_item["rule_form"] = matched_rule.get("form")

            if best_doc:
                # Usar validity_from/validity_to del matcher (ya incluye override si existe)
                valid_from_str = best_doc.get("validity_from")
                valid_to_str = best_doc.get("validity_to")
                
                # Parsear fechas si son strings
                valid_from = None
                valid_to = None
                if isinstance(valid_from_str, str):
                    try:
                        valid_from = datetime.strptime(valid_from_str, "%Y-%m-%d").date()
                    except ValueError:
                        valid_from = None
                elif isinstance(valid_from_str, dt_date):
                    valid_from = valid_from_str
                
                if isinstance(valid_to_str, str):
                    try:
                        valid_to = datetime.strptime(valid_to_str, "%Y-%m-%d").date()
                    except ValueError:
                        valid_to = None
                elif isinstance(valid_to_str, dt_date):
                    valid_to = valid_to_str
                
                plan_item["matched_doc"] = {
                    "doc_id": best_doc.get("doc_id"),
                    "type_id": best_doc.get("type_id"),
                    "file_name": best_doc.get("file_name"),
                    "status": best_doc.get("status"),
                    "validity": {
                        "valid_from": valid_from.isoformat() if valid_from else None,
                        "valid_to": valid_to.isoformat() if valid_to else None,
                        "confidence": best_doc.get("score", 0.0),
                        "has_override": best_doc.get("has_override", False)
                    }
                }
                
                # Fechas propuestas desde validity (que ya incluye override si existe)
                plan_item["proposed_fields"]["fecha_inicio_vigencia"] = _format_date_for_portal(valid_from)
                plan_item["proposed_fields"]["fecha_fin_vigencia"] = _format_date_for_portal(valid_to)

            submission_plan.append(plan_item)

        # Guardar storage_state antes de cerrar (si no se guardó antes)
        if not return_plan_only:
            if storage_state_path is None and run_dir:
                storage_state_path = run_dir / "storage_state.json"
                try:
                    context.storage_state(path=str(storage_state_path))
                    print(f"[submission_plan] Storage state guardado al finalizar en: {storage_state_path}")
                except Exception as e:
                    print(f"[WARNING] No se pudo guardar storage_state al finalizar: {e}")
                    storage_state_path = None

        context.close()
        browser.close()

    # 7) Guardar evidence (solo si NO es return_plan_only)
    if not return_plan_only:
        _safe_write_json(pending_items_path, {"items": pending_items})
        _safe_write_json(match_results_path, {"results": match_results})
        _safe_write_json(submission_plan_path, {"plan": submission_plan})

    finished = time.time()
    duration_ms = int((finished - started) * 1000)
    
    # HOTFIX C2.12.6: Si return_plan_only=True, devolver plan directamente sin tocar filesystem
    if return_plan_only:
        # Computar summary sin tocar filesystem
        # HOTFIX: NO importar date localmente (causa shadowing), usar dt_date del import global
        today = dt_date.today()
        
        matched_count = sum(1 for item in submission_plan if item.get("matched_doc") and item.get("matched_doc", {}).get("doc_id"))
        summary = {
            "pending_count": len(pending_items),
            "matched_count": matched_count,
            "unmatched_count": len(pending_items) - matched_count,
            "duration_ms": duration_ms,
        }
        
        # HOTFIX C2.13.7: Logging final antes de devolver
        print(f"[CAE][READONLY][TRACE] ========================================")
        print(f"[CAE][READONLY][TRACE] RESULTADO FINAL: pending_items={len(pending_items)} submission_plan={len(submission_plan)} matched_count={matched_count}")
        print(f"[CAE][READONLY][TRACE] ========================================")
        
        # SPRINT C2.13.0: Incluir diagnostics si se hizo búsqueda y sigue vacío
        # SPRINT C2.13.1: Incluir diagnostics si no hay matches (0 matches con repositorio)
        result = {
            "plan": submission_plan,
            "summary": summary,
            "pending_items": pending_items,
            "match_results": match_results,
            "duration_ms": duration_ms,
        }
        
        # HOTFIX C2.13.9a: TAREA C - Si hay grid_parse_mismatch, incluir error_code
        if instrumentation.get("grid_parse_mismatch") and counter_count_found and counter_count_found > 0:
            result["diagnostics"] = {
                "reason": "grid_parse_mismatch",
                "error_code": "grid_parse_mismatch",
                "frame_url": search_result.get("frame_url") if 'search_result' in locals() else None,
                "counter_text": counter_text_found,
                "counter_count": counter_count_found,
                "rows_data_count": rows_data_count,
                "note": f"UI muestra '{counter_text_found}' ({counter_count_found} registros) pero el parser extrajo 0 filas. Posible problema con selectores del grid.",
            }
            # Guardar screenshot adicional si evidence_dir disponible
            if not return_plan_only and evidence_dir:
                try:
                    screenshot_path = evidence_dir / "03_grid_parse_mismatch.png"
                    list_frame.locator("body").screenshot(path=str(screenshot_path))
                    result["diagnostics"]["screenshot_path"] = str(screenshot_path)
                except Exception:
                    pass
        # HOTFIX C2.13.9: Añadir diagnostics si search_result está disponible y se hizo búsqueda
        elif 'search_result' in locals() and search_result.get("search_clicked") and len(submission_plan) == 0:
            result["diagnostics"] = {
                "reason": "no_rows_after_search",
                "frame_url": search_result.get("frame_url"),
                "counter_text": search_result.get("counter_text_after") or search_result.get("counter_text_before"),
                "rows_before": search_result.get("rows_before", 0),
                "rows_after": search_result.get("rows_after", 0),
                "rows_data_count": rows_data_count,  # HOTFIX C2.13.9: Incluir conteo real de filas de datos
                "fallback_used": search_result.get("diagnostics", {}).get("fallback_used"),  # HOTFIX C2.13.9
                "buscar_selector_used": search_result.get("diagnostics", {}).get("buscar_selector_used"),  # HOTFIX C2.13.9
                "clicked_buscar_candidate_index": search_result.get("diagnostics", {}).get("clicked_buscar_candidate_index"),  # HOTFIX C2.13.9a
            }
        # SPRINT C2.13.1: Si hay pendientes pero 0 matches, añadir diagnostics
        elif len(pending_items) > 0 and matched_count == 0:
            result["diagnostics"] = {
                "reason": "no_matches_after_compute",
                "note": "No matching documents found between eGestión and local repository",
                "pending_count": len(pending_items),
                "matches_found": 0,
                "local_docs_considered": instrumentation.get("local_docs_considered", 0) if 'instrumentation' in locals() else 0,
            }
        
        # SPRINT C2.14.1: Incluir diagnostics de paginación si está disponible
        if instrumentation.get("pagination"):
            if not result.get("diagnostics"):
                result["diagnostics"] = {}
            result["diagnostics"]["pagination"] = instrumentation["pagination"]
        
        # SPRINT C2.13.1: Añadir información de matches a instrumentation si está disponible
        if 'instrumentation' in locals():
            result["instrumentation"] = {
                "matches_found": instrumentation.get("matches_found", 0),
                "local_docs_considered": instrumentation.get("local_docs_considered", 0),
            }
        
        print(f"[CAE][READONLY][TRACE] Devolviendo result con plan.length={len(result.get('plan', []))}")
        
        # SPRINT C2.18A: Si return_plan_only=True, incluir temp_evidence_dir en el resultado
        # para que pueda ser copiado al plan_dir final
        if return_plan_only and evidence_dir and evidence_dir.exists():
            result["_temp_evidence_dir"] = str(evidence_dir)  # Para copiar matching_debug después
        
        return result
    
    # Generar checksum y confirm_token para el plan
    
    # Checksum: hash estable de items relevantes (solo campos que afectan la ejecución)
    plan_items_for_checksum = []
    for item in submission_plan:
        plan_items_for_checksum.append({
            "pending_ref": item.get("pending_ref", {}),
            "matched_doc": {
                "doc_id": item.get("matched_doc", {}).get("doc_id"),
                "type_id": item.get("matched_doc", {}).get("type_id"),
            } if item.get("matched_doc") else None,
            "decision": item.get("decision", {}),
            "proposed_fields": item.get("proposed_fields", {}),
        })
    
    checksum_data = jsonlib.dumps(plan_items_for_checksum, sort_keys=True, ensure_ascii=False)
    plan_checksum = hashlib.sha256(checksum_data.encode('utf-8')).hexdigest()
    
    # Confirm token: HMAC con secret interno + timestamp (TTL 30 min)
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(minutes=30)
    
    # Secret interno (no usar secretos de usuario)
    # En producción, esto debería venir de una variable de entorno o config
    import os
    secret_key = os.getenv("COMETLOCAL_PLAN_SECRET", "default-secret-key-change-in-production")
    
    # Si return_plan_only=True, run_id es None, usar placeholder para token
    token_run_id = run_id if not return_plan_only else "readonly_no_run"
    token_payload = f"{token_run_id}:{plan_checksum}:{created_at.isoformat()}"
    confirm_token = hmac.new(
        secret_key.encode('utf-8'),
        token_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Guardar plan_meta.json con checksum y token info (solo si NO es return_plan_only)
    if not return_plan_only:
        plan_meta_path = run_dir / "plan_meta.json"
        _safe_write_json(
            plan_meta_path,
            {
                "plan_id": run_id,
                "plan_checksum": plan_checksum,
                "confirm_token": confirm_token,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "platform": platform,
                "coordination": coordination,
                "company_key": company_key,
                "person_key": person_key,
                "scope": "worker" if person_key else ("company" if only_target else "both"),
            },
        )
        
        # Guardar plan.json (alias de submission_plan.json para el nuevo endpoint)
        plan_json_path = run_dir / "plan.json"
        _safe_write_json(plan_json_path, {"plan": submission_plan})
        
        _safe_write_json(
            meta_path,
            {
                "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
                "company_key": company_key,
                "person_key": person_key,
                "only_target": only_target,
                "limit": limit,
                "today": today.isoformat(),
                "pending_items_count": len(pending_items),
                "match_results_count": len(match_results),
                "submission_plan_count": len(submission_plan),
                "auto_submit_ok_count": sum(1 for item in submission_plan if item["decision"]["action"] == "AUTO_SUBMIT_OK"),
                "review_required_count": sum(1 for item in submission_plan if item["decision"]["action"] == "REVIEW_REQUIRED"),
                "no_match_count": sum(1 for item in submission_plan if item["decision"]["action"] == "NO_MATCH"),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": duration_ms,
                "plan_checksum": plan_checksum,
                "confirm_token": confirm_token,
            },
        )

        # Guardar información de artifacts (storage_state)
        artifacts_info = {}
        if storage_state_path and storage_state_path.exists():
            from backend.shared.path_utils import as_str
            artifacts_info["storage_state_path"] = as_str(storage_state_path.relative_to(Path(base)))
            # Guardar log de artifacts
            artifacts_log = run_dir / "artifacts_log.md"
            
            # Añadir instrumentación al log
            instrumentation_summary = ""
            try:
                # Intentar leer instrumentation si existe
                instrumentation_path = evidence_dir / "instrumentation.json"
                if instrumentation_path.exists():
                    # HOTFIX: Usar jsonlib del import global (no import local que causa shadowing)
                    with open(instrumentation_path, "r", encoding="utf-8") as f:
                        inst_data = jsonlib.load(f)
                        instrumentation_summary = f"""
## Instrumentación
- URL actual: {inst_data.get('current_url', 'N/A')}
- Filas detectadas: {inst_data.get('rows_detected', 0)}
- Requisitos parseados: {inst_data.get('requirements_parsed', 0)}
- Tenant detectado: {inst_data.get('detected_tenant', 'N/A')}
"""
            except Exception:
                pass
            
            from datetime import datetime as dt_module
            from backend.shared.path_utils import as_str
            storage_state_rel = storage_state_path.relative_to(Path(base)) if storage_state_path else None
            artifacts_log.write_text(
                f"# Artifacts generados\n\n"
                f"- **storage_state.json**: Sesión autenticada guardada para reutilización\n"
                f"  - Path: `{as_str(storage_state_rel) if storage_state_rel else 'N/A'}`\n"
                f"  - Generado: {dt_module.utcnow().isoformat()}\n"
                f"{instrumentation_summary}",
                encoding="utf-8"
            )
        
        (run_dir / "run_finished.json").write_text(
            jsonlib.dumps(
                {
                    "run_id": run_id,
                    "status": "success",
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                    "duration_ms": duration_ms,
                    "reason": "SUBMISSION_PLAN_GENERATED",
                    "last_error": None,
                    "artifacts": artifacts_info,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    
    return run_id

