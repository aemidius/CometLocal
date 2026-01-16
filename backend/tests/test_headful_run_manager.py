"""
Tests para HeadfulRunManager.
"""

import pytest
import os
from unittest.mock import Mock, MagicMock
from backend.runs.headful_run_manager import HeadfulRunManager, HeadfulRun


def test_manager_singleton():
    """Test que HeadfulRunManager es singleton."""
    manager1 = HeadfulRunManager()
    manager2 = HeadfulRunManager()
    assert manager1 is manager2


def test_start_run_requires_dev_environment():
    """Test que start_run requiere ENVIRONMENT=dev."""
    manager = HeadfulRunManager()
    original_env = os.getenv("ENVIRONMENT")
    
    try:
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
        
        browser = Mock()
        context = Mock()
        page = Mock()
        
        with pytest.raises(RuntimeError, match="ENVIRONMENT=dev"):
            manager.start_run(
                run_id="test",
                storage_state_path="/path/to/storage.json",
                browser=browser,
                context=context,
                page=page,
            )
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env


def test_start_run_creates_new_run():
    """Test que start_run crea un nuevo run."""
    manager = HeadfulRunManager()
    original_env = os.getenv("ENVIRONMENT")
    
    try:
        os.environ["ENVIRONMENT"] = "dev"
        
        browser = Mock()
        context = Mock()
        page = Mock()
        
        run = manager.start_run(
            run_id="test_run_1",
            storage_state_path="/path/to/storage.json",
            browser=browser,
            context=context,
            page=page,
        )
        
        assert run.run_id == "test_run_1"
        assert run.browser is browser
        assert run.context is context
        assert run.page is page
        assert manager.has_run("test_run_1")
        
        # Limpiar
        manager.close_run("test_run_1")
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]


def test_start_run_returns_existing():
    """Test que start_run devuelve run existente si ya está activo."""
    manager = HeadfulRunManager()
    original_env = os.getenv("ENVIRONMENT")
    
    try:
        os.environ["ENVIRONMENT"] = "dev"
        
        browser1 = Mock()
        context1 = Mock()
        page1 = Mock()
        
        run1 = manager.start_run(
            run_id="test_run_2",
            storage_state_path="/path/to/storage.json",
            browser=browser1,
            context=context1,
            page=page1,
        )
        
        browser2 = Mock()
        context2 = Mock()
        page2 = Mock()
        
        run2 = manager.start_run(
            run_id="test_run_2",
            storage_state_path="/path/to/storage2.json",
            browser=browser2,
            context=context2,
            page=page2,
        )
        
        assert run1 is run2
        assert run1.browser is browser1  # Mantiene el original
        
        # Limpiar
        manager.close_run("test_run_2")
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]


def test_get_run():
    """Test que get_run recupera un run activo."""
    manager = HeadfulRunManager()
    original_env = os.getenv("ENVIRONMENT")
    
    try:
        os.environ["ENVIRONMENT"] = "dev"
        
        browser = Mock()
        context = Mock()
        page = Mock()
        
        manager.start_run(
            run_id="test_run_3",
            storage_state_path="/path/to/storage.json",
            browser=browser,
            context=context,
            page=page,
        )
        
        run = manager.get_run("test_run_3")
        assert run is not None
        assert run.run_id == "test_run_3"
        
        assert manager.get_run("nonexistent") is None
        
        # Limpiar
        manager.close_run("test_run_3")
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]


def test_close_run():
    """Test que close_run elimina un run."""
    manager = HeadfulRunManager()
    original_env = os.getenv("ENVIRONMENT")
    
    try:
        os.environ["ENVIRONMENT"] = "dev"
        
        browser = Mock()
        context = Mock()
        page = Mock()
        
        manager.start_run(
            run_id="test_run_4",
            storage_state_path="/path/to/storage.json",
            browser=browser,
            context=context,
            page=page,
        )
        
        assert manager.has_run("test_run_4")
        
        closed = manager.close_run("test_run_4")
        assert closed is True
        assert not manager.has_run("test_run_4")
        
        # Cerrar de nuevo debe retornar False
        closed_again = manager.close_run("test_run_4")
        assert closed_again is False
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]


def test_list_runs():
    """Test que list_runs lista todos los runs activos."""
    manager = HeadfulRunManager()
    original_env = os.getenv("ENVIRONMENT")
    
    try:
        os.environ["ENVIRONMENT"] = "dev"
        
        browser1 = Mock()
        context1 = Mock()
        page1 = Mock()
        
        browser2 = Mock()
        context2 = Mock()
        page2 = Mock()
        
        manager.start_run(
            run_id="test_run_5",
            storage_state_path="/path/to/storage1.json",
            browser=browser1,
            context=context1,
            page=page1,
        )
        
        manager.start_run(
            run_id="test_run_6",
            storage_state_path="/path/to/storage2.json",
            browser=browser2,
            context=context2,
            page=page2,
        )
        
        runs = manager.list_runs()
        assert len(runs) == 2
        assert "test_run_5" in runs
        assert "test_run_6" in runs
        assert runs["test_run_5"]["storage_state_path"] == "/path/to/storage1.json"
        
        # Limpiar
        manager.close_run("test_run_5")
        manager.close_run("test_run_6")
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
