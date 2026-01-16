"""
Endpoints para gestionar runs headful persistentes.

Permite mantener un navegador Playwright abierto y ejecutar
acciones secuenciales con supervisión humana.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import time
from datetime import datetime
from typing import Optional
import time as time_module

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.config import DATA_DIR
from backend.runs.headful_run_manager import HeadfulRunManager
from backend.runs.run_timeline import EventType
from backend.adapters.egestiona.execute_plan_gate import ExecutePlanRequest
from backend.adapters.egestiona.real_uploader import EgestionaRealUploader
from backend.repository.config_store_v1 import ConfigStoreV1

router = APIRouter(tags=["egestiona"])


class StartHeadfulRunRequest(BaseModel):
    """Request para iniciar un run headful persistente."""
    plan_id: str
    confirm_token: str


class ExecuteActionHeadfulRequest(BaseModel):
    """Request para ejecutar una acción dentro de un run headful."""
    run_id: str
    confirm_token: str
    allowlist_type_ids: list[str]
    max_uploads: int = 1
    min_confidence: float = 0.80


class CloseHeadfulRunRequest(BaseModel):
    """Request para cerrar un run headful."""
    run_id: str


def _validate_real_upload_gate_for_action(request: ExecuteActionHeadfulRequest, http_request: Request = None) -> Optional[dict]:
    """Valida guardrails para acciones reales en run headful."""
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
            "message": "Header X-USE-REAL-UPLOADER=1 es obligatorio",
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
    
    # Guardrail: max_uploads == 1
    if request.max_uploads != 1:
        return {
            "status": "error",
            "error_code": "REAL_UPLOAD_GUARDRAIL_VIOLATION",
            "message": f"max_uploads debe ser 1 para uploads reales, recibido: {request.max_uploads}",
            "details": None,
        }
    
    # Guardrail: len(allowlist_type_ids) == 1
    if len(request.allowlist_type_ids) != 1:
        return {
            "status": "error",
            "error_code": "REAL_UPLOAD_GUARDRAIL_VIOLATION",
            "message": f"allowlist_type_ids debe tener exactamente 1 tipo para uploads reales, recibido: {len(request.allowlist_type_ids)}",
            "details": None,
        }
    
    return None


@router.post("/runs/egestiona/start_headful_run")
async def start_headful_run(request: StartHeadfulRunRequest, http_request: Request = None):
    """
    Inicia un run headful persistente.
    
    Requisitos:
    - ENVIRONMENT=dev
    - Header X-USE-REAL-UPLOADER=1 (opcional pero recomendado)
    - storage_state.json debe existir en el run_dir del plan
    
    Flujo:
    1) Validar ENVIRONMENT
    2) Cargar storage_state del plan
    3) Crear browser context con storage_state
    4) Verificar autenticación
    5) Registrar run en HeadfulRunManager
    """
    # 1) Validar ENVIRONMENT
    if os.getenv("ENVIRONMENT", "").lower() != "dev":
        return {
            "status": "error",
            "error_code": "environment_violation",
            "message": "HeadfulRunManager solo está disponible en ENVIRONMENT=dev",
            "details": None,
        }
    
    plan_id = request.plan_id
    confirm_token = request.confirm_token
    
    # 2) Validar confirm_token
    plan_meta_path = Path(DATA_DIR) / "runs" / plan_id / "plan_meta.json"
    if not plan_meta_path.exists():
        return {
            "status": "error",
            "error_code": "plan_not_found",
            "message": f"Plan {plan_id} no encontrado",
            "details": None,
        }
    
    try:
        with open(plan_meta_path, "r", encoding="utf-8") as f:
            plan_meta = json.load(f)
    except Exception as e:
        return {
            "status": "error",
            "error_code": "plan_meta_invalid",
            "message": f"No se pudo leer plan_meta.json: {e}",
            "details": None,
        }
    
    stored_token = plan_meta.get("confirm_token")
    if not stored_token or confirm_token != stored_token:
        return {
            "status": "error",
            "error_code": "invalid_confirm_token",
            "message": "confirm_token no válido",
            "details": None,
        }
    
    # 3) Resolver storage_state_path
    from backend.shared.path_utils import safe_path_join
    run_finished_path = Path(DATA_DIR) / "runs" / plan_id / "run_finished.json"
    storage_state_path = None
    
    if run_finished_path.exists():
        try:
            with open(run_finished_path, "r", encoding="utf-8") as f:
                run_finished = json.load(f)
                artifacts_data = run_finished.get("artifacts", {})
                storage_state_rel = artifacts_data.get("storage_state_path")
                if storage_state_rel:
                    storage_state_path = safe_path_join(Path(DATA_DIR), storage_state_rel)
        except Exception as e:
            pass
    
    if not storage_state_path or not storage_state_path.exists():
        storage_state_path = Path(DATA_DIR) / "runs" / plan_id / "storage_state.json"
    
    if not storage_state_path.exists():
        return {
            "status": "error",
            "error_code": "missing_storage_state",
            "message": "No hay sesión guardada (storage_state.json). Ejecuta primero revisión READ-ONLY para generar storage_state.",
            "details": f"Buscado en: {storage_state_path}",
        }
    
    # 4) Verificar si el run ya está activo
    manager = HeadfulRunManager()
    if manager.has_run(plan_id):
        return {
            "status": "ok",
            "run_id": plan_id,
            "message": "Headful run ya estaba activo. Reutilizando navegador existente.",
            "already_active": True,
        }
    
    # 5) Crear browser y verificar autenticación
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            context = browser.new_context(
                storage_state=str(storage_state_path),
                viewport={"width": 1600, "height": 1000},
            )
            page = context.new_page()
            
            # Navegar y verificar autenticación
            store = ConfigStoreV1(base_dir=DATA_DIR)
            platforms = store.load_platforms()
            plat = next((p for p in platforms.platforms if p.key == "egestiona"), None)
            if not plat:
                browser.close()
                raise RuntimeError("Platform egestiona no encontrado")
            
            base_url = plat.base_url or plat.login_url or "https://coordinate.egestiona.es"
            login_url = plat.login_url or f"{base_url}/extranet_subcontratas/default_contenido.asp"
            
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            
            # Verificar autenticación
            auth_verified = False
            try:
                frame = page.frame(name="nm_contenido")
                if frame:
                    auth_verified = True
            except Exception:
                pass
            
            if not auth_verified:
                time.sleep(3)
                current_url = page.url
                if "login" not in current_url.lower() and "default_contenido" in current_url.lower():
                    auth_verified = True
            
            if not auth_verified:
                browser.close()
                return {
                    "status": "error",
                    "error_code": "storage_state_not_authenticated",
                    "message": "No se pudo verificar autenticación con storage_state",
                    "details": "El storage_state puede estar expirado o ser inválido. Ejecuta nuevamente revisión READ-ONLY.",
                }
            
            # Registrar evento de autenticación (antes de crear el run)
            # Nota: El run aún no existe, así que creamos un timeline temporal
            # que luego se asociará al run
            
            # 6) Registrar run (NO cerrar browser)
            run = manager.start_run(
                run_id=plan_id,
                storage_state_path=str(storage_state_path),
                browser=browser,
                context=context,
                page=page,
            )
            
            # Registrar eventos en timeline (el run ya tiene un evento inicial de RUN_STARTED)
            run.timeline.add_event(EventType.INFO, "Navegador iniciado (headless=False)")
            run.timeline.add_event(EventType.INFO, f"Storage state cargado desde: {storage_state_path.name}")
            run.timeline.add_event(EventType.SUCCESS, "Autenticación verificada exitosamente")
            run.timeline.add_event(EventType.INFO, "Run headful listo para acciones")
            
            return {
                "status": "ok",
                "run_id": plan_id,
                "message": "Headful run iniciado. Navegador visible.",
                "already_active": False,
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error_code": "runtime_error",
            "message": f"Error durante inicio de run headful: {str(e)}",
            "details": None,
        }


@router.post("/runs/egestiona/execute_action_headful")
async def execute_action_headful(request: ExecuteActionHeadfulRequest, http_request: Request = None):
    """
    Ejecuta una acción REAL dentro de un run headful persistente.
    
    Requisitos:
    - run_id debe estar activo en HeadfulRunManager
    - Header X-USE-REAL-UPLOADER=1
    - ENVIRONMENT=dev
    - max_uploads=1
    - len(allowlist_type_ids)=1
    """
    # 1) Validar gate
    gate_error = _validate_real_upload_gate_for_action(request, http_request)
    if gate_error:
        return gate_error
    
    run_id = request.run_id
    
    # 2) Recuperar run activo
    manager = HeadfulRunManager()
    run = manager.get_run(run_id)
    
    if run is None:
        return {
            "status": "error",
            "error_code": "headful_run_not_found",
            "message": f"Run headful {run_id} no está activo. Inicia primero con /start_headful_run",
            "details": None,
        }
    
    # Registrar evento de acción solicitada
    run.timeline.add_event(
        EventType.ACTION,
        "Acción de subida solicitada",
        metadata={
            "allowlist_type_ids": request.allowlist_type_ids,
            "max_uploads": request.max_uploads,
            "min_confidence": request.min_confidence,
        }
    )
    
    # 3) Validar confirm_token
    plan_meta_path = Path(DATA_DIR) / "runs" / run_id / "plan_meta.json"
    if plan_meta_path.exists():
        try:
            with open(plan_meta_path, "r", encoding="utf-8") as f:
                plan_meta = json.load(f)
                stored_token = plan_meta.get("confirm_token")
                if stored_token and request.confirm_token != stored_token:
                    return {
                        "status": "error",
                        "error_code": "invalid_confirm_token",
                        "message": "confirm_token no válido",
                        "details": None,
                    }
        except Exception:
            pass
    
    # 4) Cargar plan
    plan_path = Path(DATA_DIR) / "runs" / run_id / "plan.json"
    if not plan_path.exists():
        plan_path = Path(DATA_DIR) / "runs" / run_id / "evidence" / "submission_plan.json"
    
    if not plan_path.exists():
        return {
            "status": "error",
            "error_code": "plan_file_not_found",
            "message": f"Plan file no encontrado en {run_id}",
            "details": None,
        }
    
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
            plan_items = plan_data.get("plan", [])
    except Exception as e:
        return {
            "status": "error",
            "error_code": "plan_load_error",
            "message": f"Error al cargar plan: {e}",
            "details": None,
        }
    
    # 5) Aplicar guardrails
    eligible_items = []
    skipped_items = []
    
    for item in plan_items:
        matched_doc = item.get("matched_doc", {})
        type_id = matched_doc.get("type_id")
        if not type_id or type_id not in request.allowlist_type_ids:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": "not_in_allowlist",
            })
            continue
        
        confidence = matched_doc.get("validity", {}).get("confidence", 0.0)
        if confidence < request.min_confidence:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": "below_min_confidence",
            })
            continue
        
        decision = item.get("decision", {})
        if decision.get("action") != "AUTO_SUBMIT_OK":
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": f"decision.action={decision.get('action')} != AUTO_SUBMIT_OK",
            })
            continue
        
        eligible_items.append(item)
    
    items_to_upload = eligible_items[:request.max_uploads]
    
    if len(items_to_upload) != 1:
        return {
            "status": "error",
            "error_code": "invalid_item_count",
            "message": f"Debe haber exactamente 1 item elegible para subir, encontrados: {len(items_to_upload)}",
            "details": None,
        }
    
    # 6) Ejecutar RealUploader con page viva
    execution_dir = Path(DATA_DIR) / "runs" / run_id / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_items = []
    failed_items = []
    
    try:
        # Registrar inicio de ejecución
        run.timeline.add_event(
            EventType.ACTION,
            f"Iniciando subida de documento: type_id={items_to_upload[0].get('matched_doc', {}).get('type_id')}",
            metadata={"item_index": 0}
        )
        
        uploader = EgestionaRealUploader(execution_dir)
        item = items_to_upload[0]
        requirement_id = item.get("pending_ref", {}).get("row_index", 0)
        
        result = uploader.upload_one_real(
            run.page,  # Usar page viva del run
            item,
            requirement_id=f"req_{requirement_id}",
        )
        
        if result["success"]:
            uploaded_items.append({
                "item": item,
                "outcome": "uploaded",
                "upload_id": result.get("upload_id"),
                "duration_ms": result.get("duration_ms"),
                "reason": result.get("reason", "upload_success"),
                "portal_reference": result.get("portal_reference"),
            })
            # Registrar éxito
            run.timeline.add_event(
                EventType.SUCCESS,
                f"Subida completada exitosamente: portal_reference={result.get('portal_reference', 'N/A')}",
                metadata={
                    "upload_id": result.get("upload_id"),
                    "duration_ms": result.get("duration_ms"),
                }
            )
        else:
            failed_items.append({
                "item": item,
                "outcome": "failed",
                "reason": result.get("reason", "upload_failed"),
                "error": result.get("error"),
            })
            # Registrar error
            run.timeline.add_event(
                EventType.ERROR,
                f"Subida fallida: {result.get('reason', 'Error desconocido')}",
                metadata={"error": result.get("error")}
            )
    except Exception as e:
        # Registrar excepción
        run.timeline.add_event(
            EventType.ERROR,
            f"Excepción durante ejecución: {str(e)}",
            metadata={"exception_type": type(e).__name__}
        )
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Error durante ejecución: {str(e)}",
            "details": None,
        }
    
    # 7) Generar execution_meta.json
    execution_meta = {
        "uploader_type": "real",
        "allowlist_type_ids": request.allowlist_type_ids,
        "min_confidence": request.min_confidence,
        "max_uploads": request.max_uploads,
        "executed_at": datetime.utcnow().isoformat(),
        "plan_id": run_id,
        "headful_run": True,
    }
    execution_meta_path = execution_dir / "execution_meta.json"
    try:
        with open(execution_meta_path, "w", encoding="utf-8") as f:
            json.dump(execution_meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass
    
    # 8) Generar respuesta (NO cerrar browser)
    summary = {
        "total": len(plan_items),
        "eligible": len(eligible_items),
        "uploaded": len(uploaded_items),
        "skipped": len(skipped_items),
        "failed": len(failed_items),
    }
    
    all_results = uploaded_items + failed_items + skipped_items
    
    return {
        "status": "ok",
        "run_id": run_id,
        "executed": True,
        "summary": summary,
        "items": all_results,
        "uploader_type": "real",
        "headful": True,
        "browser_still_open": True,
    }


@router.post("/runs/egestiona/close_headful_run")
async def close_headful_run(request: CloseHeadfulRunRequest):
    """
    Cierra un run headful persistente.
    
    Cierra el navegador y elimina el run del manager.
    """
    run_id = request.run_id
    
    manager = HeadfulRunManager()
    run = manager.get_run(run_id)
    
    if run is None:
        return {
            "status": "error",
            "error_code": "headful_run_not_found",
            "message": f"Run headful {run_id} no está activo",
            "details": None,
        }
    
    # Registrar evento de cierre
    run.timeline.add_event(EventType.INFO, "Cerrando run headful")
    
    closed = manager.close_run(run_id)
    
    return {
        "status": "ok",
        "run_id": run_id,
        "message": "Run headful cerrado. Navegador cerrado.",
    }


@router.get("/runs/egestiona/headful_run_status")
async def get_headful_run_status(run_id: str):
    """
    Obtiene el estado y timeline de un run headful.
    
    Retorna:
    - status: "active" | "closed"
    - started_at: timestamp
    - events: lista de eventos del timeline
    - risk_level: "low" | "medium" | "high"
    """
    manager = HeadfulRunManager()
    run = manager.get_run(run_id)
    
    if run is None:
        return {
            "status": "error",
            "error_code": "headful_run_not_found",
            "message": f"Run headful {run_id} no está activo",
            "details": None,
        }
    
    risk_level = run.timeline.get_risk_level()
    has_errors = run.timeline.has_errors()
    
    return {
        "status": "ok",
        "run_id": run_id,
        "run_status": "active",
        "started_at": run.started_at,
        "started_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(run.started_at)),
        "events": run.timeline.get_events_dict(),
        "event_count": run.timeline.get_event_count(),
        "risk_level": risk_level,
        "has_errors": has_errors,
        "last_event": run.timeline.get_last_event().to_dict() if run.timeline.get_last_event() else None,
    }
