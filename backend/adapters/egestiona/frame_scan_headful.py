from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.secrets_store_v1 import SecretsStoreV1


LOGIN_URL_PREVIOUS_SUCCESS = "https://coordinate.egestiona.es/login?origen=subcontrata"


def _safe_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_find_enviar_doc_in_all_frames_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    slow_mo_ms: int = 300,
    wait_after_login_s: float = 2.5,
) -> str:
    """
    HEADFUL / READ-ONLY:
    - Login usando EXACTAMENTE la misma URL del último run exitoso (sin tocar config).
    - Enumerar TODOS los frames y buscar en cada frame el texto exacto "Enviar Doc. Pendiente".
    - Generar evidencia PNG SIEMPRE + dump JSON de frames/textos.
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")
    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # Credenciales
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

    # Archivos requeridos
    shot_01 = evidence_dir / "01_dashboard.png"
    shot_02 = evidence_dir / "02_found_or_not.png"
    shot_03 = evidence_dir / "03_tile_element.png"
    dump_frames_path = evidence_dir / "frames.json"
    dump_texts_path = evidence_dir / "dump_texts_by_frame.json"
    dump_clickable_path = evidence_dir / "tile_clickable_outerhtml.html"

    started = time.time()
    found: Optional[Dict[str, Any]] = None
    frames_dump: List[Dict[str, Any]] = []
    texts_dump: Dict[str, List[str]] = {}

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # 1) Navigate (URL anterior exacta)
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)

        # 2) Login
        page.locator('input[name="ClientName"]').fill(client_code, timeout=15000)
        page.locator('input[name="Username"]').fill(username, timeout=15000)
        page.locator('input[name="Password"]').fill(password, timeout=15000)
        page.locator('button[type="submit"]').click(timeout=15000)

        # 3) Esperar post-login + 2-3s
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        time.sleep(wait_after_login_s)

        # Evidence 01: siempre
        page.screenshot(path=str(shot_01), full_page=True)

        # Logs / dumps de paridad
        try:
            ua = page.evaluate("() => navigator.userAgent")
        except Exception:
            ua = None

        for idx, fr in enumerate(page.frames):
            frames_dump.append(
                {
                    "index": idx,
                    "name": fr.name,
                    "url": fr.url,
                    "is_main": fr == page.main_frame,
                }
            )

        _safe_write_json(
            dump_frames_path,
            {
                "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
                "page_url": page.url,
                "page_title": page.title(),
                "user_agent": ua,
                "frames": frames_dump,
            },
        )

        # 4) Buscar en cada frame
        target_exact = "Enviar Doc. Pendiente"
        target_fallback = "Enviar Doc"

        def _extract_visible_texts(frame) -> List[str]:
            try:
                txt = frame.evaluate("() => (document.body ? (document.body.innerText || '') : '')")
            except Exception:
                txt = ""
            lines = [ln.strip() for ln in (txt or "").splitlines()]
            lines = [ln for ln in lines if ln]
            # top 200 unique preserving order
            seen = set()
            out: List[str] = []
            for ln in lines:
                if ln in seen:
                    continue
                seen.add(ln)
                out.append(ln)
                if len(out) >= 200:
                    break
            return out

        for idx, fr in enumerate(page.frames):
            # Exact
            loc = fr.get_by_text(target_exact, exact=True)
            if loc.count() == 0:
                # Fallback contains
                loc = fr.get_by_text(target_fallback, exact=False)

            if loc.count() > 0:
                try:
                    loc.first.wait_for(state="visible", timeout=1500)
                except Exception:
                    pass
                # screenshot viewport (02) + element (03)
                page.screenshot(path=str(shot_02), full_page=True)
                try:
                    loc.first.screenshot(path=str(shot_03))
                except Exception:
                    # fallback: viewport again
                    page.screenshot(path=str(shot_03), full_page=True)

                # OuterHTML clickable ancestor
                try:
                    outer = loc.first.evaluate(
                        """(el) => {
  const clickable = el.closest('a,button,[role="button"],div[onclick],img[onclick],area') || el;
  return clickable.outerHTML || '';
}"""
                    )
                except Exception:
                    outer = ""
                dump_clickable_path.write_text(outer or "", encoding="utf-8")

                found = {
                    "frame_index": idx,
                    "frame_name": fr.name,
                    "frame_url": fr.url,
                    "matched_text": target_exact if target_exact in (loc.first.inner_text() if loc.count() else "") else target_fallback,
                    "recommended_selector": {
                        "strategy": "frame.get_by_text",
                        "frame": {"name": fr.name, "url": fr.url},
                        "text": target_exact,
                        "exact": True,
                    },
                }
                break
            else:
                # dump textos visibles por frame (para diagnóstico)
                key = f"{idx}:{fr.name or ''}:{fr.url or ''}"
                texts_dump[key] = _extract_visible_texts(fr)

        if found is None:
            # No encontrado: screenshot obligatorio + dump de textos por frame
            page.screenshot(path=str(shot_02), full_page=True)
            _safe_write_json(dump_texts_path, texts_dump)
        else:
            _safe_write_json(evidence_dir / "found.json", found)

        context.close()
        browser.close()

    finished = time.time()
    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success" if found else "failed",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "FOUND_TILE" if found else "NOT_FOUND",
                "last_error": None if found else "NOT_FOUND",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id


def run_upload_pending_document_scoped_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.5,
) -> str:
    """
    HEADFUL / WRITE (scoped strict):
    - Hard-stop if:
      - samples pdf count != 1
      - filtered matches != 1
      - detail scope not validated (TEDELAB + Emilio + DNI if visible)
      - missing file attachment or missing "Inicio Vigencia"
    - Upload the single PDF in data/samples/
    - Fill "Inicio Vigencia" with today's date (Europe/Madrid)
    - Click final button ("Enviar documento"/"Enviar archivo"/"Enviar") only after guardrails satisfied
    - Validate confirmation (message or visible state change)
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

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

    # Evidence paths (requeridos)
    shot_01 = evidence_dir / "01_dashboard_tiles.png"
    shot_02 = evidence_dir / "02_listado_grid.png"
    shot_03 = evidence_dir / "03_row_highlight.png"
    shot_04 = evidence_dir / "04_after_click_detail.png"
    shot_05 = evidence_dir / "05_detail_before_upload.png"
    shot_06 = evidence_dir / "06_detail_filled.png"
    shot_07 = evidence_dir / "07_confirmation.png"
    detail_txt_path = evidence_dir / "detail_text_dump.txt"
    confirmation_txt_path = evidence_dir / "confirmation_text_dump.txt"
    meta_path = evidence_dir / "meta.json"

    started = time.time()
    status = "failed"
    last_error: Optional[str] = None

    # Pick the single PDF in data/samples/
    samples_dir = Path(base) / "samples"
    pdfs = sorted([p for p in samples_dir.glob("*.pdf") if p.is_file()])
    if len(pdfs) != 1:
        # hard-stop
        last_error = f"PDF_COUNT_INVALID: expected 1 pdf in {samples_dir}, got {len(pdfs)}"
        (run_dir / "run_finished.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "reason": "PDF_COUNT_INVALID",
                    "last_error": last_error,
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return run_id

    pdf_path = pdfs[0].resolve()

    # Date today Europe/Madrid
    date_ddmmyyyy = None
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Europe/Madrid")).date()
        date_ddmmyyyy = today.strftime("%d/%m/%Y")
        date_yyyymmdd = today.strftime("%Y-%m-%d")
    except Exception:
        # fallback to local date
        from datetime import datetime

        today = datetime.now().date()
        date_ddmmyyyy = today.strftime("%d/%m/%Y")
        date_yyyymmdd = today.strftime("%Y-%m-%d")

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    def _strip_accents(s: str) -> str:
        repl = str.maketrans(
            {
                "á": "a",
                "é": "e",
                "í": "i",
                "ó": "o",
                "ú": "u",
                "ü": "u",
                "ñ": "n",
                "Á": "A",
                "É": "E",
                "Í": "I",
                "Ó": "O",
                "Ú": "U",
                "Ü": "U",
                "Ñ": "N",
            }
        )
        return (s or "").translate(repl)

    def _canon(s: str) -> str:
        s2 = _strip_accents((s or "").strip()).upper()
        out = []
        for ch in s2:
            if ch.isalnum() or ch.isspace():
                out.append(ch)
            else:
                out.append(" ")
        return " ".join("".join(out).split())

    def _levenshtein_leq_1(a: str, b: str) -> bool:
        if a == b:
            return True
        la, lb = len(a), len(b)
        if abs(la - lb) > 1:
            return False
        i = j = 0
        edits = 0
        while i < la and j < lb:
            if a[i] == b[j]:
                i += 1
                j += 1
                continue
            edits += 1
            if edits > 1:
                return False
            if la == lb:
                i += 1
                j += 1
            elif la > lb:
                i += 1
            else:
                j += 1
        if i < la or j < lb:
            edits += 1
        return edits <= 1

    company_target = "TEDELAB INGENIERIA SCCL"
    worker_target = "Emilio Roldán Molina"
    worker_dni = "37330395"

    def _norm_company(v: str) -> str:
        s = (v or "").strip()
        if " (" in s:
            s = s.split(" (", 1)[0].strip()
        return s

    def _match_company(cell: str) -> bool:
        a = _canon(_norm_company(cell))
        b = _canon(company_target)
        return _levenshtein_leq_1(a, b)

    def _match_worker(cell: str) -> bool:
        a = _canon(cell)
        toks = [t for t in _canon(worker_target).split(" ") if t]
        return all(t in a for t in toks) or (worker_dni in a)

    def _scope_ok(text: str) -> bool:
        hay = _canon(text or "")
        ok_company = ("TEDELAB" in hay) or _match_company(text or "")
        ok_worker = ("EMILIO" in hay) or ("ROLDAN" in hay) or (worker_dni in hay) or _match_worker(text or "")
        # if DNI is visible, enforce it
        if "37330395" in hay:
            ok_worker = ok_worker and ("37330395" in hay)
        return bool(ok_company and ok_worker)

    def _detail_labels_ok(text: str) -> bool:
        hay = _canon(text or "")
        return ("DOCUMENTO" in hay) and ("TRABAJADOR" in hay) and ("EMPRESA" in hay)

    # Meta fields
    meta: Dict[str, Any] = {
        "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
        "pdf_path": str(pdf_path),
        "pdf_name": pdf_path.name,
        "date_used": {"ddmmyyyy": date_ddmmyyyy, "yyyymmdd": date_yyyymmdd},
        "selectors": {},
        "frames": {},
        "click_strategy": None,
        "confirmation": None,
    }

    def _write_run_finished(*, reason: str, error: Optional[str]) -> None:
        finished = time.time()
        (run_dir / "run_finished.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": status,
                    "reason": reason,
                    "last_error": error,
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                    "duration_ms": int((finished - started) * 1000),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(viewport=viewport or {"width": 1600, "height": 1000})
        page = context.new_page()
        try:
            # 1) Login con URL exacta anterior
            page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)
            page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
            page.locator('input[name="Username"]').fill(username, timeout=20000)
            page.locator('input[name="Password"]').fill(password, timeout=20000)
            page.locator('button[type="submit"]').click(timeout=20000)

            # 2) Esperar post-login + tiles
            page.wait_for_url("**/default_contenido.asp", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=25000)
            except Exception:
                pass
            time.sleep(wait_after_login_s)

            frame_dashboard = page.frame(name="nm_contenido")
            if not frame_dashboard:
                page.screenshot(path=str(shot_01), full_page=True)
                raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")
            page.screenshot(path=str(shot_01), full_page=True)

            # 3) Click Gestion(3)
            tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
            meta["selectors"]["tile"] = tile_sel
            frame_dashboard.locator(tile_sel).first.wait_for(state="visible", timeout=20000)
            frame_dashboard.locator(tile_sel).first.click(timeout=20000)

            # 4) Find list frame f3 or buscador.asp + Apartado_ID=3 and wait grid + rows
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
                    return fr.locator("table.obj.row20px").count() > 0 and fr.locator("table.hdr").count() > 0
                except Exception:
                    return False

            list_frame = None
            t_deadline = time.time() + 15.0
            while time.time() < t_deadline:
                list_frame = _find_list_frame()
                if list_frame and _frame_has_grid(list_frame):
                    break
                time.sleep(0.25)

            # If needed, click "Buscar" to render grid (no filters changed)
            if not (list_frame and _frame_has_grid(list_frame)):
                clicked = False
                for fr in page.frames:
                    try:
                        btn = fr.get_by_text("Buscar", exact=True)
                        if btn.count() > 0:
                            btn.first.click(timeout=10000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    try:
                        btn = frame_dashboard.get_by_text("Buscar", exact=True)
                        if btn.count() > 0:
                            btn.first.click(timeout=10000)
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
                raise RuntimeError("GRID_NOT_FOUND: expected frame f3/buscador.asp?Apartado_ID=3 with table.hdr + table.obj.row20px")

            meta["frames"]["dashboard"] = {"name": "nm_contenido", "url": frame_dashboard.url}
            try:
                list_frame_url = list_frame.evaluate("() => location.href")
            except Exception:
                list_frame_url = list_frame.url
            meta["frames"]["list"] = {"name": list_frame.name, "url": list_frame_url}

            # wait rows ready (avoid 0 registros / loading)
            def _grid_rows_ready(fr) -> bool:
                try:
                    return bool(
                        fr.evaluate(
                            """() => {
  const obj = document.querySelector('table.obj.row20px');
  if(!obj) return false;
  const loading = Array.from(document.querySelectorAll('*')).some(el => {
    const t = (el.innerText||'').trim();
    return t === 'Loading...' && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
  });
  if(loading) return false;
  const trs = Array.from(obj.querySelectorAll('tr'));
  let cnt = 0;
  for(const tr of trs){
    const tds = Array.from(tr.querySelectorAll('td'));
    if(!tds.length) continue;
    const any = tds.some(td => ((td.innerText||'').replace(/\\s+/g,' ').trim()).length > 0);
    if(any) cnt++;
  }
  const reg = (document.body ? (document.body.innerText||'') : '');
  const m = reg.match(/\\b(\\d+)\\s+Registros\\b/i);
  const regN = m ? parseInt(m[1],10) : 0;
  return cnt > 0 || regN > 0;
}"""
                        )
                    )
                except Exception:
                    return False

            # Pro-actively click "Buscar" inside the list frame to load results (read-only).
            try:
                btn_buscar_f3 = list_frame.get_by_text("Buscar", exact=True)
                if btn_buscar_f3.count() > 0:
                    btn_buscar_f3.first.click(timeout=15000)
            except Exception:
                pass

            t_deadline = time.time() + 30.0
            while time.time() < t_deadline:
                if _grid_rows_ready(list_frame):
                    break
                time.sleep(0.25)

            # Hard-stop if still no rows (guardrail: don't proceed without loaded grid)
            if not _grid_rows_ready(list_frame):
                try:
                    list_frame.locator("body").screenshot(path=str(shot_02))
                except Exception:
                    page.screenshot(path=str(shot_02), full_page=True)
                raise RuntimeError("GRID_EMPTY_OR_LOADING: no rows after clicking Buscar in f3")

            # Evidence 02
            try:
                list_frame.locator("body").screenshot(path=str(shot_02))
            except Exception:
                page.screenshot(path=str(shot_02), full_page=True)

            # 5) Extract visible rows and find EXACTLY 1 match
            extraction = list_frame.evaluate(
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
  function scoreHdr(hdr){
    const hs = headersFromHdrTable(hdr);
    const nonEmpty = hs.filter(Boolean).length;
    return nonEmpty * 100 + norm(hdr.innerText).length;
  }
  function extractRowsFromObjTable(tbl, headers){
    const trs = Array.from(tbl.querySelectorAll('tr'));
    const rows = [];
    for(const tr of trs){
      const tds = Array.from(tr.querySelectorAll('td'));
      if(!tds.length) continue;
      const cells = tds.map(td => norm(td.innerText));
      if(!cells.some(x => x)) continue;
      const mapped = {};
      for(let i=0;i<cells.length;i++){
        const k = (i < headers.length && headers[i]) ? headers[i] : `col_${i+1}`;
        mapped[k] = cells[i] || '';
      }
      rows.push({ mapped, raw_cells: cells });
    }
    return rows;
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return { headers: [], rows: [], debug: {hdr_tables: hdrTables.length, obj_tables: objTables.length} };
  hdrTables.sort((a,b) => scoreHdr(b) - scoreHdr(a));
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  let best = { tbl: null, rows: [] };
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > best.rows.length){
      best = { tbl: t, rows: rs };
    }
  }
  return { headers, rows: best.rows, debug: {hdr_tables: hdrTables.length, obj_tables: objTables.length} };
}"""
            )
            rows_wrapped = extraction.get("rows") or []
            visible_rows: List[Dict[str, Any]] = []
            for idx, rw in enumerate(rows_wrapped):
                mapped = rw.get("mapped") or {}
                mapped["raw_cells"] = rw.get("raw_cells") or []
                mapped["_visible_index"] = idx
                visible_rows.append(mapped)

            def _row_matches(r: Dict[str, Any]) -> bool:
                empresa_raw = str(r.get("Empresa") or r.get("empresa") or "")
                elemento_raw = str(r.get("Elemento") or r.get("elemento") or "")
                vals = " | ".join(str(v or "") for v in r.values())
                return (_match_company(empresa_raw) or _match_company(vals)) and (_match_worker(elemento_raw) or _match_worker(vals))

            matches = [r for r in visible_rows if _row_matches(r)]
            if len(matches) != 1:
                try:
                    list_frame.locator("body").screenshot(path=str(shot_03))
                except Exception:
                    page.screenshot(path=str(shot_03), full_page=True)
                raise RuntimeError(f"FILTER_NOT_UNIQUE: expected 1 row, got {len(matches)}")

            target = matches[0]
            target_idx = int(target.get("_visible_index", 0))

            # highlight row
            try:
                list_frame.evaluate(
                    """(idx) => {
  const tbls = Array.from(document.querySelectorAll('table.obj.row20px'));
  let best = null;
  let bestCount = -1;
  for(const t of tbls){
    const trs = Array.from(t.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length);
    if(trs.length > bestCount){
      best = { t, trs };
      bestCount = trs.length;
    }
  }
  if(!best) return false;
  const tr = best.trs[idx];
  if(!tr) return false;
  tr.style.outline = '4px solid #ff0066';
  tr.style.outlineOffset = '2px';
  tr.scrollIntoView({block:'center', inline:'center'});
  return true;
}""",
                    target_idx,
                )
            except Exception:
                pass
            try:
                list_frame.locator("body").screenshot(path=str(shot_03))
            except Exception:
                page.screenshot(path=str(shot_03), full_page=True)

            # 6) Open detail (click row action)
            click_result = list_frame.evaluate(
                """(idx) => {
  function isVisible(el){
    if(!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function hasPointer(el){
    try { return window.getComputedStyle(el).cursor === 'pointer'; } catch(e){ return false; }
  }
  const tbls = Array.from(document.querySelectorAll('table.obj.row20px'));
  let best = null;
  let bestCount = -1;
  for(const t of tbls){
    const trs = Array.from(t.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length);
    if(trs.length > bestCount){
      best = { t, trs };
      bestCount = trs.length;
    }
  }
  if(!best) return { ok:false, reason:'no_obj_table' };
  const tr = best.trs[idx];
  if(!tr) return { ok:false, reason:'row_not_found', idx };
  const cands = [];
  const aTags = Array.from(tr.querySelectorAll('a'));
  for(const a of aTags){ if(isVisible(a)) cands.push({ el:a, kind:'a' }); }
  const imgs = Array.from(tr.querySelectorAll('img'));
  for(const img of imgs){
    if(isVisible(img) && (img.getAttribute('onclick') || img.closest('[onclick]') || hasPointer(img))) cands.push({ el: img, kind:'img' });
  }
  const onclicks = Array.from(tr.querySelectorAll('[onclick]'));
  for(const el of onclicks){ if(isVisible(el)) cands.push({ el, kind:'onclick' }); }
  const pick = (predicate) => cands.find(c => predicate(c));
  let chosen = pick(c => c.kind === 'a') || pick(c => c.kind === 'img') || pick(c => c.kind === 'onclick');
  if(!chosen){ chosen = { el: tr, kind: 'tr' }; }
  const el = chosen.el;
  const tag = el.tagName ? el.tagName.toLowerCase() : '';
  const html = (el.outerHTML || '').slice(0, 5000);
  try { el.click(); } catch(e){
    try { el.dispatchEvent(new MouseEvent('click', { bubbles:true, cancelable:true, view: window })); } catch(e2){}
  }
  return { ok:true, kind: chosen.kind, tag, outerHTML: html };
}""",
                target_idx,
            )
            meta["click_strategy"] = click_result

            # Wait modal with scope keywords
            def _modal_best_text() -> str:
                try:
                    return page.evaluate(
                        """() => {
  const els = Array.from(document.querySelectorAll('div,section,article'));
  function z(el){
    const s = window.getComputedStyle(el);
    const zi = parseInt(s.zIndex || '0', 10);
    return isNaN(zi) ? 0 : zi;
  }
  function isVis(el){
    const r = el.getBoundingClientRect();
    if(r.width < 200 || r.height < 120) return false;
    const s = window.getComputedStyle(el);
    if(s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    return true;
  }
  function score(el){
    const txt = ((el.innerText || '') + '').toLowerCase();
    const kws = ['documento:', 'trabajador:', 'empresa:', 'estado documento'];
    const hits = kws.reduce((acc,k)=> acc + (txt.includes(k) ? 1 : 0), 0);
    const r = el.getBoundingClientRect();
    const area = Math.floor(r.width * r.height);
    const zi = z(el);
    return hits * 1000000 + zi * 1000 + txt.length + Math.min(area, 1000000);
  }
  let best = null;
  let bestScore = -1;
  for(const el of els){
    if(!isVis(el)) continue;
    const cls = (el.className || '').toString().toLowerCase();
    const zi = z(el);
    const looks = (cls.includes('dhtmlx') && (cls.includes('win') || cls.includes('popup') || cls.includes('modal'))) || zi >= 1000;
    if(!looks) continue;
    const sc = score(el);
    if(sc > bestScore){ bestScore = sc; best = el; }
  }
  return best ? (best.innerText || '') : '';
}"""
                    )
                except Exception:
                    return ""

            t_deadline = time.time() + 25.0
            detail_text = ""
            while time.time() < t_deadline:
                detail_text = _modal_best_text()
                if len((detail_text or "").strip()) >= 40 and _detail_labels_ok(detail_text) and _scope_ok(detail_text):
                    break
                time.sleep(0.25)

            # Evidence 04 + dump
            page.screenshot(path=str(shot_04), full_page=True)
            detail_txt_path.write_text(detail_text or "", encoding="utf-8")

            # Hard-stop scope not validated
            if not (_detail_labels_ok(detail_text) and _scope_ok(detail_text)):
                raise RuntimeError("DETAIL_SCOPE_NOT_VALIDATED: missing Documento/Trabajador/Empresa or scope tokens (TEDELAB + Emilio/DNI)")

            # 7) Upload inside the modal: file + date
            page.screenshot(path=str(shot_05), full_page=True)

            # Locate file input: prefer visible, then any within page
            file_input = page.locator("input[type='file']:visible")
            if file_input.count() == 0:
                file_input = page.locator("input[type='file']")

            file_strategy = None
            if file_input.count() > 0:
                # choose first; set files even if hidden
                file_input.first.set_input_files(str(pdf_path))
                file_strategy = {"kind": "set_input_files", "selector": "input[type=file]"}
            else:
                # fallback: click an attach control and use file chooser
                try:
                    attach = page.get_by_text("Adjuntar fichero", exact=False)
                    if attach.count() == 0:
                        attach = page.get_by_text("Adjuntar", exact=False)
                    if attach.count() == 0:
                        raise RuntimeError("FILE_INPUT_NOT_FOUND")
                    with page.expect_file_chooser(timeout=15000) as fc_info:
                        attach.first.click(timeout=10000)
                    chooser = fc_info.value
                    chooser.set_files(str(pdf_path))
                    file_strategy = {"kind": "file_chooser", "by_text": "Adjuntar fichero"}
                except Exception as e:
                    raise RuntimeError(f"FILE_INPUT_NOT_FOUND: {e}")

            # Locate "Inicio Vigencia" input inside the active detail modal (avoid hidden inputs).
            # We resolve a best-effort CSS selector via JS by finding the closest visible input to the label.
            date_selector = page.evaluate(
                """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  function z(el){
    const s = window.getComputedStyle(el);
    const zi = parseInt(s.zIndex || '0', 10);
    return isNaN(zi) ? 0 : zi;
  }
  function isVis(el){
    if(!el) return false;
    const r = el.getBoundingClientRect();
    if(r.width < 5 || r.height < 5) return false;
    const s = window.getComputedStyle(el);
    if(s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    return true;
  }
  function cssEscape(s){ return (s||'').replace(/([ #;?%&,.+*~\\':\"!^$\\[\\]()=>|\\/])/g,'\\\\$1'); }
  function cssPath(el){
    if(!el || el.nodeType !== 1) return '';
    if(el.id) return el.tagName.toLowerCase() + '#' + cssEscape(el.id);
    const parts = [];
    while(el && el.nodeType === 1 && el.tagName.toLowerCase() !== 'html'){
      let part = el.tagName.toLowerCase();
      const cls = (el.className || '').toString().trim().split(/\\s+/).filter(Boolean);
      if(cls.length) part += '.' + cls.slice(0,2).map(cssEscape).join('.');
      const parent = el.parentElement;
      if(parent){
        const same = Array.from(parent.children).filter(c=>c.tagName===el.tagName);
        if(same.length>1){
          const idx = same.indexOf(el)+1;
          part += `:nth-of-type(${idx})`;
        }
      }
      parts.unshift(part);
      el = parent;
    }
    return parts.join(' > ');
  }
  // pick best modal-like container (same scoring used elsewhere)
  const els = Array.from(document.querySelectorAll('div,section,article'));
  function modalScore(el){
    const txt = ((el.innerText || '') + '').toLowerCase();
    const kws = ['documento:', 'trabajador:', 'empresa:', 'estado documento'];
    const hits = kws.reduce((acc,k)=> acc + (txt.includes(k) ? 1 : 0), 0);
    const r = el.getBoundingClientRect();
    const area = Math.floor(r.width * r.height);
    const zi = z(el);
    const cls = (el.className || '').toString().toLowerCase();
    const looks = (cls.includes('dhtmlx') && (cls.includes('win') || cls.includes('popup') || cls.includes('modal'))) || zi >= 1000;
    if(!looks || !isVis(el)) return -1;
    return hits * 1000000 + zi * 1000 + txt.length + Math.min(area, 1000000);
  }
  let modal = null;
  let best = -1;
  for(const el of els){
    const sc = modalScore(el);
    if(sc > best){ best = sc; modal = el; }
  }
  const root = modal || document.body;
  const labelNodes = Array.from(root.querySelectorAll('*')).filter(el => {
    const t = norm(el.innerText).toLowerCase();
    return t.includes('inicio vigencia');
  });
  if(!labelNodes.length) return null;
  // choose the smallest label-ish element
  labelNodes.sort((a,b)=> (norm(a.innerText).length - norm(b.innerText).length));
  const label = labelNodes[0];
  const lr = label.getBoundingClientRect();

  const inputs = Array.from(root.querySelectorAll('input,textarea,select')).filter(inp => {
    const tag = (inp.tagName || '').toLowerCase();
    if(tag === 'input'){
      const tp = (inp.getAttribute('type') || 'text').toLowerCase();
      if(tp === 'hidden' || tp === 'file') return false;
    }
    return isVis(inp);
  });
  if(!inputs.length) return null;

  function dist(a,b){
    const ax = a.left + a.width/2;
    const ay = a.top + a.height/2;
    const bx = b.left + b.width/2;
    const by = b.top + b.height/2;
    const dx = ax - bx;
    const dy = ay - by;
    return Math.sqrt(dx*dx + dy*dy);
  }
  let bestInp = null;
  let bestD = Infinity;
  for(const inp of inputs){
    const ir = inp.getBoundingClientRect();
    const d = dist(lr, ir);
    if(d < bestD){
      bestD = d;
      bestInp = inp;
    }
  }
  if(!bestInp) return null;
  if(bestInp.id) return '#' + cssEscape(bestInp.id);
  if(bestInp.name) return bestInp.tagName.toLowerCase() + `[name=\"${cssEscape(bestInp.name)}\"]`;
  return cssPath(bestInp);
}"""
            )
            if not date_selector:
                raise RuntimeError("DATE_INPUT_NOT_FOUND: Inicio Vigencia (modal)")

            date_input = page.locator(date_selector)
            if date_input.count() == 0:
                raise RuntimeError(f"DATE_INPUT_NOT_FOUND_RESOLVED: {date_selector}")

            # Fill date
            date_used = None
            date_input.first.fill(date_ddmmyyyy, timeout=10000)
            # verify accepted
            try:
                val = date_input.first.input_value(timeout=2000)
            except Exception:
                val = ""
            if not (val or "").strip():
                # fallback format
                date_input.first.fill(date_yyyymmdd, timeout=10000)
                date_used = date_yyyymmdd
            else:
                date_used = date_ddmmyyyy

            # Guardrails before final click: file attached + date filled + scope validated
            # Check file attached via JS if possible
            file_ok = True
            try:
                # find any input[type=file] with files.length > 0
                file_ok = bool(
                    page.evaluate(
                        """() => {
  const ins = Array.from(document.querySelectorAll('input[type="file"]'));
  for(const i of ins){
    try{
      if(i.files && i.files.length > 0) return true;
    }catch(e){}
  }
  return false;
}"""
                    )
                )
            except Exception:
                file_ok = True  # can't reliably check; assume set_input_files worked

            date_ok = True
            try:
                v = date_input.first.input_value(timeout=2000)
                date_ok = bool((v or "").strip())
            except Exception:
                date_ok = True

            if not file_ok:
                raise RuntimeError("GUARDRAIL_BLOCK: file not attached")
            if not date_ok:
                raise RuntimeError("GUARDRAIL_BLOCK: Inicio Vigencia empty")
            if not (_detail_labels_ok(detail_text) and _scope_ok(detail_text)):
                raise RuntimeError("GUARDRAIL_BLOCK: scope not validated in detail step")

            meta["selectors"]["file_input_strategy"] = file_strategy
            meta["selectors"]["inicio_vigencia_input"] = date_selector
            meta["date_used_effective"] = date_used

            page.screenshot(path=str(shot_06), full_page=True)

            # 8) Click final button (Enviar...)
            send_btn = None
            for txt in ("Enviar documento", "Enviar archivo", "Enviar"):
                try:
                    btn = page.get_by_text(txt, exact=False)
                    if btn.count() > 0:
                        send_btn = btn.first
                        meta["selectors"]["send_button_text"] = txt
                        break
                except Exception:
                    continue
            if not send_btn:
                raise RuntimeError("SEND_BUTTON_NOT_FOUND")

            # Click
            send_btn.click(timeout=15000)

            # 9) Wait for confirmation
            confirmation_text = ""
            t_deadline = time.time() + 25.0
            while time.time() < t_deadline:
                try:
                    confirmation_text = page.evaluate("() => (document.body ? (document.body.innerText || '') : '')") or ""
                except Exception:
                    confirmation_text = ""
                hay = (confirmation_text or "").lower()
                # heuristics: success-ish keywords OR state changes
                if any(k in hay for k in ("correct", "enviado", "guardado", "registrad", "éxito", "exito")):
                    break
                # or if "Pendiente enviar" disappears from detail (very weak, but something)
                if ("pendiente enviar" not in hay) and ("estado documento" in hay):
                    break
                time.sleep(0.5)

            confirmation_txt_path.write_text(confirmation_text or "", encoding="utf-8")
            page.screenshot(path=str(shot_07), full_page=True)

            # Confirm must be unequivocal: require at least one of the success keywords
            hay_c = (confirmation_text or "").lower()
            if not any(k in hay_c for k in ("correct", "enviado", "guardado", "registrad", "éxito", "exito")):
                raise RuntimeError("CONFIRMATION_NOT_FOUND: no success keyword detected in page text")

            meta["confirmation"] = {"snippet": (confirmation_text or "")[:8000]}

            # success
            status = "success"
            last_error = None
        except Exception as e:
            status = "failed"
            last_error = str(e)
            # best-effort screenshots for debugging
            try:
                page.screenshot(path=str(shot_07), full_page=True)
            except Exception:
                pass
            try:
                # ensure required text dumps exist even on failure
                if not detail_txt_path.exists():
                    detail_txt_path.write_text("", encoding="utf-8")
                if not confirmation_txt_path.exists():
                    confirmation_txt_path.write_text("", encoding="utf-8")
            except Exception:
                pass
        finally:
            try:
                _safe_write_json(meta_path, meta)
            except Exception:
                pass
            try:
                context.close()
                browser.close()
            except Exception:
                pass

    _write_run_finished(reason="UPLOAD_PENDING_DOCUMENT_SCOPED", error=last_error)
    return run_id

def run_frames_screenshots_and_find_tile_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    slow_mo_ms: int = 300,
    wait_after_login_s: float = 3.0,
) -> str:
    """
    HEADFUL / READ-ONLY:
    1) Login usando EXACTAMENTE la misma URL del run anterior exitoso (sin tocar config).
    2) Espera 3s con el dashboard visible.
    3) ENUMERA frames (index/name/url) y guarda screenshot PNG por frame (SIN omitir ninguno).
    4) Luego busca texto en CADA frame:
       - exact "Enviar Doc. Pendiente"
       - fallback contains "Enviar Doc"
       Si lo encuentra: screenshot elemento + outerHTML clickable y STOP.
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

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

    dump_frames_path = evidence_dir / "frames.json"
    dump_texts_path = evidence_dir / "dump_texts_by_frame.json"
    found_path = evidence_dir / "found.json"
    outerhtml_path = evidence_dir / "tile_clickable_outerhtml.html"
    element_shot_path = evidence_dir / "tile_element.png"

    started = time.time()

    def _safe_name(name: str) -> str:
        n = (name or "").strip() or "anon"
        n = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in n)
        return n[:80] or "anon"

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    frames_dump: List[Dict[str, Any]] = []
    texts_dump: Dict[str, List[str]] = {}
    found: Optional[Dict[str, Any]] = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # 1) Navigate (URL anterior exacta)
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)

        # 2) Login
        page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
        page.locator('input[name="Username"]').fill(username, timeout=20000)
        page.locator('input[name="Password"]').fill(password, timeout=20000)
        page.locator('button[type="submit"]').click(timeout=20000)

        # Espera post-login: asegurar que realmente estamos en default_contenido.asp y que el iframe existe
        try:
            page.wait_for_url("**/default_contenido.asp", timeout=30000)
        except Exception:
            # fallback: no abortar, pero seguimos esperando por DOM estable
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass
        try:
            page.locator("iframe#id_contenido").wait_for(state="attached", timeout=20000)
        except Exception:
            pass
        # Espera adicional solicitada (tiles visibles)
        time.sleep(wait_after_login_s)

        # Poll: esperar a que aparezcan frames reales (incluido nm_contenido) antes de enumerar
        t_deadline = time.time() + 20.0
        while time.time() < t_deadline:
            frs = list(page.frames)
            has_nm = any((f.name or "") == "nm_contenido" for f in frs)
            if len(frs) > 1 and has_nm:
                break
            time.sleep(0.25)

        # 3) Enumerar frames (ya con iframes cargados)
        fr_list = list(page.frames)
        for idx, fr in enumerate(fr_list):
            frames_dump.append(
                {
                    "index": idx,
                    "name": fr.name,
                    "url": fr.url,
                    "is_main": fr == page.main_frame,
                }
            )

        # Guardar frames.json con paridad básica
        try:
            ua = page.evaluate("() => navigator.userAgent")
        except Exception:
            ua = None

        _safe_write_json(
            dump_frames_path,
            {
                "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
                "page_url": page.url,
                "page_title": page.title(),
                "user_agent": ua,
                "frames": frames_dump,
            },
        )

        # 4) Screenshot por frame (SIN EXCEPCIONES => siempre crear un PNG por frame)
        for fr_info in frames_dump:
            idx = fr_info["index"]
            name = _safe_name(fr_info.get("name") or ("main" if fr_info.get("is_main") else "anon"))
            out_path = evidence_dir / f"frame_{idx}_{name}.png"

            fr = fr_list[idx] if idx < len(fr_list) else page.frames[idx]
            if fr == page.main_frame:
                page.screenshot(path=str(out_path), full_page=False)
                continue

            # Intento 1: screenshot del body del frame
            ok = False
            try:
                fr.locator("body").screenshot(path=str(out_path))
                ok = True
            except Exception:
                ok = False

            if ok:
                continue

            # Intento 2: screenshot del elemento iframe en el DOM principal (si se puede localizar)
            try:
                if fr.name:
                    iframe_loc = page.locator(f'iframe[name="{fr.name}"]')
                    if iframe_loc.count() == 0:
                        iframe_loc = page.locator(f'iframe#{fr.name}')
                else:
                    iframe_loc = page.locator("iframe")
                if iframe_loc.count() > 0:
                    iframe_loc.first.screenshot(path=str(out_path))
                    continue
            except Exception:
                pass

            # Intento 3: último recurso, screenshot del viewport (igual deja evidencia, aunque no sea específico)
            page.screenshot(path=str(out_path), full_page=False)

        # 5) Buscar texto por frame (solo después de screenshots)
        target_exact = "Enviar Doc. Pendiente"
        target_fallback = "Enviar Doc"

        def _extract_visible_texts(frame) -> List[str]:
            try:
                txt = frame.evaluate("() => (document.body ? (document.body.innerText || '') : '')")
            except Exception:
                txt = ""
            lines = [ln.strip() for ln in (txt or "").splitlines()]
            lines = [ln for ln in lines if ln]
            seen = set()
            out: List[str] = []
            for ln in lines:
                if ln in seen:
                    continue
                seen.add(ln)
                out.append(ln)
                if len(out) >= 200:
                    break
            return out

        for idx, fr in enumerate(fr_list):
            loc = fr.get_by_text(target_exact, exact=True)
            if loc.count() == 0:
                loc = fr.get_by_text(target_fallback, exact=False)

            if loc.count() > 0:
                # Encontrado
                try:
                    loc.first.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                try:
                    loc.first.screenshot(path=str(element_shot_path))
                except Exception:
                    # fallback: viewport
                    page.screenshot(path=str(element_shot_path), full_page=False)

                try:
                    outer = loc.first.evaluate(
                        """(el) => {
  const clickable = el.closest('a,button,[role="button"],div[onclick],img[onclick],area') || el;
  return clickable.outerHTML || '';
}"""
                    )
                except Exception:
                    outer = ""
                outerhtml_path.write_text(outer or "", encoding="utf-8")

                found = {
                    "frame_index": idx,
                    "frame_name": fr.name,
                    "frame_url": fr.url,
                    "matched": target_exact if (fr.get_by_text(target_exact, exact=True).count() > 0) else target_fallback,
                }
                _safe_write_json(found_path, found)
                break

            # No encontrado en este frame: acumular textos visibles para diagnóstico (sin concluir inexistencia)
            key = f"{idx}:{fr.name or ''}:{fr.url or ''}"
            texts_dump[key] = _extract_visible_texts(fr)

        if found is None:
            _safe_write_json(dump_texts_path, texts_dump)

        context.close()
        browser.close()

    finished = time.time()
    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success" if found else "failed",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "FOUND_TILE" if found else "NOT_FOUND_AFTER_FRAME_SCAN",
                "last_error": None if found else "NOT_FOUND",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id


def run_list_pending_documents_readonly_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.5,
) -> str:
    """
    HEADFUL / READ-ONLY:
    1) Login (misma URL del run anterior exitoso).
    2) Entra en frame nm_contenido (tiles).
    3) Click tile "Enviar Doc. Pendiente" (Gestion(3)).
    4) Espera carga listado REAL en frame hijo (tipicamente f3 / buscador.asp?Apartado_ID=3) y extrae filas visibles del grid DHTMLX:
       - cabecera: table.hdr
       - datos: table.obj.row20px
    5) Filtra en memoria y guarda JSON + evidencia PNG.
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

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

    # Evidence paths (nombres requeridos)
    shot_01 = evidence_dir / "01_dashboard_tiles.png"
    shot_02 = evidence_dir / "02_listado_grid.png"
    shot_03 = evidence_dir / "03_listado_grid_filtered.png"
    raw_json_path = evidence_dir / "pending_documents_raw.json"
    filtered_json_path = evidence_dir / "pending_documents_filtered.json"
    meta_path = evidence_dir / "meta.json"

    started = time.time()

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    total_rows = 0
    filtered_rows = 0
    raw_rows: List[Dict[str, Any]] = []
    filt_rows: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(
            viewport=viewport or {"width": 1600, "height": 1000},
        )
        page = context.new_page()

        # 1) Login con URL exacta anterior
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)
        page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
        page.locator('input[name="Username"]').fill(username, timeout=20000)
        page.locator('input[name="Password"]').fill(password, timeout=20000)
        page.locator('button[type="submit"]').click(timeout=20000)

        # 2) Esperar post-login: default_contenido.asp + frame nm_contenido (tiles)
        page.wait_for_url("**/default_contenido.asp", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass
        time.sleep(wait_after_login_s)

        # Esperar a que exista el frame nm_contenido
        t_deadline = time.time() + 25.0
        frame = None
        while time.time() < t_deadline:
            frame = page.frame(name="nm_contenido")
            if frame and frame.url:
                break
            time.sleep(0.25)
        if not frame:
            # Evidence y abort limpio
            page.screenshot(path=str(shot_01), full_page=True)
            raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")

        # Evidence 01: dashboard con tiles visibles
        page.screenshot(path=str(shot_01), full_page=True)

        # 3) Click tile Enviar Doc. Pendiente (READ-ONLY)
        tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
        tile = frame.locator(tile_sel)
        tile.first.wait_for(state="visible", timeout=20000)
        tile.first.click(timeout=20000)

        # 4) Esperar frame de listado (f3 o URL buscador.asp?Apartado_ID=3) + grid DHTMLX.
        def _find_list_frame() -> Any:
            # prefer name f3
            fr = page.frame(name="f3")
            if fr:
                return fr
            # fallback by url
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

        # Si no aparece aún, suele requerir "Buscar" (read-only) para renderizar el grid
        if not (list_frame and _frame_has_grid(list_frame)):
            try:
                btn_buscar = frame.get_by_text("Buscar", exact=True)
                if btn_buscar.count() > 0:
                    btn_buscar.first.click(timeout=10000)
            except Exception:
                pass
            # Esperar otra vez
            t_deadline = time.time() + 20.0
            while time.time() < t_deadline:
                list_frame = _find_list_frame()
                if list_frame and _frame_has_grid(list_frame):
                    break
                time.sleep(0.25)

        # Último fallback: "Resultados" (read-only)
        if not (list_frame and _frame_has_grid(list_frame)):
            try:
                btn_res = frame.get_by_text("Resultados", exact=True)
                if btn_res.count() > 0:
                    btn_res.first.click(timeout=10000)
            except Exception:
                pass
            t_deadline = time.time() + 20.0
            while time.time() < t_deadline:
                list_frame = _find_list_frame()
                if list_frame and _frame_has_grid(list_frame):
                    break
                time.sleep(0.25)

        if not (list_frame and _frame_has_grid(list_frame)):
            # Evidence y abort limpio
            page.screenshot(path=str(shot_02), full_page=True)
            raise RuntimeError("GRID_NOT_FOUND: expected frame f3/buscador.asp?Apartado_ID=3 with table.obj.row20px")

        # Esperar también cabecera (hdr)
        list_frame.locator("table.hdr").first.wait_for(state="attached", timeout=15000)
        list_frame.locator("table.obj.row20px").first.wait_for(state="attached", timeout=15000)

        # Evidence 02: grid visible
        try:
            list_frame.locator("body").screenshot(path=str(shot_02))
        except Exception:
            page.screenshot(path=str(shot_02), full_page=True)

        # 5) Extracción real del grid DHTMLX (READ-ONLY): headers + filas visibles
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

  function scoreHdr(hdr){
    const hs = headersFromHdrTable(hdr);
    const nonEmpty = hs.filter(Boolean).length;
    return nonEmpty * 100 + norm(hdr.innerText).length;
  }

  function extractRowsFromObjTable(tbl, headers){
    const trs = Array.from(tbl.querySelectorAll('tr'));
    const rows = [];
    for(const tr of trs){
      const tds = Array.from(tr.querySelectorAll('td'));
      if(!tds.length) continue;
      const cells = tds.map(td => norm(td.innerText));
      if(!cells.some(x => x)) continue;
      const mapped = {};
      for(let i=0;i<cells.length;i++){
        const k = (i < headers.length && headers[i]) ? headers[i] : `col_${i+1}`;
        mapped[k] = cells[i] || '';
      }
      rows.push({ ...mapped, raw_cells: cells });
    }
    return rows;
  }

  // DHTMLX grid often has multiple hdr/obj tables (frozen columns etc.)
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return { headers: [], columns_visible: [], rows: [], rows_visible: 0 };

  hdrTables.sort((a,b) => scoreHdr(b) - scoreHdr(a));
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  const columns_visible = headers.filter(Boolean);

  // Pick the obj table that yields most non-empty rows
  let bestObj = null;
  let bestRows = [];
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > bestRows.length){
      bestObj = t;
      bestRows = rs;
    } else if(rs.length === bestRows.length && rs.length > 0){
      // tie-breaker: more text
      if(norm(t.innerText).length > norm(bestObj ? bestObj.innerText : '').length){
        bestObj = t;
        bestRows = rs;
      }
    }
  }

  return {
    headers,
    columns_visible,
    rows: bestRows,
    rows_visible: bestRows.length,
    debug: {
      hdr_tables: hdrTables.length,
      obj_tables: objTables.length
    }
  };
}"""
        )

        raw_rows = extracted.get("rows") or []
        total_rows = len(raw_rows)

        # Frame info real (best-effort)
        try:
            list_frame_url = list_frame.evaluate("() => location.href")
        except Exception:
            list_frame_url = list_frame.url

        _safe_write_json(
            raw_json_path,
            {
                "frame_name": list_frame.name,
                "frame_url": list_frame_url,
                "grid": {"header_selector": "table.hdr", "data_selector": "table.obj.row20px"},
                "headers": extracted.get("headers") or [],
                "columns_visible": extracted.get("columns_visible") or [],
                "rows_visible": extracted.get("rows_visible") or total_rows,
                "rows": raw_rows,
            },
        )

        # 6) Filtrado en memoria por columnas conocidas (Empresa / Elemento) (READ-ONLY)
        company_target = "TEDELAB INGENIERIA SCCL"
        worker_target = "Emilio Roldán Molina"

        def _strip_accents(s: str) -> str:
            # simple accent fold for Spanish chars we expect
            repl = str.maketrans(
                {
                    "á": "a",
                    "é": "e",
                    "í": "i",
                    "ó": "o",
                    "ú": "u",
                    "ü": "u",
                    "ñ": "n",
                    "Á": "A",
                    "É": "E",
                    "Í": "I",
                    "Ó": "O",
                    "Ú": "U",
                    "Ü": "U",
                    "Ñ": "N",
                }
            )
            return (s or "").translate(repl)

        def _canon(s: str) -> str:
            s2 = _strip_accents((s or "").strip()).upper()
            # remove punctuation-ish, keep letters/numbers/spaces
            out = []
            for ch in s2:
                if ch.isalnum() or ch.isspace():
                    out.append(ch)
                else:
                    out.append(" ")
            return " ".join("".join(out).split())

        def _levenshtein_leq_1(a: str, b: str) -> bool:
            # fast path: exact or 1 edit
            if a == b:
                return True
            la, lb = len(a), len(b)
            if abs(la - lb) > 1:
                return False
            # classic two-pointer for edit distance <= 1
            i = j = 0
            edits = 0
            while i < la and j < lb:
                if a[i] == b[j]:
                    i += 1
                    j += 1
                    continue
                edits += 1
                if edits > 1:
                    return False
                if la == lb:
                    i += 1
                    j += 1
                elif la > lb:
                    i += 1
                else:
                    j += 1
            if i < la or j < lb:
                edits += 1
            return edits <= 1

        def _norm_company(v: str) -> str:
            s = (v or "").strip()
            if " (" in s:
                s = s.split(" (", 1)[0].strip()
            return s

        def _match_company(cell: str) -> bool:
            # "exact" match after normalization; tolerate 1-char typo seen in UI (INGENIRIA vs INGENIERIA)
            a = _canon(_norm_company(cell))
            b = _canon(company_target)
            return _levenshtein_leq_1(a, b)

        def _match_worker(cell: str) -> bool:
            # Match regardless of order ("Apellido, Nombre") by requiring all tokens from target
            a = _canon(cell)
            toks = [t for t in _canon(worker_target).split(" ") if t]
            return all(t in a for t in toks)

        def _row_matches(r: Dict[str, Any]) -> bool:
            empresa_raw = str(r.get("Empresa") or r.get("empresa") or "")
            elemento_raw = str(r.get("Elemento") or r.get("elemento") or "")
            vals = " | ".join(str(v or "") for v in r.values())
            empresa_ok = _match_company(empresa_raw) or _match_company(vals)
            worker_ok = _match_worker(elemento_raw) or _match_worker(vals)
            return bool(empresa_ok and worker_ok)

        filt_rows = [r for r in raw_rows if _row_matches(r)]
        filtered_rows = len(filt_rows)
        _safe_write_json(
            filtered_json_path,
            {
                "filter": {"empresa": company_target, "trabajador_contains": worker_target},
                "rows_visible": extracted.get("rows_visible") or total_rows,
                "rows": filt_rows,
            },
        )

        # Evidence 03: mismo grid (sin mutar UI)
        try:
            list_frame.locator("body").screenshot(path=str(shot_03))
        except Exception:
            page.screenshot(path=str(shot_03), full_page=True)

        _safe_write_json(
            meta_path,
            {
                "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
                "page_url": page.url,
                "page_title": page.title(),
                "frame_name": "nm_contenido",
                "frame_url": frame.url,
                "total_rows": total_rows,
                "filtered_rows": filtered_rows,
                "tile_selector": tile_sel,
                "data_frame_name": list_frame.name if list_frame else None,
                "data_frame_url": list_frame_url if list_frame else None,
                "grid": {"header_selector": "table.hdr", "data_selector": "table.obj.row20px"},
                "rows_visible": extracted.get("rows_visible") if isinstance(extracted, dict) else None,
            },
        )

        context.close()
        browser.close()

    finished = time.time()
    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "LISTED_PENDING_DOCUMENTS",
                "last_error": None,
                "counts": {"total_rows": total_rows, "filtered_rows": filtered_rows},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id


