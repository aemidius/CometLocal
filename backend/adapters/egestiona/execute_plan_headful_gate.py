"""
Endpoint de ejecución real headful con sesión reutilizada.

Usa storage_state guardado en build_submission_plan_readonly para
reutilizar sesión autenticada sin hacer login de nuevo.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import time
import shutil
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.config import DATA_DIR
from backend.adapters.egestiona.execute_plan_gate import ExecutePlanRequest
from backend.adapters.egestiona.real_uploader import EgestionaRealUploader
from backend.repository.config_store_v1 import ConfigStoreV1

router = APIRouter(tags=["egestiona"])


def _validate_real_upload_gate(request: ExecutePlanRequest, http_request: Request = None) -> dict:
    """
    Valida guardrails para uploads reales.
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
    
    # Validar guardrails obligatorios
    try:
        request.validate()
    except ValueError as e:
        return {
            "status": "error",
            "error_code": "validation_error",
            "message": str(e),
            "details": None,
        }
    
    # Guardrail extra: max_uploads == 1
    if request.max_uploads != 1:
        return {
            "status": "error",
            "error_code": "REAL_UPLOAD_GUARDRAIL_VIOLATION",
            "message": f"max_uploads debe ser 1 para uploads reales, recibido: {request.max_uploads}",
            "details": None,
        }
    
    # Guardrail extra: len(allowlist_type_ids) == 1
    if len(request.allowlist_type_ids) != 1:
        return {
            "status": "error",
            "error_code": "REAL_UPLOAD_GUARDRAIL_VIOLATION",
            "message": f"allowlist_type_ids debe tener exactamente 1 tipo para uploads reales, recibido: {len(request.allowlist_type_ids)}",
            "details": None,
        }
    
    return None  # Pasa validación


