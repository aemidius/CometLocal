"""
Detector de objetivos visuales (botones) en capturas de pantalla.

v3.4.0: Detecta botones críticos (Guardar, Adjuntar, Confirmar) usando OCR
para permitir clicks por coordenadas cuando el DOM no es accesible.
"""

import logging
from typing import List, Optional, Dict, Any
import re

from backend.shared.models import BrowserObservation, VisualTarget

logger = logging.getLogger(__name__)


# Palabras clave para detectar botones críticos
BUTTON_KEYWORDS = {
    "guardar": ["guardar", "guardar cambios", "guardar y continuar", "save", "save changes"],
    "adjuntar": ["adjuntar", "adjuntar archivo", "subir archivo", "añadir documento", 
                 "upload", "upload file", "attach", "attach file"],
    "confirmar": ["confirmar", "aceptar", "enviar", "continuar", "confirm", "accept", 
                  "send", "submit", "continue"],
}


class VisualTargetDetector:
    """
    Detecta botones visuales en una observación del navegador usando OCR.
    
    v3.4.0: Usa ocr_blocks para localizar botones críticos y devolver
    VisualTarget con coordenadas para clicks por pantalla.
    """
    
    def __init__(self, min_confidence: float = 0.8):
        """
        Inicializa el detector.
        
        Args:
            min_confidence: Confianza mínima requerida para considerar un match válido
        """
        self.min_confidence = min_confidence
    
    def find_targets(self, observation: BrowserObservation) -> List[VisualTarget]:
        """
        Busca botones visuales en la observación usando OCR.
        
        v3.4.0: Recorre ocr_blocks y busca keywords de BUTTON_KEYWORDS.
        Si un bloque tiene coordenadas, las usa; si no, deja x/y como None.
        
        Args:
            observation: BrowserObservation con ocr_blocks (opcional)
            
        Returns:
            Lista de VisualTarget detectados (puede estar vacía)
        """
        targets: List[VisualTarget] = []
        
        # Si no hay ocr_blocks, no podemos detectar nada
        if not observation.ocr_blocks:
            return targets
        
        # Normalizar ocr_blocks: pueden venir como dicts o como OCRBlock
        ocr_blocks_list: List[Dict[str, Any]] = []
        for block in observation.ocr_blocks:
            if isinstance(block, dict):
                ocr_blocks_list.append(block)
            else:
                # Si es un OCRBlock, convertirlo a dict
                ocr_blocks_list.append(block.model_dump() if hasattr(block, 'model_dump') else {
                    "text": getattr(block, 'text', ''),
                    "x": getattr(block, 'x', None),
                    "y": getattr(block, 'y', None),
                    "width": getattr(block, 'width', None),
                    "height": getattr(block, 'height', None),
                })
        
        # Recorrer cada bloque OCR
        for block in ocr_blocks_list:
            block_text = block.get("text", "")
            if not block_text:
                continue
            
            # Normalizar texto a minúsculas para comparación
            text_lower = block_text.lower().strip()
            
            # Buscar matches con cada categoría de botón
            for label, keywords in BUTTON_KEYWORDS.items():
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    
                    # Calcular confianza según el tipo de match
                    confidence = 0.0
                    
                    # Match exacto: confianza 1.0
                    if text_lower == keyword_lower:
                        confidence = 1.0
                    # Contiene la keyword completa: confianza 0.9
                    elif keyword_lower in text_lower:
                        confidence = 0.9
                    # Contiene palabras de la keyword: confianza 0.8
                    elif self._partial_match(text_lower, keyword_lower):
                        confidence = 0.8
                    
                    # Si la confianza es suficiente, crear VisualTarget
                    if confidence >= self.min_confidence:
                        # Extraer coordenadas del bloque (si existen)
                        x = block.get("x")
                        y = block.get("y")
                        width = block.get("width")
                        height = block.get("height")
                        
                        # Si hay coordenadas, calcular el centro para el click
                        click_x = None
                        click_y = None
                        if x is not None and y is not None:
                            if width is not None and height is not None:
                                # Click en el centro del bloque
                                click_x = x + width // 2
                                click_y = y + height // 2
                            else:
                                # Usar las coordenadas directamente
                                click_x = x
                                click_y = y
                        
                        target = VisualTarget(
                            label=label,
                            x=click_x,
                            y=click_y,
                            width=width,
                            height=height,
                            confidence=confidence,
                            source="ocr_block",
                            text=block_text,
                        )
                        
                        # Evitar duplicados: si ya hay un target con el mismo label y similar confianza, no añadir
                        existing = next(
                            (t for t in targets if t.label == label and abs(t.confidence - confidence) < 0.1),
                            None
                        )
                        if not existing:
                            targets.append(target)
                            logger.debug(
                                "[visual-target] Detected button: label=%r confidence=%.2f x=%r y=%r text=%r",
                                label, confidence, click_x, click_y, block_text[:50]
                            )
        
        return targets
    
    def _partial_match(self, text: str, keyword: str) -> bool:
        """
        Verifica si el texto contiene palabras clave de la keyword.
        
        Args:
            text: Texto a analizar (normalizado a minúsculas)
            keyword: Keyword a buscar (normalizado a minúsculas)
            
        Returns:
            True si hay match parcial
        """
        # Dividir keyword en palabras
        keyword_words = keyword.split()
        if len(keyword_words) == 1:
            # Si es una sola palabra, ya se comprobó con "in"
            return False
        
        # Verificar que todas las palabras importantes estén en el texto
        important_words = [w for w in keyword_words if len(w) > 3]  # Palabras de más de 3 caracteres
        if not important_words:
            important_words = keyword_words
        
        matches = sum(1 for word in important_words if word in text)
        return matches >= len(important_words) * 0.7  # Al menos 70% de las palabras importantes














