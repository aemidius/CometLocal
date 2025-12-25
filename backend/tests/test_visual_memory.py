"""
Tests para Visual Memory Store v5.2.0
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from backend.vision.visual_memory import VisualMemoryStore
from backend.shared.models import (
    VisualMemorySnapshot,
    VisualHeatmap,
    VisualHeatmapCell,
    VisualLandmark,
)


class TestVisualMemoryStore:
    """Tests para VisualMemoryStore"""
    
    @pytest.fixture
    def temp_dir(self):
        """Directorio temporal para tests"""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def visual_memory(self, temp_dir):
        """Instancia de VisualMemoryStore con directorio temporal"""
        return VisualMemoryStore(base_dir=str(temp_dir))
    
    def test_update_heatmap_cell(self, visual_memory):
        """Test actualización de celda de heatmap"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        # Actualizar celda
        visual_memory.update_heatmap_cell(
            platform=platform,
            page_signature=page_sig,
            row=1,
            col=2,
            success=True,
        )
        
        # Verificar que se guardó
        snapshot = visual_memory.load_snapshot(platform, page_sig)
        assert snapshot is not None
        assert snapshot.heatmap is not None
        assert len(snapshot.heatmap.cells) == 1
        
        cell = snapshot.heatmap.cells[0]
        assert cell.row == 1
        assert cell.col == 2
        assert cell.clicks == 1
        assert cell.successes == 1
        assert cell.failures == 0
        assert cell.score > 0.0
    
    def test_update_heatmap_cell_failure(self, visual_memory):
        """Test actualización de celda con fallo"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        # Actualizar con fallo
        visual_memory.update_heatmap_cell(
            platform=platform,
            page_signature=page_sig,
            row=0,
            col=0,
            success=False,
        )
        
        snapshot = visual_memory.load_snapshot(platform, page_sig)
        assert snapshot is not None
        cell = snapshot.heatmap.cells[0]
        assert cell.failures == 1
        assert cell.score < 0.0  # Penalización
    
    def test_persistence(self, visual_memory):
        """Test persistencia de snapshots"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        # Crear y guardar snapshot
        visual_memory.update_heatmap_cell(
            platform=platform,
            page_signature=page_sig,
            row=2,
            col=3,
            success=True,
        )
        
        # Cargar de nuevo
        snapshot = visual_memory.load_snapshot(platform, page_sig)
        assert snapshot is not None
        assert snapshot.platform == platform
        assert snapshot.page_signature == page_sig
        assert len(snapshot.heatmap.cells) == 1
    
    def test_get_best_cells(self, visual_memory):
        """Test obtención de mejores celdas"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        # Crear múltiples celdas con diferentes scores
        visual_memory.update_heatmap_cell(platform, page_sig, 0, 0, success=True)  # Score positivo
        visual_memory.update_heatmap_cell(platform, page_sig, 0, 0, success=True)  # Mejor score
        visual_memory.update_heatmap_cell(platform, page_sig, 1, 1, success=False)  # Score negativo
        visual_memory.update_heatmap_cell(platform, page_sig, 2, 2, success=True)  # Score positivo
        
        # Obtener mejores celdas
        best_cells = visual_memory.get_best_cells(platform, page_sig, top_k=2)
        
        assert len(best_cells) == 2
        # Deben estar ordenadas por score descendente
        assert best_cells[0].score >= best_cells[1].score
    
    def test_register_landmark_use(self, visual_memory):
        """Test registro de uso de landmark"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        landmark = VisualLandmark(
            platform=platform,
            page_signature=page_sig,
            x_center=0.5,
            y_center=0.3,
            width=0.1,
            height=0.05,
            text_snippet="Subir documento",
            landmark_type="button",
            role="upload",
        )
        
        # Registrar uso exitoso
        visual_memory.register_landmark_use(
            platform=platform,
            page_signature=page_sig,
            landmark=landmark,
            success=True,
        )
        
        # Verificar que se guardó
        snapshot = visual_memory.load_snapshot(platform, page_sig)
        assert snapshot is not None
        assert len(snapshot.landmarks) == 1
        
        saved_landmark = snapshot.landmarks[0]
        assert saved_landmark.text_snippet == "Subir documento"
        assert saved_landmark.role == "upload"
        assert saved_landmark.uses == 1
        assert saved_landmark.successes == 1
        assert saved_landmark.score > 0.0
    
    def test_get_best_landmarks(self, visual_memory):
        """Test obtención de mejores landmarks"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        # Crear múltiples landmarks
        landmark1 = VisualLandmark(
            platform=platform,
            page_signature=page_sig,
            x_center=0.5,
            y_center=0.3,
            width=0.1,
            height=0.05,
            text_snippet="Subir",
            landmark_type="button",
            role="upload",
        )
        
        landmark2 = VisualLandmark(
            platform=platform,
            page_signature=page_sig,
            x_center=0.7,
            y_center=0.8,
            width=0.1,
            height=0.05,
            text_snippet="Guardar",
            landmark_type="button",
            role="save",
        )
        
        # Registrar usos (landmark1 más exitoso)
        visual_memory.register_landmark_use(platform, page_sig, landmark1, success=True)
        visual_memory.register_landmark_use(platform, page_sig, landmark1, success=True)
        visual_memory.register_landmark_use(platform, page_sig, landmark2, success=False)
        
        # Obtener mejores landmarks
        best_landmarks = visual_memory.get_best_landmarks(platform, page_sig, top_k=2)
        
        assert len(best_landmarks) == 2
        # Deben estar ordenados por score descendente
        assert best_landmarks[0].score >= best_landmarks[1].score
        # El primero debería ser landmark1 (más exitoso)
        assert best_landmarks[0].text_snippet == "Subir"
    
    def test_get_best_landmarks_filtered_by_role(self, visual_memory):
        """Test obtención de landmarks filtrados por role"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        landmark_upload = VisualLandmark(
            platform=platform,
            page_signature=page_sig,
            x_center=0.5,
            y_center=0.3,
            width=0.1,
            height=0.05,
            text_snippet="Subir",
            landmark_type="button",
            role="upload",
        )
        
        landmark_save = VisualLandmark(
            platform=platform,
            page_signature=page_sig,
            x_center=0.7,
            y_center=0.8,
            width=0.1,
            height=0.05,
            text_snippet="Guardar",
            landmark_type="button",
            role="save",
        )
        
        visual_memory.register_landmark_use(platform, page_sig, landmark_upload, success=True)
        visual_memory.register_landmark_use(platform, page_sig, landmark_save, success=True)
        
        # Filtrar por role "upload"
        upload_landmarks = visual_memory.get_best_landmarks(
            platform, page_sig, role="upload", top_k=5
        )
        
        assert len(upload_landmarks) == 1
        assert upload_landmarks[0].role == "upload"
        assert upload_landmarks[0].text_snippet == "Subir"
    
    def test_error_handling_read_write(self, visual_memory, temp_dir):
        """Test que errores de lectura/escritura no lanzan excepción"""
        # Intentar leer snapshot inexistente (no debe lanzar excepción)
        snapshot = visual_memory.load_snapshot("nonexistent", "nonexistent")
        assert snapshot is None
        
        # Intentar actualizar con datos inválidos (no debe lanzar excepción)
        # Esto se maneja internamente con try/except
        visual_memory.update_heatmap_cell(
            platform="test",
            page_signature="test",
            row=-1,  # Inválido pero no debe lanzar
            col=-1,
            success=True,
        )
        
        # No debe haber excepción
        assert True
    
    def test_multiple_updates_same_cell(self, visual_memory):
        """Test múltiples actualizaciones de la misma celda"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        # Actualizar misma celda múltiples veces
        visual_memory.update_heatmap_cell(platform, page_sig, 1, 1, success=True)
        visual_memory.update_heatmap_cell(platform, page_sig, 1, 1, success=True)
        visual_memory.update_heatmap_cell(platform, page_sig, 1, 1, success=False)
        
        snapshot = visual_memory.load_snapshot(platform, page_sig)
        assert snapshot is not None
        cell = snapshot.heatmap.cells[0]
        
        assert cell.clicks == 3
        assert cell.successes == 2
        assert cell.failures == 1
        # Score: 2 - (1 * 0.5) = 1.5
        assert cell.score == 1.5
    
    def test_landmark_reuse(self, visual_memory):
        """Test reutilización de landmark existente"""
        platform = "test_platform"
        page_sig = "test_page_signature"
        
        landmark = VisualLandmark(
            platform=platform,
            page_signature=page_sig,
            x_center=0.5,
            y_center=0.3,
            width=0.1,
            height=0.05,
            text_snippet="Subir",
            landmark_type="button",
            role="upload",
        )
        
        # Registrar uso múltiples veces
        visual_memory.register_landmark_use(platform, page_sig, landmark, success=True)
        visual_memory.register_landmark_use(platform, page_sig, landmark, success=True)
        
        snapshot = visual_memory.load_snapshot(platform, page_sig)
        assert snapshot is not None
        # Debe haber solo un landmark (reutilizado)
        assert len(snapshot.landmarks) == 1
        
        saved_landmark = snapshot.landmarks[0]
        assert saved_landmark.uses == 2
        assert saved_landmark.successes == 2
















