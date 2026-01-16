"""
Visual Memory Store: Gestión de memoria visual (heatmaps y landmarks).

v5.2.0: Almacena y consulta memoria visual para navegación basada en coordenadas.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from backend.shared.models import (
    VisualMemorySnapshot,
    VisualHeatmap,
    VisualHeatmapCell,
    VisualLandmark,
)
from backend.config import VISUAL_MEMORY_BASE_DIR, VISUAL_MEMORY_ENABLED

logger = logging.getLogger(__name__)


class VisualMemoryStore:
    """
    Almacén de memoria visual.
    
    v5.2.0: Gestiona persistencia y consulta de heatmaps y landmarks visuales.
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Inicializa el almacén de memoria visual.
        
        Args:
            base_dir: Directorio base para almacenar snapshots (default: VISUAL_MEMORY_BASE_DIR)
        """
        if base_dir is None:
            base_dir = VISUAL_MEMORY_BASE_DIR
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[visual-memory] Initialized with base_dir: {self.base_dir}")
    
    def _get_snapshot_path(self, platform: str, page_signature: str) -> Path:
        """
        Obtiene la ruta del archivo de snapshot.
        
        Args:
            platform: Nombre de la plataforma
            page_signature: Firma de la página
            
        Returns:
            Path al archivo JSON
        """
        # Normalizar nombre de plataforma
        safe_platform = platform.replace(" ", "_").replace("/", "_").lower()
        safe_signature = page_signature.replace("/", "_").replace("\\", "_")
        
        platform_dir = self.base_dir / safe_platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        
        return platform_dir / f"{safe_signature}.json"
    
    def load_snapshot(
        self,
        platform: str,
        page_signature: str,
    ) -> Optional[VisualMemorySnapshot]:
        """
        Carga un snapshot de memoria visual desde disco.
        
        Args:
            platform: Nombre de la plataforma
            page_signature: Firma de la página
            
        Returns:
            VisualMemorySnapshot cargado o None si no existe
        """
        if not VISUAL_MEMORY_ENABLED:
            return None
        
        snapshot_path = self._get_snapshot_path(platform, page_signature)
        
        if not snapshot_path.exists():
            logger.debug(f"[visual-memory] No snapshot found for {platform}/{page_signature}")
            return None
        
        try:
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Reconstruir heatmap si existe
            heatmap = None
            if data.get("heatmap"):
                heatmap_data = data["heatmap"]
                cells = [
                    VisualHeatmapCell(**cell_data)
                    for cell_data in heatmap_data.get("cells", [])
                ]
                heatmap = VisualHeatmap(
                    platform=heatmap_data.get("platform", platform),
                    page_signature=heatmap_data.get("page_signature", page_signature),
                    rows=heatmap_data.get("rows", 4),
                    cols=heatmap_data.get("cols", 6),
                    cells=cells,
                    last_updated_at=heatmap_data.get("last_updated_at"),
                )
            
            # Reconstruir landmarks
            landmarks = [
                VisualLandmark(**landmark_data)
                for landmark_data in data.get("landmarks", [])
            ]
            
            snapshot = VisualMemorySnapshot(
                platform=data.get("platform", platform),
                page_signature=data.get("page_signature", page_signature),
                heatmap=heatmap,
                landmarks=landmarks,
                version=data.get("version", 1),
            )
            
            logger.debug(
                f"[visual-memory] Loaded snapshot for {platform}/{page_signature}: "
                f"{len(cells) if heatmap else 0} cells, {len(landmarks)} landmarks"
            )
            
            return snapshot
        
        except Exception as e:
            logger.warning(
                f"[visual-memory] Error loading snapshot for {platform}/{page_signature}: {e}",
                exc_info=True,
            )
            return None
    
    def save_snapshot(self, snapshot: VisualMemorySnapshot) -> bool:
        """
        Guarda un snapshot de memoria visual en disco.
        
        Args:
            snapshot: Snapshot a guardar
            
        Returns:
            True si se guardó correctamente
        """
        if not VISUAL_MEMORY_ENABLED:
            return False
        
        snapshot_path = self._get_snapshot_path(snapshot.platform, snapshot.page_signature)
        
        try:
            # Convertir a dict
            data = {
                "platform": snapshot.platform,
                "page_signature": snapshot.page_signature,
                "version": snapshot.version,
                "landmarks": [landmark.model_dump() for landmark in snapshot.landmarks],
            }
            
            if snapshot.heatmap:
                data["heatmap"] = {
                    "platform": snapshot.heatmap.platform,
                    "page_signature": snapshot.heatmap.page_signature,
                    "rows": snapshot.heatmap.rows,
                    "cols": snapshot.heatmap.cols,
                    "cells": [cell.model_dump() for cell in snapshot.heatmap.cells],
                    "last_updated_at": snapshot.heatmap.last_updated_at,
                }
            
            # Guardar JSON
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(
                f"[visual-memory] Saved snapshot for {snapshot.platform}/{snapshot.page_signature}"
            )
            
            return True
        
        except Exception as e:
            logger.warning(
                f"[visual-memory] Error saving snapshot for {snapshot.platform}/{snapshot.page_signature}: {e}",
                exc_info=True,
            )
            return False
    
    def update_heatmap_cell(
        self,
        platform: str,
        page_signature: str,
        row: int,
        col: int,
        success: bool,
        weight: float = 1.0,
    ) -> None:
        """
        Actualiza una celda del heatmap.
        
        Args:
            platform: Nombre de la plataforma
            page_signature: Firma de la página
            row: Fila de la celda
            col: Columna de la celda
            success: Si la acción fue exitosa
            weight: Peso de la actualización (default: 1.0)
        """
        if not VISUAL_MEMORY_ENABLED:
            return
        
        try:
            # Cargar snapshot existente o crear nuevo
            snapshot = self.load_snapshot(platform, page_signature)
            if snapshot is None:
                snapshot = VisualMemorySnapshot(
                    platform=platform,
                    page_signature=page_signature,
                )
            
            # Crear o obtener heatmap
            if snapshot.heatmap is None:
                snapshot.heatmap = VisualHeatmap(
                    platform=platform,
                    page_signature=page_signature,
                    rows=4,
                    cols=6,
                )
            
            # Buscar celda existente
            cell = None
            for c in snapshot.heatmap.cells:
                if c.row == row and c.col == col:
                    cell = c
                    break
            
            # Crear celda si no existe
            if cell is None:
                cell = VisualHeatmapCell(row=row, col=col)
                snapshot.heatmap.cells.append(cell)
            
            # Actualizar contadores
            cell.clicks += int(weight)
            if success:
                cell.successes += int(weight)
            else:
                cell.failures += int(weight)
            
            # Calcular score (successes - failures * 0.5)
            cell.score = cell.successes - (cell.failures * 0.5)
            
            # Actualizar timestamp
            cell.last_used_at = datetime.now().isoformat()
            snapshot.heatmap.last_updated_at = datetime.now().isoformat()
            
            # Guardar snapshot
            self.save_snapshot(snapshot)
        
        except Exception as e:
            logger.warning(
                f"[visual-memory] Error updating heatmap cell: {e}",
                exc_info=True,
            )
            # No lanzar excepción, solo loguear
    
    def register_landmark_use(
        self,
        platform: str,
        page_signature: str,
        landmark: VisualLandmark,
        success: bool,
        weight: float = 1.0,
    ) -> None:
        """
        Registra el uso de un landmark.
        
        Args:
            platform: Nombre de la plataforma
            page_signature: Firma de la página
            landmark: Landmark usado
            success: Si la acción fue exitosa
            weight: Peso de la actualización (default: 1.0)
        """
        if not VISUAL_MEMORY_ENABLED:
            return
        
        try:
            # Cargar snapshot existente o crear nuevo
            snapshot = self.load_snapshot(platform, page_signature)
            if snapshot is None:
                snapshot = VisualMemorySnapshot(
                    platform=platform,
                    page_signature=page_signature,
                )
            
            # Buscar landmark existente (por posición aproximada y texto)
            existing_landmark = None
            for lm in snapshot.landmarks:
                if (
                    abs(lm.x_center - landmark.x_center) < 0.1 and
                    abs(lm.y_center - landmark.y_center) < 0.1 and
                    lm.text_snippet == landmark.text_snippet
                ):
                    existing_landmark = lm
                    break
            
            # Si no existe, añadir nuevo
            if existing_landmark is None:
                existing_landmark = landmark
                snapshot.landmarks.append(existing_landmark)
            
            # Actualizar contadores
            existing_landmark.uses += int(weight)
            if success:
                existing_landmark.successes += int(weight)
            else:
                existing_landmark.failures += int(weight)
            
            # Calcular score
            existing_landmark.score = existing_landmark.successes - (existing_landmark.failures * 0.5)
            
            # Actualizar timestamp
            existing_landmark.last_used_at = datetime.now().isoformat()
            
            # Guardar snapshot
            self.save_snapshot(snapshot)
        
        except Exception as e:
            logger.warning(
                f"[visual-memory] Error registering landmark use: {e}",
                exc_info=True,
            )
            # No lanzar excepción, solo loguear
    
    def get_best_cells(
        self,
        platform: str,
        page_signature: str,
        top_k: int = 5,
    ) -> List[VisualHeatmapCell]:
        """
        Obtiene las mejores celdas del heatmap.
        
        Args:
            platform: Nombre de la plataforma
            page_signature: Firma de la página
            top_k: Número de celdas a retornar
            
        Returns:
            Lista de celdas ordenadas por score descendente
        """
        if not VISUAL_MEMORY_ENABLED:
            return []
        
        snapshot = self.load_snapshot(platform, page_signature)
        if snapshot is None or snapshot.heatmap is None:
            return []
        
        # Ordenar por score descendente
        sorted_cells = sorted(
            snapshot.heatmap.cells,
            key=lambda c: c.score,
            reverse=True,
        )
        
        return sorted_cells[:top_k]
    
    def get_best_landmarks(
        self,
        platform: str,
        page_signature: str,
        role: Optional[str] = None,
        top_k: int = 5,
    ) -> List[VisualLandmark]:
        """
        Obtiene los mejores landmarks.
        
        Args:
            platform: Nombre de la plataforma
            page_signature: Firma de la página
            role: Rol opcional para filtrar (ej: "upload", "save")
            top_k: Número de landmarks a retornar
            
        Returns:
            Lista de landmarks ordenados por score descendente
        """
        if not VISUAL_MEMORY_ENABLED:
            return []
        
        snapshot = self.load_snapshot(platform, page_signature)
        if snapshot is None:
            return []
        
        # Filtrar por role si se especifica
        landmarks = snapshot.landmarks
        if role:
            landmarks = [lm for lm in landmarks if lm.role == role]
        
        # Ordenar por score descendente
        sorted_landmarks = sorted(
            landmarks,
            key=lambda lm: lm.score,
            reverse=True,
        )
        
        return sorted_landmarks[:top_k]

























