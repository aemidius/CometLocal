"""
Fixture determinista para testing de build_submission_plan_readonly.

Genera un plan con items predefinidos para validar guardrails y ejecución.
"""

from __future__ import annotations

import json
import time
import uuid
import hashlib
import hmac
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, Any, List

from backend.config import DATA_DIR


def build_fixture_plan(base_dir: str | Path = "data") -> str:
    """
    Genera un plan fixture determinista con 3 items:
    - item1: type_id="T_FIX_OK", confidence=0.95, AUTO_SUBMIT_OK (elegible)
    - item2: type_id="T_FIX_LOW", confidence=0.40, AUTO_SUBMIT_OK (baja confianza)
    - item3: type_id="T_FIX_BLOCKED", confidence=0.90, REVIEW_REQUIRED (no elegible)
    
    Returns:
        run_id del plan generado
    """
    base = Path(base_dir)
    run_id = f"r_{uuid.uuid4().hex}"
    run_dir = base / "runs" / run_id
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    started = time.time()
    today = date.today()
    
    # Generar items fixture
    fixture_items = [
        {
            "pending_ref": {
                "tipo_doc": "Seguro de Responsabilidad Civil",
                "elemento": "Trabajador",
                "empresa": "FIXTURE_COMPANY",
                "row_index": 0
            },
            "expected_doc_type_text": "Seguro de Responsabilidad Civil Trabajador",
            "matched_doc": {
                "doc_id": "DOC_FIX_OK",
                "type_id": "T_FIX_OK",
                "file_name": "fixture_ok.pdf",
                "status": "valid",
                "validity": {
                    "valid_from": today.isoformat(),
                    "valid_to": (today + timedelta(days=365)).isoformat(),
                    "confidence": 0.95,
                    "has_override": False
                }
            },
            "proposed_fields": {
                "fecha_inicio_vigencia": today.isoformat(),
                "fecha_fin_vigencia": (today + timedelta(days=365)).isoformat()
            },
            "decision": {
                "action": "AUTO_SUBMIT_OK",
                "confidence": 0.95,
                "reasons": ["Fixture item OK"],
                "blocking_issues": []
            },
            "pending_fingerprint": f"FIXTURE_OK_{run_id}",
            "rule_form": None
        },
        {
            "pending_ref": {
                "tipo_doc": "Seguro de Vida",
                "elemento": "Trabajador",
                "empresa": "FIXTURE_COMPANY",
                "row_index": 1
            },
            "expected_doc_type_text": "Seguro de Vida Trabajador",
            "matched_doc": {
                "doc_id": "DOC_FIX_LOW",
                "type_id": "T_FIX_LOW",
                "file_name": "fixture_low.pdf",
                "status": "valid",
                "validity": {
                    "valid_from": today.isoformat(),
                    "valid_to": (today + timedelta(days=365)).isoformat(),
                    "confidence": 0.40,
                    "has_override": False
                }
            },
            "proposed_fields": {
                "fecha_inicio_vigencia": today.isoformat(),
                "fecha_fin_vigencia": (today + timedelta(days=365)).isoformat()
            },
            "decision": {
                "action": "AUTO_SUBMIT_OK",
                "confidence": 0.40,
                "reasons": ["Fixture item LOW confidence"],
                "blocking_issues": []
            },
            "pending_fingerprint": f"FIXTURE_LOW_{run_id}",
            "rule_form": None
        },
        {
            "pending_ref": {
                "tipo_doc": "Certificado Médico",
                "elemento": "Trabajador",
                "empresa": "FIXTURE_COMPANY",
                "row_index": 2
            },
            "expected_doc_type_text": "Certificado Médico Trabajador",
            "matched_doc": {
                "doc_id": "DOC_FIX_BLOCKED",
                "type_id": "T_FIX_BLOCKED",
                "file_name": "fixture_blocked.pdf",
                "status": "valid",
                "validity": {
                    "valid_from": today.isoformat(),
                    "valid_to": (today + timedelta(days=365)).isoformat(),
                    "confidence": 0.90,
                    "has_override": False
                }
            },
            "proposed_fields": {
                "fecha_inicio_vigencia": today.isoformat(),
                "fecha_fin_vigencia": (today + timedelta(days=365)).isoformat()
            },
            "decision": {
                "action": "REVIEW_REQUIRED",
                "confidence": 0.90,
                "reasons": ["Fixture item requires review"],
                "blocking_issues": ["Review required"]
            },
            "pending_fingerprint": f"FIXTURE_BLOCKED_{run_id}",
            "rule_form": None
        }
    ]
    
    # Guardar submission_plan.json
    submission_plan_path = evidence_dir / "submission_plan.json"
    _safe_write_json(submission_plan_path, {"plan": fixture_items})
    
    # Generar checksum y confirm_token
    plan_items_for_checksum = []
    for item in fixture_items:
        plan_items_for_checksum.append({
            "pending_ref": item.get("pending_ref", {}),
            "matched_doc": {
                "doc_id": item.get("matched_doc", {}).get("doc_id"),
                "type_id": item.get("matched_doc", {}).get("type_id"),
            } if item.get("matched_doc") else None,
            "decision": item.get("decision", {}),
            "proposed_fields": item.get("proposed_fields", {}),
        })
    
    checksum_data = json.dumps(plan_items_for_checksum, sort_keys=True, ensure_ascii=False)
    plan_checksum = hashlib.sha256(checksum_data.encode('utf-8')).hexdigest()
    
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(minutes=30)
    
    secret_key = os.getenv("COMETLOCAL_PLAN_SECRET", "default-secret-key-change-in-production")
    
    token_payload = f"{run_id}:{plan_checksum}:{created_at.isoformat()}"
    confirm_token = hmac.new(
        secret_key.encode('utf-8'),
        token_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Guardar plan_meta.json
    plan_meta_path = run_dir / "plan_meta.json"
    _safe_write_json(
        plan_meta_path,
        {
            "plan_id": run_id,
            "plan_checksum": plan_checksum,
            "confirm_token": confirm_token,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "platform": "egestiona",
            "coordination": "FIXTURE",
            "company_key": "FIXTURE_COMPANY",
            "person_key": None,
            "scope": "both",
            "fixture": True,
        },
    )
    
    # Guardar plan.json
    plan_json_path = run_dir / "plan.json"
    _safe_write_json(plan_json_path, {"plan": fixture_items})
    
    # Guardar meta.json
    finished = time.time()
    meta_path = evidence_dir / "meta.json"
    _safe_write_json(
        meta_path,
        {
            "company_key": "FIXTURE_COMPANY",
            "person_key": None,
            "only_target": False,
            "limit": 3,
            "today": today.isoformat(),
            "pending_items_count": 3,
            "match_results_count": 3,
            "submission_plan_count": 3,
            "auto_submit_ok_count": 2,
            "review_required_count": 1,
            "no_match_count": 0,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
            "duration_ms": int((finished - started) * 1000),
            "plan_checksum": plan_checksum,
            "confirm_token": confirm_token,
            "fixture": True,
        },
    )
    
    return run_id


def _safe_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Escribe JSON de forma segura."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[FIXTURE] Error al escribir {path}: {e}")
