"""
Tests para DocumentAnalyzer v4.4.0
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import date
from unittest.mock import MagicMock, AsyncMock, patch

from backend.agents.document_analyzer import DocumentAnalyzer
from backend.shared.models import DocumentAnalysisResult
from backend.vision.ocr_service import OCRService


class TestDocumentAnalyzer:
    """Tests para DocumentAnalyzer"""
    
    def test_analyze_extracts_dates(self):
        """Test que detecta fechas en el texto"""
        async def run_test():
            analyzer = DocumentAnalyzer()
            
            # Crear un PDF de prueba con texto simple
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("""
                Juan Pérez
                Fecha de reconocimiento: 01/03/2025
                Fecha de caducidad: 01/03/2026
                """)
                temp_path = f.name
            
            try:
                # Mock pypdf para simular extracción de texto
                with patch('backend.agents.document_analyzer.PYPDF_AVAILABLE', True):
                    with patch('backend.agents.document_analyzer.PdfReader') as mock_pdf:
                        mock_reader = MagicMock()
                        mock_page = MagicMock()
                        mock_page.extract_text.return_value = """
                        Juan Pérez
                        Fecha de reconocimiento: 01/03/2025
                        Fecha de caducidad: 01/03/2026
                        """
                        mock_reader.pages = [mock_page]
                        mock_pdf.return_value = mock_reader
                        
                        result = await analyzer.analyze(
                            file_path=temp_path,
                            expected_doc_type="reconocimiento_medico",
                            worker_full_name="Juan Pérez",
                        )
                        
                        assert isinstance(result, DocumentAnalysisResult)
                        assert result.issue_date == date(2025, 3, 1)
                        assert result.expiry_date == date(2026, 3, 1)
                        assert len(result.raw_dates) >= 2
                        assert "01/03/2025" in result.raw_dates or "2025-03-01" in str(result.issue_date)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        import asyncio
        asyncio.run(run_test())
    
    def test_analyze_detects_worker_name(self):
        """Test que detecta el nombre del trabajador cuando coincide con worker_full_name"""
        async def run_test():
            analyzer = DocumentAnalyzer()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
                f.write("dummy")  # Solo para crear el archivo
                temp_path = f.name
            
            try:
                with patch('backend.agents.document_analyzer.PYPDF_AVAILABLE', True):
                    with patch('backend.agents.document_analyzer.PdfReader') as mock_pdf:
                        mock_reader = MagicMock()
                        mock_page = MagicMock()
                        # Asegurar que el texto es suficientemente largo (>50 caracteres)
                        mock_page.extract_text.return_value = "Juan Pérez García\nReconocimiento médico\nFecha de emisión: 01/03/2025\nFecha de caducidad: 01/03/2026"
                        mock_reader.pages = [mock_page]
                        mock_pdf.return_value = mock_reader
                        
                        result = await analyzer.analyze(
                            file_path=temp_path,
                            expected_doc_type="reconocimiento_medico",
                            worker_full_name="Juan Pérez García",
                        )
                        
                        assert result.worker_name == "Juan Pérez García"
                        assert result.confidence > 0.0
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        import asyncio
        asyncio.run(run_test())
    
    def test_analyze_uses_expected_doc_type(self):
        """Test que usa expected_doc_type cuando está disponible"""
        async def run_test():
            analyzer = DocumentAnalyzer()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("Test document")
                temp_path = f.name
            
            try:
                with patch('backend.agents.document_analyzer.PYPDF_AVAILABLE', True):
                    with patch('backend.agents.document_analyzer.PdfReader') as mock_pdf:
                        mock_reader = MagicMock()
                        mock_page = MagicMock()
                        mock_page.extract_text.return_value = "Test document"
                        mock_reader.pages = [mock_page]
                        mock_pdf.return_value = mock_reader
                        
                        result = await analyzer.analyze(
                            file_path=temp_path,
                            expected_doc_type="reconocimiento_medico",
                        )
                        
                        assert result.doc_type == "reconocimiento_medico"
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        import asyncio
        asyncio.run(run_test())
    
    def test_analyze_handles_no_text_gracefully(self):
        """Test que maneja correctamente PDFs sin texto o con texto muy corto"""
        async def run_test():
            analyzer = DocumentAnalyzer()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("")
                temp_path = f.name
            
            try:
                with patch('backend.agents.document_analyzer.PYPDF_AVAILABLE', True):
                    with patch('backend.agents.document_analyzer.PdfReader') as mock_pdf:
                        mock_reader = MagicMock()
                        mock_page = MagicMock()
                        mock_page.extract_text.return_value = ""  # Texto vacío
                        mock_reader.pages = [mock_page]
                        mock_pdf.return_value = mock_reader
                        
                        result = await analyzer.analyze(
                            file_path=temp_path,
                        )
                        
                        assert isinstance(result, DocumentAnalysisResult)
                        assert len(result.warnings) > 0
                        assert "No se ha podido extraer texto útil" in result.warnings[0] or "texto muy corto" in result.warnings[0]
                        assert result.confidence < 0.5
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        import asyncio
        asyncio.run(run_test())
    
    def test_analyze_handles_pypdf_unavailable(self):
        """Test que maneja correctamente cuando pypdf no está disponible"""
        async def run_test():
            analyzer = DocumentAnalyzer()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("Test")
                temp_path = f.name
            
            try:
                with patch('backend.agents.document_analyzer.PYPDF_AVAILABLE', False):
                    result = await analyzer.analyze(
                        file_path=temp_path,
                    )
                    
                    assert isinstance(result, DocumentAnalysisResult)
                    assert len(result.warnings) > 0
                    assert "pypdf no está disponible" in result.warnings[0]
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        import asyncio
        asyncio.run(run_test())
    
    def test_analyze_calculates_confidence(self):
        """Test que calcula confidence correctamente"""
        async def run_test():
            analyzer = DocumentAnalyzer()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("Juan Pérez\nFecha: 01/03/2025\nCaducidad: 01/03/2026")
                temp_path = f.name
            
            try:
                with patch('backend.agents.document_analyzer.PYPDF_AVAILABLE', True):
                    with patch('backend.agents.document_analyzer.PdfReader') as mock_pdf:
                        mock_reader = MagicMock()
                        mock_page = MagicMock()
                        mock_page.extract_text.return_value = "Juan Pérez\nFecha: 01/03/2025\nCaducidad: 01/03/2026"
                        mock_reader.pages = [mock_page]
                        mock_pdf.return_value = mock_reader
                        
                        result = await analyzer.analyze(
                            file_path=temp_path,
                            expected_doc_type="reconocimiento_medico",
                            worker_full_name="Juan Pérez",
                        )
                        
                        assert 0.0 <= result.confidence <= 1.0
                        # Con texto, worker_name y fechas, debería tener confidence > 0.5
                        assert result.confidence > 0.5
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        import asyncio
        asyncio.run(run_test())

