"""
Tests unitarios para document_repository.py v2.2.0

Cubre:
- DocumentRepository.find_latest
- DocumentRepository.find_all
- Comportamiento con diferentes combinaciones de company/worker/doc_type
- Ordenamiento por fecha
- Integración con resolve_document_request
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
import time
from datetime import datetime, timedelta

from backend.agents.document_repository import (
    DocumentRepository,
    DocumentDescriptor,
)
from backend.documents.helpers import resolve_document_request
from backend.shared.models import DocumentRequest


class TestDocumentRepository:
    """Tests para DocumentRepository"""
    
    def setup_method(self):
        """Crea un directorio temporal para cada test"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_path = Path(self.temp_dir)
        self.repo = DocumentRepository(self.base_path)
    
    def teardown_method(self):
        """Limpia el directorio temporal después de cada test"""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def _create_test_structure(self):
        """Crea una estructura de prueba con documentos"""
        # EmpresaX/JuanPerez/prl/doc1.pdf (más antiguo)
        prl_dir = self.base_path / "EmpresaX" / "JuanPerez" / "prl"
        prl_dir.mkdir(parents=True)
        doc1 = prl_dir / "doc1.pdf"
        doc1.write_text("Contenido doc1")
        # Hacer que doc1 sea más antiguo
        old_time = time.time() - 3600  # 1 hora atrás
        os.utime(str(doc1), (old_time, old_time))
        
        # EmpresaX/JuanPerez/prl/doc2.pdf (más reciente)
        doc2 = prl_dir / "doc2.pdf"
        doc2.write_text("Contenido doc2")
        # doc2 es más reciente (por defecto)
        
        # EmpresaX/JuanPerez/reconocimiento_medico/rec1.pdf
        rec_dir = self.base_path / "EmpresaX" / "JuanPerez" / "reconocimiento_medico"
        rec_dir.mkdir(parents=True)
        rec1 = rec_dir / "rec1.pdf"
        rec1.write_text("Contenido reconocimiento")
        
        # EmpresaX/MariaGarcia/prl/doc3.pdf
        maria_prl_dir = self.base_path / "EmpresaX" / "MariaGarcia" / "prl"
        maria_prl_dir.mkdir(parents=True)
        doc3 = maria_prl_dir / "doc3.pdf"
        doc3.write_text("Contenido doc3")
        
        return {
            "doc1": doc1,
            "doc2": doc2,
            "rec1": rec1,
            "doc3": doc3,
        }
    
    def test_find_latest_with_all_fields(self):
        """Encuentra el documento más reciente cuando se especifican todos los campos"""
        docs = self._create_test_structure()
        
        result = self.repo.find_latest(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type="prl"
        )
        
        assert result is not None
        assert result.path == docs["doc2"]  # doc2 es más reciente
        assert result.company == "EmpresaX"
        assert result.worker == "JuanPerez"
        assert result.doc_type == "prl"
    
    def test_find_all_ordered_by_date(self):
        """list_documents devuelve documentos ordenados por fecha (más reciente primero)"""
        docs = self._create_test_structure()
        
        results = self.repo.list_documents(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type="prl"
        )
        
        assert len(results) == 2
        assert results[0].path == docs["doc2"]  # Más reciente primero
        assert results[1].path == docs["doc1"]  # Más antiguo segundo
        assert float(results[0].extra.get("modified_time", 0)) > float(results[1].extra.get("modified_time", 0))
    
    def test_find_all_without_worker(self):
        """list_documents encuentra documentos de todos los trabajadores cuando worker es None"""
        self._create_test_structure()
        
        results = self.repo.list_documents(
            company="EmpresaX",
            worker=None,
            doc_type="prl"
        )
        
        # Debe encontrar doc1, doc2 (JuanPerez) y doc3 (MariaGarcia)
        assert len(results) == 3
        worker_names = {r.worker for r in results}
        assert "JuanPerez" in worker_names
        assert "MariaGarcia" in worker_names
    
    def test_find_all_without_doc_type(self):
        """list_documents encuentra todos los tipos de documentos cuando doc_type es None"""
        self._create_test_structure()
        
        results = self.repo.list_documents(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type=None
        )
        
        # Debe encontrar doc1, doc2 (prl) y rec1 (reconocimiento_medico)
        assert len(results) == 3
        doc_types = {r.doc_type for r in results}
        assert "prl" in doc_types
        assert "reconocimiento_medico" in doc_types
    
    def test_find_all_without_worker_and_doc_type(self):
        """list_documents encuentra todos los documentos de la empresa cuando solo se especifica company"""
        self._create_test_structure()
        
        results = self.repo.list_documents(
            company="EmpresaX",
            worker=None,
            doc_type=None
        )
        
        # Debe encontrar todos los documentos: doc1, doc2, rec1, doc3
        assert len(results) == 4
    
    def test_find_latest_not_found(self):
        """find_latest devuelve None cuando no se encuentra ningún documento"""
        result = self.repo.find_latest(
            company="EmpresaInexistente",
            worker="TrabajadorInexistente",
            doc_type="prl"
        )
        
        assert result is None
    
    def test_find_all_empty_repository(self):
        """list_documents devuelve lista vacía cuando el repositorio está vacío"""
        results = self.repo.list_documents(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type="prl"
        )
        
        assert results == []
    
    def test_allowed_extensions_filtering(self):
        """Solo se incluyen archivos con extensiones permitidas"""
        prl_dir = self.base_path / "EmpresaX" / "JuanPerez" / "prl"
        prl_dir.mkdir(parents=True)
        
        # Crear archivos con diferentes extensiones
        (prl_dir / "doc.pdf").write_text("PDF")
        (prl_dir / "doc.docx").write_text("DOCX")
        (prl_dir / "doc.txt").write_text("TXT")
        (prl_dir / "doc.exe").write_text("EXE")  # No permitido
        
        results = self.repo.list_documents(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type="prl"
        )
        
        # Debe encontrar solo .pdf, .docx, .txt (no .exe)
        assert len(results) == 3
        extensions = {r.path.suffix.lower() for r in results}
        assert ".pdf" in extensions
        assert ".docx" in extensions
        assert ".txt" in extensions
        assert ".exe" not in extensions
    
    def test_infer_doc_type_from_directory_name(self):
        """Infiere correctamente el tipo de documento desde el nombre del directorio"""
        # Crear directorios con nombres variados
        (self.base_path / "EmpresaX" / "JuanPerez" / "contratos").mkdir(parents=True)
        (self.base_path / "EmpresaX" / "JuanPerez" / "formación").mkdir(parents=True)
        (self.base_path / "EmpresaX" / "JuanPerez" / "reconocimientos").mkdir(parents=True)
        
        # Crear archivos
        (self.base_path / "EmpresaX" / "JuanPerez" / "contratos" / "c1.pdf").write_text("Contrato")
        (self.base_path / "EmpresaX" / "JuanPerez" / "formación" / "f1.pdf").write_text("Formación")
        (self.base_path / "EmpresaX" / "JuanPerez" / "reconocimientos" / "r1.pdf").write_text("Reconocimiento")
        
        results = self.repo.list_documents(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type=None
        )
        
        assert len(results) == 3
        doc_types = {r.doc_type for r in results}
        # El nuevo sistema usa el nombre del directorio directamente
        assert "contratos" in doc_types or "contrato" in doc_types
        assert "formación" in doc_types or "formacion" in doc_types
        assert "reconocimientos" in doc_types or "reconocimiento_medico" in doc_types


