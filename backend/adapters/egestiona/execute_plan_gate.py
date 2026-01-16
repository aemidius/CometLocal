"""
Endpoint de ejecución de plan con guardrails y confirmación.

Separado de flows.py para mantener la organización.
"""

from __future__ import annotations

from pathlib import Path
import json
import hmac
import hashlib
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import os
from backend.config import DATA_DIR
from backend.adapters.egestiona.fake_uploader import FakeConnectorUploader

router = APIRouter(tags=["egestiona"])


class ExecutePlanRequest(BaseModel):
    plan_id: str
    confirm_token: str
    allowlist_type_ids: List[str]
    max_uploads: int
    min_confidence: float = 0.80
    headless: bool = True
    use_fake_uploader: bool = True
    
    def validate(self):
        """Validar guardrails obligatorios."""
        if not self.allowlist_type_ids or len(self.allowlist_type_ids) == 0:
            raise ValueError("allowlist_type_ids es obligatorio y no puede estar vacío")
        if self.max_uploads is None or self.max_uploads < 1:
            raise ValueError("max_uploads es obligatorio y debe ser >= 1")
        if self.min_confidence is None or self.min_confidence < 0.0 or self.min_confidence > 1.0:
            raise ValueError("min_confidence es obligatorio y debe estar entre 0.0 y 1.0")


