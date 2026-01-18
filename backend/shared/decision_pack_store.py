"""
SPRINT C2.18B: Store para Decision Packs.

Persistencia de Decision Packs en data/runs/{plan_id}/decision_packs/
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

from backend.shared.decision_pack import DecisionPackV1, ManualDecisionV1
from backend.config import DATA_DIR


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Escribe JSON de forma atómica."""
    import tempfile
    import shutil
    
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Escribir a archivo temporal
    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        delete=False,
        dir=path.parent,
        suffix='.tmp'
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False, default=str)
        tmp_path = Path(tmp.name)
    
    # Mover temp a archivo final (atomic en mayoría de sistemas)
    tmp_path.replace(path)


class DecisionPackStore:
    """Store para Decision Packs."""
    
    def __init__(self, base_dir: Path = None):
        """
        Inicializa el store.
        
        Args:
            base_dir: Directorio base (default: DATA_DIR)
        """
        self.base_dir = Path(base_dir) if base_dir else Path(DATA_DIR)
    
    def _get_decision_packs_dir(self, plan_id: str) -> Path:
        """Obtiene el directorio de decision packs para un plan."""
        return self.base_dir / "runs" / plan_id / "decision_packs"
    
    def _get_pack_path(self, plan_id: str, decision_pack_id: str) -> Path:
        """Obtiene la ruta del archivo de un pack."""
        return self._get_decision_packs_dir(plan_id) / f"{decision_pack_id}.json"
    
    def _get_index_path(self, plan_id: str) -> Path:
        """Obtiene la ruta del índice."""
        return self._get_decision_packs_dir(plan_id) / "index.json"
    
    def save_pack(self, pack: DecisionPackV1) -> None:
        """
        Guarda un Decision Pack.
        
        Args:
            pack: DecisionPackV1 a guardar
        """
        pack_path = self._get_pack_path(pack.plan_id, pack.decision_pack_id)
        
        # Serializar pack
        pack_dict = pack.model_dump(mode="json")
        
        # Guardar pack
        _atomic_write_json(pack_path, pack_dict)
        
        # Actualizar índice
        self._update_index(pack.plan_id, pack.decision_pack_id)
    
    def load_pack(self, plan_id: str, decision_pack_id: str) -> Optional[DecisionPackV1]:
        """
        Carga un Decision Pack.
        
        Args:
            plan_id: ID del plan
            decision_pack_id: ID del pack
        
        Returns:
            DecisionPackV1 o None si no existe
        """
        pack_path = self._get_pack_path(plan_id, decision_pack_id)
        
        if not pack_path.exists():
            return None
        
        try:
            with open(pack_path, "r", encoding="utf-8") as f:
                pack_dict = json.load(f)
            
            return DecisionPackV1(**pack_dict)
        except Exception as e:
            print(f"[DecisionPackStore] Error al cargar pack {decision_pack_id}: {e}")
            return None
    
    def list_packs(self, plan_id: str) -> List[Dict[str, Any]]:
        """
        Lista todos los packs de un plan.
        
        Args:
            plan_id: ID del plan
        
        Returns:
            Lista de metadatos de packs
        """
        index_path = self._get_index_path(plan_id)
        
        if not index_path.exists():
            return []
        
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            return index_data.get("packs", [])
        except Exception:
            return []
    
    def _update_index(self, plan_id: str, decision_pack_id: str) -> None:
        """Actualiza el índice de packs."""
        index_path = self._get_index_path(plan_id)
        
        # Cargar índice existente
        packs = []
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                packs = index_data.get("packs", [])
            except Exception:
                packs = []
        
        # Verificar si el pack ya está en el índice
        pack_exists = any(p.get("decision_pack_id") == decision_pack_id for p in packs)
        
        if not pack_exists:
            # Cargar pack para obtener metadata
            pack = self.load_pack(plan_id, decision_pack_id)
            if pack:
                packs.append({
                    "decision_pack_id": pack.decision_pack_id,
                    "created_at": pack.created_at.isoformat(),
                    "decisions_count": len(pack.decisions),
                })
        
        # Guardar índice
        index_data = {
            "plan_id": plan_id,
            "packs": packs,
            "updated_at": datetime.now().isoformat(),
        }
        _atomic_write_json(index_path, index_data)
