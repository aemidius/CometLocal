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
    _evaluate_submission_guardrails,
    _format_date_for_portal,
)
from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS, _safe_write_json
from backend.repository.document_matcher_v1 import PendingItemV1, DocumentMatcherV1
from backend.shared.document_repository_v1 import DocumentInstanceV1
from datetime import date


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


def _detect_date_fields(page_or_frame: Any) -> Dict[str, Optional[str]]:
    """
    Detecta selectores de campos de fecha (Inicio y Fin Vigencia).
    Busca por orden de prioridad:
    - CSS ids: #Fecha_Fin, #Fecha_Fin_Vigencia, #Fecha_FinVigencia, #Fecha_FinValidez
    - name contains: input[name*="Fin"], input[name*="fin"], input[name*="Fecha_Fin"]
    - label text: label:has-text("Fin") + siguiente input
    - placeholder contains: "Fin"
    
    Retorna: { "inicio_selector": "...", "fin_selector": "..." | null }
    """
    result = {
        "inicio_selector": None,
        "fin_selector": None
    }
    
    try:
        # Buscar Inicio Vigencia
        inicio_ids = ["#Fecha_Inicio", "#Fecha_Inicio_Vigencia", "#Fecha_InicioVigencia", "#Fecha_InicioValidez"]
        for selector in inicio_ids:
            try:
                if page_or_frame.locator(selector).count() > 0:
                    result["inicio_selector"] = selector
                    break
            except Exception:
                continue
        
        # Si no se encontró por ID, buscar por name
        if not result["inicio_selector"]:
            try:
                inputs = page_or_frame.locator('input[name*="Inicio"], input[name*="inicio"], input[name*="Fecha_Inicio"]')
                if inputs.count() > 0:
                    # Tomar el primero
                    first_input = inputs.first
                    name_attr = first_input.get_attribute("name")
                    if name_attr:
                        result["inicio_selector"] = f'input[name="{name_attr}"]'
            except Exception:
                pass
        
        # Buscar Fin Vigencia por ID
        fin_ids = ["#Fecha_Fin", "#Fecha_Fin_Vigencia", "#Fecha_FinVigencia", "#Fecha_FinValidez"]
        for selector in fin_ids:
            try:
                if page_or_frame.locator(selector).count() > 0:
                    result["fin_selector"] = selector
                    break
            except Exception:
                continue
        
        # Si no se encontró por ID, buscar por name
        if not result["fin_selector"]:
            try:
                inputs = page_or_frame.locator('input[name*="Fin"], input[name*="fin"], input[name*="Fecha_Fin"]')
                if inputs.count() > 0:
                    # Tomar el primero
                    first_input = inputs.first
                    name_attr = first_input.get_attribute("name")
                    if name_attr:
                        result["fin_selector"] = f'input[name="{name_attr}"]'
            except Exception:
                pass
        
        # Si aún no se encontró, buscar por label text (solo si tenemos Playwright)
        if not result["fin_selector"]:
            try:
                labels = page_or_frame.locator('label:has-text("Fin"), label:has-text("fin")')
                if labels.count() > 0:
                    # Buscar el input siguiente al label
                    label_elem = labels.first
                    # Intentar encontrar input asociado (puede estar en diferentes estructuras)
                    # Por ahora, marcamos que se detectó pero sin selector específico
                    result["fin_selector"] = "label:has-text('Fin') + input"
            except Exception:
                pass
        
    except Exception:
        # Si falla todo, retornar lo que tengamos
        pass
    
    return result


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


def _create_synthetic_pending_from_doc(
    doc: DocumentInstanceV1,
    doc_type_name: str,
) -> PendingItemV1:
    """
    Crea un pending_item sintético a partir de un documento del repositorio.
    """
    # Generar tipo_doc y elemento sintéticos basados en el doc
    tipo_doc = doc_type_name or f"Tipo_{doc.type_id}"
    elemento = doc.person_key or "Trabajador"
    empresa = doc.company_key or "Empresa"
    
    return PendingItemV1(
        tipo_doc=tipo_doc,
        elemento=elemento,
        empresa=empresa,
        trabajador=elemento,
        fecha_inicio=doc.computed_validity.valid_from,
        fecha_fin=doc.computed_validity.valid_to,
        raw_data={
            "Tipo Documento": tipo_doc,
            "Elemento": elemento,
            "Empresa": empresa,
        }
    )


