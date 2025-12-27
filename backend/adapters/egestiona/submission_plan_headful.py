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
from backend.shared.document_repository_v1 import DocumentStatusV1
from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS, _safe_write_json
from backend.adapters.egestiona.match_pending_headful import (
    _parse_date_from_cell,
    run_match_pending_documents_readonly_headful,
)


def _format_date_for_portal(d: Optional[date]) -> Optional[str]:
    """Formatea fecha como DD/MM/YYYY para el portal."""
    if not d:
        return None
    return d.strftime("%d/%m/%Y")


def _evaluate_submission_guardrails(
    match_result: Dict[str, Any],
    today: date,
    only_target: bool,
    match_count: int,
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
    validity = best_doc.get("validity", {})
    valid_from = validity.get("valid_from")
    valid_to = validity.get("valid_to")
    
    # Parsear fechas si son strings
    if isinstance(valid_from, str):
        try:
            valid_from = datetime.strptime(valid_from, "%Y-%m-%d").date()
        except ValueError:
            valid_from = None
    if isinstance(valid_to, str):
        try:
            valid_to = datetime.strptime(valid_to, "%Y-%m-%d").date()
        except ValueError:
            valid_to = None
    
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
    
    # Regla 3: Si today NOT in [valid_from, valid_to + grace_days] -> REVIEW_REQUIRED
    # Nota: grace_days se obtiene del tipo, pero por ahora usamos 0
    grace_days = 0  # TODO: obtener del tipo si es necesario
    if valid_from and valid_to:
        valid_until = valid_to
        # Añadir grace_days si es necesario
        from datetime import timedelta
        if grace_days > 0:
            valid_until = valid_to + timedelta(days=grace_days)
        
        if today < valid_from:
            decision["blocking_issues"].append(f"today ({today}) < valid_from ({valid_from})")
            decision["reasons"].append(f"Validity period starts in the future ({valid_from})")
            return decision
        elif today > valid_until:
            decision["blocking_issues"].append(f"today ({today}) > valid_to+grace ({valid_until})")
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
) -> str:
    """
    HEADFUL / READ-ONLY:
    1) Login y obtiene listado de pendientes (reutiliza lógica de matching).
    2) Para cada pendiente, hace matching con repo.
    3) Evalúa guardrails y genera plan de envío.
    4) Genera evidence: pending_items.json, match_results.json, submission_plan.json, meta.json.
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
    submission_plan_path = evidence_dir / "submission_plan.json"
    meta_path = evidence_dir / "meta.json"

    started = time.time()
    today = date.today()

    # Reutilizar lógica de extracción de pendientes
    # (copiamos el código de match_pending_headful pero añadimos evaluación de guardrails)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright sync_api not available") from e

    pending_items: List[Dict[str, Any]] = []
    match_results: List[Dict[str, Any]] = []
    submission_plan: List[Dict[str, Any]] = []

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
            empresa_norm = _norm_company(empresa_raw)
            empresa_match = company_key.lower() in empresa_norm.lower() if company_key else True
            elemento_match = person_key.lower() in elemento_raw.lower() if person_key else True
            return empresa_match and elemento_match

        target_rows = [r for r in raw_rows if _row_matches_target(r)][:limit]

        # 6) Convertir a PendingItemV1, hacer matching y generar plan
        for row in target_rows:
            tipo_doc = str(row.get("Tipo Documento") or row.get("tipo_doc") or row.get("Tipo") or "")
            elemento = str(row.get("Elemento") or row.get("elemento") or "")
            empresa = str(row.get("Empresa") or row.get("empresa") or "")
            
            fecha_inicio = _parse_date_from_cell(row.get("Inicio") or row.get("inicio") or row.get("Fecha Inicio") or "")
            fecha_fin = _parse_date_from_cell(row.get("Fin") or row.get("fin") or row.get("Fecha Fin") or "")

            pending = PendingItemV1(
                tipo_doc=tipo_doc,
                elemento=elemento,
                empresa=empresa,
                trabajador=elemento,
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

            # Generar plan de envío
            best_doc = match_result.get("best_doc")
            match_count = 1 if best_doc else 0
            
            # Evaluar guardrails
            decision = _evaluate_submission_guardrails(
                match_result,
                today,
                only_target,
                match_count
            )

            # Construir plan item
            plan_item: Dict[str, Any] = {
                "pending_ref": {
                    "tipo_doc": tipo_doc,
                    "elemento": elemento,
                    "empresa": empresa,
                    "row_index": len(pending_items) - 1
                },
                "expected_doc_type_text": f"{tipo_doc} {elemento}",
                "matched_doc": None,
                "proposed_fields": {
                    "fecha_inicio_vigencia": None,
                    "fecha_fin_vigencia": None
                },
                "decision": decision
            }

            if best_doc:
                validity = best_doc.get("validity", {})
                valid_from = validity.get("valid_from")
                valid_to = validity.get("valid_to")
                
                # Parsear fechas si son strings
                if isinstance(valid_from, str):
                    try:
                        valid_from = datetime.strptime(valid_from, "%Y-%m-%d").date()
                    except ValueError:
                        valid_from = None
                if isinstance(valid_to, str):
                    try:
                        valid_to = datetime.strptime(valid_to, "%Y-%m-%d").date()
                    except ValueError:
                        valid_to = None
                
                plan_item["matched_doc"] = {
                    "doc_id": best_doc.get("doc_id"),
                    "type_id": best_doc.get("type_id"),
                    "file_name": best_doc.get("file_name"),
                    "status": best_doc.get("status"),
                    "validity": {
                        "valid_from": valid_from.isoformat() if valid_from else None,
                        "valid_to": valid_to.isoformat() if valid_to else None,
                        "confidence": validity.get("confidence", 0.0)
                    }
                }
                
                # Fechas propuestas desde computed_validity
                plan_item["proposed_fields"]["fecha_inicio_vigencia"] = _format_date_for_portal(valid_from)
                plan_item["proposed_fields"]["fecha_fin_vigencia"] = _format_date_for_portal(valid_to)

            submission_plan.append(plan_item)

        context.close()
        browser.close()

    # 7) Guardar evidence
    _safe_write_json(pending_items_path, {"items": pending_items})
    _safe_write_json(match_results_path, {"results": match_results})
    _safe_write_json(submission_plan_path, {"plan": submission_plan})

    finished = time.time()
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
                "reason": "SUBMISSION_PLAN_GENERATED",
                "last_error": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_id

