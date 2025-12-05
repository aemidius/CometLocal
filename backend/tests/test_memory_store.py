"""
Tests para memory_store v3.9.0
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from backend.memory.memory_store import MemoryStore, _normalize_company_name
from backend.shared.models import WorkerMemory, CompanyMemory, PlatformMemory


class TestMemoryStore:
    """Tests para MemoryStore"""
    
    @pytest.fixture
    def temp_dir(self):
        """Crea un directorio temporal para tests"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    def test_normalize_company_name(self):
        """_normalize_company_name debe normalizar nombres correctamente"""
        assert _normalize_company_name("Empresa Test") == "empresa_test"
        assert _normalize_company_name("Empresa-Test") == "empresa-test"  # Los guiones se mantienen
        assert _normalize_company_name("Empresa  Test") == "empresa_test"
        assert _normalize_company_name("Empresa@Test") == "empresa_test"
        assert _normalize_company_name("EMPRESA TEST") == "empresa_test"
    
    def test_save_and_load_worker_memory(self, temp_dir):
        """Debe poder guardar y cargar memoria de trabajador"""
        store = MemoryStore(temp_dir)
        
        worker_memory = WorkerMemory(
            worker_id="worker_123",
            full_name="Juan Pérez",
            company_name="Empresa Test",
            successful_docs={"dni": 2, "contrato": 1},
            failed_docs={"reconocimiento_medico": 1},
            last_seen=datetime.now(),
            notes="Trabajador activo",
        )
        
        # Guardar
        store.save_worker(worker_memory)
        
        # Cargar
        loaded = store.load_worker("worker_123")
        
        assert loaded is not None
        assert loaded.worker_id == "worker_123"
        assert loaded.full_name == "Juan Pérez"
        assert loaded.company_name == "Empresa Test"
        assert loaded.successful_docs == {"dni": 2, "contrato": 1}
        assert loaded.failed_docs == {"reconocimiento_medico": 1}
        assert loaded.notes == "Trabajador activo"
        assert loaded.last_seen is not None
    
    def test_save_and_load_company_memory(self, temp_dir):
        """Debe poder guardar y cargar memoria de empresa"""
        store = MemoryStore(temp_dir)
        
        company_memory = CompanyMemory(
            company_name="Empresa Test",
            platform="test_platform",
            required_docs_counts={"dni": 10, "contrato": 8},
            missing_docs_counts={"reconocimiento_medico": 2},
            upload_error_counts={"formacion": 1},
            last_seen=datetime.now(),
        )
        
        # Guardar
        store.save_company(company_memory)
        
        # Cargar
        loaded = store.load_company("Empresa Test", "test_platform")
        
        assert loaded is not None
        assert loaded.company_name == "Empresa Test"
        assert loaded.platform == "test_platform"
        assert loaded.required_docs_counts == {"dni": 10, "contrato": 8}
        assert loaded.missing_docs_counts == {"reconocimiento_medico": 2}
        assert loaded.upload_error_counts == {"formacion": 1}
    
    def test_save_and_load_platform_memory(self, temp_dir):
        """Debe poder guardar y cargar memoria de plataforma"""
        store = MemoryStore(temp_dir)
        
        platform_memory = PlatformMemory(
            platform="test_platform",
            visual_click_usage=15,
            visual_recovery_usage=5,
            upload_error_counts=3,
            ocr_usage=20,
            last_seen=datetime.now(),
        )
        
        # Guardar
        store.save_platform(platform_memory)
        
        # Cargar
        loaded = store.load_platform("test_platform")
        
        assert loaded is not None
        assert loaded.platform == "test_platform"
        assert loaded.visual_click_usage == 15
        assert loaded.visual_recovery_usage == 5
        assert loaded.upload_error_counts == 3
        assert loaded.ocr_usage == 20
    
    def test_memory_store_handles_missing_files(self, temp_dir):
        """Debe retornar None cuando no existe el archivo"""
        store = MemoryStore(temp_dir)
        
        # Intentar cargar memoria inexistente
        worker = store.load_worker("nonexistent")
        assert worker is None
        
        company = store.load_company("Nonexistent Company")
        assert company is None
        
        platform = store.load_platform("nonexistent_platform")
        assert platform is None
    
    def test_memory_store_handles_corrupt_json_gracefully(self, temp_dir):
        """Debe manejar JSON corrupto sin lanzar excepciones fatales"""
        store = MemoryStore(temp_dir)
        
        # Crear archivo JSON corrupto
        corrupt_file = Path(temp_dir) / "workers" / "corrupt_worker.json"
        corrupt_file.parent.mkdir(parents=True, exist_ok=True)
        with open(corrupt_file, 'w') as f:
            f.write("{ invalid json }")
        
        # Intentar cargar debe retornar None sin lanzar excepción
        loaded = store.load_worker("corrupt_worker")
        assert loaded is None
    
    def test_memory_store_incremental_updates(self, temp_dir):
        """Debe poder actualizar memoria incrementalmente"""
        store = MemoryStore(temp_dir)
        
        # Crear memoria inicial
        worker_memory = WorkerMemory(
            worker_id="worker_123",
            successful_docs={"dni": 1},
            failed_docs={},
        )
        store.save_worker(worker_memory)
        
        # Cargar y actualizar
        loaded = store.load_worker("worker_123")
        assert loaded is not None
        loaded.successful_docs["contrato"] = 1
        loaded.failed_docs["reconocimiento_medico"] = 1
        store.save_worker(loaded)
        
        # Verificar que se guardó correctamente
        reloaded = store.load_worker("worker_123")
        assert reloaded is not None
        assert reloaded.successful_docs == {"dni": 1, "contrato": 1}
        assert reloaded.failed_docs == {"reconocimiento_medico": 1}

