"""
Tests para PageContractError y manejo de errores estructurados.
"""

import pytest
from pathlib import Path
from backend.adapters.egestiona.page_contract_validator import PageContractError, validate_pending_page_contract


def test_page_contract_error_creation():
    """Test que PageContractError se crea correctamente."""
    error = PageContractError(
        error_code="test_error",
        message="Test message",
        details={"key": "value"},
        evidence_paths={"screenshot": "test.png"}
    )
    
    assert error.error_code == "test_error"
    assert error.message == "Test message"
    assert error.details == {"key": "value"}
    assert error.evidence_paths == {"screenshot": "test.png"}
    assert str(error) == "Test message"


def test_page_contract_error_optional_fields():
    """Test que PageContractError funciona con campos opcionales."""
    error = PageContractError(
        error_code="test_error",
        message="Test message"
    )
    
    assert error.error_code == "test_error"
    assert error.message == "Test message"
    assert error.details == {}
    assert error.evidence_paths == {}


def test_validate_pending_page_contract_raises_on_no_auth():
    """Test que validate_pending_page_contract lanza PageContractError cuando no hay autenticación."""
    from unittest.mock import Mock
    
    # Mock page sin autenticación
    mock_page = Mock()
    mock_page.frame.return_value = None
    mock_page.locator.return_value.count.return_value = 0
    mock_page.url = "http://example.com/login"
    mock_page.screenshot = Mock()
    mock_page.evaluate = Mock(return_value={"url": "http://example.com/login", "title": "Login", "bodyText": "Login page"})
    
    evidence_dir = Path("/tmp/test_evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    with pytest.raises(PageContractError) as exc_info:
        validate_pending_page_contract(
            page=mock_page,
            list_frame=None,
            evidence_dir=evidence_dir,
        )
    
    assert exc_info.value.error_code == "not_authenticated"
    assert "autenticación" in exc_info.value.message.lower()


def test_validate_pending_page_contract_raises_on_wrong_page():
    """Test que validate_pending_page_contract lanza PageContractError cuando no hay frame correcto."""
    from unittest.mock import Mock
    
    # Mock page autenticado pero sin frame correcto
    mock_page = Mock()
    mock_page.frame.return_value = Mock()  # nm_contenido existe
    mock_page.url = "http://example.com/dashboard"
    mock_page.screenshot = Mock()
    mock_page.evaluate = Mock(return_value={"url": "http://example.com/dashboard", "title": "Dashboard", "bodyText": "Dashboard"})
    
    evidence_dir = Path("/tmp/test_evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    with pytest.raises(PageContractError) as exc_info:
        validate_pending_page_contract(
            page=mock_page,
            list_frame=None,  # No hay frame
            evidence_dir=evidence_dir,
        )
    
    assert exc_info.value.error_code == "wrong_page"
    assert "frame" in exc_info.value.message.lower() or "vista" in exc_info.value.message.lower()


def test_validate_pending_page_contract_raises_on_wrong_frame_url():
    """Test que validate_pending_page_contract lanza PageContractError cuando el frame tiene URL incorrecta."""
    from unittest.mock import Mock
    
    # Mock page y frame con URL incorrecta
    mock_page = Mock()
    mock_page.frame.return_value = Mock()  # nm_contenido existe
    mock_page.url = "http://example.com/dashboard"
    
    mock_list_frame = Mock()
    mock_list_frame.url = "http://example.com/wrong_page.asp"  # URL incorrecta
    mock_list_frame.locator.return_value.screenshot = Mock()
    mock_list_frame.evaluate = Mock(return_value={"url": "http://example.com/wrong_page.asp", "title": "Wrong", "bodyText": "Wrong page"})
    
    evidence_dir = Path("/tmp/test_evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    with pytest.raises(PageContractError) as exc_info:
        validate_pending_page_contract(
            page=mock_page,
            list_frame=mock_list_frame,
            evidence_dir=evidence_dir,
        )
    
    assert exc_info.value.error_code == "wrong_page"
    assert "url" in exc_info.value.message.lower() or "frame" in exc_info.value.message.lower()


def test_validate_pending_page_contract_raises_on_no_table():
    """Test que validate_pending_page_contract lanza PageContractError cuando no hay tabla renderizada."""
    from unittest.mock import Mock
    
    # Mock page y frame correctos pero sin tabla
    mock_page = Mock()
    mock_page.frame.return_value = Mock()  # nm_contenido existe
    mock_page.url = "http://example.com/dashboard"
    
    mock_list_frame = Mock()
    mock_list_frame.url = "http://example.com/buscador.asp?Apartado_ID=3"  # URL correcta
    # Configurar locator para que count() devuelva 0 (no hay tablas)
    # Necesitamos que locator("table.hdr") y locator("table.obj.row20px") devuelvan objetos con count() = 0
    mock_hdr_locator = Mock()
    mock_hdr_locator.count.return_value = 0
    mock_obj_locator = Mock()
    mock_obj_locator.count.return_value = 0
    mock_body_locator = Mock()
    mock_body_locator.screenshot = Mock()
    
    def locator_side_effect(selector):
        if selector == "table.hdr":
            return mock_hdr_locator
        elif selector == "table.obj.row20px":
            return mock_obj_locator
        elif selector == "body":
            return mock_body_locator
        return Mock()
    
    mock_list_frame.locator.side_effect = locator_side_effect
    # evaluate debe devolver un dict con los campos que el código espera
    mock_list_frame.evaluate = Mock(return_value={
        "url": "http://example.com/buscador.asp?Apartado_ID=3",
        "title": "Test",
        "bodyText": "no hay tablas aquí",
        "hasHdrTable": False,
        "hasObjTable": False,
        "hdrTableCount": 0,
        "objTableCount": 0
    })
    
    evidence_dir = Path("/tmp/test_evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    with pytest.raises(PageContractError) as exc_info:
        validate_pending_page_contract(
            page=mock_page,
            list_frame=mock_list_frame,
            evidence_dir=evidence_dir,
        )
    
    assert exc_info.value.error_code == "pending_list_not_loaded"
    assert "tabla" in exc_info.value.message.lower() or "renderizada" in exc_info.value.message.lower()
