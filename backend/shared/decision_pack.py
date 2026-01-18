"""
SPRINT C2.18B: Decision Pack - Revisión humana sin romper PLAN/DECISION/EXECUTION.

Permite crear decisiones manuales (overrides) para items del plan sin modificar
el plan_id congelado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import hashlib
import json


class ManualDecisionAction(str, Enum):
    """Acciones manuales permitidas."""
    MARK_AS_MATCH = "MARK_AS_MATCH"  # Vincular doc local concreto como match
    FORCE_UPLOAD = "FORCE_UPLOAD"  # Forzar subida con archivo local
    SKIP = "SKIP"  # Declarar que no se sube


class ManualDecisionV1(BaseModel):
    """Decisión manual para un item del plan."""
    item_id: str = Field(..., description="ID del item en el plan (pending_item_key)")
    action: ManualDecisionAction = Field(..., description="Acción manual elegida")
    chosen_local_doc_id: Optional[str] = Field(
        None,
        description="ID del documento local elegido (para MARK_AS_MATCH)"
    )
    chosen_file_path: Optional[str] = Field(
        None,
        description="Ruta del archivo a subir (para FORCE_UPLOAD; relativa o absoluta)"
    )
    reason: str = Field(
        ...,
        description="Razón de la decisión (requerido para SKIP, recomendado en otros)"
    )
    decided_by: str = Field(
        default="human",
        description="Quién tomó la decisión (default: 'human')"
    )
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de la decisión"
    )


class DecisionPackV1(BaseModel):
    """Pack de decisiones manuales para un plan."""
    plan_id: str = Field(..., description="ID del plan al que aplica")
    decision_pack_id: str = Field(..., description="Hash estable del pack")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de creación"
    )
    decisions: List[ManualDecisionV1] = Field(
        default_factory=list,
        description="Lista de decisiones manuales"
    )

    @classmethod
    def create(
        cls,
        plan_id: str,
        decisions: List[ManualDecisionV1],
    ) -> "DecisionPackV1":
        """
        Crea un DecisionPackV1 y calcula su hash estable.
        
        El hash se basa en:
        - plan_id
        - decisions (item_id, action, chosen_local_doc_id/file_path, reason)
        - NO incluye decided_by ni decided_at para estabilidad
        """
        # Canonizar decisiones para hash (sin campos volátiles)
        canonical_decisions = []
        for d in decisions:
            canonical_decisions.append({
                "item_id": d.item_id,
                "action": d.action.value,
                "chosen_local_doc_id": d.chosen_local_doc_id,
                "chosen_file_path": d.chosen_file_path,
                "reason": d.reason,
            })
        
        # Ordenar por item_id para estabilidad
        canonical_decisions.sort(key=lambda x: x["item_id"])
        
        # Crear contenido canonizado para hash
        canonical_content = {
            "plan_id": plan_id,
            "decisions": canonical_decisions,
        }
        
        # Hash SHA256
        json_str = json.dumps(canonical_content, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(json_str.encode("utf-8"))
        decision_pack_id = f"pack_{hash_obj.hexdigest()[:16]}"
        
        return cls(
            plan_id=plan_id,
            decision_pack_id=decision_pack_id,
            decisions=decisions,
        )

    def get_decision_for_item(self, item_id: str) -> Optional[ManualDecisionV1]:
        """Obtiene la decisión manual para un item específico."""
        for decision in self.decisions:
            if decision.item_id == item_id:
                return decision
        return None

    def apply_to_decisions(
        self,
        plan_decisions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Aplica las decisiones manuales a las decisiones del plan.
        
        REGLAS:
        - MARK_AS_MATCH: convierte a AUTO_UPLOAD (si doc existe)
        - FORCE_UPLOAD: convierte a AUTO_UPLOAD con chosen_file_path
        - SKIP: convierte a DO_NOT_UPLOAD (o equivalente)
        
        Returns:
            Lista de decisiones modificadas
        """
        # Crear mapa de decisiones manuales por item_id
        manual_map = {d.item_id: d for d in self.decisions}
        
        # Aplicar overrides
        modified_decisions = []
        for plan_decision in plan_decisions:
            item_id = plan_decision.get("pending_item_key") or plan_decision.get("item_id")
            if not item_id:
                # Mantener decisión original si no tiene item_id
                modified_decisions.append(plan_decision)
                continue
            
            manual_decision = manual_map.get(item_id)
            if not manual_decision:
                # Sin override, mantener decisión original
                modified_decisions.append(plan_decision)
                continue
            
            # Aplicar override según acción
            modified_decision = plan_decision.copy()
            
            if manual_decision.action == ManualDecisionAction.MARK_AS_MATCH:
                # Convertir a AUTO_UPLOAD
                modified_decision["decision"] = "AUTO_UPLOAD"
                modified_decision["decision_reason"] = f"Manual override: {manual_decision.reason}"
                if manual_decision.chosen_local_doc_id:
                    modified_decision["local_doc_id"] = manual_decision.chosen_local_doc_id
                    modified_decision["portal_reference"] = manual_decision.chosen_local_doc_id
            
            elif manual_decision.action == ManualDecisionAction.FORCE_UPLOAD:
                # Convertir a AUTO_UPLOAD con file_path
                modified_decision["decision"] = "AUTO_UPLOAD"
                modified_decision["decision_reason"] = f"Manual override: {manual_decision.reason}"
                if manual_decision.chosen_file_path:
                    modified_decision["chosen_file_path"] = manual_decision.chosen_file_path
            
            elif manual_decision.action == ManualDecisionAction.SKIP:
                # Convertir a DO_NOT_UPLOAD
                modified_decision["decision"] = "DO_NOT_UPLOAD"
                modified_decision["decision_reason"] = f"Manual skip: {manual_decision.reason}"
            
            # Añadir metadata del override
            modified_decision["manual_override"] = {
                "action": manual_decision.action.value,
                "decided_by": manual_decision.decided_by,
                "decided_at": manual_decision.decided_at.isoformat(),
            }
            
            modified_decisions.append(modified_decision)
        
        return modified_decisions
