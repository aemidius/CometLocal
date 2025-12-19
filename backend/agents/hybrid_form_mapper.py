"""
HybridFormMapper: Mapeador híbrido DOM + OCR + proximidad visual para campos de formulario.

v4.7.0: Combina información DOM, OCR blocks y proximidad visual para mapear campos
de formularios incluso cuando los labels no están asociados o están renderizados visualmente.
"""

import logging
import math
import unicodedata
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

from backend.shared.models import MappedField
from backend.agents.form_field_mapper import (
    FormFieldMapper,
    normalize_text,
    calculate_score,
    SEMANTIC_FIELD_KEYWORDS,
)

logger = logging.getLogger(__name__)


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Calcula distancia euclídea entre dos puntos."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def get_input_center(dom_input: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """
    Obtiene el centro de un input del DOM usando JavaScript.
    Por ahora, estimamos usando la posición del elemento.
    """
    # Esto se calculará en el navegador, aquí solo devolvemos None
    # El cálculo real se hará en el navegador
    return None


class HybridFormMapper:
    """
    Mapeador híbrido que combina DOM, OCR y proximidad visual.
    
    v4.7.0: Detecta campos de formulario usando múltiples fuentes de información
    para manejar casos complejos donde DOM solo no es suficiente.
    """
    
    def __init__(
        self,
        dom_structure: Dict[str, Any],
        ocr_blocks: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Inicializa el mapper híbrido.
        
        Args:
            dom_structure: Estructura DOM con labels e inputs
            ocr_blocks: Lista de bloques OCR con texto y bounding boxes
        """
        self.dom_structure = dom_structure
        self.ocr_blocks = ocr_blocks or []
        self.labels = dom_structure.get("labels", [])
        self.inputs = dom_structure.get("inputs", [])
        
        # Mapper heurístico base (v4.6.0) como fallback
        self.heuristic_mapper = FormFieldMapper(dom_structure)
    
    def _calculate_proximity_score(
        self,
        input_bbox: Dict[str, Any],
        ocr_bbox: Dict[str, Any],
    ) -> float:
        """
        Calcula score de proximidad entre un input y un bloque OCR.
        
        Args:
            input_bbox: Bounding box del input {x, y, width, height}
            ocr_bbox: Bounding box del OCR block {x, y, width, height}
            
        Returns:
            Score de proximidad (0.0 a 1.0, mayor = más cercano)
        """
        if not all(k in input_bbox for k in ["x", "y", "width", "height"]):
            return 0.0
        if not all(k in ocr_bbox for k in ["x", "y", "width", "height"]):
            return 0.0
        
        # Centro del input
        input_center_x = input_bbox["x"] + input_bbox["width"] / 2
        input_center_y = input_bbox["y"] + input_bbox["height"] / 2
        
        # Centro del OCR block
        ocr_center_x = ocr_bbox["x"] + ocr_bbox["width"] / 2
        ocr_center_y = ocr_bbox["y"] + ocr_bbox["height"] / 2
        
        # Distancia euclídea
        distance = euclidean_distance(
            input_center_x, input_center_y,
            ocr_center_x, ocr_center_y
        )
        
        # Normalizar distancia (asumiendo viewport ~1280x720)
        max_distance = math.sqrt(1280 ** 2 + 720 ** 2)
        normalized_distance = min(1.0, distance / max_distance)
        
        # Score inverso (más cercano = mayor score)
        proximity_score = 1.0 - normalized_distance
        
        # Bonus por alineación horizontal (labels suelen estar arriba o a la izquierda)
        horizontal_alignment = abs(input_center_x - ocr_center_x) < (input_bbox["width"] * 2)
        if horizontal_alignment:
            proximity_score *= 1.2
        
        # Penalizar si el OCR está muy abajo del input (menos probable que sea label)
        if ocr_center_y > input_center_y + input_bbox["height"] * 2:
            proximity_score *= 0.7
        
        return min(1.0, max(0.0, proximity_score))
    
    def _get_input_bounding_box(self, input_elem: Dict[str, Any], browser_page) -> Optional[Dict[str, Any]]:
        """
        Obtiene el bounding box de un input usando JavaScript en el navegador.
        
        Args:
            input_elem: Diccionario con información del input
            browser_page: Página de Playwright
            
        Returns:
            Bounding box {x, y, width, height} o None
        """
        if not browser_page:
            return None
        
        try:
            selector = input_elem.get("selector")
            if not selector:
                return None
            
            bbox = browser_page.evaluate(f"""
                () => {{
                    const elem = document.querySelector('{selector}');
                    if (!elem) return null;
                    const rect = elem.getBoundingClientRect();
                    return {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }};
                }}
            """)
            
            return bbox
        except Exception as e:
            logger.debug(f"[hybrid-mapper] Error getting bbox for {input_elem.get('selector')}: {e}")
            return None
    
    def _map_via_ocr_only(self, semantic_fields: List[str]) -> Dict[str, Optional[MappedField]]:
        """
        Mapea campos usando solo OCR blocks (sin DOM).
        
        v4.7.0: Detecta labels visuales aunque no estén en el DOM.
        
        Args:
            semantic_fields: Lista de campos semánticos a mapear
            
        Returns:
            Diccionario de semantic_field -> MappedField (o None)
        """
        results: Dict[str, Optional[MappedField]] = {}
        
        for semantic_field in semantic_fields:
            if semantic_field not in SEMANTIC_FIELD_KEYWORDS:
                results[semantic_field] = None
                continue
            
            keywords = SEMANTIC_FIELD_KEYWORDS[semantic_field]
            positive_keywords = keywords["positive"]
            negative_keywords = keywords["negative"]
            
            best_match: Optional[MappedField] = None
            best_score = -1.0
            
            # Buscar en OCR blocks
            for ocr_block in self.ocr_blocks:
                text = ocr_block.get("text", "")
                if not text:
                    continue
                
                score = calculate_score(text, positive_keywords, negative_keywords)
                
                if score > best_score:
                    best_score = score
                    
                    # Intentar encontrar el input más cercano
                    # Por ahora, usamos un selector genérico basado en el texto
                    # En una implementación completa, buscaríamos el input más cercano visualmente
                    selector = None
                    
                    # Buscar input que pueda estar cerca
                    ocr_x = ocr_block.get("x", 0)
                    ocr_y = ocr_block.get("y", 0)
                    
                    # Buscar el input más cercano en el DOM
                    closest_input = None
                    min_distance = float('inf')
                    
                    for inp in self.inputs:
                        # Estimación simple: si el input tiene un name/id relacionado
                        inp_name = inp.get("name", "").lower()
                        inp_id = inp.get("id", "").lower()
                        if semantic_field.replace("_", "") in inp_name or semantic_field.replace("_", "") in inp_id:
                            closest_input = inp
                            break
                    
                    if closest_input:
                        selector = closest_input.get("selector")
                    
                    if selector and best_score > 0:
                        confidence = min(1.0, best_score / 2.0)
                        best_match = MappedField(
                            semantic_field=semantic_field,
                            selector=selector,
                            label_text=text,
                            score=best_score,
                            confidence=confidence,
                            source="ocr",
                        )
            
            results[semantic_field] = best_match if best_match and best_match.score > 0 else None
        
        return results
    
    def _map_via_hybrid(
        self,
        semantic_fields: List[str],
        browser_page=None,
    ) -> Dict[str, Optional[MappedField]]:
        """
        Mapea campos combinando DOM y OCR con proximidad visual.
        
        v4.7.0: Fusiona información de múltiples fuentes.
        
        Args:
            semantic_fields: Lista de campos semánticos a mapear
            browser_page: Página de Playwright para obtener bounding boxes
            
        Returns:
            Diccionario de semantic_field -> MappedField (o None)
        """
        results: Dict[str, Optional[MappedField]] = {}
        
        # Primero, obtener mapeo DOM (heurístico)
        dom_mapped = self.heuristic_mapper.map_semantic_fields(semantic_fields)
        
        # Mapeo OCR solo
        ocr_mapped = self._map_via_ocr_only(semantic_fields)
        
        # Para cada campo semántico, fusionar resultados
        for semantic_field in semantic_fields:
            dom_field = dom_mapped.get(semantic_field)
            ocr_field = ocr_mapped.get(semantic_field)
            
            # Si ambos coinciden en el mismo selector, alta confianza
            if dom_field and ocr_field and dom_field.selector == ocr_field.selector:
                # Fusionar: usar el mejor score y alta confianza
                best_score = max(dom_field.score, ocr_field.score)
                confidence = min(1.0, 0.8 + (best_score / 10.0))  # Alta confianza cuando coinciden
                
                results[semantic_field] = MappedField(
                    semantic_field=semantic_field,
                    selector=dom_field.selector,
                    label_text=dom_field.label_text or ocr_field.label_text,
                    score=best_score,
                    confidence=confidence,
                    source="hybrid",
                )
            elif dom_field:
                # Solo DOM: confianza media
                results[semantic_field] = MappedField(
                    semantic_field=dom_field.semantic_field,
                    selector=dom_field.selector,
                    label_text=dom_field.label_text,
                    score=dom_field.score,
                    confidence=min(0.8, dom_field.confidence),
                    source="dom",
                )
            elif ocr_field:
                # Solo OCR: confianza media-baja
                results[semantic_field] = MappedField(
                    semantic_field=ocr_field.semantic_field,
                    selector=ocr_field.selector,
                    label_text=ocr_field.label_text,
                    score=ocr_field.score,
                    confidence=min(0.6, ocr_field.confidence),
                    source="ocr",
                )
            else:
                results[semantic_field] = None
        
        return results
    
    def map_semantic_fields(
        self,
        semantic_fields: List[str],
        browser_page=None,
    ) -> Dict[str, Optional[MappedField]]:
        """
        Mapea campos semánticos usando estrategia híbrida.
        
        v4.7.0: Combina DOM, OCR y proximidad visual.
        
        Args:
            semantic_fields: Lista de campos semánticos a mapear
            browser_page: Página de Playwright (opcional, para bounding boxes)
            
        Returns:
            Diccionario de semantic_field -> MappedField (o None si no se encontró)
        """
        # Si hay OCR blocks, usar mapeo híbrido
        if self.ocr_blocks:
            logger.debug(f"[hybrid-mapper] Using hybrid mapping with {len(self.ocr_blocks)} OCR blocks")
            return self._map_via_hybrid(semantic_fields, browser_page)
        else:
            # Fallback a mapper heurístico (v4.6.0)
            logger.debug("[hybrid-mapper] No OCR blocks, falling back to heuristic mapper")
            return self.heuristic_mapper.map_semantic_fields(semantic_fields)











