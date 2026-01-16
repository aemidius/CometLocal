from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime
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
from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS, _safe_write_json


def _parse_date_from_cell(cell_value: str) -> Optional[date]:
    """Intenta parsear una fecha desde un string de celda."""
    if not cell_value:
        return None
    cell_str = str(cell_value).strip()
    if not cell_str or cell_str == "-":
        return None
    
    # Intentar formatos comunes: DD/MM/YYYY, YYYY-MM-DD
    from datetime import datetime as dt
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
        try:
            return dt.strptime(cell_str, fmt).date()
        except ValueError:
            continue
    
    return None


def run_match_pending_documents_readonly_headful(
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
) -> str:
    """
    HEADFUL / READ-ONLY:
    1) Login y obtiene listado de pendientes (reutiliza lógica existente).
    2) Para cada pendiente (o solo el target si only_target=True), hace matching con repo.
    3) Genera evidence: pending_items.json, match_results.json, meta.json.
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)
    repo_store = DocumentRepositoryStoreV1(base_dir=base)
    matcher = DocumentMatcherV1(repo_store, base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")
    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    client_code = (coord.client_code or "").strip()
    username = (coord.username or "").strip()
    password_ref = (coord.password_ref or "").strip()
    password = secrets.get_secret(password_ref) if password_ref else None
    if not client_code or not username or not password:
        raise ValueError("Missing credentials: client_code/username/password_ref")

    run_id = f"r_{uuid.uuid4().hex}"
    run_dir = Path(base) / "runs" / run_id
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Evidence paths
    shot_01 = evidence_dir / "01_dashboard_tiles.png"
    shot_02 = evidence_dir / "02_listado_grid.png"
    pending_items_path = evidence_dir / "pending_items.json"
    match_results_path = evidence_dir / "match_results.json"
    meta_path = evidence_dir / "meta.json"

    started = time.time()

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    pending_items: List[Dict[str, Any]] = []
    match_results: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(
            viewport=viewport or {"width": 1600, "height": 1000},
        )
        page = context.new_page()

        # 1) Login (reutilizar lógica existente)
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)
        page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
        page.locator('input[name="Username"]').fill(username, timeout=20000)
        page.locator('input[name="Password"]').fill(password, timeout=20000)
        page.locator('button[type="submit"]').click(timeout=20000)

        page.wait_for_url("**/default_contenido.asp", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass
        time.sleep(wait_after_login_s)

        # Cerrar todos los overlays DHTMLX bloqueantes (pipeline completo)
        try:
            from backend.adapters.egestiona.priority_comms_headful import dismiss_all_dhx_blockers, PriorityCommsModalNotDismissed, DhxBlockerNotDismissed
            dismiss_all_dhx_blockers(page, evidence_dir, timeout_seconds=30)
        except (PriorityCommsModalNotDismissed, DhxBlockerNotDismissed) as e:
            # Re-lanzar como RuntimeError para que el endpoint lo capture
            raise RuntimeError(f"DHX_BLOCKER_NOT_DISMISSED: {e}") from e
        except Exception as e:
            # Si falla, guardar evidence pero continuar (no romper el flujo)
            print(f"[WARNING] Error inesperado al cerrar overlays DHTMLX: {e}")
            try:
                page.screenshot(path=str(evidence_dir / "dhx_blocker_error.png"), full_page=True)
            except Exception:
                pass
        
        # CAMBIO 5: Aumentar robustez anti-intercepts después de cerrar blockers
        try:
            page.wait_for_timeout(300)  # 300ms
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass  # No crítico

        # CAMBIO 2: Navegación robusta al área de pendientes
        list_frame = None
        skip_old_navigation = False
        try:
            from backend.adapters.egestiona.navigation_helpers import ensure_pending_upload_dashboard, PendingEntryPointNotReached
            list_frame = ensure_pending_upload_dashboard(page, evidence_dir, max_retries=2, timeout_seconds=15)
            print(f"[MATCH_PENDING] Navegación robusta completada, grid encontrado")
            skip_old_navigation = True
        except PendingEntryPointNotReached as e:
            page.screenshot(path=str(shot_01), full_page=True)
            raise RuntimeError(f"PENDING_ENTRY_POINT_NOT_REACHED: {e}") from e
        except Exception as e:
            # Fallback a navegación antigua si falla
            print(f"[WARNING] Error en navegación robusta, usando fallback: {e}")
            skip_old_navigation = False

        if not skip_old_navigation:
            # Esperar frame nm_contenido
            t_deadline = time.time() + 25.0
            frame = None
            while time.time() < t_deadline:
                frame = page.frame(name="nm_contenido")
                if frame and frame.url:
                    break
                time.sleep(0.25)
            if not frame:
                page.screenshot(path=str(shot_01), full_page=True)
                raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")

            page.screenshot(path=str(shot_01), full_page=True)

            # 2) Click tile Enviar Doc. Pendiente
            tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
            tile = frame.locator(tile_sel)
            tile.first.wait_for(state="visible", timeout=20000)
            tile.first.click(timeout=20000)

            # 3) Buscar grid usando función determinística
            from backend.adapters.egestiona.navigation_helpers import pick_pending_grid_frame
            list_frame = pick_pending_grid_frame(page)
            
            if not list_frame:
                # Fallback: buscar por función antigua
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
                    page.screenshot(path=str(shot_02), full_page=True)
                    raise RuntimeError("GRID_NOT_FOUND")
        
        # Validar que el grid está realmente cargado con espera explícita
        from backend.adapters.egestiona.navigation_helpers import validate_pending_grid_loaded
        print(f"[MATCH_PENDING] Validando que el grid está completamente cargado...")
        
        # Esperar explícitamente a que el grid termine de cargar
        # wait_for_function: desaparece spinner + aparece al menos el header del grid
        try:
            # Esperar a que desaparezca spinner
            spinner_gone = False
            for _ in range(10):  # 10 intentos de 0.5s = 5s máximo
                try:
                    spinner = list_frame.locator('.loading, .spinner, [class*="loading"], [class*="spinner"]')
                    if spinner.count() == 0 or not spinner.first.is_visible(timeout=200):
                        spinner_gone = True
                        break
                except Exception:
                    spinner_gone = True
                    break
                time.sleep(0.5)
            
            # Esperar a que aparezca header del grid
            header_appeared = False
            for _ in range(10):  # 10 intentos de 0.5s = 5s máximo
                try:
                    if list_frame.locator("table.hdr").count() > 0:
                        header_appeared = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            
            if not spinner_gone or not header_appeared:
                print(f"[MATCH_PENDING] Grid no terminó de cargar (spinner_gone={spinner_gone}, header_appeared={header_appeared})")
        except Exception as e:
            print(f"[MATCH_PENDING] Error al esperar carga del grid: {e}")
        
        # Validación final
        if not validate_pending_grid_loaded(list_frame, evidence_dir):
            print(f"[MATCH_PENDING] Grid no está completamente cargado, esperando...")
            time.sleep(2.0)
            if not validate_pending_grid_loaded(list_frame, evidence_dir):
                page.screenshot(path=str(shot_02), full_page=True)
                raise RuntimeError("GRID_NOT_LOADED: Grid encontrado pero no está completamente cargado")

        list_frame.locator("table.hdr").first.wait_for(state="attached", timeout=15000)
        list_frame.locator("table.obj.row20px").first.wait_for(state="attached", timeout=15000)

        try:
            list_frame.locator("body").screenshot(path=str(shot_02))
        except Exception:
            page.screenshot(path=str(shot_02), full_page=True)

        # 4) Extraer grid (reutilizar código existente)
        extracted = list_frame.evaluate(
            """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  function headersFromHdrTable(hdr){
    const cells = Array.from(hdr.querySelectorAll('tr:nth-of-type(2) td'));
    if(cells.length){
      return cells.map(td => {
        const span = td.querySelector('.hdrcell span');
        return span ? norm(span.innerText) : norm(td.innerText);
      });
    }
    return Array.from(hdr.querySelectorAll('.hdrcell span')).map(s => norm(s.innerText));
  }
  function extractRowsFromObjTable(obj, headers){
    const rows = Array.from(obj.querySelectorAll('tbody tr'));
    return rows.map(tr => {
      const cells = Array.from(tr.querySelectorAll('td'));
      const row = {};
      headers.forEach((h, i) => {
        if(cells[i]) row[h] = norm(cells[i].innerText);
      });
      return row;
    });
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return {headers:[], rows:[]};
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  let bestObj = null;
  let bestRows = [];
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > bestRows.length){
      bestObj = t;
      bestRows = rs;
    }
  }
  return {headers, rows: bestRows};
}"""
        )

        raw_rows = extracted.get("rows") or []

        # 5) Convertir a PendingItemV1 y filtrar si only_target
        from backend.shared.text_normalizer import normalize_text_robust, normalize_company_name, text_contains, extract_company_code
        
        def _row_matches_target(r: Dict[str, Any]) -> bool:
            """Filtra por company_key y person_key si only_target=True usando normalización robusta."""
            if not only_target:
                return True
            empresa_raw = str(r.get("Empresa") or r.get("empresa") or "")
            elemento_raw = str(r.get("Elemento") or r.get("elemento") or "")
            
            # Matching robusto de empresa
            # company_key puede ser tax_id (ej: "F63161988") o nombre de empresa
            empresa_match = True
            if company_key:
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
                        company_key_norm = normalize_text_robust(company_key)
                        empresa_match = text_contains(empresa_norm, company_key_norm)
                else:
                    # No hay código en la empresa, buscar por nombre normalizado
                    empresa_norm = normalize_company_name(empresa_raw)
                    company_key_norm = normalize_text_robust(company_key)
                    empresa_match = text_contains(empresa_norm, company_key_norm)
            
            elemento_norm = normalize_text_robust(elemento_raw)
            person_key_norm = normalize_text_robust(person_key) if person_key else ""
            elemento_match = text_contains(elemento_norm, person_key_norm) if person_key else True
            
            return empresa_match and elemento_match

        target_rows = [r for r in raw_rows if _row_matches_target(r)][:limit]

        # CAMBIO 3: Validar que 0 pendientes no es falso 0
        if len(target_rows) == 0 and len(raw_rows) == 0:
            print(f"[MATCH_PENDING] 0 pendientes encontrados, validando que no es falso 0...")
            # Comprobación de sanity: ¿Estamos realmente en la pantalla de pendientes?
            is_valid_pending_page = False
            try:
                # Verificar indicadores de que estamos en la pantalla correcta
                indicators = [
                    list_frame.locator('text=/documentaci[oó]n.*pendiente/i'),
                    list_frame.locator('text=/gesti[oó]n.*documental/i'),
                    list_frame.locator('table.obj'),
                    list_frame.locator('.listado_link'),
                    list_frame.locator('table.hdr'),
                ]
                for indicator in indicators:
                    if indicator.count() > 0:
                        is_valid_pending_page = True
                        print(f"[MATCH_PENDING] Indicador de pantalla válida encontrado")
                        break
            except Exception as e:
                print(f"[MATCH_PENDING] Error al validar pantalla: {e}")
            
            if not is_valid_pending_page:
                print(f"[MATCH_PENDING] Pantalla no válida, re-navegando...")
                # Re-navegar con ensure_pending_upload_dashboard
                try:
                    from backend.adapters.egestiona.navigation_helpers import ensure_pending_upload_dashboard, PendingEntryPointNotReached
                    list_frame = ensure_pending_upload_dashboard(page, evidence_dir, max_retries=1, timeout_seconds=10)
                    # Reintentar extracción
                    extracted = list_frame.evaluate(
                        """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  function headersFromHdrTable(hdr){
    const cells = Array.from(hdr.querySelectorAll('tr:nth-of-type(2) td'));
    if(cells.length){
      return cells.map(td => {
        const span = td.querySelector('.hdrcell span');
        return span ? norm(span.innerText) : norm(td.innerText);
      });
    }
    return Array.from(hdr.querySelectorAll('.hdrcell span')).map(s => norm(s.innerText));
  }
  function extractRowsFromObjTable(obj, headers){
    const rows = Array.from(obj.querySelectorAll('tbody tr'));
    return rows.map(tr => {
      const cells = Array.from(tr.querySelectorAll('td'));
      const row = {};
      headers.forEach((h, i) => {
        if(cells[i]) row[h] = norm(cells[i].innerText);
      });
      return row;
    });
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return {headers:[], rows:[]};
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  let bestObj = null;
  let bestRows = [];
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > bestRows.length){
      bestObj = t;
      bestRows = rs;
    }
  }
  return {headers, rows: bestRows};
}"""
                    )
                    raw_rows = extracted.get("rows") or []
                    target_rows = [r for r in raw_rows if _row_matches_target(r)][:limit]
                    print(f"[MATCH_PENDING] Después de re-navegación: {len(raw_rows)} filas totales, {len(target_rows)} target")
                except Exception as e:
                    print(f"[MATCH_PENDING] Error en re-navegación: {e}")
                    # Continuar con 0 pendientes si la re-navegación falla
            else:
                # Estamos en la pantalla correcta y el grid está cargado, pero no hay filas
                print(f"[MATCH_PENDING] Pantalla válida, grid cargado, pero 0 filas. Confirmando que no hay spinner...")
                try:
                    # Verificar que no hay spinner/loading
                    spinner = list_frame.locator('.loading, .spinner, [class*="loading"], [class*="spinner"]')
                    if spinner.count() > 0 and spinner.first.is_visible(timeout=500):
                        print(f"[MATCH_PENDING] Spinner detectado, esperando...")
                        time.sleep(2.0)
                        # Reintentar extracción una vez más
                        extracted = list_frame.evaluate(
                            """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  function headersFromHdrTable(hdr){
    const cells = Array.from(hdr.querySelectorAll('tr:nth-of-type(2) td'));
    if(cells.length){
      return cells.map(td => {
        const span = td.querySelector('.hdrcell span');
        return span ? norm(span.innerText) : norm(td.innerText);
      });
    }
    return Array.from(hdr.querySelectorAll('.hdrcell span')).map(s => norm(s.innerText));
  }
  function extractRowsFromObjTable(obj, headers){
    const rows = Array.from(obj.querySelectorAll('tbody tr'));
    return rows.map(tr => {
      const cells = Array.from(tr.querySelectorAll('td'));
      const row = {};
      headers.forEach((h, i) => {
        if(cells[i]) row[h] = norm(cells[i].innerText);
      });
      return row;
    });
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return {headers:[], rows:[]};
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  let bestObj = null;
  let bestRows = [];
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > bestRows.length){
      bestObj = t;
      bestRows = rs;
    }
  }
  return {headers, rows: bestRows};
}"""
                        )
                        raw_rows = extracted.get("rows") or []
                        target_rows = [r for r in raw_rows if _row_matches_target(r)][:limit]
                except Exception:
                    pass

        # 6) Convertir a PendingItemV1 y hacer matching
        for row in target_rows:
            tipo_doc = str(row.get("Tipo Documento") or row.get("tipo_doc") or row.get("Tipo") or "")
            elemento = str(row.get("Elemento") or row.get("elemento") or "")
            empresa = str(row.get("Empresa") or row.get("empresa") or "")
            
            # Intentar parsear fechas
            fecha_inicio = _parse_date_from_cell(row.get("Inicio") or row.get("inicio") or row.get("Fecha Inicio") or "")
            fecha_fin = _parse_date_from_cell(row.get("Fin") or row.get("fin") or row.get("Fecha Fin") or "")

            pending = PendingItemV1(
                tipo_doc=tipo_doc,
                elemento=elemento,
                empresa=empresa,
                trabajador=elemento,  # En eGestiona, Elemento suele ser el trabajador
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                raw_data=row
            )

            pending_dict = pending.to_dict()
            pending_items.append(pending_dict)

            # Hacer matching (con platform y coord para reglas)
            match_result = matcher.match_pending_item(
                pending,
                company_key=company_key,
                person_key=person_key,
                platform_key=platform,
                coord_label=coordination,
                evidence_dir=evidence_dir  # Pasar evidence_dir para debug
            )

            match_results.append({
                "pending_item": pending_dict,
                "match_result": match_result
            })

        # INSTRUMENTACIÓN: Capturar información diagnóstica antes de cerrar
        diagnostic_info = {}
        try:
            # Información básica de la página
            diagnostic_info["page_url"] = page.url
            diagnostic_info["page_title"] = page.title()
            
            # Lista de frames
            frames_info = []
            for frame in page.frames:
                try:
                    frames_info.append({
                        "name": frame.name or "unnamed",
                        "url": frame.url or "",
                    })
                except Exception:
                    pass
            diagnostic_info["frames"] = frames_info
            
            # Frame principal usado
            if 'list_frame' in locals() and list_frame:
                try:
                    diagnostic_info["main_frame_url"] = list_frame.url or ""
                    diagnostic_info["main_frame_name"] = list_frame.name or ""
                except Exception:
                    pass
            
            # Estrategia de navegación usada
            diagnostic_info["navigation_strategy"] = "robust" if skip_old_navigation else "fallback"
            
            # Información del grid
            if 'list_frame' in locals() and list_frame:
                try:
                    grid_count = list_frame.locator("table.obj.row20px").count()
                    diagnostic_info["grid_table_count"] = grid_count
                    diagnostic_info["grid_selector"] = "table.obj.row20px"
                    diagnostic_info["grid_rows_detected"] = grid_count
                except Exception:
                    pass
            
            # Breadcrumbs y títulos
            breadcrumbs = []
            try:
                if 'list_frame' in locals() and list_frame:
                    # Buscar breadcrumbs comunes
                    breadcrumb_selectors = [
                        '.breadcrumb',
                        '[class*="breadcrumb"]',
                        '.ruta',
                        '[class*="ruta"]',
                    ]
                    for selector in breadcrumb_selectors:
                        try:
                            breadcrumb_elem = list_frame.locator(selector)
                            if breadcrumb_elem.count() > 0:
                                breadcrumb_text = breadcrumb_elem.first.text_content() or ""
                                if breadcrumb_text:
                                    breadcrumbs.append(breadcrumb_text.strip()[:200])
                                    break
                        except Exception:
                            continue
            except Exception:
                pass
            diagnostic_info["breadcrumbs"] = breadcrumbs
            
            # Contar listado_link
            listado_link_count = 0
            try:
                if 'frame' in locals() and frame:
                    listado_link_count = frame.locator('a.listado_link').count()
            except Exception:
                pass
            diagnostic_info["listado_link_count"] = listado_link_count
            
            # Verificar grid container
            has_grid_container = False
            try:
                if 'list_frame' in locals() and list_frame:
                    has_grid_container = list_frame.locator("table.obj").count() > 0
            except Exception:
                pass
            diagnostic_info["has_grid_container"] = has_grid_container
            
            # Primeros items (texto)
            first_items_text = []
            try:
                if 'list_frame' in locals() and list_frame and len(pending_items) > 0:
                    for item in pending_items[:3]:
                        tipo_doc = str(item.get("tipo_doc", ""))
                        elemento = str(item.get("elemento", ""))
                        empresa = str(item.get("empresa", ""))
                        first_items_text.append(f"{tipo_doc}|{elemento}|{empresa}")
            except Exception:
                pass
            diagnostic_info["first_items_text"] = first_items_text
            
            # Calcular screen signature
            from backend.adapters.egestiona.stability_test_pending import compute_screen_signature
            screen_signature = compute_screen_signature(
                page_url=diagnostic_info.get("page_url", ""),
                title=diagnostic_info.get("page_title", ""),
                breadcrumbs=breadcrumbs,
                listado_link_count=listado_link_count,
                has_grid_container=has_grid_container,
                first_items_text=first_items_text,
            )
            diagnostic_info["screen_signature"] = screen_signature
            
            # Si hay 0 pendientes, guardar diagnostic_zero_case.json
            if len(pending_items) == 0:
                print(f"[MATCH_PENDING] 0 pendientes detectados, guardando diagnóstico...")
                diagnostic_info["zero_case"] = True
                diagnostic_info["raw_rows_count"] = len(raw_rows) if 'raw_rows' in locals() else 0
                diagnostic_info["target_rows_count"] = len(target_rows) if 'target_rows' in locals() else 0
                
                # Guardar HTML dump
                try:
                    html_dump_path = evidence_dir / "zero_case.html"
                    if 'list_frame' in locals() and list_frame:
                        html_content = list_frame.content()
                        html_dump_path.write_text(html_content, encoding='utf-8')
                        diagnostic_info["html_dump_path"] = str(html_dump_path.relative_to(run_dir))
                except Exception as e:
                    print(f"[MATCH_PENDING] Error al guardar HTML dump: {e}")
                
                # Screenshot
                try:
                    screenshot_path = evidence_dir / "zero_case.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    diagnostic_info["screenshot_path"] = str(screenshot_path.relative_to(run_dir))
                except Exception as e:
                    print(f"[MATCH_PENDING] Error al guardar screenshot: {e}")
            
            # Guardar diagnostic info siempre
            diagnostic_path = evidence_dir / "diagnostic_info.json"
            _safe_write_json(diagnostic_path, diagnostic_info)
            
            # Si es zero case, también guardar como diagnostic_zero_case.json
            if len(pending_items) == 0:
                zero_case_path = evidence_dir / "diagnostic_zero_case.json"
                _safe_write_json(zero_case_path, diagnostic_info)
                print(f"[MATCH_PENDING] Diagnostic zero case guardado: {zero_case_path}")
        
        except Exception as e:
            print(f"[MATCH_PENDING] Error al capturar información diagnóstica: {e}")

        context.close()
        browser.close()

    # 7) Guardar evidence
    _safe_write_json(pending_items_path, {"items": pending_items})
    _safe_write_json(match_results_path, {"results": match_results})

    finished = time.time()
    _safe_write_json(
        meta_path,
        {
            "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
            "company_key": company_key,
            "person_key": person_key,
            "only_target": only_target,
            "limit": limit,
            "pending_items_count": len(pending_items),
            "match_results_count": len(match_results),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
            "duration_ms": int((finished - started) * 1000),
        },
    )

    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "MATCHED_PENDING_DOCUMENTS",
                "last_error": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id

