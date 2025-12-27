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
from backend.adapters.egestiona.submission_plan_headful import (
    run_build_submission_plan_readonly_headful,
)
from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS, _safe_write_json


def _norm_company(v: str) -> str:
    """Normaliza nombre de empresa (quita código entre paréntesis)."""
    s = (v or "").strip()
    if " (" in s:
        s = s.split(" (", 1)[0].strip()
    return s


def _row_matches_target(row: Dict[str, Any], company_key: str, person_key: Optional[str]) -> bool:
    """Verifica si una fila del grid coincide con el target."""
    empresa_raw = str(row.get("Empresa") or row.get("empresa") or "")
    elemento_raw = str(row.get("Elemento") or row.get("elemento") or "")
    empresa_norm = _norm_company(empresa_raw)
    empresa_match = company_key.lower() in empresa_norm.lower() if company_key else True
    elemento_match = person_key.lower() in elemento_raw.lower() if person_key else True
    return empresa_match and elemento_match


def _find_exact_row(
    list_frame: Any,
    company_key: str,
    person_key: Optional[str],
    expected_tipo_doc: Optional[str] = None,
) -> Optional[int]:
    """
    Encuentra el índice exacto de la fila que coincide con el target.
    Retorna el índice (0-based) o None si no se encuentra.
    """
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
    
    rows = extracted.get("rows") or []
    for idx, row in enumerate(rows):
        if _row_matches_target(row, company_key, person_key):
            if expected_tipo_doc:
                tipo_doc = str(row.get("Tipo Documento") or row.get("tipo_doc") or "")
                if expected_tipo_doc.lower() not in tipo_doc.lower():
                    continue
            return idx
    return None


def _fill_date_field(detail_frame: Any, label_text: str, date_value: str) -> bool:
    """
    Rellena un campo de fecha en el modal de detalle.
    Busca el label y luego el input asociado.
    Retorna True si se rellenó correctamente, False si no se encontró.
    """
    try:
        # Buscar label
        label = detail_frame.get_by_text(label_text, exact=False)
        if label.count() == 0:
            return False
        
        # Buscar input asociado (puede estar en diferentes estructuras)
        # Intentar varios selectores comunes
        selectors = [
            'input[type="text"]',
            'input[type="date"]',
            'input[name*="Fecha"]',
            'input[name*="fecha"]',
        ]
        
        label_elem = label.first
        # Buscar el input más cercano al label
        for selector in selectors:
            inputs = detail_frame.locator(selector)
            if inputs.count() > 0:
                # Intentar encontrar el input que está cerca del label
                # (simplificado: tomar el primero visible)
                for i in range(inputs.count()):
                    inp = inputs.nth(i)
                    if inp.is_visible():
                        inp.fill(date_value, timeout=5000)
                        return True
        
        return False
    except Exception:
        return False