class TestDocumentRepositoryHelpers:
    """Tests para helpers de integración"""
    
    def setup_method(self):
        """Crea un directorio temporal para cada test"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_path = Path(self.temp_dir)
        
        # Crear estructura de prueba
        prl_dir = self.base_path / "EmpresaX" / "JuanPerez" / "prl"
        prl_dir.mkdir(parents=True)
        doc1 = prl_dir / "doc1.pdf"
        doc1.write_text("Contenido doc1")
    
    def teardown_method(self):
        """Limpia el directorio temporal después de cada test"""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_resolve_document_request_found(self):
        """resolve_document_request encuentra un documento existente"""
        # Resetear la instancia global del repositorio primero
        from backend.documents import helpers
        helpers._repository_instance = None
        
        doc_request = DocumentRequest(
            company="EmpresaX",
            worker="JuanPerez",
            doc_type="prl"
        )
        
        # Pasar base_path directamente para evitar problemas con config
        result = resolve_document_request(doc_request, base_path=self.base_path)
        
        assert result is not None
        assert result.company == "EmpresaX"
        assert result.worker == "JuanPerez"
        assert result.doc_type == "prl"
        assert result.path.exists()
        
        # Resetear instancia
        helpers._repository_instance = None
    
    def test_resolve_document_request_not_found(self):
        """resolve_document_request devuelve None cuando no se encuentra el documento"""
        from backend.documents import helpers
        helpers._repository_instance = None
        
        doc_request = DocumentRequest(
            company="EmpresaInexistente",
            worker="TrabajadorInexistente",
            doc_type="prl"
        )
        
        # Pasar base_path directamente
        result = resolve_document_request(doc_request, base_path=self.base_path)
        
        assert result is None
        
        # Resetear instancia
        helpers._repository_instance = None


class TestDocumentRepositoryIntegration:
    """Tests de integración para verificar formato en StepResult.info"""
    
    def test_document_info_format(self):
        """Verifica que DocumentInfo.to_dict() produce el formato esperado"""
        import tempfile
        from pathlib import Path
        
        temp_dir = tempfile.mkdtemp()
        try:
            base_path = Path(temp_dir)
            repo = DocumentRepository(base_path)
            
            # Crear documento de prueba
            doc_path = base_path / "EmpresaX" / "JuanPerez" / "prl" / "doc.pdf"
            doc_path.parent.mkdir(parents=True)
            doc_path.write_text("Contenido")
            
            doc_info = repo.find_latest(
                company="EmpresaX",
                worker="JuanPerez",
                doc_type="prl"
            )
            
            assert doc_info is not None
            # Verificar estructura (DocumentDescriptor es un dataclass simple)
            assert doc_info.path is not None
            assert doc_info.company == "EmpresaX"
            assert doc_info.worker == "JuanPerez"
            assert doc_info.doc_type == "prl"
            assert isinstance(doc_info.extra, dict)
        finally:
            import shutil
            shutil.rmtree(temp_dir)
    
    def test_requested_document_format(self):
        """Verifica que el formato de requested_document en StepResult.info es correcto"""
        from backend.shared.models import StepResult, BrowserObservation
        from backend.documents.helpers import resolve_document_request
        from backend.shared.models import DocumentRequest
        import tempfile
        from pathlib import Path
        
        temp_dir = tempfile.mkdtemp()
        try:
            # Resetear instancia primero
            from backend.documents import helpers
            helpers._repository_instance = None
            
            # Crear documento de prueba
            base_path = Path(temp_dir)
            doc_path = base_path / "EmpresaX" / "JuanPerez" / "prl" / "doc.pdf"
            doc_path.parent.mkdir(parents=True)
            doc_path.write_text("Contenido")
            
            # Resolver petición pasando base_path directamente
            doc_request = DocumentRequest(
                company="EmpresaX",
                worker="JuanPerez",
                doc_type="prl"
            )
            
            doc_info = resolve_document_request(doc_request, base_path=base_path)
            
            assert doc_info is not None
            
            # Simular adjuntar a StepResult.info
            obs = BrowserObservation(
                url="https://example.com",
                title="Test",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            step_result = StepResult(
                observation=obs,
                info={
                    "requested_document": {
                        "company": doc_info.company,
                        "worker": doc_info.worker,
                        "doc_type": doc_info.doc_type,
                        "found": True,
                        "path": str(doc_info.path),  # Solo para debug interno
                    }
                }
            )
            
            # Verificar estructura
            assert "requested_document" in step_result.info
            req_doc = step_result.info["requested_document"]
            assert req_doc["company"] == "EmpresaX"
            assert req_doc["worker"] == "JuanPerez"
            assert req_doc["doc_type"] == "prl"
            assert req_doc["found"] is True
            assert "path" in req_doc
        finally:
            helpers._repository_instance = None
            import shutil
            shutil.rmtree(temp_dir)