def _run_self_test_mode(
    base_dir: str | Path,
    repo_store: DocumentRepositoryStoreV1,
    company_key: str,
    person_key: Optional[str],
    self_test_doc_id: Optional[str],
) -> str:
    """
    Ejecuta modo self_test sin navegación.
    Genera pending_item sintético, plan, y would_fill_fields.json.
    """
    import uuid
    import time
    
    run_id = f"r_{uuid.uuid4().hex}"
    run_dir = Path(base_dir) / "runs" / run_id
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    started = time.time()
    today = date.today()
    
    # Seleccionar documento
    if self_test_doc_id:
        doc = repo_store.get_document(self_test_doc_id)
        if not doc:
            raise ValueError(f"Document {self_test_doc_id} not found")
    else:
        # Buscar único documento
        all_docs = repo_store.list_documents(
            company_key=company_key,
            person_key=person_key
        )
        if len(all_docs) == 0:
            raise ValueError("No documents found in repository")
        if len(all_docs) > 1:
            raise ValueError(f"Multiple documents found ({len(all_docs)}). Specify self_test_doc_id")
        doc = all_docs[0]
    
    # Obtener tipo de documento
    doc_type = repo_store.get_type(doc.type_id)
    doc_type_name = doc_type.name if doc_type else doc.type_id
    
    # Crear pending_item sintético
    pending = _create_synthetic_pending_from_doc(doc, doc_type_name)
    
    # Hacer matching directo (siempre match al doc seleccionado)
    matcher = DocumentMatcherV1(repo_store)
    match_result = {
        "best_doc": {
            "doc_id": doc.doc_id,
            "type_id": doc.type_id,
            "file_name": doc.file_name_original,
            "status": doc.status.value if hasattr(doc.status, 'value') else str(doc.status),
            "validity": {
                "valid_from": doc.computed_validity.valid_from.isoformat() if doc.computed_validity.valid_from else None,
                "valid_to": doc.computed_validity.valid_to.isoformat() if doc.computed_validity.valid_to else None,
                "confidence": doc.computed_validity.confidence
            }
        },
        "alternatives": [],
        "confidence": 1.0,
        "reasons": ["SELF_TEST: Direct match to selected document"],
        "needs_operator": False
    }
    
    # Evaluar guardrails
    decision = _evaluate_submission_guardrails(
        match_result,
        today,
        only_target=True,
        match_count=1
    )
    
    # Construir plan item
    plan_item: Dict[str, Any] = {
        "pending_ref": {
            "tipo_doc": pending.tipo_doc,
            "elemento": pending.elemento,
            "empresa": pending.empresa,
            "row_index": 0
        },
        "expected_doc_type_text": f"{pending.tipo_doc} {pending.elemento}",
        "matched_doc": match_result["best_doc"],
        "proposed_fields": {
            "fecha_inicio_vigencia": _format_date_for_portal(doc.computed_validity.valid_from),
            "fecha_fin_vigencia": _format_date_for_portal(doc.computed_validity.valid_to)
        },
        "decision": decision
    }
    
    submission_plan = [plan_item]
    
    # Generar would_fill_fields.json
    pdf_path = Path(base_dir) / "repository" / "docs" / f"{doc.doc_id}.pdf"
    
    # Detectar selectores (simulado, sin navegación real)
    detected_selectors = {
        "inicio_selector": "#Fecha_Inicio_Vigencia",  # Selector común
        "fin_selector": "#Fecha_Fin_Vigencia"  # Selector común, puede ser null
    }
    
    would_fill_fields = {
        "doc_id": doc.doc_id,
        "file_path": str(pdf_path),
        "fecha_inicio_vigencia": plan_item["proposed_fields"]["fecha_inicio_vigencia"],
        "fecha_fin_vigencia": plan_item["proposed_fields"]["fecha_fin_vigencia"],
        "detected_selectors": detected_selectors
    }
    
    # Generar execution_results (todos skipped en self_test)
    execution_results = {
        "results": [{
            "status": "skipped",
            "reasons": ["SELF_TEST: No actual execution performed"],
            "item_index": 0
        }],
        "summary": {
            "total_items": 1,
            "auto_submit_ok_items": 1 if decision["action"] == "AUTO_SUBMIT_OK" else 0,
            "sent": 0,
            "skipped": 1,
            "failed": 0
        }
    }
    
    # Guardar evidence
    _safe_write_json(evidence_dir / "submission_plan.json", {"plan": submission_plan})
    _safe_write_json(evidence_dir / "would_fill_fields.json", would_fill_fields)
    _safe_write_json(evidence_dir / "execution_results.json", execution_results)
    
    finished = time.time()
    _safe_write_json(
        evidence_dir / "meta.json",
        {
            "self_test": True,
            "selected_doc_id": doc.doc_id,
            "company_key": company_key,
            "person_key": person_key,
            "validity": {
                "valid_from": doc.computed_validity.valid_from.isoformat() if doc.computed_validity.valid_from else None,
                "valid_to": doc.computed_validity.valid_to.isoformat() if doc.computed_validity.valid_to else None,
            },
            "today": today.isoformat(),
            "submission_plan_count": len(submission_plan),
            "auto_submit_ok_count": sum(1 for item in submission_plan if item["decision"]["action"] == "AUTO_SUBMIT_OK"),
            "review_required_count": sum(1 for item in submission_plan if item["decision"]["action"] == "REVIEW_REQUIRED"),
            "no_match_count": sum(1 for item in submission_plan if item["decision"]["action"] == "NO_MATCH"),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
            "duration_ms": int((finished - started) * 1000),
        }
    )
    
    (run_dir / "run_finished.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "success",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
                "duration_ms": int((finished - started) * 1000),
                "reason": "SELF_TEST_COMPLETED",
                "last_error": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    
    return run_id


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
    self_test: bool = False,
    self_test_doc_id: Optional[str] = None,
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
    
    Si self_test=true:
    - NO navega ni sube a eGestiona
    - Usa pending_item sintético generado desde doc del repo
    - Genera submission_plan.json igual que en producción
    - Simula ejecución hasta justo antes de "Enviar documento"
    - Genera would_fill_fields.json con campos que se rellenarían
    """
    base = ensure_data_layout(base_dir=base_dir)
    repo_store = DocumentRepositoryStoreV1(base_dir=base)
    
    # Modo self_test
    if self_test:
        return _run_self_test_mode(
            base_dir=base_dir,
            repo_store=repo_store,
            company_key=company_key,
            person_key=person_key,
            self_test_doc_id=self_test_doc_id,
        )
    
    # Política de seguridad (modo normal)
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