def _execute_single_item(
    page: Any,
    frame: Any,
    list_frame: Any,
    plan_item: Dict[str, Any],
    company_key: str,
    person_key: Optional[str],
    evidence_dir: Path,
    item_index: int,
) -> Dict[str, Any]:
    """
    Ejecuta el envío de un solo item del plan.
    Retorna: {"status": "sent" | "skipped" | "failed", "reasons": [...]}
    """
    result = {
        "status": "skipped",
        "reasons": [],
        "item_index": item_index
    }
    
    pending_ref = plan_item.get("pending_ref", {})
    matched_doc = plan_item.get("matched_doc")
    proposed_fields = plan_item.get("proposed_fields", {})
    decision = plan_item.get("decision", {})
    
    # Validar que tiene match
    if not matched_doc:
        result["reasons"].append("No matched document in plan item")
        return result
    
    doc_id = matched_doc.get("doc_id")
    if not doc_id:
        result["status"] = "failed"
        result["reasons"].append("Missing doc_id in matched_doc")
        return result
    
    # Validar que el PDF existe
    pdf_path = Path("data") / "repository" / "docs" / f"{doc_id}.pdf"
    if not pdf_path.exists():
        result["status"] = "failed"
        result["reasons"].append(f"PDF not found: {pdf_path}")
        return result
    
    # Localizar fila exacta
    expected_tipo_doc = pending_ref.get("tipo_doc")
    row_idx = _find_exact_row(list_frame, company_key, person_key, expected_tipo_doc)
    
    if row_idx is None:
        result["status"] = "failed"
        result["reasons"].append("Could not locate exact row in grid")
        return result
    
    # Screenshot: fila localizada
    shot_03 = evidence_dir / f"03_row_item_{item_index}.png"
    try:
        list_frame.locator("body").screenshot(path=str(shot_03))
    except Exception:
        page.screenshot(path=str(shot_03), full_page=True)
    
    # Click en la fila para abrir detalle
    try:
        rows = list_frame.locator("table.obj.row20px tbody tr")
        if rows.count() <= row_idx:
            result["status"] = "failed"
            result["reasons"].append(f"Row index {row_idx} out of bounds")
            return result
        
        rows.nth(row_idx).click(timeout=10000)
        time.sleep(1.0)  # Esperar a que se abra el modal
    except Exception as e:
        result["status"] = "failed"
        result["reasons"].append(f"Failed to click row: {e}")
        return result
    
    # Identificar frame de detalle (puede ser modal o frame)
    detail_frame = None
    t_deadline = time.time() + 10.0
    while time.time() < t_deadline:
        # Intentar frame f3 (donde suele estar el detalle)
        detail_frame = page.frame(name="f3")
        if detail_frame:
            # Verificar que tiene contenido de detalle
            try:
                if detail_frame.locator("input[type='file']").count() > 0:
                    break
            except Exception:
                pass
        # También puede ser el frame principal si es modal
        try:
            if page.locator("input[type='file']").count() > 0:
                detail_frame = page
                break
        except Exception:
            pass
        time.sleep(0.25)
    
    if not detail_frame:
        result["status"] = "failed"
        result["reasons"].append("Could not locate detail frame/modal")
        return result
    
    # Screenshot: detalle abierto
    shot_04 = evidence_dir / f"04_detail_item_{item_index}.png"
    try:
        if detail_frame == page:
            page.screenshot(path=str(shot_04), full_page=True)
        else:
            detail_frame.locator("body").screenshot(path=str(shot_04))
    except Exception:
        page.screenshot(path=str(shot_04), full_page=True)
    
    # Revalidar scope en detalle (simplificado: verificar que aparece empresa/trabajador)
    # TODO: implementar validación más robusta si es necesario
    
    # Seleccionar archivo
    try:
        file_input = detail_frame.locator("input[type='file']").first
        file_input.set_input_files(str(pdf_path), timeout=10000)
        time.sleep(0.5)
    except Exception as e:
        result["status"] = "failed"
        result["reasons"].append(f"Failed to select file: {e}")
        return result
    
    # Rellenar fechas desde proposed_fields
    fecha_inicio = proposed_fields.get("fecha_inicio_vigencia")
    fecha_fin = proposed_fields.get("fecha_fin_vigencia")
    
    if fecha_inicio:
        filled = _fill_date_field(detail_frame, "Inicio Vigencia", fecha_inicio)
        if not filled:
            result["reasons"].append(f"Could not fill 'Inicio Vigencia' field (value: {fecha_inicio})")
        else:
            result["reasons"].append(f"Filled 'Inicio Vigencia' with {fecha_inicio}")
    
    if fecha_fin:
        filled = _fill_date_field(detail_frame, "Fin Vigencia", fecha_fin)
        if not filled:
            # No es hard stop si no se encuentra
            result["reasons"].append(f"Could not fill 'Fin Vigencia' field (value: {fecha_fin}) - continuing")
        else:
            result["reasons"].append(f"Filled 'Fin Vigencia' with {fecha_fin}")
    
    # Screenshot: formulario rellenado
    shot_05 = evidence_dir / f"05_filled_item_{item_index}.png"
    try:
        if detail_frame == page:
            page.screenshot(path=str(shot_05), full_page=True)
        else:
            detail_frame.locator("body").screenshot(path=str(shot_05))
    except Exception:
        page.screenshot(path=str(shot_05), full_page=True)
    
    # Click "Enviar documento"
    try:
        # Buscar botón de envío (varios posibles textos)
        send_texts = ["Enviar documento", "Enviar", "Enviar Documento"]
        send_button = None
        for text in send_texts:
            btn = detail_frame.get_by_text(text, exact=False)
            if btn.count() > 0:
                send_button = btn.first
                break
        
        if not send_button:
            result["status"] = "failed"
            result["reasons"].append("Could not find 'Enviar documento' button")
            return result
        
        send_button.click(timeout=10000)
        time.sleep(2.0)  # Esperar confirmación
    except Exception as e:
        result["status"] = "failed"
        result["reasons"].append(f"Failed to click send button: {e}")
        return result
    
    # Esperar confirmación inequívoca
    confirmation_text = None
    confirmation_patterns = [
        "Operación realizada correctamente",
        "operación realizada correctamente",
        "Documento enviado",
        "documento enviado",
        "correctamente",
    ]
    
    t_deadline = time.time() + 10.0
    while time.time() < t_deadline:
        try:
            page_text = page.locator("body").inner_text()
            for pattern in confirmation_patterns:
                if pattern.lower() in page_text.lower():
                    confirmation_text = pattern
                    break
            if confirmation_text:
                break
        except Exception:
            pass
        time.sleep(0.5)
    
    # Screenshot: confirmación
    shot_06 = evidence_dir / f"06_confirmation_item_{item_index}.png"
    try:
        page.screenshot(path=str(shot_06), full_page=True)
    except Exception:
        pass
    
    if confirmation_text:
        result["status"] = "sent"
        result["reasons"].append(f"Confirmation received: '{confirmation_text}'")
    else:
        result["status"] = "failed"
        result["reasons"].append("No confirmation message found after send")
    
    return result