@router.post("/runs/egestiona/execute_plan_headful")
async def egestiona_execute_plan_headful(request: ExecutePlanRequest, http_request: Request = None):
    """
    Ejecuta un plan de envío REAL usando sesión autenticada reutilizada (headful).
    
    Requisitos:
    - Header X-USE-REAL-UPLOADER=1
    - ENVIRONMENT=dev
    - max_uploads=1
    - len(allowlist_type_ids)=1
    - storage_state.json debe existir en el run_dir del plan
    
    Flujo:
    1) Validar gate
    2) Cargar storage_state del plan
    3) Crear browser context con storage_state
    4) Verificar autenticación
    5) Ejecutar RealUploader con page viva
    6) Generar evidencias
    """
    # 1) Validar gate
    gate_error = _validate_real_upload_gate(request, http_request)
    if gate_error:
        return gate_error
    
    plan_id = request.plan_id
    confirm_token = request.confirm_token
    allowlist_type_ids = request.allowlist_type_ids
    max_uploads = request.max_uploads
    min_confidence = request.min_confidence
    
    # 2) Validar confirm_token (reutilizar lógica de execute_plan_gate)
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
    
    # Validar TTL
    expires_at_str = plan_meta.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            if datetime.utcnow() > expires_at:
                return {
                    "status": "error",
                    "error_code": "confirm_token_expired",
                    "message": f"confirm_token expiró a las {expires_at_str}",
                    "details": None,
                }
        except Exception as e:
            return {
                "status": "error",
                "error_code": "token_ttl_parse_error",
                "message": f"Error al validar TTL: {e}",
                "details": None,
            }
    
    # 3) Cargar plan
    plan_path = Path(DATA_DIR) / "runs" / plan_id / "plan.json"
    if not plan_path.exists():
        plan_path = Path(DATA_DIR) / "runs" / plan_id / "evidence" / "submission_plan.json"
    
    if not plan_path.exists():
        return {
            "status": "error",
            "error_code": "plan_file_not_found",
            "message": f"Plan file no encontrado en {plan_id}",
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
    
    # 4) Aplicar guardrails (igual que execute_plan_gate)
    eligible_items = []
    skipped_items = []
    
    for item in plan_items:
        matched_doc = item.get("matched_doc", {})
        type_id = matched_doc.get("type_id")
        if not type_id or type_id not in allowlist_type_ids:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": "not_in_allowlist",
            })
            continue
        
        confidence = matched_doc.get("validity", {}).get("confidence", 0.0)
        if confidence < min_confidence:
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
    
    items_to_upload = eligible_items[:max_uploads]
    if len(eligible_items) > max_uploads:
        for item in eligible_items[max_uploads:]:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": f"max_uploads={max_uploads} alcanzado",
            })
    
    # Validar que hay exactamente 1 item para subir
    if len(items_to_upload) != 1:
        return {
            "status": "error",
            "error_code": "invalid_item_count",
            "message": f"Debe haber exactamente 1 item elegible para subir, encontrados: {len(items_to_upload)}",
            "details": None,
        }
    
    # 5) Resolver storage_state_path
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
    
    # Si no está en run_finished.json, intentar path estándar
    if not storage_state_path or not storage_state_path.exists():
        storage_state_path = Path(DATA_DIR) / "runs" / plan_id / "storage_state.json"
    
    if not storage_state_path.exists():
        return {
            "status": "error",
            "error_code": "missing_storage_state",
            "message": "No hay sesión guardada (storage_state.json). Ejecuta primero revisión READ-ONLY para generar storage_state.",
            "details": f"Buscado en: {storage_state_path}",
        }
    
    # 6) Ejecutar con Playwright y RealUploader
    execution_dir = Path(DATA_DIR) / "runs" / plan_id / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_items = []
    failed_items = []
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            context = browser.new_context(
                storage_state=str(storage_state_path),
                viewport={"width": 1600, "height": 1000},
            )
            page = context.new_page()
            
            try:
                # 7) Verificar autenticación navegando a e-gestiona
                store = ConfigStoreV1(base_dir=DATA_DIR)
                platforms = store.load_platforms()
                plat = next((p for p in platforms.platforms if p.key == "egestiona"), None)
                if not plat:
                    raise RuntimeError("Platform egestiona no encontrado")
                
                # Obtener URL base
                base_url = plat.base_url or plat.login_url or "https://coordinate.egestiona.es"
                login_url = plat.login_url or f"{base_url}/extranet_subcontratas/default_contenido.asp"
                
                # Navegar y verificar autenticación
                page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                
                # Esperar indicador de autenticación (frame nm_contenido o selector de logout)
                auth_verified = False
                try:
                    # Intentar encontrar frame nm_contenido (indica que está autenticado)
                    frame = page.frame(name="nm_contenido")
                    if frame:
                        auth_verified = True
                except Exception:
                    pass
                
                if not auth_verified:
                    # Intentar buscar selector de logout o usuario
                    try:
                        logout_selectors = [
                            'text=/desconectar|logout|cerrar sesión/i',
                            'a[href*="logout"]',
                            'a[href*="desconectar"]',
                        ]
                        for selector in logout_selectors:
                            if page.locator(selector).count() > 0:
                                auth_verified = True
                                break
                    except Exception:
                        pass
                
                if not auth_verified:
                    # Timeout: esperar a que cargue la página
                    time.sleep(3)
                    # Verificar URL (si no está en login, probablemente autenticado)
                    current_url = page.url
                    if "login" not in current_url.lower() and "default_contenido" in current_url.lower():
                        auth_verified = True
                
                if not auth_verified:
                    raise RuntimeError("storage_state_not_authenticated: No se pudo verificar autenticación con storage_state")
                
                # 8) Screenshot antes de ejecutar (obligatorio)
                before_upload_path = execution_dir / "before_upload.png"
                try:
                    page.screenshot(path=str(before_upload_path), full_page=True)
                except Exception as e:
                    print(f"Warning: No se pudo capturar before_upload.png: {e}")
                
                # 9) Ejecutar RealUploader
                uploader = EgestionaRealUploader(execution_dir)
                item = items_to_upload[0]
                requirement_id = item.get("pending_ref", {}).get("row_index", 0)
                
                result = uploader.upload_one_real(
                    page,
                    item,
                    requirement_id=f"req_{requirement_id}",
                )
                
                # 10) Copiar evidencias obligatorias a execution_dir directamente
                # RealUploader guarda en execution_dir / "items" / requirement_id /
                item_evidence_dir = execution_dir / "items" / f"req_{requirement_id}"
                if item_evidence_dir.exists():
                    # Copiar before_upload.png si existe (o usar el que ya capturamos)
                    item_before = item_evidence_dir / "before_upload.png"
                    if item_before.exists() and not before_upload_path.exists():
                        shutil.copy2(item_before, before_upload_path)
                    
                    # Copiar after_upload.png
                    after_upload_path = execution_dir / "after_upload.png"
                    item_after = item_evidence_dir / "after_upload.png"
                    if item_after.exists():
                        shutil.copy2(item_after, after_upload_path)
                    
                    # Copiar upload_log.txt
                    upload_log_path = execution_dir / "upload_log.txt"
                    item_log = item_evidence_dir / "upload_log.txt"
                    if item_log.exists():
                        shutil.copy2(item_log, upload_log_path)
                
                if result["success"]:
                    uploaded_items.append({
                        "item": item,
                        "outcome": "uploaded",
                        "upload_id": result.get("upload_id"),
                        "duration_ms": result.get("duration_ms"),
                        "reason": result.get("reason", "upload_success"),
                        "portal_reference": result.get("portal_reference"),
                    })
                else:
                    failed_items.append({
                        "item": item,
                        "outcome": "failed",
                        "reason": result.get("reason", "upload_failed"),
                        "error": result.get("error"),
                    })
                
            finally:
                browser.close()
                
    except RuntimeError as e:
        error_msg = str(e)
        if "storage_state_not_authenticated" in error_msg or "No se pudo verificar autenticación" in error_msg:
            return {
                "status": "error",
                "error_code": "storage_state_not_authenticated",
                "message": f"No se pudo verificar autenticación con storage_state: {error_msg}",
                "details": "El storage_state puede estar expirado o ser inválido. Ejecuta nuevamente revisión READ-ONLY.",
            }
        return {
            "status": "error",
            "error_code": "runtime_error",
            "message": error_msg,
            "details": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Error durante ejecución: {str(e)}",
            "details": None,
        }
    
    # 9) Generar execution_meta.json
    execution_meta = {
        "uploader_type": "real",
        "allowlist_type_ids": allowlist_type_ids,
        "min_confidence": min_confidence,
        "max_uploads": max_uploads,
        "executed_at": datetime.utcnow().isoformat(),
        "plan_id": plan_id,
        "storage_state_used": str(storage_state_path.relative_to(Path(DATA_DIR))) if storage_state_path else None,
    }
    execution_meta_path = execution_dir / "execution_meta.json"
    try:
        with open(execution_meta_path, "w", encoding="utf-8") as f:
            json.dump(execution_meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: No se pudo escribir execution_meta.json: {e}")
    
    # 10) Generar respuesta
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
        "plan_id": plan_id,
        "executed": True,
        "summary": summary,
        "items": all_results,
        "uploader_type": "real",
        "headful": True,
    }
