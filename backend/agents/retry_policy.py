"""
RetryPolicy para reintentos inteligentes de sub-objetivos.

v2.6.0: Sistema de reintentos basado en evidencias reales (upload_status, upload_verification).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RetryPolicy:
    """
    Política de reintentos para sub-objetivos fallidos.
    
    v2.6.0: Define cuándo y cómo reintentar sub-objetivos basándose en:
    - Estado de upload (upload_status)
    - Verificación visual (upload_verification)
    - Límites de intentos
    """
    max_retries: int = 2
    retry_on_upload_status: set[str] = field(default_factory=lambda: {
        "not_confirmed",
        "no_input_found",
        "error_detected",
    })
    retry_on_goal_failure: bool = True
    backoff_seconds: float = 1.5

    def can_retry(self, attempt_index: int) -> bool:
        """
        Verifica si se puede realizar otro intento.
        
        Args:
            attempt_index: Índice del intento actual (0 = primer intento)
            
        Returns:
            True si attempt_index < max_retries
        """
        return attempt_index < self.max_retries

    def should_retry_upload(self, upload_status: Optional[str]) -> bool:
        """
        Determina si se debe reintentar basándose en el estado del upload.
        
        Args:
            upload_status: Estado del upload ("success", "not_confirmed", "no_input_found", "error_detected", etc.)
            
        Returns:
            True si upload_status está en retry_on_upload_status
        """
        if not upload_status:
            return False
        return upload_status in self.retry_on_upload_status
    
    def should_retry_verification(self, verification_status: Optional[str]) -> bool:
        """
        Determina si se debe reintentar basándose en el estado de verificación.
        
        Args:
            verification_status: Estado de verificación ("confirmed", "not_confirmed", "error_detected", etc.)
            
        Returns:
            True si verification_status indica que se debe reintentar
        """
        if not verification_status:
            return False
        # Reintentar si no está confirmado o hay error
        return verification_status in {"not_confirmed", "error_detected"}















