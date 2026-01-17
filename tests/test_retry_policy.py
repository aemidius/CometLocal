"""
Unit tests para retry policy.

SPRINT C2.16: Valida que la política de reintentos funciona correctamente.
"""
import pytest
from backend.shared.retry_policy import (
    retry_with_policy,
    get_max_retries_for_phase,
    calculate_backoff,
    add_jitter,
)


def test_get_max_retries_for_phase():
    """Test: get_max_retries_for_phase devuelve valores correctos"""
    assert get_max_retries_for_phase("login") == 1
    assert get_max_retries_for_phase("navigation") == 2
    assert get_max_retries_for_phase("grid_load") == 2
    assert get_max_retries_for_phase("upload") == 0
    assert get_max_retries_for_phase("verification") == 1
    assert get_max_retries_for_phase("pagination") == 2


def test_get_max_retries_for_phase_upload_retryable():
    """Test: upload con error retryable permite 1 retry"""
    assert get_max_retries_for_phase("upload", "upload_click_intercepted") == 1
    assert get_max_retries_for_phase("upload", "overlay_blocking") == 1
    assert get_max_retries_for_phase("upload", "upload_failed") == 0


def test_calculate_backoff():
    """Test: calculate_backoff calcula backoff exponencial suave"""
    assert calculate_backoff(1) == 500  # base_ms
    assert calculate_backoff(2) == 750  # 500 * 1.5
    assert calculate_backoff(3) == 1125  # 500 * 1.5^2


def test_add_jitter():
    """Test: add_jitter añade jitter aleatorio"""
    backoff = 1000
    jittered = add_jitter(backoff, max_jitter_ms=250)
    
    assert 1000 <= jittered <= 1250


def test_retry_with_policy_success_first_attempt():
    """Test: retry_with_policy no retry si el primer intento es exitoso"""
    call_count = [0]
    
    def fn():
        call_count[0] += 1
        return "success"
    
    result = retry_with_policy(fn, "grid_load")
    
    assert result == "success"
    assert call_count[0] == 1


def test_retry_with_policy_success_after_retry():
    """Test: retry_with_policy retry y éxito en segundo intento"""
    call_count = [0]
    
    def fn():
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("First attempt failed")
        return "success"
    
    result = retry_with_policy(fn, "grid_load", max_retries=1)
    
    assert result == "success"
    assert call_count[0] == 2


def test_retry_with_policy_fails_after_max_retries():
    """Test: retry_with_policy lanza excepción si todos los reintentos fallan"""
    call_count = [0]
    
    def fn():
        call_count[0] += 1
        raise Exception("Always fails")
    
    with pytest.raises(Exception, match="Always fails"):
        retry_with_policy(fn, "grid_load", max_retries=2)
    
    assert call_count[0] == 3  # 1 inicial + 2 retries


def test_retry_with_policy_on_retry_callback():
    """Test: retry_with_policy llama on_retry callback"""
    call_count = [0]
    retry_calls = []
    
    def fn():
        call_count[0] += 1
        if call_count[0] < 2:
            raise Exception("Fail")
        return "success"
    
    def on_retry(attempt, exc):
        retry_calls.append((attempt, exc))
    
    result = retry_with_policy(fn, "grid_load", on_retry=on_retry, max_retries=1)
    
    assert result == "success"
    assert len(retry_calls) == 1
    assert retry_calls[0][0] == 1
