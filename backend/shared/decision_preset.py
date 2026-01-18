"""
SPRINT C2.20A: Decision Presets - Plantillas reutilizables para Decision Packs.

Permite crear presets (plantillas) de decisiones que se pueden aplicar en lote
a múltiples items del plan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
import hashlib
import json

from backend.shared.decision_pack import ManualDecisionAction


class DecisionPresetScope(BaseModel):
    """Alcance del preset (dónde se aplica)."""
    platform: str = Field(default="egestiona", description="Plataforma (default: egestiona)")
    type_id: str = Field(..., description="Tipo de documento requerido")
    subject_key: Optional[str] = Field(None, description="Clave de empresa (opcional)")
    period_key: Optional[str] = Field(None, description="Clave de período (opcional)")


class DecisionPresetDefaults(BaseModel):
    """Valores por defecto del preset."""
    reason: Optional[str] = Field(None, description="Razón por defecto (para SKIP)")
    file_path: Optional[str] = Field(None, description="Ruta de archivo por defecto (para FORCE_UPLOAD)")
    local_doc_id: Optional[str] = Field(None, description="ID de documento local (para MARK_AS_MATCH, normalmente no útil en masa)")


class DecisionPresetV1(BaseModel):
    """Preset (plantilla) de decisión reutilizable."""
    preset_id: str = Field(..., description="Hash estable del contenido canonizado")
    name: str = Field(..., description="Nombre del preset")
    scope: DecisionPresetScope = Field(..., description="Alcance del preset")
    action: ManualDecisionAction = Field(..., description="Acción del preset")
    defaults: DecisionPresetDefaults = Field(
        default_factory=DecisionPresetDefaults,
        description="Valores por defecto"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de creación"
    )
    is_enabled: bool = Field(default=True, description="Si está habilitado")

    @classmethod
    def create(
        cls,
        name: str,
        scope: DecisionPresetScope,
        action: ManualDecisionAction,
        defaults: Optional[DecisionPresetDefaults] = None,
    ) -> "DecisionPresetV1":
        """
        Crea un DecisionPresetV1 y calcula su preset_id estable.
        
        El preset_id se basa en:
        - scope (platform, type_id, subject_key, period_key)
        - action
        - defaults (reason, file_path, local_doc_id)
        """
        if defaults is None:
            defaults = DecisionPresetDefaults()
        
        # Canonizar para hash
        canonical_content = {
            "scope": {
                "platform": scope.platform,
                "type_id": scope.type_id,
                "subject_key": scope.subject_key or "",
                "period_key": scope.period_key or "",
            },
            "action": action.value,
            "defaults": {
                "reason": defaults.reason or "",
                "file_path": defaults.file_path or "",
                "local_doc_id": defaults.local_doc_id or "",
            },
        }
        
        # Hash SHA256
        json_str = json.dumps(canonical_content, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(json_str.encode("utf-8"))
        preset_id = f"preset_{hash_obj.hexdigest()[:16]}"
        
        return cls(
            preset_id=preset_id,
            name=name,
            scope=scope,
            action=action,
            defaults=defaults,
        )
    
    def matches_item(
        self,
        item_type_id: Optional[str],
        item_subject_key: Optional[str] = None,
        item_period_key: Optional[str] = None,
        platform: str = "egestiona",
    ) -> bool:
        """
        Verifica si el preset aplica a un item específico.
        
        Args:
            item_type_id: Type ID del item
            item_subject_key: Subject key del item (opcional)
            item_period_key: Period key del item (opcional)
            platform: Plataforma del item
        
        Returns:
            True si el preset aplica al item
        """
        # Verificar platform
        if self.scope.platform != platform:
            return False
        
        # Verificar type_id (requerido)
        if self.scope.type_id != item_type_id:
            return False
        
        # Verificar subject_key (si el preset lo requiere)
        if self.scope.subject_key:
            if self.scope.subject_key != item_subject_key:
                return False
        
        # Verificar period_key (si el preset lo requiere)
        if self.scope.period_key:
            if self.scope.period_key != item_period_key:
                return False
        
        return True
