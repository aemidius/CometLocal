"""
Endpoint de ejecución de auto-upload multi-documento.

SPRINT C2.15: Ejecuta múltiples uploads con guardrails, rate-limit y stop-on-error.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.config import DATA_DIR
from backend.adapters.egestiona.real_uploader import EgestionaRealUploader
from backend.adapters.egestiona.upload_policy import evaluate_upload_policy
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.document_matcher_v1 import DocumentMatcherV1
from starlette.concurrency import run_in_threadpool
# SPRINT C2.16: Hardening
from backend.shared.error_classifier import classify_exception, classify_error_code, ErrorCode
from backend.shared.retry_policy import retry_with_policy, get_max_retries_for_phase
from backend.shared.phase_timeout import run_with_phase_timeout, DEFAULT_TIMEOUTS
from backend.shared.evidence_helper import ensure_evidence_dir, generate_error_evidence
from backend.shared.run_summary import save_run_summary

router = APIRouter(tags=["egestiona"])


class ExecuteAutoUploadRequest(BaseModel):
    """Request para ejecutar auto-upload multi-documento."""
    coord: str = "Kern"
    company_key: str
    person_key: Optional[str] = None
    only_target: bool = True
    allowlist_type_ids: Optional[List[str]] = None
    items: Optional[List[str]] = None  # SPRINT C2.17: Opcional si se usa plan_id
    plan_id: Optional[str] = None  # SPRINT C2.17: ID del plan congelado
    decision_pack_id: Optional[str] = None  # SPRINT C2.18B: ID del Decision Pack con overrides
    max_uploads: int = 5  # SPRINT C2.15: Límite por defecto
    stop_on_first_error: bool = True  # SPRINT C2.15: Parar en primer error
    continue_on_error: bool = False  # SPRINT C2.16: Continuar con siguiente item si error es "no side-effect"
    rate_limit_seconds: float = 1.5  # SPRINT C2.15: Sleep entre uploads


def _validate_auto_upload_gate(request: ExecuteAutoUploadRequest, http_request: Request = None) -> Optional[dict]:
    """
    Valida guardrails para auto-upload.
    Retorna dict con error si falla, None si pasa.
    """
    # Verificar header X-USE-REAL-UPLOADER
    real_uploader_requested = False
    if http_request:
        real_uploader_header = http_request.headers.get("X-USE-REAL-UPLOADER", "0")
        if real_uploader_header == "1":
            real_uploader_requested = True
    
    if not real_uploader_requested:
        return {
            "status": "error",
            "error_code": "real_uploader_not_requested",
            "message": "Header X-USE-REAL-UPLOADER=1 es obligatorio para este endpoint",
            "details": None,
        }
    
    # Verificar ENVIRONMENT=dev
    if os.getenv("ENVIRONMENT", "").lower() != "dev":
        return {
            "status": "error",
            "error_code": "real_upload_environment_violation",
            "message": "RealUploader solo está disponible en ENVIRONMENT=dev",
            "details": None,
        }
    
    # Validar max_uploads <= 5 por defecto
    if request.max_uploads > 5:
        return {
            "status": "error",
            "error_code": "max_uploads_exceeded",
            "message": f"max_uploads no puede ser mayor a 5, recibido: {request.max_uploads}",
            "details": None,
        }
    
    # SPRINT C2.17: Validar items o plan_id
    if not request.plan_id and (not request.items or len(request.items) == 0):
        return {
            "status": "error",
            "error_code": "no_items",
            "message": "items no puede estar vacío si no se proporciona plan_id",
            "details": None,
        }
    
    # Validar que len(items) <= max_uploads (solo si se proporciona items explícitamente)
    if request.items and len(request.items) > request.max_uploads:
        return {
            "status": "error",
            "error_code": "items_exceed_max_uploads",
            "message": f"items ({len(request.items)}) excede max_uploads ({request.max_uploads})",
            "details": None,
        }
    
    return None  # Pasa validación


@router.post("/runs/egestiona/execute_auto_upload")
async def egestiona_execute_auto_upload(
    request: ExecuteAutoUploadRequest,
    http_request: Request = None,
):
    """
    SPRINT C2.15: Ejecuta auto-upload multi-documento.
    
    Requisitos:
    - Header X-USE-REAL-UPLOADER=1
    - ENVIRONMENT=dev
    - max_uploads <= 5
    - len(items) <= max_uploads
    
    Flujo:
    1) Validar gate
    2) Construir snapshot completo (reutilizar C2.14.1)
    3) Para cada pending_item_key:
       - Re-localizar item en portal (C2.14.1)
       - Revalidar política server-side (NO subir si decision != AUTO_UPLOAD)
       - Ejecutar uploader real
       - Verificar post-condición
       - Guardar evidencia por item
    4) Devolver reporte final
    
    Response:
    {
        status: "ok" | "partial" | "error",
        results: [{pending_item_key, success, reason?, evidence_paths...}],
        summary: {...}
    }
    """
    # 1) Validar gate
    gate_error = _validate_auto_upload_gate(request, http_request)
    if gate_error:
        return gate_error
    
    import uuid
    from datetime import datetime
    run_id = f"auto_upload_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    execution_dir = Path(DATA_DIR) / "runs" / run_id / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    
    # SPRINT C2.16: Inicializar métricas de run
    started_at = datetime.utcnow()
    errors_logged = []  # Lista de errores para run_summary
    
    # SPRINT C2.17: Cargar plan congelado si se proporciona plan_id
    frozen_plan = None
    plan_decisions_map = {}  # pending_item_key -> decision
    
    if request.plan_id:
        # SPRINT C2.20B: Registrar inicio de ejecución
        try:
            from backend.shared.run_metrics import record_execution_started
            record_execution_started(request.plan_id, run_id)
        except Exception as e:
            print(f"[CAE][AUTO_UPLOAD] WARNING: Error recording execution start: {e}")
        
        # Cargar plan congelado desde data/runs/
        plan_path = Path(DATA_DIR) / "runs" / request.plan_id / "plan_response.json"
        if plan_path.exists():
            with open(plan_path, "r", encoding="utf-8") as f:
                import json
                frozen_plan = json.load(f)
            
            # SPRINT C2.18B: Aplicar Decision Pack si se proporciona
            plan_decisions = frozen_plan.get("decisions", [])
            decision_pack = None
            if request.decision_pack_id:
                from backend.shared.decision_pack_store import DecisionPackStore
                pack_store = DecisionPackStore()
                decision_pack = pack_store.load_pack(request.plan_id, request.decision_pack_id)
                if decision_pack:
                    plan_decisions = decision_pack.apply_to_decisions(plan_decisions)
                    print(f"[CAE][AUTO_UPLOAD] Decision Pack aplicado: {request.decision_pack_id}")
                    
                    # SPRINT C2.19A: Generar hints desde Decision Pack
                    try:
                        from backend.shared.learning_hints_generator import generate_hints_from_decision_pack
                        hint_ids = generate_hints_from_decision_pack(
                            plan_id=request.plan_id,
                            decision_pack=decision_pack,
                            plan_data=frozen_plan,
                        )
                        if hint_ids:
                            print(f"[CAE][AUTO_UPLOAD] Generados {len(hint_ids)} hints de aprendizaje")
                    except Exception as e:
                        print(f"[CAE][AUTO_UPLOAD] WARNING: Error generando hints: {e}")
                else:
                    print(f"[CAE][AUTO_UPLOAD] WARNING: Decision Pack {request.decision_pack_id} not found, usando decisiones originales")
            
            # Crear mapa de decisiones (con overrides aplicados si hay)
            for decision in plan_decisions:
                pending_item_key = decision.get("pending_item_key")
                if pending_item_key:
                    plan_decisions_map[pending_item_key] = decision
            
            print(f"[CAE][AUTO_UPLOAD] Plan congelado cargado: plan_id={request.plan_id}, {len(plan_decisions_map)} decisiones")
        else:
            return {
                "status": "error",
                "error_code": "plan_not_found",
                "message": f"Plan {request.plan_id} not found",
                "details": None,
                "results": [],
                "summary": {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "skipped": 0,
                },
            }
    
    # 2) Construir snapshot completo para obtener items con pending_item_key
    from backend.adapters.egestiona.submission_plan_headful import run_build_submission_plan_readonly_headful
    from starlette.concurrency import run_in_threadpool
    
    items_to_process = request.items if request.items else []
    
    # SPRINT C2.17: Si hay plan_id, obtener items AUTO_UPLOAD del plan congelado
    if request.plan_id and frozen_plan:
        auto_upload_items = [
            d.get("pending_item_key")
            for d in frozen_plan.get("decisions", [])
            if d.get("decision") == "AUTO_UPLOAD"
        ]
        items_to_process = auto_upload_items[:request.max_uploads]  # Limitar a max_uploads
        print(f"[CAE][AUTO_UPLOAD] Procesando {len(items_to_process)} items AUTO_UPLOAD del plan {request.plan_id}")
    
    if not items_to_process:
        return {
            "status": "error",
            "error_code": "no_items_to_process",
            "message": "No items to process (empty items list or no AUTO_UPLOAD items in plan)",
            "details": None,
            "results": [],
            "summary": {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
            },
        }
    
    print(f"[CAE][AUTO_UPLOAD] Construyendo snapshot para {len(items_to_process)} items...")
    
    # SPRINT C2.16: Guardar plan_result para run_summary
    plan_result = None
    try:
        plan_result = await run_in_threadpool(
            lambda: run_build_submission_plan_readonly_headful(
                base_dir="data",
                platform="egestiona",
                coordination=request.coord,
                company_key=request.company_key,
                person_key=request.person_key,
                limit=200,  # Obtener todos los items
                only_target=request.only_target,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
                return_plan_only=True,
                max_pages=10,
                max_items=200,
            )
        )
    except Exception as snapshot_error:
        error_classification = classify_exception(snapshot_error, "grid_load", {})
        errors_logged.append({
            "phase": "grid_load",
            "error_code": error_classification["error_code"],
            "message": error_classification["message"],
            "transient": error_classification["is_transient"],
            "attempt": 1,
        })
        raise snapshot_error
    
    if not isinstance(plan_result, dict):
        return {
            "status": "error",
            "error_code": "snapshot_failed",
            "message": f"Failed to build snapshot: {type(plan_result)}",
            "details": None,
            "results": [],
            "summary": {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
            },
        }
    
    # Crear mapa de pending_item_key -> plan_item
    plan_items_map = {}
    for plan_item in plan_result.get("plan", []):
        pending_item_key = plan_item.get("pending_item_key") or plan_item.get("pending_ref", {}).get("pending_item_key")
        if pending_item_key:
            plan_items_map[pending_item_key] = plan_item
    
    # SPRINT C2.17: Filtrar items a procesar: solo AUTO_UPLOAD
    items_to_upload = []
    skipped_count = 0  # Inicializar contador
    
    for pending_item_key in items_to_process:
        # SPRINT C2.17: Si hay plan_id, verificar decisión del plan congelado
        if request.plan_id and frozen_plan:
            decision_obj = plan_decisions_map.get(pending_item_key)
            if not decision_obj:
                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item {pending_item_key} no encontrado en plan congelado, saltando")
                skipped_count += 1
                results.append({
                    "pending_item_key": pending_item_key,
                    "success": False,
                    "reason": "item_not_in_frozen_plan",
                })
                continue
            
            decision = decision_obj.get("decision")
            if decision != "AUTO_UPLOAD":
                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item {pending_item_key} tiene decision={decision}, no AUTO_UPLOAD, saltando")
                skipped_count += 1
                results.append({
                    "pending_item_key": pending_item_key,
                    "success": False,
                    "reason": f"decision_not_auto_upload",
                    "decision": decision,
                    "decision_reason": decision_obj.get("decision_reason"),
                })
                continue
        
        # Si no hay plan_id, validar server-side (legacy)
        if not request.plan_id:
            plan_item = plan_items_map.get(pending_item_key)
            if not plan_item:
                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item {pending_item_key} no encontrado en snapshot, saltando")
                skipped_count += 1
                results.append({
                    "pending_item_key": pending_item_key,
                    "success": False,
                    "reason": "item_not_found_in_snapshot",
                })
                continue
        
        items_to_upload.append(pending_item_key)
    
    if not items_to_upload:
        return {
            "status": "error",
            "error_code": "no_auto_upload_items",
            "message": "No items with decision=AUTO_UPLOAD to process",
            "details": None,
            "results": results,
            "summary": {
                "total": len(items_to_process),
                "success": 0,
                "failed": 0,
                "skipped": skipped_count,
            },
        }
    
    # SPRINT C2.17: Filtrar items a procesar: solo AUTO_UPLOAD
    items_to_upload = []
    skipped_count = 0
    pre_results = []  # Resultados de items filtrados antes de ejecutar
    
    for pending_item_key in items_to_process:
        # SPRINT C2.17: Si hay plan_id, verificar decisión del plan congelado
        if request.plan_id and frozen_plan:
            decision_obj = plan_decisions_map.get(pending_item_key)
            if not decision_obj:
                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item {pending_item_key} no encontrado en plan congelado, saltando")
                skipped_count += 1
                pre_results.append({
                    "pending_item_key": pending_item_key,
                    "success": False,
                    "reason": "item_not_in_frozen_plan",
                })
                continue
            
            decision = decision_obj.get("decision")
            if decision != "AUTO_UPLOAD":
                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item {pending_item_key} tiene decision={decision}, no AUTO_UPLOAD, saltando")
                skipped_count += 1
                pre_results.append({
                    "pending_item_key": pending_item_key,
                    "success": False,
                    "reason": f"decision_not_auto_upload",
                    "decision": decision,
                    "decision_reason": decision_obj.get("decision_reason"),
                })
                continue
        
        # Si no hay plan_id, validar server-side (legacy)
        if not request.plan_id:
            plan_item = plan_items_map.get(pending_item_key)
            if not plan_item:
                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item {pending_item_key} no encontrado en snapshot, saltando")
                skipped_count += 1
                pre_results.append({
                    "pending_item_key": pending_item_key,
                    "success": False,
                    "reason": "item_not_found_in_snapshot",
                })
                continue
        
        items_to_upload.append(pending_item_key)
    
    if not items_to_upload:
        return {
            "status": "error",
            "error_code": "no_auto_upload_items",
            "message": "No items with decision=AUTO_UPLOAD to process",
            "details": None,
            "results": pre_results,
            "summary": {
                "total": len(items_to_process),
                "success": 0,
                "failed": 0,
                "skipped": skipped_count,
            },
        }
    
    # 3) Ejecutar uploads 1 a 1
    results = pre_results.copy()  # Incluir resultados de items filtrados
    success_count = 0
    failed_count = 0
    attempted_uploads = 0
    success_uploads = 0
    failed_uploads = 0
    
    # Crear browser context reutilizable (una vez para todos los uploads)
    from playwright.sync_api import sync_playwright
    from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS
    
    base = ensure_data_layout(base_dir="data")
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)
    
    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == "egestiona"), None)
    if not plat:
        return {
            "status": "error",
            "error_code": "platform_not_found",
            "message": "platform 'egestiona' not found",
            "details": None,
            "results": [],
            "summary": {
                "total": len(request.items),
                "success": 0,
                "failed": 0,
                "skipped": 0,
            },
        }
    
    coord = next((c for c in plat.coordinations if c.label == request.coord), None)
    if not coord:
        return {
            "status": "error",
            "error_code": "coordination_not_found",
            "message": f"coordination '{request.coord}' not found",
            "details": None,
            "results": [],
            "summary": {
                "total": len(request.items),
                "success": 0,
                "failed": 0,
                "skipped": 0,
            },
        }
    
    # Resolver credenciales
    creds = secrets.get_credentials(platform_key="egestiona", coord_label=request.coord)
    if not creds or not creds.username or not creds.password:
        return {
            "status": "error",
            "error_code": "missing_credentials",
            "message": f"Credentials not found for {request.coord}",
            "details": None,
            "results": [],
            "summary": {
                "total": len(request.items),
                "success": 0,
                "failed": 0,
                "skipped": 0,
            },
        }
    
    # URL de login
    url = plat.login_url or coord.url_override or plat.base_url
    
    uploader = EgestionaRealUploader(execution_dir)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            context = browser.new_context(
                viewport={"width": 1600, "height": 1000},
            )
            page = context.new_page()
            
            # SPRINT C2.16: Login con retry policy y timeout
            print(f"[CAE][AUTO_UPLOAD] Haciendo login...")
            
            def do_login():
                page.goto(url)
                page.fill('input[name="usuario"], input[name="username"], input[type="text"]', creds.username)
                page.fill('input[name="password"], input[type="password"]', creds.password)
                page.click('button[type="submit"], input[type="submit"], button:has-text("Entrar")')
                page.wait_for_timeout(3000)
            
            try:
                run_with_phase_timeout(
                    phase="login",
                    fn=do_login,
                    timeout_s=DEFAULT_TIMEOUTS["login"],
                    on_timeout_evidence=lambda: generate_error_evidence(
                        page=page,
                        phase="login",
                        attempt=1,
                        error=Exception("Login timeout"),
                        evidence_dir=execution_dir,
                        context={"url": url},
                        run_id=run_id,
                    ),
                )
            except Exception as login_error:
                error_classification = classify_exception(login_error, "login", {"url": url})
                errors_logged.append({
                    "phase": "login",
                    "error_code": error_classification["error_code"],
                    "message": error_classification["message"],
                    "transient": error_classification["is_transient"],
                    "attempt": 1,
                })
                
                # Generar evidencia
                evidence_paths = generate_error_evidence(
                    page=page,
                    phase="login",
                    attempt=1,
                    error=login_error,
                    evidence_dir=execution_dir,
                    context={"url": url},
                    run_id=run_id,
                )
                
                # Retry si es transitorio
                if error_classification["is_transient"]:
                    try:
                        retry_with_policy(
                            fn=do_login,
                            phase="login",
                            error_code=error_classification["error_code"],
                            context={"url": url},
                            on_retry=lambda attempt, exc: print(f"[RETRY][login] Attempt {attempt}"),
                        )
                    except Exception as retry_error:
                        # Si retry también falla, abortar
                        raise retry_error
                else:
                    raise login_error
            
            # SPRINT C2.17: Para cada item (usar items_to_upload si existe, sino request.items)
            items_list = items_to_upload if items_to_upload else (request.items if request.items else [])
            for idx, pending_item_key in enumerate(items_list):
                print(f"[CAE][AUTO_UPLOAD] Procesando item {idx+1}/{len(items_list)}: {pending_item_key}")
                
                # Buscar plan_item correspondiente
                plan_item = plan_items_map.get(pending_item_key)
                if not plan_item:
                    results.append({
                        "pending_item_key": pending_item_key,
                        "success": False,
                        "reason": "item_not_found_in_snapshot",
                        "evidence_paths": {},
                    })
                    skipped_count += 1
                    continue
                
                # SPRINT C2.17: Si hay plan_id, usar decisión del plan congelado (NO revalidar)
                # Si NO hay plan_id, revalidar política server-side (legacy)
                if not request.plan_id:
                    # SPRINT C2.15: Revalidar política server-side (NO subir si decision != AUTO_UPLOAD)
                    pending_ref = plan_item.get("pending_ref", {})
                    match_result = {
                        "best_doc": plan_item.get("matched_doc", {}),
                        "confidence": plan_item.get("matched_doc", {}).get("validity", {}).get("confidence", 0.0),
                        "candidates": [],
                    }
                    
                    pending_item_dict = {
                        "tipo_doc": pending_ref.get("tipo_doc"),
                        "elemento": pending_ref.get("elemento"),
                        "empresa": pending_ref.get("empresa"),
                    }
                    
                    from backend.adapters.egestiona.upload_policy import evaluate_upload_policy
                    policy_result = evaluate_upload_policy(
                        pending_item=pending_item_dict,
                        match_result=match_result,
                        company_key=request.company_key,
                        person_key=request.person_key,
                        only_target=request.only_target,
                        base_dir="data",
                    )
                    
                    if policy_result["decision"] != "AUTO_UPLOAD":
                        results.append({
                            "pending_item_key": pending_item_key,
                            "success": False,
                            "reason": f"policy_rejected: {policy_result['reason_code']}",
                            "policy_decision": policy_result["decision"],
                            "policy_reason": policy_result["reason"],
                            "evidence_paths": {},
                        })
                        skipped_count += 1
                        print(f"[CAE][AUTO_UPLOAD] ⚠️ Item rechazado por política: {policy_result['reason_code']}")
                        continue
                
                # SPRINT C2.17: Obtener decisión del plan congelado (si existe)
                decision_obj = plan_decisions_map.get(pending_item_key) if request.plan_id else None
                decision = decision_obj.get("decision") if decision_obj else "AUTO_UPLOAD"  # Default si no hay plan_id
                decision_reason = decision_obj.get("decision_reason") if decision_obj else None
                
                # SPRINT C2.15: Re-localizar item en portal usando pending_item_key (C2.14.1)
                # El uploader ya tiene lógica de re-localización, pero necesitamos asegurar
                # que el plan_item tiene pending_item_key en pending_ref
                if "pending_item_key" not in plan_item.get("pending_ref", {}):
                    plan_item["pending_ref"]["pending_item_key"] = pending_item_key
                
                # Ejecutar upload
                item_evidence_dir = execution_dir / "items" / pending_item_key.replace("|", "_").replace(":", "_")[:100]  # Limitar longitud
                item_evidence_dir.mkdir(parents=True, exist_ok=True)
                
                # SPRINT C2.16: Upload con retry policy, timeout y clasificación de errores
                upload_attempted = False
                upload_succeeded = False
                upload_error = None
                upload_error_code = None
                
                try:
                    def do_upload():
                        nonlocal upload_attempted, upload_succeeded
                        upload_attempted = True
                        result = uploader.upload_one_real(
                            page,
                            plan_item,
                            requirement_id=f"auto_upload_{idx+1}",
                        )
                        upload_succeeded = result.get("success", False)
                        return result
                    
                    # SPRINT C2.16.1: Wrapper para retry con refresh si item_not_found_before_upload
                    def do_upload_with_retry():
                        nonlocal upload_attempted
                        try:
                            return do_upload()
                        except Exception as e:
                            # Clasificar error
                            error_classification = classify_exception(
                                e,
                                "upload",
                                {"pending_item_key": pending_item_key, "upload_attempted": upload_attempted},
                            )
                            
                            # SPRINT C2.16.1: Si es item_not_found_before_upload, hacer refresh antes de retry
                            if error_classification["error_code"] == ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD:
                                print(f"[CAE][AUTO_UPLOAD] ⚠️ Item not found, haciendo refresh del listado...")
                                try:
                                    # Navegar de nuevo al listado de pendientes
                                    # (El uploader ya tiene lógica de navegación, pero aquí forzamos refresh)
                                    from backend.adapters.egestiona.pagination_helper import detect_pagination_controls, click_pagination_button
                                    from backend.adapters.egestiona.grid_extract import extract_dhtmlx_grid
                                    
                                    # Buscar frame del listado
                                    list_frame = None
                                    for frame in page.frames:
                                        if "buscador.asp" in frame.url or "pendientes" in frame.url.lower():
                                            list_frame = frame
                                            break
                                    
                                    if list_frame:
                                        # Ir a primera página si hay paginación
                                        pagination_info = detect_pagination_controls(list_frame)
                                        if pagination_info.get("has_pagination") and pagination_info.get("first_button"):
                                            first_btn = pagination_info["first_button"]
                                            if first_btn.get("isVisible") and first_btn.get("isEnabled"):
                                                click_pagination_button(list_frame, first_btn, item_evidence_dir)
                                                time.sleep(1.0)
                                        
                                        # Refrescar grid (esperar a que se actualice)
                                        time.sleep(1.5)
                                        
                                        print(f"[CAE][AUTO_UPLOAD] ✅ Refresh completado, reintentando upload...")
                                except Exception as refresh_error:
                                    print(f"[CAE][AUTO_UPLOAD] ⚠️ Error en refresh: {refresh_error}")
                            
                            raise e
                    
                    upload_result = run_with_phase_timeout(
                        phase="upload",
                        fn=do_upload_with_retry,
                        timeout_s=DEFAULT_TIMEOUTS["upload"],
                        on_timeout_evidence=lambda: generate_error_evidence(
                            page=page,
                            phase="upload",
                            attempt=1,
                            error=Exception("Upload timeout"),
                            evidence_dir=item_evidence_dir,
                            context={"pending_item_key": pending_item_key, "upload_attempted": upload_attempted},
                            run_id=run_id,
                        ),
                    )
                    
                    if upload_result["success"]:
                        success_count += 1
                        attempted_uploads += 1
                        success_uploads += 1
                        results.append({
                            "pending_item_key": pending_item_key,
                            "success": True,
                            "reason": upload_result.get("reason", "upload_success"),
                            "decision": decision or "AUTO_UPLOAD",  # SPRINT C2.17: Incluir decisión
                            "decision_reason": decision_reason,  # SPRINT C2.17: Incluir razón
                            "upload_id": upload_result.get("upload_id"),
                            "post_verification": upload_result.get("post_verification"),
                            "evidence_paths": {
                                "item_dir": str(item_evidence_dir),
                                "before_upload": str(item_evidence_dir / "before_upload.png"),
                                "after_upload": str(item_evidence_dir / "after_upload.png"),
                                "upload_log": str(item_evidence_dir / "upload_log.txt"),
                            },
                        })
                        print(f"[CAE][AUTO_UPLOAD] ✅ Item {idx+1} subido exitosamente")
                    else:
                        # Clasificar error del upload_result
                        reason = upload_result.get("reason", "upload_failed")
                        upload_error_code = None
                        
                        # SPRINT C2.16.1: Si es item_not_found_before_upload, aplicar retry con refresh
                        if reason == "item_not_found_before_upload" or "item_not_found" in reason.lower():
                            upload_error_code = ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD.value
                            
                            # Intentar retry con refresh (solo 1 vez)
                            max_retries = get_max_retries_for_phase("upload", upload_error_code, {"upload_attempted": upload_attempted})
                            if max_retries > 0:
                                print(f"[CAE][AUTO_UPLOAD] 🔄 Retry con refresh para item_not_found_before_upload...")
                                try:
                                    # Refresh del listado (ya hecho en do_upload_with_retry si fue excepción)
                                    # Si viene de upload_result, hacer refresh aquí
                                    from backend.adapters.egestiona.pagination_helper import detect_pagination_controls, click_pagination_button
                                    
                                    list_frame = None
                                    for frame in page.frames:
                                        if "buscador.asp" in frame.url or "pendientes" in frame.url.lower():
                                            list_frame = frame
                                            break
                                    
                                    if list_frame:
                                        pagination_info = detect_pagination_controls(list_frame)
                                        if pagination_info.get("has_pagination") and pagination_info.get("first_button"):
                                            first_btn = pagination_info["first_button"]
                                            if first_btn.get("isVisible") and first_btn.get("isEnabled"):
                                                click_pagination_button(list_frame, first_btn, item_evidence_dir)
                                                time.sleep(1.5)
                                    
                                    # Reintentar upload
                                    upload_result = uploader.upload_one_real(
                                        page,
                                        plan_item,
                                        requirement_id=f"auto_upload_{idx+1}_retry",
                                    )
                                    
                                    if upload_result["success"]:
                                        success_count += 1
                                        attempted_uploads += 1
                                        success_uploads += 1
                                        results.append({
                                            "pending_item_key": pending_item_key,
                                            "success": True,
                                            "reason": upload_result.get("reason", "upload_success_after_retry"),
                                            "upload_id": upload_result.get("upload_id"),
                                            "post_verification": upload_result.get("post_verification"),
                                            "evidence_paths": {
                                                "item_dir": str(item_evidence_dir),
                                                "before_upload": str(item_evidence_dir / "before_upload.png"),
                                                "after_upload": str(item_evidence_dir / "after_upload.png"),
                                                "upload_log": str(item_evidence_dir / "upload_log.txt"),
                                            },
                                        })
                                        print(f"[CAE][AUTO_UPLOAD] ✅ Item {idx+1} subido exitosamente después de retry")
                                        continue  # Saltar al siguiente item
                                except Exception as retry_error:
                                    print(f"[CAE][AUTO_UPLOAD] ❌ Retry falló: {retry_error}")
                                    # Continuar con el flujo de error normal
                        
                        # Si no se hizo retry o el retry falló, clasificar error normalmente
                        if not upload_error_code:
                            error_classification = classify_error_code(
                                error_code=reason if reason in [e.value for e in ErrorCode] else ErrorCode.UPLOAD_FAILED.value,
                                phase="upload",
                                context={"pending_item_key": pending_item_key, "upload_result": upload_result, "upload_attempted": upload_attempted},
                            )
                            upload_error_code = error_classification["error_code"]
                        else:
                            error_classification = classify_error_code(
                                error_code=upload_error_code,
                                phase="upload",
                                context={"pending_item_key": pending_item_key, "upload_result": upload_result, "upload_attempted": upload_attempted},
                            )
                        
                        failed_count += 1
                        attempted_uploads += 1
                        failed_uploads += 1
                        
                        errors_logged.append({
                            "phase": "upload",
                            "error_code": upload_error_code,
                            "message": upload_result.get("error") or reason,
                            "transient": error_classification["is_transient"],
                            "attempt": 1,
                        })
                        
                        results.append({
                            "pending_item_key": pending_item_key,
                            "success": False,
                            "reason": reason,
                            "decision": decision or "AUTO_UPLOAD",  # SPRINT C2.17: Incluir decisión
                            "decision_reason": decision_reason,  # SPRINT C2.17: Incluir razón
                            "error": upload_result.get("error"),
                            "error_code": upload_error_code,
                            "evidence_paths": {
                                "item_dir": str(item_evidence_dir),
                                "upload_log": str(item_evidence_dir / "upload_log.txt"),
                            },
                        })
                        print(f"[CAE][AUTO_UPLOAD] ❌ Item {idx+1} falló: {reason}")
                        
                        # SPRINT C2.16: Continue-on-error logic
                        should_continue = False
                        if request.continue_on_error:
                            # Solo continuar si el error es "no side-effect" (antes de upload) o verificación fallida
                            if reason in ["item_not_found_before_upload", "verification_failed"]:
                                should_continue = True
                                print(f"[CAE][AUTO_UPLOAD] ⚠️ Continue-on-error: continuando con siguiente item (error: {reason})")
                        
                        if not should_continue and request.stop_on_first_error:
                            print(f"[CAE][AUTO_UPLOAD] ⚠️ Stop-on-error activado, deteniendo ejecución")
                            break
                
                except Exception as e:
                    upload_error = e
                    
                    import traceback
                    error_trace = traceback.format_exc()
                    
                    # Clasificar excepción
                    error_classification = classify_exception(
                        e,
                        "upload",
                        {"pending_item_key": pending_item_key, "upload_attempted": upload_attempted},
                    )
                    upload_error_code = error_classification["error_code"]
                    
                    # SPRINT C2.16.1: Si es item_not_found_before_upload, intentar retry con refresh
                    if error_classification["error_code"] == ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD:
                        max_retries = get_max_retries_for_phase("upload", upload_error_code, {"upload_attempted": upload_attempted})
                        if max_retries > 0:
                            print(f"[CAE][AUTO_UPLOAD] 🔄 Retry con refresh para item_not_found_before_upload (excepción)...")
                            try:
                                # Refresh del listado
                                from backend.adapters.egestiona.pagination_helper import detect_pagination_controls, click_pagination_button
                                
                                list_frame = None
                                for frame in page.frames:
                                    if "buscador.asp" in frame.url or "pendientes" in frame.url.lower():
                                        list_frame = frame
                                        break
                                
                                if list_frame:
                                    pagination_info = detect_pagination_controls(list_frame)
                                    if pagination_info.get("has_pagination") and pagination_info.get("first_button"):
                                        first_btn = pagination_info["first_button"]
                                        if first_btn.get("isVisible") and first_btn.get("isEnabled"):
                                            click_pagination_button(list_frame, first_btn, item_evidence_dir)
                                            time.sleep(1.5)
                                
                                # Reintentar upload
                                upload_result = uploader.upload_one_real(
                                    page,
                                    plan_item,
                                    requirement_id=f"auto_upload_{idx+1}_retry",
                                )
                                
                                if upload_result["success"]:
                                    success_count += 1
                                    attempted_uploads += 1
                                    success_uploads += 1
                                    results.append({
                                        "pending_item_key": pending_item_key,
                                        "success": True,
                                        "reason": upload_result.get("reason", "upload_success_after_retry"),
                                        "decision": decision,  # SPRINT C2.17: Incluir decisión
                                        "decision_reason": decision_reason,  # SPRINT C2.17: Incluir razón
                                        "upload_id": upload_result.get("upload_id"),
                                        "post_verification": upload_result.get("post_verification"),
                                        "evidence_paths": {
                                            "item_dir": str(item_evidence_dir),
                                            "before_upload": str(item_evidence_dir / "before_upload.png"),
                                            "after_upload": str(item_evidence_dir / "after_upload.png"),
                                            "upload_log": str(item_evidence_dir / "upload_log.txt"),
                                        },
                                    })
                                    print(f"[CAE][AUTO_UPLOAD] ✅ Item {idx+1} subido exitosamente después de retry")
                                    continue  # Saltar al siguiente item
                            except Exception as retry_error:
                                print(f"[CAE][AUTO_UPLOAD] ❌ Retry falló: {retry_error}")
                                # Continuar con el flujo de error normal
                    
                    # Si llegamos aquí, el error no se pudo resolver con retry
                    failed_count += 1
                    attempted_uploads += 1
                    failed_uploads += 1
                    
                    errors_logged.append({
                        "phase": "upload",
                        "error_code": upload_error_code,
                        "message": error_classification["message"],
                        "transient": error_classification["is_transient"],
                        "attempt": 1,
                    })
                    
                    # Generar evidencia automática
                    evidence_paths = generate_error_evidence(
                        page=page,
                        phase="upload",
                        attempt=1,
                        error=e,
                        evidence_dir=item_evidence_dir,
                        context={"pending_item_key": pending_item_key, "upload_attempted": upload_attempted},
                        run_id=run_id,
                    )
                    
                    results.append({
                        "pending_item_key": pending_item_key,
                        "success": False,
                        "reason": "upload_exception",
                        "decision": decision or "AUTO_UPLOAD",  # SPRINT C2.17: Incluir decisión
                        "decision_reason": decision_reason,  # SPRINT C2.17: Incluir razón
                        "error": str(e),
                        "error_code": upload_error_code,
                        "traceback": error_trace if os.getenv("ENVIRONMENT", "").lower() == "dev" else None,
                        "evidence_paths": evidence_paths,
                    })
                    print(f"[CAE][AUTO_UPLOAD] ❌ Item {idx+1} excepción: {e}")
                    
                    # SPRINT C2.16: Continue-on-error logic
                    should_continue = False
                    if request.continue_on_error:
                        # Solo continuar si el error es "no side-effect" (antes de upload) o verificación fallida
                        if error_classification["is_transient"] and not upload_attempted:
                            should_continue = True
                            print(f"[CAE][AUTO_UPLOAD] ⚠️ Continue-on-error: continuando con siguiente item (error transitorio antes de upload)")
                    
                    if not should_continue and request.stop_on_first_error:
                        print(f"[CAE][AUTO_UPLOAD] ⚠️ Stop-on-error activado, deteniendo ejecución")
                        break
                
                # Rate-limit: sleep entre uploads (excepto el último)
                if idx < len(items_list) - 1:
                    time.sleep(request.rate_limit_seconds)
            
            context.close()
            browser.close()
    
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error_code": "execution_failed",
            "message": str(e),
            "details": traceback.format_exc() if os.getenv("ENVIRONMENT", "").lower() == "dev" else None,
            "results": results,
            "summary": {
                "total": len(items_to_process) if items_to_process else (len(request.items) if request.items else 0),
                "success": success_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "plan_id": request.plan_id,  # SPRINT C2.17: Incluir plan_id en summary
            },
            "plan_id": request.plan_id,  # SPRINT C2.17: Incluir plan_id en nivel superior
        }
    
    # SPRINT C2.16: Guardar run_summary
    finished_at = datetime.utcnow()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    
    # Obtener counts del snapshot (si está disponible)
    # plan_result puede ser None si hubo error antes de construirlo
    if plan_result and isinstance(plan_result, dict):
        pending_total = len(plan_result.get("pending_items", []))
        decisions = plan_result.get("decisions", [])
        auto_upload_count = len([d for d in decisions if d.get("decision") == "AUTO_UPLOAD"])
        review_required_count = len([d for d in decisions if d.get("decision") == "REVIEW_REQUIRED"])
        no_match_count = len([d for d in decisions if d.get("decision") == "NO_MATCH"])
    else:
        pending_total = 0
        auto_upload_count = 0
        review_required_count = 0
        no_match_count = 0
    
    # SPRINT C2.16.1: Preparar rutas de evidencia principales
    evidence_root = str(execution_dir.parent) if execution_dir else None
    evidence_paths = {
        "execution_dir": str(execution_dir),
    }
    
    # Añadir rutas de evidencias de errores si existen
    for error in errors_logged:
        phase = error.get("phase")
        if phase:
            phase_evidence_dir = execution_dir / phase / "attempt_1"
            if phase_evidence_dir.exists():
                evidence_paths[f"{phase}_evidence"] = str(phase_evidence_dir)
    
    try:
        save_run_summary(
            run_id=run_id,
            platform="egestiona",
            coord=request.coord,
            company_key=request.company_key,
            person_key=request.person_key,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            pending_total=pending_total,
            auto_upload_count=auto_upload_count,
            review_required_count=review_required_count,
            no_match_count=no_match_count,
            attempted_uploads=attempted_uploads,
            success_uploads=success_count,
            failed_uploads=failed_count,
            errors=errors_logged,
            evidence_root=evidence_root,  # SPRINT C2.16.1
            evidence_paths=evidence_paths,  # SPRINT C2.16.1
            run_kind="execution",  # SPRINT C2.17: Tipo de run
            base_dir="data",
        )
    except Exception as summary_error:
        print(f"[CAE][AUTO_UPLOAD] ⚠️ Error guardando run_summary: {summary_error}")
    
    # SPRINT C2.20B: Registrar finalización de ejecución
    if request.plan_id:
        try:
            from backend.shared.run_metrics import record_execution_finished
            record_execution_finished(request.plan_id)
        except Exception as e:
            print(f"[CAE][AUTO_UPLOAD] WARNING: Error recording execution finished: {e}")
    
    # Determinar status final
    if failed_count == 0 and skipped_count == 0:
        final_status = "ok"
    elif success_count > 0:
        final_status = "partial"
    else:
        final_status = "error"
    
    summary = {
        "total": len(items_to_process) if items_to_process else (len(request.items) if request.items else 0),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "run_id": run_id,
        "plan_id": request.plan_id,  # SPRINT C2.17: Incluir plan_id en summary
    }
    
    return {
        "status": final_status,
        "results": results,
        "summary": summary,
        "plan_id": request.plan_id,  # SPRINT C2.17: Incluir plan_id en nivel superior
        "artifacts": {
            "run_id": run_id,
            "execution_dir": str(execution_dir),
            "run_summary_path": str(Path(DATA_DIR) / "runs" / run_id / "run_summary.json"),
        },
    }