@router.post("/runs/egestiona/execute_submission_plan")
async def egestiona_execute_submission_plan(request: ExecutePlanRequest, http_request: Request = None):
    """
    Ejecuta un plan de envío con guardrails estrictos y confirmación.
    
    Guardrails:
    - confirm_token: Debe ser válido y no expirado (TTL 30 min)
    - allowlist_type_ids: Solo se suben documentos de estos tipos
    - max_uploads: Límite duro de subidas
    - min_confidence: Solo items con confidence >= min_confidence
    
    Por defecto usa FakeConnectorUploader (no toca el portal real).
    Solo en producción (use_fake_uploader=false) se sube realmente.
    
    Response:
    - status: "ok" | "error"
    - summary: {total, eligible, uploaded, skipped, failed}
    - items: array con outcome y reason por item
    """
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
    
    # Verificar si se solicita RealUploader (header presente)
    real_uploader_requested = False
    if http_request:
        real_uploader_header = http_request.headers.get("X-USE-REAL-UPLOADER", "0")
        if real_uploader_header == "1":
            real_uploader_requested = True
    
    plan_id = request.plan_id
    confirm_token = request.confirm_token
    allowlist_type_ids = request.allowlist_type_ids
    max_uploads = request.max_uploads
    min_confidence = request.min_confidence
    
    # Guardrail extra de seguridad para uploads reales (si se solicita)
    if real_uploader_requested:
        if max_uploads != 1:
            return {
                "status": "error",
                "error_code": "REAL_UPLOAD_GUARDRAIL_VIOLATION",
                "message": f"max_uploads debe ser 1 para uploads reales, recibido: {max_uploads}",
                "details": None,
            }
        if len(allowlist_type_ids) != 1:
            return {
                "status": "error",
                "error_code": "REAL_UPLOAD_GUARDRAIL_VIOLATION",
                "message": f"allowlist_type_ids debe tener exactamente 1 tipo para uploads reales, recibido: {len(allowlist_type_ids)}",
                "details": None,
            }
        # Verificar ENVIRONMENT=dev
        if os.getenv("ENVIRONMENT", "").lower() != "dev":
            return {
                "status": "error",
                "error_code": "REAL_UPLOAD_ENVIRONMENT_VIOLATION",
                "message": "RealUploader solo está disponible en ENVIRONMENT=dev",
                "details": None,
            }
        use_real_uploader = True
        use_fake_uploader = False
    else:
        use_real_uploader = False
        use_fake_uploader = request.use_fake_uploader  # Usar el valor del request
    
    # 1) Validar confirm_token
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
    
    # Validar token
    stored_token = plan_meta.get("confirm_token")
    stored_checksum = plan_meta.get("plan_checksum")
    created_at_str = plan_meta.get("created_at")
    expires_at_str = plan_meta.get("expires_at")
    
    if not stored_token or not stored_checksum:
        return {
            "status": "error",
            "error_code": "plan_meta_incomplete",
            "message": "Plan no tiene confirm_token o checksum",
            "details": None,
        }
    
    # Validar token HMAC
    if confirm_token != stored_token:
        return {
            "status": "error",
            "error_code": "invalid_confirm_token",
            "message": "confirm_token no válido",
            "details": None,
        }
    
    # Validar TTL
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
    
    # 2) Cargar plan
    plan_path = Path(DATA_DIR) / "runs" / plan_id / "plan.json"
    if not plan_path.exists():
        # Fallback a submission_plan.json
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
    
    # 3) Aplicar guardrails
    eligible_items = []
    skipped_items = []
    
    for item in plan_items:
        # Guardrail: allowlist_type_ids
        matched_doc = item.get("matched_doc", {})
        type_id = matched_doc.get("type_id")
        if not type_id or type_id not in allowlist_type_ids:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": "not_in_allowlist",
            })
            continue
        
        # Guardrail: min_confidence
        confidence = matched_doc.get("validity", {}).get("confidence", 0.0)
        if confidence < min_confidence:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": "below_min_confidence",
            })
            continue
        
        # Guardrail: solo AUTO_SUBMIT_OK
        decision = item.get("decision", {})
        if decision.get("action") != "AUTO_SUBMIT_OK":
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": f"decision.action={decision.get('action')} != AUTO_SUBMIT_OK",
            })
            continue
        
        eligible_items.append(item)
    
    # Guardrail: max_uploads
    items_to_upload = eligible_items[:max_uploads]
    if len(eligible_items) > max_uploads:
        for item in eligible_items[max_uploads:]:
            skipped_items.append({
                "item": item,
                "outcome": "skipped",
                "reason": f"max_uploads={max_uploads} alcanzado",
            })
    
    # 4) Ejecutar uploads (seleccionar uploader según modo)
    execution_dir = Path(DATA_DIR) / "runs" / plan_id / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_items = []
    failed_items = []
    
    if use_real_uploader:
        # RealUploader requiere Playwright page autenticada
        # Por ahora, esto requiere que se pase la página desde fuera
        # En este sprint, asumimos que se llama desde un contexto que tiene la página
        from backend.adapters.egestiona.real_uploader import EgestionaRealUploader
        uploader = EgestionaRealUploader(execution_dir)
        
        # NOTA: RealUploader requiere página autenticada
        # Por ahora, retornamos error indicando que se necesita implementar
        # la integración con el contexto de ejecución que tiene la página
        return {
            "status": "error",
            "error_code": "real_uploader_not_implemented",
            "message": "RealUploader requiere integración con contexto de ejecución que tenga página autenticada. Use FakeUploader para pruebas.",
            "details": "En desarrollo: integración con run_execute_submission_plan_scoped_headful",
        }
    else:
        # FakeUploader (default)
        uploader = FakeConnectorUploader(execution_dir)
        
        for item in items_to_upload:
            try:
                result = uploader.upload_one(item)
                uploaded_items.append({
                    "item": item,
                    "outcome": "uploaded" if result["success"] else "failed",
                    "upload_id": result.get("upload_id"),
                    "duration_ms": result.get("duration_ms"),
                    "reason": result.get("reason", "upload_success"),
                    "portal_reference": result.get("portal_reference"),
                })
            except Exception as e:
                failed_items.append({
                    "item": item,
                    "outcome": "failed",
                    "reason": f"upload_error: {str(e)}",
                })
    
    # 5) Generar execution_meta.json
    execution_meta = {
        "uploader_type": "real" if use_real_uploader else "fake",
        "allowlist_type_ids": allowlist_type_ids,
        "min_confidence": min_confidence,
        "max_uploads": max_uploads,
        "executed_at": datetime.utcnow().isoformat(),
        "plan_id": plan_id,
    }
    execution_meta_path = execution_dir / "execution_meta.json"
    try:
        with open(execution_meta_path, "w", encoding="utf-8") as f:
            json.dump(execution_meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: No se pudo escribir execution_meta.json: {e}")
    
    # 6) Generar respuesta
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
        "use_fake_uploader": use_fake_uploader,
        "uploader_type": "real" if use_real_uploader else "fake",
    }
