"""
Tests para RetryPolicy v2.6.0
"""

import pytest
from backend.agents.retry_policy import RetryPolicy


class TestRetryPolicy:
    """Tests para RetryPolicy"""
    
    def test_can_retry_within_limit(self):
        """can_retry devuelve True si attempt_index < max_retries"""
        policy = RetryPolicy(max_retries=2)
        
        assert policy.can_retry(0) is True
        assert policy.can_retry(1) is True
        assert policy.can_retry(2) is False
        assert policy.can_retry(3) is False
    
    def test_can_retry_zero_max_retries(self):
        """can_retry devuelve False si max_retries es 0"""
        policy = RetryPolicy(max_retries=0)
        
        assert policy.can_retry(0) is False
        assert policy.can_retry(1) is False
    
    def test_should_retry_upload_with_retryable_status(self):
        """should_retry_upload devuelve True para estados que requieren retry"""
        policy = RetryPolicy()
        
        assert policy.should_retry_upload("not_confirmed") is True
        assert policy.should_retry_upload("no_input_found") is True
        assert policy.should_retry_upload("error_detected") is True
    
    def test_should_retry_upload_with_non_retryable_status(self):
        """should_retry_upload devuelve False para estados que no requieren retry"""
        policy = RetryPolicy()
        
        assert policy.should_retry_upload("success") is False
        assert policy.should_retry_upload("file_not_found") is False
        assert policy.should_retry_upload(None) is False
    
    def test_should_retry_upload_custom_policy(self):
        """should_retry_upload respeta retry_on_upload_status personalizado"""
        policy = RetryPolicy(retry_on_upload_status={"custom_error"})
        
        assert policy.should_retry_upload("custom_error") is True
        assert policy.should_retry_upload("not_confirmed") is False
    
    def test_should_retry_verification(self):
        """should_retry_verification devuelve True para estados que requieren retry"""
        policy = RetryPolicy()
        
        assert policy.should_retry_verification("not_confirmed") is True
        assert policy.should_retry_verification("error_detected") is True
        assert policy.should_retry_verification("confirmed") is False
        assert policy.should_retry_verification("not_applicable") is False
        assert policy.should_retry_verification(None) is False






















