"""
SPRINT C2.19A: Learning Store - Aprendizaje determinista desde decisiones humanas.

Almacena hints aprendidos de Decision Packs con MARK_AS_MATCH para mejorar
futuros matchings de forma determinista y auditable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import hashlib
import json
from pathlib import Path

from backend.config import DATA_DIR
from backend.shared.tenant_paths import tenant_learning_root, resolve_read_path, ensure_write_dir


class HintStrength(str, Enum):
    """Fuerza del hint."""
    EXACT = "EXACT"  # subject+type+period presentes
    SOFT = "SOFT"  # falta period o info incompleta


class LearnedHintV1(BaseModel):
    """Hint aprendido de una decisión humana MARK_AS_MATCH."""
    hint_id: str = Field(..., description="Hash estable del contenido")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de creación"
    )
    source: str = Field(default="decision_pack", description="Origen del hint")
    plan_id: Optional[str] = Field(None, description="Plan origen")
    decision_pack_id: Optional[str] = Field(None, description="Decision Pack origen")
    item_fingerprint: str = Field(..., description="Fingerprint determinista del pending item")
    learned_mapping: Dict[str, Any] = Field(..., description="Mapeo aprendido")
    conditions: Dict[str, Any] = Field(..., description="Condiciones de aplicación")
    strength: HintStrength = Field(..., description="Fuerza del hint")
    notes: Optional[str] = Field(None, description="Notas opcionales")
    disabled: bool = Field(default=False, description="Si está desactivado")

    @classmethod
    def create(
        cls,
        plan_id: str,
        decision_pack_id: str,
        item_fingerprint: str,
        type_id_expected: str,
        local_doc_id: str,
        local_doc_fingerprint: Optional[str],
        subject_key: Optional[str],
        person_key: Optional[str],
        period_key: Optional[str],
        portal_type_label_normalized: Optional[str],
        notes: Optional[str] = None,
    ) -> "LearnedHintV1":
        """
        Crea un LearnedHintV1 y calcula su hint_id estable.
        
        El hint_id se basa en:
        - item_fingerprint
        - type_id_expected
        - local_doc_id
        - conditions (subject, period, portal_label)
        """
        # Construir conditions
        conditions = {}
        if subject_key:
            conditions["subject_key"] = subject_key
        if person_key:
            conditions["person_key"] = person_key
        if period_key:
            conditions["period_key"] = period_key
        if portal_type_label_normalized:
            conditions["portal_type_label_normalized"] = portal_type_label_normalized
        
        # Determinar strength
        strength = HintStrength.EXACT
        if not period_key or not subject_key:
            strength = HintStrength.SOFT
        
        # Construir learned_mapping
        learned_mapping = {
            "type_id_expected": type_id_expected,
            "local_doc_id": local_doc_id,
        }
        if local_doc_fingerprint:
            learned_mapping["local_doc_fingerprint"] = local_doc_fingerprint
        
        # Canonizar para hash
        canonical_content = {
            "item_fingerprint": item_fingerprint,
            "type_id_expected": type_id_expected,
            "local_doc_id": local_doc_id,
            "conditions": conditions,
        }
        
        # Hash SHA256
        json_str = json.dumps(canonical_content, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(json_str.encode("utf-8"))
        hint_id = f"hint_{hash_obj.hexdigest()[:16]}"
        
        return cls(
            hint_id=hint_id,
            plan_id=plan_id,
            decision_pack_id=decision_pack_id,
            item_fingerprint=item_fingerprint,
            learned_mapping=learned_mapping,
            conditions=conditions,
            strength=strength,
            notes=notes,
        )


class LearningStore:
    """Store para hints aprendidos."""
    
    def __init__(self, base_dir: Path = None, tenant_id: str = "default"):
        """
        Inicializa el store.
        
        Args:
            base_dir: Directorio base (default: DATA_DIR)
            tenant_id: ID del tenant (default: "default")
        """
        self.base_dir = Path(base_dir) if base_dir else Path(DATA_DIR)
        self.tenant_id = tenant_id
        
        # SPRINT C2.22B: Usar tenant learning root para escritura
        self.tenant_learning_dir = tenant_learning_root(self.base_dir, tenant_id)
        self.legacy_learning_dir = self.base_dir / "learning"
        
        # Para lectura: tenant con fallback legacy (NO crear directorio)
        # Si tenant dir no existe, usar legacy
        if self.tenant_learning_dir.exists():
            self.learning_dir_read = self.tenant_learning_dir
        else:
            self.learning_dir_read = self.legacy_learning_dir
        
        # Para escritura: siempre usar tenant path (se crea cuando se escribe)
        # NO crear aquí para permitir fallback legacy en lectura
        self.learning_dir_write = self.tenant_learning_dir
        
        # Archivos (usar tenant para escritura, resolved para lectura)
        self.hints_file_write = self.learning_dir_write / "hints_v1.jsonl"
        self.hints_file_read = self.learning_dir_read / "hints_v1.jsonl"
        self.index_file_write = self.learning_dir_write / "index_v1.json"
        self.index_file_read = self.learning_dir_read / "index_v1.json"
        self.tombstones_file_write = self.learning_dir_write / "tombstones_v1.json"
        self.tombstones_file_read = self.learning_dir_read / "tombstones_v1.json"
        
        # Para compatibilidad: usar write para operaciones que crean archivos
        self.hints_file = self.hints_file_write
        self.index_file = self.index_file_write
        self.tombstones_file = self.tombstones_file_write
    
    def add_hints(self, hints: List[LearnedHintV1]) -> List[str]:
        """
        Añade hints al store (append-only, idempotente).
        
        Args:
            hints: Lista de hints a añadir
        
        Returns:
            Lista de hint_ids añadidos (sin duplicados)
        """
        added_ids = []
        
        # Cargar hints existentes para verificar duplicados
        existing_hints = self._load_all_hints()
        existing_ids = {h.hint_id for h in existing_hints}
        
        # Filtrar duplicados
        new_hints = [h for h in hints if h.hint_id not in existing_ids]
        
        if not new_hints:
            return []
        
        # SPRINT C2.22B: Append a JSONL en tenant path (escritura)
        # Asegurar que el directorio existe antes de escribir
        ensure_write_dir(self.learning_dir_write)
        with open(self.hints_file_write, "a", encoding="utf-8") as f:
            for hint in new_hints:
                hint_dict = hint.model_dump(mode="json")
                f.write(json.dumps(hint_dict, ensure_ascii=False) + "\n")
                added_ids.append(hint.hint_id)
        
        # Actualizar índice
        self._rebuild_index()
        
        return added_ids
    
    def find_hints(
        self,
        platform: str,
        type_id: Optional[str] = None,
        subject_key: Optional[str] = None,
        person_key: Optional[str] = None,
        period_key: Optional[str] = None,
        portal_label_norm: Optional[str] = None,
    ) -> List[LearnedHintV1]:
        """
        Busca hints que coincidan con los criterios.
        
        Args:
            platform: Plataforma (ej: "egestiona")
            type_id: Tipo de documento esperado
            subject_key: Clave de empresa
            person_key: Clave de persona
            period_key: Clave de período
            portal_label_norm: Label normalizado del portal
        
        Returns:
            Lista de hints que coinciden (solo activos)
        """
        all_hints = self._load_all_hints()
        disabled_ids = self._load_disabled_ids()
        
        matching = []
        for hint in all_hints:
            # Saltar desactivados
            if hint.hint_id in disabled_ids or hint.disabled:
                continue
            
            # Verificar condiciones
            conditions = hint.conditions
            learned_mapping = hint.learned_mapping
            
            # Verificar type_id
            if type_id and learned_mapping.get("type_id_expected") != type_id:
                continue
            
            # Verificar subject_key
            if subject_key and conditions.get("subject_key") != subject_key:
                continue
            
            # Verificar person_key
            if person_key and conditions.get("person_key") != person_key:
                continue
            
            # Verificar period_key (si se proporciona y el hint lo requiere)
            if period_key is not None:
                hint_period = conditions.get("period_key")
                if hint_period and hint_period != period_key:
                    continue
            
            # Verificar portal_label_norm (opcional)
            if portal_label_norm:
                hint_label = conditions.get("portal_type_label_normalized")
                if hint_label and hint_label != portal_label_norm:
                    continue
            
            matching.append(hint)
        
        return matching
    
    def disable_hint(self, hint_id: str, reason: Optional[str] = None) -> bool:
        """
        Desactiva un hint.
        
        Args:
            hint_id: ID del hint a desactivar
            reason: Razón opcional para desactivar
        
        Returns:
            True si se desactivó, False si no existe
        """
        disabled_ids = self._load_disabled_ids()
        if hint_id in disabled_ids:
            return True  # Ya está desactivado
        
        # Añadir a tombstones con razón si se proporciona
        disabled_ids.add(hint_id)
        tombstone_data = {"disabled_ids": list(disabled_ids)}
        if reason:
            if "reasons" not in tombstone_data:
                tombstone_data["reasons"] = {}
            tombstone_data["reasons"][hint_id] = reason
        
        # SPRINT C2.22B: Guardar tombstones en tenant path (escritura)
        # Asegurar que el directorio existe antes de escribir
        ensure_write_dir(self.learning_dir_write)
        with open(self.tombstones_file_write, "w", encoding="utf-8") as f:
            json.dump(tombstone_data, f, indent=2, ensure_ascii=False)
        
        return True
    
    def list_hints(
        self,
        plan_id: Optional[str] = None,
        decision_pack_id: Optional[str] = None,
        strength: Optional[HintStrength] = None,
        include_disabled: bool = False,
    ) -> List[LearnedHintV1]:
        """
        Lista hints con filtros opcionales.
        
        Args:
            plan_id: Filtrar por plan_id
            decision_pack_id: Filtrar por decision_pack_id
            strength: Filtrar por strength
            include_disabled: Incluir hints desactivados
        
        Returns:
            Lista de hints
        """
        all_hints = self._load_all_hints()
        disabled_ids = self._load_disabled_ids()
        
        filtered = []
        for hint in all_hints:
            # Filtrar desactivados
            if not include_disabled and (hint.hint_id in disabled_ids or hint.disabled):
                continue
            
            # Aplicar filtros
            if plan_id and hint.plan_id != plan_id:
                continue
            if decision_pack_id and hint.decision_pack_id != decision_pack_id:
                continue
            if strength and hint.strength != strength:
                continue
            
            filtered.append(hint)
        
        return filtered
    
    def _load_all_hints(self) -> List[LearnedHintV1]:
        """Carga todos los hints desde JSONL (con fallback legacy)."""
        # SPRINT C2.22B: Recalcular path de lectura dinámicamente (tenant o legacy)
        # Si tenant dir existe ahora, usar tenant, si no legacy
        if self.tenant_learning_dir.exists():
            hints_file = self.hints_file_write
        else:
            hints_file = self.legacy_learning_dir / "hints_v1.jsonl"
        
        if not hints_file.exists():
            return []
        
        hints = []
        try:
            with open(hints_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        hint_dict = json.loads(line)
                        hints.append(LearnedHintV1(**hint_dict))
                    except Exception as e:
                        print(f"[LearningStore] Error parsing hint line: {e}")
                        continue
        except Exception as e:
            print(f"[LearningStore] Error loading hints: {e}")
        
        return hints
    
    def _load_disabled_ids(self) -> set:
        """Carga IDs de hints desactivados (con fallback legacy)."""
        # SPRINT C2.22B: Recalcular path de lectura dinámicamente (tenant o legacy)
        # Si tenant dir existe ahora, usar tenant, si no legacy
        if self.tenant_learning_dir.exists():
            tombstones_file = self.tombstones_file_write
        else:
            tombstones_file = self.legacy_learning_dir / "tombstones_v1.json"
        
        if not tombstones_file.exists():
            return set()
        
        try:
            with open(tombstones_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("disabled_ids", []))
        except Exception:
            return set()
    
    def _rebuild_index(self) -> None:
        """Reconstruye el índice (opcional, para lookup rápido)."""
        all_hints = self._load_all_hints()
        disabled_ids = self._load_disabled_ids()
        
        index = {
            "total_hints": len(all_hints),
            "active_hints": len([h for h in all_hints if h.hint_id not in disabled_ids]),
            "disabled_hints": len(disabled_ids),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # SPRINT C2.22B: Guardar índice en tenant path (escritura)
        # Asegurar que el directorio existe antes de escribir
        ensure_write_dir(self.learning_dir_write)
        with open(self.index_file_write, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
