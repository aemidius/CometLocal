from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from backend.repository.submission_rules_store_v1 import SubmissionRulesStoreV1
from backend.shared.document_repository_v1 import SubmissionRuleV1


router = APIRouter(
    prefix="/api/repository/rules",
    tags=["submission-rules"],
)


@router.get("", response_model=List[SubmissionRuleV1])
async def list_rules(include_disabled: bool = False) -> List[SubmissionRuleV1]:
    """Lista todas las reglas de envío. Siempre devuelve un array (puede estar vacío)."""
    try:
        store = SubmissionRulesStoreV1()
        rules = store.list_rules(include_disabled=include_disabled)
        # Asegurar que siempre es una lista
        if not isinstance(rules, list):
            return []
        return rules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer reglas: {str(e)}")


@router.get("/{rule_id}", response_model=SubmissionRuleV1)
async def get_rule(rule_id: str) -> SubmissionRuleV1:
    """Obtiene una regla por ID."""
    store = SubmissionRulesStoreV1()
    rule = store.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return rule


@router.post("", response_model=SubmissionRuleV1)
async def create_rule(rule: SubmissionRuleV1) -> SubmissionRuleV1:
    """Crea una nueva regla de envío."""
    store = SubmissionRulesStoreV1()
    try:
        return store.create_rule(rule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{rule_id}", response_model=SubmissionRuleV1)
async def update_rule(rule_id: str, rule: SubmissionRuleV1) -> SubmissionRuleV1:
    """Actualiza una regla existente."""
    store = SubmissionRulesStoreV1()
    try:
        return store.update_rule(rule_id, rule)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class DuplicateRuleRequest(BaseModel):
    new_rule_id: str


@router.post("/{rule_id}/duplicate", response_model=SubmissionRuleV1)
async def duplicate_rule(
    rule_id: str,
    request: DuplicateRuleRequest
) -> SubmissionRuleV1:
    """Duplica una regla con nuevo ID."""
    store = SubmissionRulesStoreV1()
    try:
        return store.duplicate_rule(rule_id, request.new_rule_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str) -> dict:
    """Elimina una regla."""
    store = SubmissionRulesStoreV1()
    try:
        store.delete_rule(rule_id)
        return {"status": "ok", "message": f"Rule {rule_id} deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))