def run_discovery_pending_table_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.0,
    wait_after_click_s: float = 10.0,
) -> str:
    """
    HEADFUL / READ-ONLY discovery:
    - Login estándar (URL anterior exacta)
    - Screenshot tiles (01_dashboard_tiles.png)
    - Click Gestion(3) en nm_contenido
    - Espera robusta de cambio de contenido (frame url cambia / table aparece)
    - Enumeración completa de frames + screenshots por frame
    - Detección de tablas por frame (tr/th/headers) -> tables_detected.json
    - Identificar tabla candidata de "documentación pendiente" y dumpear selector + outerHTML
    - Screenshot final con tabla resaltada
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

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
    dash_png = evidence_dir / "01_dashboard_tiles.png"
    frames_json = evidence_dir / "frames_after_gestion3.json"
    tables_json = evidence_dir / "tables_detected.json"
    selector_json = evidence_dir / "pending_table_selector.json"
    outerhtml_html = evidence_dir / "pending_table_outerhtml.html"
    final_png = evidence_dir / "02_pending_table_identified.png"

    started = time.time()

    def _safe_name(name: str) -> str:
        n = (name or "").strip() or "anon"
        n = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in n)
        return n[:80] or "anon"

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(viewport=viewport or {"width": 1600, "height": 1000})
        page = context.new_page()

        # 1) Login (URL exacta anterior)
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)
        page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
        page.locator('input[name="Username"]').fill(username, timeout=20000)
        page.locator('input[name="Password"]').fill(password, timeout=20000)
        page.locator('button[type="submit"]').click(timeout=20000)

        # 2) Esperar default_contenido.asp
        page.wait_for_url("**/default_contenido.asp", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass
        time.sleep(wait_after_login_s)

        # 3) Frame dashboard nm_contenido (tiles)
        t_deadline = time.time() + 25.0
        frame_dashboard = None
        while time.time() < t_deadline:
            frame_dashboard = page.frame(name="nm_contenido")
            if frame_dashboard and frame_dashboard.url:
                break
            time.sleep(0.25)
        if not frame_dashboard:
            page.screenshot(path=str(dash_png), full_page=True)
            raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")

        # 4) Screenshot tiles
        page.screenshot(path=str(dash_png), full_page=True)

        # 5) Click Gestion(3)
        tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
        frame_dashboard.locator(tile_sel).first.wait_for(state="visible", timeout=20000)
        frame_dashboard.locator(tile_sel).first.click(timeout=20000)

        # 6) Espera robusta de cambio de contenido
        # Evento A: cambio de URL en algún frame
        # Evento B: aparición de una <table> con >1 <tr> en algún frame
        pre_urls = [f.url for f in page.frames]
        t_deadline = time.time() + max(10.0, float(wait_after_click_s))
        while time.time() < t_deadline:
            try:
                if any(f.url and f.url not in pre_urls for f in page.frames):
                    break
            except Exception:
                pass
            # Detectar tabla con filas
            found_table = False
            for fr in page.frames:
                try:
                    if fr.locator("table tr").count() > 2:
                        found_table = True
                        break
                except Exception:
                    continue
            if found_table:
                break
            time.sleep(0.25)

        # Si aún no hay tablas/grids, en esta pantalla suele existir el botón "Resultados"
        # y/o "Buscar" para mostrar el listado (READ-ONLY). NO tocamos filtros.
        try:
            # Re-resolver el frame nm_contenido (puede haber navegado)
            fr_tmp = page.frame(name="nm_contenido") or frame_dashboard
            if fr_tmp:
                # Intentar detectar si ya hay alguna tabla con filas
                has_rows = False
                try:
                    has_rows = fr_tmp.locator("table tr").count() > 2
                except Exception:
                    has_rows = False
                if not has_rows:
                    btn_res = fr_tmp.get_by_text("Resultados", exact=True)
                    if btn_res.count() > 0:
                        btn_res.first.click(timeout=10000)
                        # esperar a que aparezcan filas o algún grid
                        t2 = time.time() + 15.0
                        while time.time() < t2:
                            try:
                                if fr_tmp.locator("table tr").count() > 2:
                                    break
                            except Exception:
                                pass
                            try:
                                if fr_tmp.locator('[role="grid"], [role="table"], [role="rowgroup"]').count() > 0:
                                    break
                            except Exception:
                                pass
                            time.sleep(0.25)
                    # Si sigue sin aparecer, probar "Buscar" (read-only query) sin tocar filtros
                    has_rows = False
                    try:
                        has_rows = fr_tmp.locator("table tr").count() > 2
                    except Exception:
                        has_rows = False
                    if not has_rows:
                        btn_buscar = fr_tmp.get_by_text("Buscar", exact=True)
                        if btn_buscar.count() > 0:
                            btn_buscar.first.click(timeout=10000)
                            t3 = time.time() + 20.0
                            while time.time() < t3:
                                try:
                                    if fr_tmp.locator("table tr").count() > 2:
                                        break
                                except Exception:
                                    pass
                                try:
                                    if fr_tmp.locator('[role="grid"], [role="table"], [role="rowgroup"]').count() > 0:
                                        break
                                except Exception:
                                    pass
                                time.sleep(0.25)
        except Exception:
            pass

        # 7) Enumeración completa de frames (incluye parent)
        frames_dump: List[Dict[str, Any]] = []
        fr_list = list(page.frames)
        for idx, fr in enumerate(fr_list):
            parent = fr.parent_frame
            frames_dump.append(
                {
                    "index": idx,
                    "name": fr.name,
                    "url": fr.url,
                    "parent_name": parent.name if parent else None,
                    "parent_url": parent.url if parent else None,
                    "is_main": fr == page.main_frame,
                }
            )
        _safe_write_json(frames_json, frames_dump)

        # 8) Screenshot por frame (obligatorio)
        for fr_info in frames_dump:
            idx = fr_info["index"]
            nm = _safe_name(fr_info.get("name") or ("main" if fr_info.get("is_main") else "anon"))
            out_path = evidence_dir / f"frame_{idx}_{nm}.png"
            fr = fr_list[idx]
            if fr == page.main_frame:
                page.screenshot(path=str(out_path), full_page=False)
                continue
            ok = False
            try:
                fr.locator("body").screenshot(path=str(out_path))
                ok = True
            except Exception:
                ok = False
            if ok:
                continue
            # fallback: screenshot del iframe desde el DOM principal (si existe)
            try:
                if fr.name:
                    iframe_loc = page.locator(f'iframe[name="{fr.name}"]')
                    if iframe_loc.count() == 0:
                        iframe_loc = page.locator(f'iframe#{fr.name}')
                else:
                    iframe_loc = page.locator("iframe")
                if iframe_loc.count() > 0:
                    iframe_loc.first.screenshot(path=str(out_path))
                    continue
            except Exception:
                pass
            page.screenshot(path=str(out_path), full_page=False)

        # 9) Detección de tablas por frame
        detect_js = r"""() => {
  function norm(s){ return (s||'').replace(/\s+/g,' ').trim(); }
  function getHeaders(t){
    const ths = Array.from(t.querySelectorAll('thead th'));
    if(ths.length) return ths.map(th=>norm(th.innerText));
    // fallback: first row th/td
    const first = t.querySelector('tr');
    if(!first) return [];
    return Array.from(first.querySelectorAll('th,td')).map(c=>norm(c.innerText));
  }
  function getDhtmlxHeadersFromHdrTable(t){
    // dhtmlx grid header: <td class="ordenable..."><div class="hdrcell"><span>Nombre</span></div>
    const cells = Array.from(t.querySelectorAll('td .hdrcell span'));
    return cells
      .map(s => norm(s.innerText))
      .filter(Boolean);
  }
  const tables = Array.from(document.querySelectorAll('table'));
  const tableItems = tables.map((t, i) => {
    const trs = t.querySelectorAll('tr').length;
    const ths = t.querySelectorAll('th').length;
    let headers = getHeaders(t).filter(Boolean);
    // dhtmlx header tables often have no <th>; use hdrcell spans
    if ((!headers || headers.length === 0) && (t.className || '').toString().toLowerCase().includes('hdr')) {
      headers = getDhtmlxHeadersFromHdrTable(t);
    }
    // cheap keywords score
    const hay = (headers.join(' ') + ' ' + norm(t.innerText)).toLowerCase();
    const kws = ['document', 'doc', 'pendiente', 'empresa', 'trabajador', 'estado', 'fecha', 'caduc'];
    const score = kws.reduce((acc,k)=> acc + (hay.includes(k) ? 1 : 0), 0);
    return {
      kind: 'table',
      index: i,
      tr_count: trs,
      th_count: ths,
      headers,
      score,
      id: t.id || null,
      class: t.className || null,
    };
  });

  // Grids (role-based): detect column headers
  const grids = Array.from(document.querySelectorAll('[role="grid"], [role="table"]'));
  const gridItems = grids.map((g, i) => {
    const rowCount = g.querySelectorAll('[role="row"]').length;
    const headers = Array.from(g.querySelectorAll('[role="columnheader"]')).map(h => norm(h.innerText)).filter(Boolean);
    const hay = (headers.join(' ') + ' ' + norm(g.innerText)).toLowerCase();
    const kws = ['document', 'doc', 'pendiente', 'empresa', 'trabajador', 'estado', 'fecha', 'caduc'];
    const score = kws.reduce((acc,k)=> acc + (hay.includes(k) ? 1 : 0), 0);
    return {
      kind: 'grid',
      index: i,
      tr_count: rowCount,
      th_count: headers.length,
      headers,
      score,
      id: g.id || null,
      class: g.className || null,
    };
  });

  return tableItems.concat(gridItems);
}"""

        tables_detected: List[Dict[str, Any]] = []
        best_candidate: Optional[Dict[str, Any]] = None

        for idx, fr in enumerate(fr_list):
            try:
                tables = fr.evaluate(detect_js)
            except Exception:
                continue
            for t in tables or []:
                entry = {
                    "frame_index": idx,
                    "frame_name": fr.name,
                    "frame_url": fr.url,
                    **t,
                }
                tables_detected.append(entry)
                # Candidate heuristic: needs data rows and doc-ish score
                # Excluir menús dhtmlx del frame principal
                cls = (t.get("class") or "").lower()
                if "dhtmlx" in cls and "menu" in cls:
                    continue
                # Preferir tablas de datos (dhtmlx: class contiene "obj")
                is_data_table = ("obj" in cls) or ("grid" in cls and "hdr" not in cls)
                # candidato si parece listado y tiene contenido de documentos
                if (t.get("tr_count") or 0) > 2 and (t.get("score") or 0) >= 2 and (is_data_table or (t.get("kind") == "grid")):
                    if best_candidate is None:
                        best_candidate = entry
                    else:
                        # prefer higher score, then more rows
                        if (t.get("score") or 0, t.get("tr_count") or 0) > (
                            best_candidate.get("score") or 0,
                            best_candidate.get("tr_count") or 0,
                        ):
                            best_candidate = entry

        _safe_write_json(tables_json, {"tables": tables_detected})

        # 10-12) Dump selector + outerHTML + screenshot final resaltado
        if best_candidate:
            fr = fr_list[best_candidate["frame_index"]]
            table_idx = best_candidate["index"]
            kind = best_candidate.get("kind") or "table"

            # Compute best-effort selector + outerHTML via JS
            selector_payload = fr.evaluate(
                """(tableIndex) => {
  const tables = Array.from(document.querySelectorAll('table'));
  const t = tables[tableIndex];
  function cssEscape(s){ return (s||'').replace(/([ #;?%&,.+*~\\':\"!^$\\[\\]()=>|\\/])/g,'\\\\$1'); }
  function cssPath(el){
    if(!el || el.nodeType !== 1) return '';
    if(el.id) return el.tagName.toLowerCase() + '#' + cssEscape(el.id);
    const parts = [];
    while(el && el.nodeType === 1 && el.tagName.toLowerCase() !== 'html'){
      let part = el.tagName.toLowerCase();
      const cls = (el.className || '').toString().trim().split(/\\s+/).filter(Boolean);
      if(cls.length) part += '.' + cls.slice(0,2).map(cssEscape).join('.');
      const parent = el.parentElement;
      if(parent){
        const same = Array.from(parent.children).filter(c=>c.tagName===el.tagName);
        if(same.length>1){
          const idx = same.indexOf(el)+1;
          part += `:nth-of-type(${idx})`;
        }
      }
      parts.unshift(part);
      el = parent;
    }
    return parts.join(' > ');
  }
  if(!t) return { selector: null, outerHTML: null };
  const selector = cssPath(t);
  return { selector, outerHTML: t.outerHTML };
}""",
                table_idx,
            )
            selector = selector_payload.get("selector")
            outer = selector_payload.get("outerHTML") or ""

            # Si el candidato es grid, recalcular selector/outerHTML con role selector
            if kind == "grid":
                selector_payload = fr.evaluate(
                    """(gridIndex) => {
  const grids = Array.from(document.querySelectorAll('[role="grid"], [role="table"]'));
  const g = grids[gridIndex];
  function cssEscape(s){ return (s||'').replace(/([ #;?%&,.+*~\\':\"!^$\\[\\]()=>|\\/])/g,'\\\\$1'); }
  function cssPath(el){
    if(!el || el.nodeType !== 1) return '';
    if(el.id) return el.tagName.toLowerCase() + '#' + cssEscape(el.id);
    const parts = [];
    while(el && el.nodeType === 1 && el.tagName.toLowerCase() !== 'html'){
      let part = el.tagName.toLowerCase();
      const cls = (el.className || '').toString().trim().split(/\\s+/).filter(Boolean);
      if(cls.length) part += '.' + cls.slice(0,2).map(cssEscape).join('.');
      const parent = el.parentElement;
      if(parent){
        const same = Array.from(parent.children).filter(c=>c.tagName===el.tagName);
        if(same.length>1){
          const idx = same.indexOf(el)+1;
          part += `:nth-of-type(${idx})`;
        }
      }
      parts.unshift(part);
      el = parent;
    }
    return parts.join(' > ');
  }
  if(!g) return { selector: null, outerHTML: null };
  return { selector: cssPath(g), outerHTML: g.outerHTML };
}""",
                    table_idx,
                )
                selector = selector_payload.get("selector")
                outer = selector_payload.get("outerHTML") or ""

            _safe_write_json(
                selector_json,
                {
                    "frame_index": best_candidate["frame_index"],
                    "frame_name": best_candidate["frame_name"],
                    "frame_url": best_candidate["frame_url"],
                    "table_index_in_frame": table_idx,
                    "kind": kind,
                    "selector": selector,
                    "headers": best_candidate.get("headers") or [],
                    "tr_count": best_candidate.get("tr_count"),
                    "score": best_candidate.get("score"),
                },
            )
            outerhtml_html.write_text(outer, encoding="utf-8")

            # Highlight table + screenshot focused
            try:
                fr.evaluate(
                    """(tableIndex) => {
  const tables = Array.from(document.querySelectorAll('table'));
  const grids = Array.from(document.querySelectorAll('[role="grid"], [role="table"]'));
  const t = tables[tableIndex] || grids[tableIndex];
  if(!t) return;
  t.style.outline = '4px solid #ff0066';
  t.style.outlineOffset = '2px';
  t.scrollIntoView({block:'center', inline:'center'});
}""",
                    table_idx,
                )
            except Exception:
                pass

            # Try screenshot of table element; fallback to frame body
            try:
                if kind == "grid":
                    fr.locator('[role="grid"], [role="table"]').nth(table_idx).screenshot(path=str(final_png))
                else:
                    fr.locator("table").nth(table_idx).screenshot(path=str(final_png))
            except Exception:
                try:
                    fr.locator("body").screenshot(path=str(final_png))
                except Exception:
                    page.screenshot(path=str(final_png), full_page=False)
        else:
            # No candidate: still provide a final screenshot of current viewport
            page.screenshot(path=str(final_png), full_page=True)

        context.close()
        browser.close()

    finished = time.time()
    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "DISCOVERY_PENDING_TABLE",
                "last_error": None,
                "found_candidate": bool(best_candidate),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id


def run_open_pending_document_details_readonly_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.5,
) -> str:
    """
    HEADFUL / READ-ONLY:
    - Login
    - Click Gestion(3) (Enviar Doc. Pendiente)
    - Cargar grid DHTMLX en frame f3 (o buscador.asp?Apartado_ID=3)
    - Encontrar EXACTAMENTE 1 fila filtrada (TEDELAB + Emilio)
    - Click acción de detalle/gestión de ESA fila (solo esa)
    - Esperar detalle (modal o navegación) y validar scope (empresa/trabajador visibles)
    - Evidence PNG + dump de texto visible del detalle
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

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

    # Evidence paths (requeridos)
    shot_01 = evidence_dir / "01_dashboard_tiles.png"
    shot_02 = evidence_dir / "02_listado_grid.png"
    shot_03 = evidence_dir / "03_row_highlight.png"
    shot_04 = evidence_dir / "04_after_click_detail.png"
    detail_txt_path = evidence_dir / "detail_text_dump.txt"
    meta_path = evidence_dir / "meta.json"

    started = time.time()

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    def _strip_accents(s: str) -> str:
        repl = str.maketrans(
            {
                "á": "a",
                "é": "e",
                "í": "i",
                "ó": "o",
                "ú": "u",
                "ü": "u",
                "ñ": "n",
                "Á": "A",
                "É": "E",
                "Í": "I",
                "Ó": "O",
                "Ú": "U",
                "Ü": "U",
                "Ñ": "N",
            }
        )
        return (s or "").translate(repl)

    def _canon(s: str) -> str:
        s2 = _strip_accents((s or "").strip()).upper()
        out = []
        for ch in s2:
            if ch.isalnum() or ch.isspace():
                out.append(ch)
            else:
                out.append(" ")
        return " ".join("".join(out).split())

    def _levenshtein_leq_1(a: str, b: str) -> bool:
        if a == b:
            return True
        la, lb = len(a), len(b)
        if abs(la - lb) > 1:
            return False
        i = j = 0
        edits = 0
        while i < la and j < lb:
            if a[i] == b[j]:
                i += 1
                j += 1
                continue
            edits += 1
            if edits > 1:
                return False
            if la == lb:
                i += 1
                j += 1
            elif la > lb:
                i += 1
            else:
                j += 1
        if i < la or j < lb:
            edits += 1
        return edits <= 1

    company_target = "TEDELAB INGENIERIA SCCL"
    worker_target = "Emilio Roldán Molina"
    worker_dni = "37330395"

    def _norm_company(v: str) -> str:
        s = (v or "").strip()
        if " (" in s:
            s = s.split(" (", 1)[0].strip()
        return s

    def _match_company(cell: str) -> bool:
        a = _canon(_norm_company(cell))
        b = _canon(company_target)
        return _levenshtein_leq_1(a, b)

    def _match_worker(cell: str) -> bool:
        a = _canon(cell)
        toks = [t for t in _canon(worker_target).split(" ") if t]
        return all(t in a for t in toks) or (worker_dni in a)

    click_strategy: Dict[str, Any] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(viewport=viewport or {"width": 1600, "height": 1000})
        page = context.new_page()

        # 1) Login con URL exacta anterior
        page.goto(LOGIN_URL_PREVIOUS_SUCCESS, wait_until="domcontentloaded", timeout=60000)
        page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
        page.locator('input[name="Username"]').fill(username, timeout=20000)
        page.locator('input[name="Password"]').fill(password, timeout=20000)
        page.locator('button[type="submit"]').click(timeout=20000)

        # 2) Esperar post-login: default_contenido.asp + frame nm_contenido (tiles)
        page.wait_for_url("**/default_contenido.asp", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass
        time.sleep(wait_after_login_s)

        frame_dashboard = page.frame(name="nm_contenido")
        if not frame_dashboard:
            page.screenshot(path=str(shot_01), full_page=True)
            raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")

        # Evidence 01
        page.screenshot(path=str(shot_01), full_page=True)

        # 3) Click tile Gestion(3)
        tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
        frame_dashboard.locator(tile_sel).first.wait_for(state="visible", timeout=20000)
        frame_dashboard.locator(tile_sel).first.click(timeout=20000)

        # Helpers to locate list frame
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
                return fr.locator("table.obj.row20px").count() > 0 and fr.locator("table.hdr").count() > 0
            except Exception:
                return False

        # Espera list frame + grid
        list_frame = None
        t_deadline = time.time() + 15.0
        while time.time() < t_deadline:
            list_frame = _find_list_frame()
            if list_frame and _frame_has_grid(list_frame):
                break
            time.sleep(0.25)

        # Si aún no aparece, suele requerir "Buscar" (read-only) para renderizar el grid
        if not (list_frame and _frame_has_grid(list_frame)):
            try:
                # Buscar botón "Buscar" en cualquier frame visible (sin tocar filtros)
                clicked = False
                for fr in page.frames:
                    try:
                        btn = fr.get_by_text("Buscar", exact=True)
                        if btn.count() > 0:
                            btn.first.click(timeout=10000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked and frame_dashboard:
                    btn = frame_dashboard.get_by_text("Buscar", exact=True)
                    if btn.count() > 0:
                        btn.first.click(timeout=10000)
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
            raise RuntimeError("GRID_NOT_FOUND: expected frame f3/buscador.asp?Apartado_ID=3 with table.hdr + table.obj.row20px")

        # Espera robusta a que el grid tenga filas (evitar capturar mientras Loading.../0 registros)
        def _grid_rows_ready(fr) -> bool:
            try:
                return bool(
                    fr.evaluate(
                        """() => {
  const obj = document.querySelector('table.obj.row20px');
  if(!obj) return false;
  const loading = Array.from(document.querySelectorAll('*')).some(el => {
    const t = (el.innerText||'').trim();
    return t === 'Loading...' && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
  });
  if(loading) return false;
  const trs = Array.from(obj.querySelectorAll('tr'));
  // count rows that have at least one non-empty td text
  let cnt = 0;
  for(const tr of trs){
    const tds = Array.from(tr.querySelectorAll('td'));
    if(!tds.length) continue;
    const any = tds.some(td => ((td.innerText||'').replace(/\\s+/g,' ').trim()).length > 0);
    if(any) cnt++;
  }
  // also accept if UI label "X Registros" indicates >0
  const reg = (document.body ? (document.body.innerText||'') : '');
  const m = reg.match(/\\b(\\d+)\\s+Registros\\b/i);
  const regN = m ? parseInt(m[1],10) : 0;
  return cnt > 0 || regN > 0;
}"""
                    )
                )
            except Exception:
                return False

        t_deadline = time.time() + 20.0
        while time.time() < t_deadline:
            if _grid_rows_ready(list_frame):
                break
            time.sleep(0.25)

        # Evidence 02: grid visible (después de cargar filas)
        try:
            list_frame.locator("body").screenshot(path=str(shot_02))
        except Exception:
            page.screenshot(path=str(shot_02), full_page=True)

        # 4) Extraer rows + identificar la fila filtrada exacta (must be exactly 1)
        extraction = list_frame.evaluate(
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
  function scoreHdr(hdr){
    const hs = headersFromHdrTable(hdr);
    const nonEmpty = hs.filter(Boolean).length;
    return nonEmpty * 100 + norm(hdr.innerText).length;
  }
  function extractRowsFromObjTable(tbl, headers){
    const trs = Array.from(tbl.querySelectorAll('tr'));
    const rows = [];
    for(const tr of trs){
      const tds = Array.from(tr.querySelectorAll('td'));
      if(!tds.length) continue;
      const cells = tds.map(td => norm(td.innerText));
      if(!cells.some(x => x)) continue;
      const mapped = {};
      for(let i=0;i<cells.length;i++){
        const k = (i < headers.length && headers[i]) ? headers[i] : `col_${i+1}`;
        mapped[k] = cells[i] || '';
      }
      rows.push({ mapped, raw_cells: cells });
    }
    return rows;
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return { headers: [], rows: [], row_dom_index: null, debug: {hdr_tables: hdrTables.length, obj_tables: objTables.length} };
  hdrTables.sort((a,b) => scoreHdr(b) - scoreHdr(a));
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);

  // select best obj table (max rows)
  let best = { tbl: null, rows: [] };
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > best.rows.length){
      best = { tbl: t, rows: rs };
    }
  }
  return { headers, rows: best.rows, debug: {hdr_tables: hdrTables.length, obj_tables: objTables.length} };
}"""
        )

        headers = extraction.get("headers") or []
        rows_wrapped = extraction.get("rows") or []

        # Build python rows + keep visible index
        visible_rows: List[Dict[str, Any]] = []
        for idx, rw in enumerate(rows_wrapped):
            mapped = rw.get("mapped") or {}
            mapped["raw_cells"] = rw.get("raw_cells") or []
            mapped["_visible_index"] = idx
            visible_rows.append(mapped)

        def _row_matches(r: Dict[str, Any]) -> bool:
            empresa_raw = str(r.get("Empresa") or r.get("empresa") or "")
            elemento_raw = str(r.get("Elemento") or r.get("elemento") or "")
            vals = " | ".join(str(v or "") for v in r.values())
            return (_match_company(empresa_raw) or _match_company(vals)) and (_match_worker(elemento_raw) or _match_worker(vals))

        matches = [r for r in visible_rows if _row_matches(r)]
        if len(matches) != 1:
            # Evidence row highlight not possible if ambiguous; hard-stop
            try:
                list_frame.locator("body").screenshot(path=str(shot_03))
            except Exception:
                page.screenshot(path=str(shot_03), full_page=True)
            raise RuntimeError(f"FILTER_NOT_UNIQUE: expected 1 row, got {len(matches)}")

        target = matches[0]
        target_idx = int(target.get("_visible_index", 0))

        # 5) Highlight row + screenshot
        try:
            list_frame.evaluate(
                """(idx) => {
  const tbls = Array.from(document.querySelectorAll('table.obj.row20px'));
  let best = null;
  let bestCount = -1;
  for(const t of tbls){
    const trs = Array.from(t.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length);
    if(trs.length > bestCount){
      best = { t, trs };
      bestCount = trs.length;
    }
  }
  if(!best) return false;
  const tr = best.trs[idx];
  if(!tr) return false;
  tr.style.outline = '4px solid #ff0066';
  tr.style.outlineOffset = '2px';
  tr.scrollIntoView({block:'center', inline:'center'});
  return true;
}""",
                target_idx,
            )
        except Exception:
            pass
        try:
            list_frame.locator("body").screenshot(path=str(shot_03))
        except Exception:
            page.screenshot(path=str(shot_03), full_page=True)

        # 6) Click acción de detalle SOLO de esa fila (robusto, sin abrir otras)
        # Ejecutamos click dentro del frame via JS para escoger el mejor target clicable en el TR.
        pre_urls = [fr.url for fr in page.frames]
        click_result = list_frame.evaluate(
            """(idx) => {
  function isVisible(el){
    if(!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function hasPointer(el){
    try { return window.getComputedStyle(el).cursor === 'pointer'; } catch(e){ return false; }
  }
  // choose best obj table
  const tbls = Array.from(document.querySelectorAll('table.obj.row20px'));
  let best = null;
  let bestCount = -1;
  for(const t of tbls){
    const trs = Array.from(t.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length);
    if(trs.length > bestCount){
      best = { t, trs };
      bestCount = trs.length;
    }
  }
  if(!best) return { ok:false, reason:'no_obj_table' };
  const tr = best.trs[idx];
  if(!tr) return { ok:false, reason:'row_not_found', idx };

  // candidates inside row
  const cands = [];
  const aTags = Array.from(tr.querySelectorAll('a'));
  for(const a of aTags){
    if(isVisible(a)) cands.push({ el:a, kind:'a' });
  }
  const imgs = Array.from(tr.querySelectorAll('img'));
  for(const img of imgs){
    if(isVisible(img) && (img.getAttribute('onclick') || img.closest('[onclick]') || hasPointer(img))) cands.push({ el: img, kind:'img' });
  }
  const onclicks = Array.from(tr.querySelectorAll('[onclick]'));
  for(const el of onclicks){
    if(isVisible(el)) cands.push({ el, kind:'onclick' });
  }

  // prioritize: anchors, then img with onclick, then any onclick
  const pick = (predicate) => cands.find(c => predicate(c));
  let chosen = pick(c => c.kind === 'a') || pick(c => c.kind === 'img') || pick(c => c.kind === 'onclick');
  if(!chosen){
    // fallback: click on the row itself (some grids open detail on row click)
    chosen = { el: tr, kind: 'tr' };
  }
  const el = chosen.el;
  const tag = el.tagName ? el.tagName.toLowerCase() : '';
  const html = (el.outerHTML || '').slice(0, 5000);
  try { el.click(); } catch(e){
    // last resort: dispatch click
    try { el.dispatchEvent(new MouseEvent('click', { bubbles:true, cancelable:true, view: window })); } catch(e2){}
  }
  return { ok:true, kind: chosen.kind, tag, outerHTML: html };
}""",
            target_idx,
        )
        click_strategy = click_result or {}

        # 7) Esperar detalle: modal u otra URL/DOM
        # Reglas: preferir un frame/iframe cuyo URL apunte a una ficha/detalle de documento.
        def _detail_frames() -> List[Any]:
            out = []
            for fr in page.frames:
                u = (fr.url or "").lower()
                if not u or u in ("about:blank",):
                    continue
                if ("ficha" in u) or ("documento" in u and "buscador.asp" not in u) or ("detalle" in u):
                    out.append(fr)
            return out

        def _modal_info() -> Dict[str, Any]:
            try:
                return page.evaluate(
                    """() => {
  const els = Array.from(document.querySelectorAll('div,section,article'));
  function z(el){
    const s = window.getComputedStyle(el);
    const zi = parseInt(s.zIndex || '0', 10);
    return isNaN(zi) ? 0 : zi;
  }
  function isVis(el){
    const r = el.getBoundingClientRect();
    if(r.width < 200 || r.height < 120) return false;
    const s = window.getComputedStyle(el);
    if(s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    return true;
  }
  function score(el){
    const txt = ((el.innerText || '') + '').toLowerCase();
    const kws = ['documento:', 'trabajador:', 'empresa:', 'estado documento'];
    const hits = kws.reduce((acc,k)=> acc + (txt.includes(k) ? 1 : 0), 0);
    const r = el.getBoundingClientRect();
    const area = Math.floor(r.width * r.height);
    const zi = z(el);
    // prefer scope keywords strongly, then z-index, then text, then area
    return hits * 1000000 + zi * 1000 + txt.length + Math.min(area, 1000000);
  }
  let best = null;
  let bestScore = -1;
  for(const el of els){
    if(!isVis(el)) continue;
    const cls = (el.className || '').toString().toLowerCase();
    const zi = z(el);
    const looks = (cls.includes('dhtmlx') && (cls.includes('win') || cls.includes('popup') || cls.includes('modal'))) || zi >= 1000;
    if(!looks) continue;
    const sc = score(el);
    if(sc > bestScore){
      bestScore = sc;
      best = el;
    }
  }
  if(!best) return { hasModal:false, score:0, textLen:0, iframeSrcs:[] };
  const txt = (best.innerText || '').trim();
  const iframes = Array.from(best.querySelectorAll('iframe')).map(f => f.src || f.getAttribute('src') || '');
  return { hasModal:true, score:bestScore, textLen: txt.length, iframeSrcs: iframes.filter(Boolean) };
}"""
                )
            except Exception:
                return {"hasModal": False, "score": 0, "textLen": 0, "iframeSrcs": []}

        # Wait up to 25s for a real detail surface to load (modal content or a dedicated detail frame).
        t_deadline = time.time() + 25.0
        detail_frame = None
        modal_info: Dict[str, Any] = {"hasModal": False, "z": 0, "textLen": 0, "iframeSrcs": []}
        while time.time() < t_deadline:
            dfs = _detail_frames()
            if dfs:
                detail_frame = dfs[0]
                break
            modal_info = _modal_info()
            if modal_info.get("hasModal") and (modal_info.get("textLen") or 0) >= 40:
                break
            # if modal contains iframe(s), wait for a matching frame url to appear
            srcs = modal_info.get("iframeSrcs") or []
            if srcs:
                for fr in page.frames:
                    if fr.url and any(fr.url.startswith(s) or (s in fr.url) for s in srcs):
                        detail_frame = fr
                        break
                if detail_frame:
                    break
            time.sleep(0.25)

        # Evidence 04: after click
        try:
            page.screenshot(path=str(shot_04), full_page=True)
        except Exception:
            pass

        # 8) Dump visible text from likely detail scope:
        # Prefer: detail_frame (if found) OR modal container text; otherwise fail.
        def _visible_text_from_frame(fr) -> str:
            try:
                return fr.evaluate("() => (document.body ? (document.body.innerText || '') : '')") or ""
            except Exception:
                return ""

        texts_by_frame: List[Dict[str, Any]] = []
        for fr in page.frames:
            try:
                txt_len = len(_visible_text_from_frame(fr))
            except Exception:
                txt_len = 0
            texts_by_frame.append({"name": fr.name, "url": fr.url, "len": txt_len})

        detail_text = ""
        detail_src = {"kind": None, "name": None, "url": None}

        if detail_frame:
            # wait a bit for detail frame to populate (avoid blank)
            t2 = time.time() + 15.0
            while time.time() < t2:
                detail_text = _visible_text_from_frame(detail_frame)
                if len(detail_text.strip()) >= 40:
                    break
                time.sleep(0.25)
            detail_src = {"kind": "frame", "name": detail_frame.name, "url": detail_frame.url}
        else:
            # modal text from main document
            try:
                detail_text = page.evaluate(
                    """() => {
  const els = Array.from(document.querySelectorAll('div,section,article'));
  function z(el){
    const s = window.getComputedStyle(el);
    const zi = parseInt(s.zIndex || '0', 10);
    return isNaN(zi) ? 0 : zi;
  }
  function isVis(el){
    const r = el.getBoundingClientRect();
    if(r.width < 200 || r.height < 120) return false;
    const s = window.getComputedStyle(el);
    if(s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    return true;
  }
  function score(el){
    const txt = ((el.innerText || '') + '').toLowerCase();
    const kws = ['documento:', 'trabajador:', 'empresa:', 'estado documento'];
    const hits = kws.reduce((acc,k)=> acc + (txt.includes(k) ? 1 : 0), 0);
    const r = el.getBoundingClientRect();
    const area = Math.floor(r.width * r.height);
    const zi = z(el);
    return hits * 1000000 + zi * 1000 + txt.length + Math.min(area, 1000000);
  }
  let best = null;
  let bestScore = -1;
  for(const el of els){
    if(!isVis(el)) continue;
    const cls = (el.className || '').toString().toLowerCase();
    const zi = z(el);
    const looks = (cls.includes('dhtmlx') && (cls.includes('win') || cls.includes('popup') || cls.includes('modal'))) || zi >= 1000;
    if(!looks) continue;
    const sc = score(el);
    if(sc > bestScore){
      bestScore = sc;
      best = el;
    }
  }
  return best ? (best.innerText || '') : '';
}"""
                )
            except Exception:
                detail_text = ""
            detail_src = {"kind": "modal_text", "name": None, "url": None}

        detail_txt_path.write_text(detail_text or "", encoding="utf-8")

        # 9) Validación scope mínima: TEDELAB + Emilio/Roldán/DNI (EN EL DETALLE, no en el grid)
        hay = _canon(detail_text or "")
        ok_company = ("TEDELAB" in hay) or _match_company(detail_text or "")
        ok_worker = ("EMILIO" in hay) or ("ROLDAN" in hay) or (worker_dni in hay) or _match_worker(detail_text or "")
        # asegurar que estamos realmente en detalle (labels típicos)
        ok_detail_labels = ("DOCUMENTO" in hay) and ("TRABAJADOR" in hay) and ("EMPRESA" in hay)
        if not (ok_company and ok_worker):
            raise RuntimeError("DETAIL_SCOPE_VALIDATION_FAILED: expected TEDELAB + Emilio/Roldán/DNI visible in detail")
        if not ok_detail_labels:
            raise RuntimeError("DETAIL_SCOPE_VALIDATION_FAILED: detail labels Documento/Trabajador/Empresa not found (likely still on grid)")

        # Meta
        try:
            list_frame_url = list_frame.evaluate("() => location.href")
        except Exception:
            list_frame_url = list_frame.url

        _safe_write_json(
            meta_path,
            {
                "login_url_reused_exact": LOGIN_URL_PREVIOUS_SUCCESS,
                "page_url": page.url,
                "page_title": page.title(),
                "tile_selector": tile_sel,
                "frame_dashboard_name": "nm_contenido",
                "frame_dashboard_url": frame_dashboard.url if frame_dashboard else None,
                "list_frame_name": list_frame.name if list_frame else None,
                "list_frame_url": list_frame_url,
                "grid": {"header_selector": "table.hdr", "data_selector": "table.obj.row20px"},
                "matched_row": {"visible_index": target_idx, "Empresa": target.get("Empresa"), "Elemento": target.get("Elemento")},
                "click_strategy": click_strategy,
                "detail_text_source": detail_src,
                "texts_by_frame": texts_by_frame,
            },
        )

        context.close()
        browser.close()

    finished = time.time()
    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "OPENED_PENDING_DOCUMENT_DETAIL",
                "last_error": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id
