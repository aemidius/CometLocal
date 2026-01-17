"""
Unit tests para clasificador de errores.

SPRINT C2.16: Valida que los errores se clasifican correctamente como transitorios vs definitivos.
"""
import pytest
from backend.shared.error_classifier import classify_exception, classify_error_code, ErrorCode
from backend.shared.phase_timeout import PhaseTimeoutError


def test_classify_timeout():
    """Test: Timeout -> transient true"""
    timeout_error = PhaseTimeoutError("grid_load", 60.0, "Timeout after 60s")
    
    result = classify_exception(timeout_error, "grid_load", {})
    
    assert result["error_code"] == ErrorCode.TIMEOUT_GRID_LOAD
    assert result["is_transient"] is True
    assert result["retry_after_ms"] is not None


def test_classify_item_not_found():
    """Test: item_not_found -> transient true (pero con límite de retries)"""
    item_not_found_error = Exception("item_not_found_before_upload: Item not found in grid")
    
    result = classify_exception(item_not_found_error, "upload", {"pending_item_key": "test_key"})
    
    assert result["error_code"] == ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD
    assert result["is_transient"] is True  # Puede ser que el item se movió de página
    assert result["retry_after_ms"] is not None


def test_classify_verification_failed():
    """Test: verification_failed -> transient true (1 retry)"""
    verification_error = Exception("verification_failed: Item still present after upload")
    
    result = classify_exception(verification_error, "verification", {})
    
    # Si el mensaje contiene "item_still_present", debe ser NO transitorio
    if "item_still_present" in str(verification_error).lower():
        assert result["error_code"] == ErrorCode.ITEM_STILL_PRESENT_AFTER_UPLOAD
        assert result["is_transient"] is False
    else:
        assert result["error_code"] == ErrorCode.VERIFICATION_FAILED
        assert result["is_transient"] is True
        assert result["retry_after_ms"] is not None


def test_classify_network_transient():
    """Test: Network error -> transient true"""
    network_error = Exception("ECONNREFUSED: Connection refused")
    
    result = classify_exception(network_error, "navigation", {})
    
    assert result["error_code"] == ErrorCode.NETWORK_TRANSIENT
    assert result["is_transient"] is True
    assert result["retry_after_ms"] is not None


def test_classify_upload_click_intercepted():
    """Test: Upload click intercepted -> transient true"""
    click_error = Exception("click intercepted: element is blocked by overlay")
    
    result = classify_exception(click_error, "upload", {})
    
    assert result["error_code"] == ErrorCode.UPLOAD_CLICK_INTERCEPTED
    assert result["is_transient"] is True
    assert result["retry_after_ms"] is not None


def test_classify_error_code_timeout():
    """Test: classify_error_code para timeout"""
    result = classify_error_code(ErrorCode.TIMEOUT_GRID_LOAD, "grid_load", {})
    
    assert result["error_code"] == ErrorCode.TIMEOUT_GRID_LOAD
    assert result["is_transient"] is True
    assert result["retry_after_ms"] is not None


def test_classify_error_code_item_not_found():
    """Test: classify_error_code para item_not_found"""
    result = classify_error_code(ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD, "upload", {})
    
    assert result["error_code"] == ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD
    assert result["is_transient"] is True
    assert result["retry_after_ms"] is not None


def test_classify_error_code_upload_failed():
    """Test: classify_error_code para upload_failed (no transient)"""
    result = classify_error_code(ErrorCode.UPLOAD_FAILED, "upload", {})
    
    assert result["error_code"] == ErrorCode.UPLOAD_FAILED
    assert result["is_transient"] is False
    assert result["retry_after_ms"] is None
