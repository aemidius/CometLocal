"""
SPRINT C2.20A: Store para Decision Presets.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
import json

from backend.config import DATA_DIR
from backend.shared.decision_preset import DecisionPresetV1
from backend.shared.tenant_paths import tenant_presets_root, resolve_read_path, ensure_write_dir


class DecisionPresetStore:
    """Store para presets de decisiones."""
    
    def __init__(self, base_dir: Path = None, tenant_id: str = "default"):
        """
        Inicializa el store.
        
        Args:
            base_dir: Directorio base (default: DATA_DIR)
            tenant_id: ID del tenant (default: "default")
        """
        self.base_dir = Path(base_dir) if base_dir else Path(DATA_DIR)
        self.tenant_id = tenant_id
        
        # SPRINT C2.22B: Usar tenant presets root
        self.tenant_presets_dir = tenant_presets_root(self.base_dir, tenant_id)
        self.legacy_presets_dir = self.base_dir / "presets"
        
        # Para lectura: tenant con fallback legacy (NO crear directorio)
        # Si tenant dir no existe, usar legacy
        if self.tenant_presets_dir.exists():
            self.presets_dir_read = self.tenant_presets_dir
        else:
            self.presets_dir_read = self.legacy_presets_dir
        
        # Para escritura: siempre usar tenant path (se crea cuando se escribe)
        # NO crear aquí para permitir fallback legacy en lectura
        self.presets_dir_write = self.tenant_presets_dir
        
        # Archivos (usar tenant para escritura, resolved para lectura)
        self.presets_file_write = self.presets_dir_write / "decision_presets_v1.json"
        self.presets_file_read = self.presets_dir_read / "decision_presets_v1.json"
        
        # Para compatibilidad: usar write para operaciones que crean archivos
        self.presets_dir = self.presets_dir_write
        self.presets_file = self.presets_file_write
    
    def list_presets(
        self,
        type_id: Optional[str] = None,
        subject_key: Optional[str] = None,
        period_key: Optional[str] = None,
        platform: Optional[str] = None,
        include_disabled: bool = False,
    ) -> List[DecisionPresetV1]:
        """
        Lista presets con filtros opcionales.
        
        Args:
            type_id: Filtrar por type_id
            subject_key: Filtrar por subject_key
            period_key: Filtrar por period_key
            platform: Filtrar por platform
            include_disabled: Incluir presets desactivados
        
        Returns:
            Lista de presets que coinciden
        """
        all_presets = self._load_all_presets()
        
        filtered = []
        for preset in all_presets:
            # Filtrar desactivados
            if not include_disabled and not preset.is_enabled:
                continue
            
            # Aplicar filtros
            if type_id and preset.scope.type_id != type_id:
                continue
            if subject_key and preset.scope.subject_key != subject_key:
                continue
            if period_key and preset.scope.period_key != period_key:
                continue
            if platform and preset.scope.platform != platform:
                continue
            
            filtered.append(preset)
        
        return filtered
    
    def upsert_preset(self, preset: DecisionPresetV1) -> str:
        """
        Crea o actualiza un preset.
        
        Args:
            preset: Preset a crear/actualizar
        
        Returns:
            preset_id del preset
        """
        all_presets = self._load_all_presets()
        
        # Buscar si ya existe (por preset_id)
        existing_index = None
        for i, p in enumerate(all_presets):
            if p.preset_id == preset.preset_id:
                existing_index = i
                break
        
        if existing_index is not None:
            # Actualizar
            all_presets[existing_index] = preset
        else:
            # Añadir nuevo
            all_presets.append(preset)
        
        # Guardar
        self._save_presets(all_presets)
        
        return preset.preset_id
    
    def disable_preset(self, preset_id: str) -> bool:
        """
        Desactiva un preset.
        
        Args:
            preset_id: ID del preset a desactivar
        
        Returns:
            True si se desactivó, False si no existe
        """
        all_presets = self._load_all_presets()
        
        for preset in all_presets:
            if preset.preset_id == preset_id:
                preset.is_enabled = False
                self._save_presets(all_presets)
                return True
        
        return False
    
    def _load_all_presets(self) -> List[DecisionPresetV1]:
        """Carga todos los presets desde el archivo (con fallback legacy)."""
        # SPRINT C2.22B: Recalcular path de lectura dinámicamente (tenant o legacy)
        # Si tenant dir existe ahora, usar tenant, si no legacy
        if self.tenant_presets_dir.exists():
            presets_file = self.presets_file_write
        else:
            presets_file = self.legacy_presets_dir / "decision_presets_v1.json"
        
        if not presets_file.exists():
            return []
        
        try:
            with open(presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                presets = []
                for preset_dict in data.get("presets", []):
                    try:
                        presets.append(DecisionPresetV1(**preset_dict))
                    except Exception as e:
                        print(f"[DecisionPresetStore] Error parsing preset: {e}")
                        continue
                return presets
        except Exception as e:
            print(f"[DecisionPresetStore] Error loading presets: {e}")
            return []
    
    def _save_presets(self, presets: List[DecisionPresetV1]) -> None:
        """Guarda todos los presets al archivo (en tenant path)."""
        # SPRINT C2.22B: Guardar en tenant path (escritura)
        # Asegurar que el directorio existe antes de escribir
        ensure_write_dir(self.presets_dir_write)
        data = {
            "presets": [p.model_dump(mode="json") for p in presets],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        with open(self.presets_file_write, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_preset(self, preset_id: str) -> Optional[DecisionPresetV1]:
        """
        Obtiene un preset por ID.
        
        Args:
            preset_id: ID del preset
        
        Returns:
            Preset o None si no existe
        """
        all_presets = self._load_all_presets()
        for preset in all_presets:
            if preset.preset_id == preset_id:
                return preset
        return None
