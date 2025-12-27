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
    matcher = DocumentMatcherV1(repo_store)

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
            page.screenshot(path=str(shot_02), full_page=True)
            raise RuntimeError("GRID_NOT_FOUND")

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
        def _norm_company(v: str) -> str:
            s = (v or "").strip()
            if " (" in s:
                s = s.split(" (", 1)[0].strip()
            return s

        def _row_matches_target(r: Dict[str, Any]) -> bool:
            """Filtra por company_key y person_key si only_target=True."""
            if not only_target:
                return True
            empresa_raw = str(r.get("Empresa") or r.get("empresa") or "")
            elemento_raw = str(r.get("Elemento") or r.get("elemento") or "")
            # Normalizar empresa (quitar código entre paréntesis)
            empresa_norm = _norm_company(empresa_raw)
            # Verificar si contiene company_key o si el elemento contiene person_key
            # (simplificado: buscar en texto)
            empresa_match = company_key.lower() in empresa_norm.lower() if company_key else True
            elemento_match = person_key.lower() in elemento_raw.lower() if person_key else True
            return empresa_match and elemento_match

        target_rows = [r for r in raw_rows if _row_matches_target(r)][:limit]

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

            # Hacer matching
            match_result = matcher.match_pending_item(
                pending,
                company_key=company_key,
                person_key=person_key
            )

            match_results.append({
                "pending_item": pending_dict,
                "match_result": match_result
            })

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

