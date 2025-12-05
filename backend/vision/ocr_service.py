"""
Servicio de OCR/visión para análisis de capturas de pantalla.

v3.3.0: Interfaz encapsulada para extraer texto de imágenes usando OCR.
Preparado para integrar con LM Studio / modelos de visión (Qwen2.5-VL, FARA, etc.).
"""

import logging
from typing import Optional, List
from pydantic import BaseModel

from backend.config import VISION_OCR_ENABLED, VISION_OCR_PROVIDER

logger = logging.getLogger(__name__)


class OCRBlock(BaseModel):
    """
    Bloque de texto extraído por OCR.
    
    v3.3.0: Representa un fragmento de texto con su posición (opcional).
    v3.4.0: Añade bounding boxes para interacción por coordenadas.
    """
    text: str
    x: Optional[int] = None  # v3.4.0: coordenada X del bloque
    y: Optional[int] = None  # v3.4.0: coordenada Y del bloque
    width: Optional[int] = None  # v3.4.0: ancho del bloque
    height: Optional[int] = None  # v3.4.0: alto del bloque


class OCRResult(BaseModel):
    """
    Resultado completo de un análisis OCR.
    
    v3.3.0: Contiene el texto completo y bloques individuales.
    """
    full_text: str
    blocks: List[OCRBlock]


class OCRService:
    """
    Servicio de OCR para análisis de capturas de pantalla.
    
    v3.3.0: Interfaz encapsulada que permite cambiar el proveedor sin afectar el código cliente.
    Por ahora es un stub que devuelve None o resultados simulados.
    
    TODO: Integrar con LM Studio / modelo de visión real cuando esté disponible.
    """
    
    def __init__(self, enabled: bool = None, provider: str = None):
        """
        Inicializa el servicio OCR.
        
        Args:
            enabled: Si está habilitado (por defecto usa VISION_OCR_ENABLED de config)
            provider: Proveedor a usar (por defecto usa VISION_OCR_PROVIDER de config)
        """
        self.enabled = enabled if enabled is not None else VISION_OCR_ENABLED
        self.provider = provider or VISION_OCR_PROVIDER
        self._call_count = 0
        self._failure_count = 0
    
    async def analyze_screenshot(self, image_path: str) -> Optional[OCRResult]:
        """
        Analiza una captura de pantalla y devuelve texto extraído.
        
        v3.3.0: Por ahora es un stub. Cuando se integre el modelo real:
        - Llamar a LM Studio / API de visión con la imagen
        - Parsear la respuesta
        - Devolver OCRResult con el texto extraído
        
        Args:
            image_path: Ruta al archivo de imagen (PNG, JPEG, etc.)
            
        Returns:
            OCRResult con el texto extraído, o None si está deshabilitado o falla
        """
        self._call_count += 1
        
        if not self.enabled:
            logger.debug("[ocr] OCR service disabled, skipping analysis")
            return None
        
        if not image_path:
            logger.debug("[ocr] No image path provided")
            self._failure_count += 1
            return None
        
        # TODO v3.3.1+: Integrar con modelo real de visión
        # Por ahora, stub que devuelve None
        # Cuando se integre:
        #   - Leer imagen desde image_path
        #   - Enviar a LM Studio / API de visión
        #   - Parsear respuesta y construir OCRResult
        #   - Manejar errores y devolver None si falla
        
        logger.debug(
            "[ocr] OCR analysis requested (stub mode): image_path=%r provider=%r",
            image_path, self.provider
        )
        
        # Stub: devolver None por ahora
        # En producción, aquí iría la llamada real al modelo
        self._failure_count += 1
        return None
    
    def get_stats(self) -> dict:
        """
        Devuelve estadísticas del servicio OCR.
        
        Returns:
            Dict con contadores de llamadas y fallos
        """
        return {
            "calls": self._call_count,
            "failures": self._failure_count,
            "successes": self._call_count - self._failure_count,
        }