def run_execute_submission_plan_scoped_headful(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    company_key: str,
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    dry_run: bool = True,
    confirm_execute: bool = False,
    slow_mo_ms: int = 300,
    viewport: Optional[Dict[str, int]] = None,
    wait_after_login_s: float = 2.5,
) -> str:
    """
    HEADFUL / WRITE (con guardrails):
    1) Construye submission plan (reutiliza lógica existente).
    2) Si dry_run=true: solo genera plan, NO ejecuta.
    3) Si dry_run=false pero confirm_execute=false: hard stop.
    4) Si dry_run=false y confirm_execute=true: ejecuta items con AUTO_SUBMIT_OK.
    5) Genera evidence completa.
    """
    # Política de seguridad
    if dry_run:
        # Solo generar plan, no ejecutar
        return run_build_submission_plan_readonly_headful(
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
    
    if not confirm_execute:
        raise RuntimeError(
            "SECURITY_HARD_STOP: dry_run=false but confirm_execute=false. "
            "Set confirm_execute=true to allow execution."
        )
    
    # Construir plan primero
    plan_run_id = run_build_submission_plan_readonly_headful(
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
    
    # Cargar plan
    plan_path = Path(base_dir) / "runs" / plan_run_id / "evidence" / "submission_plan.json"
    if not plan_path.exists():
        raise RuntimeError(f"Plan not found: {plan_path}")
    
    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    submission_plan = plan_data.get("plan", [])
    
    # Validar plan
    if not submission_plan:
        # Si hay 0 pendientes, salir OK sin hacer nada
        execution_results = {
            "results": [],
            "summary": {
                "total_items": 0,
                "sent": 0,
                "skipped": 0,
                "failed": 0
            }
        }
        execution_path = Path(base_dir) / "runs" / plan_run_id / "evidence" / "execution_results.json"
        _safe_write_json(execution_path, execution_results)
        return plan_run_id
    
    # Filtrar items AUTO_SUBMIT_OK
    auto_submit_items = [
        item for item in submission_plan
        if item.get("decision", {}).get("action") == "AUTO_SUBMIT_OK"
    ]
    
    if not auto_submit_items:
        execution_results = {
            "results": [],
            "summary": {
                "total_items": len(submission_plan),
                "sent": 0,
                "skipped": len(submission_plan),
                "failed": 0
            }
        }
        execution_path = Path(base_dir) / "runs" / plan_run_id / "evidence" / "execution_results.json"
        _safe_write_json(execution_path, execution_results)
        return plan_run_id
    
    # Validar guardrails adicionales
    for item in auto_submit_items:
        decision = item.get("decision", {})
        blocking_issues = decision.get("blocking_issues", [])
        if blocking_issues:
            raise RuntimeError(
                f"GUARDRAIL_VIOLATION: Item has blocking_issues: {blocking_issues}"
            )
    
    # Ejecutar items
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
    
    evidence_dir = Path(base_dir) / "runs" / plan_run_id / "evidence"
    execution_results: List[Dict[str, Any]] = []
    confirmation_texts: List[str] = []
    
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        context = browser.new_context(
            viewport=viewport or {"width": 1600, "height": 1000},
        )
        page = context.new_page()
        
        # Login
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
            raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")
        
        # Click tile Enviar Doc. Pendiente
        tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
        tile = frame.locator(tile_sel)
        tile.first.wait_for(state="visible", timeout=20000)
        tile.first.click(timeout=20000)
        
        # Esperar grid
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
            raise RuntimeError("GRID_NOT_FOUND")
        
        list_frame.locator("table.hdr").first.wait_for(state="attached", timeout=15000)
        list_frame.locator("table.obj.row20px").first.wait_for(state="attached", timeout=15000)
        
        # Ejecutar cada item
        for idx, item in enumerate(auto_submit_items):
            result = _execute_single_item(
                page, frame, list_frame, item, company_key, person_key, evidence_dir, idx
            )
            execution_results.append(result)
            if result.get("status") == "sent":
                # Extraer texto de confirmación si está disponible
                try:
                    page_text = page.locator("body").inner_text()
                    confirmation_texts.append(page_text[:500])  # Primeros 500 chars
                except Exception:
                    pass
        
        context.close()
        browser.close()
    
    # Guardar execution_results
    execution_path = evidence_dir / "execution_results.json"
    summary = {
        "total_items": len(submission_plan),
        "auto_submit_ok_items": len(auto_submit_items),
        "sent": sum(1 for r in execution_results if r.get("status") == "sent"),
        "skipped": sum(1 for r in execution_results if r.get("status") == "skipped"),
        "failed": sum(1 for r in execution_results if r.get("status") == "failed"),
    }
    _safe_write_json(execution_path, {
        "results": execution_results,
        "summary": summary
    })
    
    # Guardar confirmación
    if confirmation_texts:
        confirmation_path = evidence_dir / "confirmation_text_dump.txt"
        confirmation_path.write_text("\n---\n".join(confirmation_texts), encoding="utf-8")
    
    return plan_run_id

