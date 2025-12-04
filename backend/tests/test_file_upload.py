"""
Tests unitarios para file upload v2.3.0

Cubre:
- BrowserController.upload_file
- _maybe_execute_file_upload
- Integración con FileUploadInstruction
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import anyio

from backend.browser.browser import BrowserController
from backend.agents.file_upload import FileUploadInstruction
from backend.agents.agent_runner import _maybe_execute_file_upload
from backend.shared.models import BrowserObservation, StepResult


class TestBrowserControllerUploadFile:
    """Tests para BrowserController.upload_file"""
    
    def test_upload_file_success(self):
        """upload_file sube correctamente un archivo cuando hay input[type='file']"""
        async def _test():
            # Crear archivo temporal
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False)
            temp_file.write("Test content")
            temp_file.close()
            temp_path = temp_file.name
            
            try:
                # Mock de Playwright page
                mock_page = MagicMock()
                mock_page.wait_for_timeout = AsyncMock()  # Mock para wait_for_timeout
                mock_locator = MagicMock()
                mock_page.locator.return_value = mock_locator
                mock_locator.first = mock_locator
                mock_locator.get_attribute = AsyncMock(return_value="file")
                mock_locator.set_input_files = AsyncMock()  # Necesita ser AsyncMock
                
                # Mock de observación
                mock_obs = BrowserObservation(
                    url="https://example.com/upload",
                    title="Upload Page",
                    visible_text_excerpt="Upload form",
                    clickable_texts=[],
                    input_hints=[],
                )
                
                controller = BrowserController()
                controller.page = mock_page
                
                # Mock get_observation
                controller.get_observation = AsyncMock(return_value=mock_obs)
                
                # Ejecutar upload
                result = await controller.upload_file("input[type='file']", temp_path)
                
                # Verificar que se llamó set_input_files
                mock_locator.set_input_files.assert_called_once_with(temp_path)
                
                # Verificar que se devolvió la observación
                assert result == mock_obs
                
            finally:
                # Limpiar archivo temporal
                Path(temp_path).unlink()
        
        anyio.run(_test)
    
    def test_upload_file_no_input_found(self):
        """upload_file lanza excepción cuando no hay input[type='file']"""
        async def _test():
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False)
            temp_file.write("Test content")
            temp_file.close()
            temp_path = temp_file.name
            
            try:
                # Mock de Playwright page sin input file
                mock_page = MagicMock()
                mock_locator = MagicMock()
                mock_page.locator.return_value = mock_locator
                mock_locator.first = mock_locator
                # Simular que get_attribute lanza excepción o devuelve None
                # Para que falle, hacemos que locator.first no tenga get_attribute
                mock_locator.get_attribute = AsyncMock(side_effect=Exception("Element not found"))
                
                controller = BrowserController()
                controller.page = mock_page
                
                # Ejecutar upload - debe lanzar excepción
                with pytest.raises(Exception) as exc_info:
                    await controller.upload_file("input[type='file']", temp_path)
                
                error_msg = str(exc_info.value).lower()
                assert "not found" in error_msg or "no se encontró" in error_msg or "error" in error_msg
                
            finally:
                Path(temp_path).unlink()
        
        anyio.run(_test)


class TestMaybeExecuteFileUpload:
    """Tests para _maybe_execute_file_upload"""
    
    def test_maybe_execute_file_upload_success(self):
        """_maybe_execute_file_upload ejecuta upload exitosamente"""
        async def _test():
            # Crear archivo temporal
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False)
            temp_file.write("Test content")
            temp_file.close()
            temp_path = Path(temp_file.name)
            
            try:
                # Crear FileUploadInstruction
                instruction = FileUploadInstruction(
                    path=temp_path,
                    description="Test document",
                    company="TestCompany",
                    worker="TestWorker",
                    doc_type="prl",
                )
                
                # Mock de BrowserController
                mock_browser = MagicMock(spec=BrowserController)
                mock_obs = BrowserObservation(
                    url="https://example.com/upload",
                    title="Upload Page",
                    visible_text_excerpt="Upload form",
                    clickable_texts=[],
                    input_hints=[],
                )
                mock_browser.upload_file = AsyncMock(return_value=mock_obs)
                mock_browser.get_observation = AsyncMock(return_value=mock_obs)
                
                # Ejecutar
                result = await _maybe_execute_file_upload(mock_browser, instruction)
                
                # Verificar resultado
                assert result is not None
                assert isinstance(result, StepResult)
                assert result.info["upload_status"] == "success"
                assert result.info["file_upload_instruction"]["description"] == "Test document"
                assert result.last_action is not None
                assert result.last_action.type == "upload_file"
                assert result.error is None
                
                # Verificar que se llamó upload_file
                mock_browser.upload_file.assert_called_once()
                
            finally:
                Path(temp_path).unlink()
        
        anyio.run(_test)
    
    def test_maybe_execute_file_upload_file_not_found(self):
        """_maybe_execute_file_upload maneja archivo no encontrado"""
        async def _test():
            # Crear FileUploadInstruction con archivo inexistente
            instruction = FileUploadInstruction(
                path=Path("/nonexistent/file.pdf"),
                description="Nonexistent document",
            )
            
            # Mock de BrowserController
            mock_browser = MagicMock(spec=BrowserController)
            mock_obs = BrowserObservation(
                url="https://example.com",
                title="Test",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            mock_browser.get_observation = AsyncMock(return_value=mock_obs)
            
            # Ejecutar
            result = await _maybe_execute_file_upload(mock_browser, instruction)
            
            # Verificar resultado
            assert result is not None
            assert isinstance(result, StepResult)
            assert result.info["upload_status"] == "file_not_found"
            assert result.error is not None
            assert "no encontrado" in result.error.lower() or "not found" in result.error.lower()
        
        anyio.run(_test)
    
    def test_maybe_execute_file_upload_no_input_found(self):
        """_maybe_execute_file_upload maneja cuando no hay input[type='file']"""
        async def _test():
            # Crear archivo temporal
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False)
            temp_file.write("Test content")
            temp_file.close()
            temp_path = Path(temp_file.name)
            
            try:
                # Crear FileUploadInstruction
                instruction = FileUploadInstruction(
                    path=temp_path,
                    description="Test document",
                )
                
                # Mock de BrowserController que lanza excepción de "no encontrado"
                mock_browser = MagicMock(spec=BrowserController)
                mock_obs = BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                )
                mock_browser.upload_file = AsyncMock(side_effect=Exception("No se encontró input[type='file']"))
                mock_browser.get_observation = AsyncMock(return_value=mock_obs)
                
                # Ejecutar
                result = await _maybe_execute_file_upload(mock_browser, instruction)
                
                # Verificar resultado
                assert result is not None
                assert isinstance(result, StepResult)
                assert result.info["upload_status"] == "no_input_found"
                assert result.error is not None
                
            finally:
                Path(temp_path).unlink()
        
        anyio.run(_test)
    
    def test_maybe_execute_file_upload_error(self):
        """_maybe_execute_file_upload maneja errores genéricos"""
        async def _test():
            # Crear archivo temporal
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False)
            temp_file.write("Test content")
            temp_file.close()
            temp_path = Path(temp_file.name)
            
            try:
                # Crear FileUploadInstruction
                instruction = FileUploadInstruction(
                    path=temp_path,
                    description="Test document",
                )
                
                # Mock de BrowserController que lanza excepción genérica
                mock_browser = MagicMock(spec=BrowserController)
                mock_obs = BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                )
                mock_browser.upload_file = AsyncMock(side_effect=Exception("Generic error"))
                mock_browser.get_observation = AsyncMock(return_value=mock_obs)
                
                # Ejecutar
                result = await _maybe_execute_file_upload(mock_browser, instruction)
                
                # Verificar resultado
                assert result is not None
                assert isinstance(result, StepResult)
                assert result.info["upload_status"] == "error"
                assert result.error is not None
                
            finally:
                Path(temp_path).unlink()
        
        anyio.run(_test)


class TestFileUploadIntegration:
    """Tests de integración para uploads en el flujo del agente"""
    
    def test_upload_step_included_in_metrics(self):
        """Los steps de upload se incluyen en el flujo de métricas"""
        from backend.agents.agent_runner import AgentMetrics
        
        metrics = AgentMetrics()
        
        # Simular un step con upload
        from backend.shared.models import StepResult, BrowserObservation, BrowserAction
        
        upload_step = StepResult(
            observation=BrowserObservation(
                url="https://example.com",
                title="Test",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            ),
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": "/test/file.pdf", "selector": "input[type='file']"}
            ),
            error=None,
            info={
                "upload_status": "success",
                "file_upload_instruction": {
                    "path": "/test/file.pdf",
                    "description": "Test document",
                }
            }
        )
        
        # Simular conteo de uploads (como se hace en run_llm_task_with_answer)
        if upload_step.info and "upload_status" in upload_step.info:
            metrics.upload_attempts += 1
            upload_status = upload_step.info.get("upload_status")
            if upload_status == "success":
                metrics.upload_successes += 1
        
        # Verificar contadores
        assert metrics.upload_attempts == 1
        assert metrics.upload_successes == 1
        
        # Verificar que aparece en el summary
        summary = metrics.to_summary_dict()
        assert "upload_info" in summary["summary"]
        assert summary["summary"]["upload_info"]["upload_attempts"] == 1
        assert summary["summary"]["upload_info"]["upload_successes"] == 1
        assert summary["summary"]["upload_info"]["upload_success_ratio"] == 1.0

