"""
FormFieldMapper: Mapeador heurístico de campos de formulario sin LLM.

v4.6.0: Detecta y mapea campos de formulario desconocidos basándose únicamente
en las etiquetas visibles usando keywords y heurísticas.
"""

import logging
import unicodedata
from typing import Dict, List, Optional, Any
from collections import defaultdict

from backend.shared.models import MappedField

logger = logging.getLogger(__name__)

# v4.6.0: Keywords para mapeo heurístico
SEMANTIC_FIELD_KEYWORDS = {
    "issue_date": {
        "positive": ["emisión", "emision", "expedición", "expedicion", "reconocimiento", "realización", "realizacion"],
        "negative": ["caducidad", "vencimiento", "expira", "válido hasta", "valido hasta"],
    },
    "expiry_date": {
        "positive": ["caducidad", "válido hasta", "valido hasta", "expira", "vencimiento", "validez hasta"],
        "negative": ["emisión", "emision", "expedición", "expedicion"],
    },
    "worker_name": {
        "positive": ["trabajador", "empleado", "persona", "nombre completo", "nom complet", "treballador"],
        "negative": ["fecha", "documento", "document"],
    },
}


def normalize_text(text: str) -> str:
    """
    Normaliza texto para comparación: lowercase y sin acentos.
    
    Args:
        text: Texto a normalizar
        
    Returns:
        Texto normalizado
    """
    # Convertir a lowercase
    text_lower = text.lower()
    
    # Quitar acentos
    nfd = unicodedata.normalize('NFD', text_lower)
    text_normalized = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    
    return text_normalized


def calculate_score(text: str, positive_keywords: List[str], negative_keywords: List[str]) -> float:
    """
    Calcula el score heurístico de un texto basándose en keywords.
    
    Args:
        text: Texto a evaluar
        positive_keywords: Lista de keywords positivas
        negative_keywords: Lista de keywords negativas
        
    Returns:
        Score = (#positivas) - (#negativas)
    """
    normalized = normalize_text(text)
    
    positive_count = sum(1 for keyword in positive_keywords if normalize_text(keyword) in normalized)
    negative_count = sum(1 for keyword in negative_keywords if normalize_text(keyword) in normalized)
    
    score = positive_count - negative_count
    return float(score)


class FormFieldMapper:
    """
    Mapeador heurístico de campos de formulario.
    
    v4.6.0: Mapea campos semánticos a campos de formulario reales usando
    keywords y heurísticas, sin necesidad de LLM.
    """
    
    def __init__(self, dom: Dict[str, Any]):
        """
        Inicializa el mapper con la estructura DOM del formulario.
        
        Args:
            dom: Estructura DOM con labels e inputs
                {
                    "labels": [{"text": "...", "for": "#selector"}],
                    "inputs": [{"selector": "#selector", "name": "...", "id": "..."}]
                }
        """
        self.dom = dom
        self.labels = dom.get("labels", [])
        self.inputs = dom.get("inputs", [])
    
    def map_semantic_fields(self, semantic_fields: List[str]) -> Dict[str, Optional[MappedField]]:
        """
        Mapea campos semánticos a campos de formulario usando heurísticas.
        
        Args:
            semantic_fields: Lista de campos semánticos a mapear
                ["issue_date", "expiry_date", "worker_name"]
        
        Returns:
            Diccionario de semantic_field -> MappedField (o None si no se encontró)
        """
        results: Dict[str, Optional[MappedField]] = {}
        
        # Construir mapeo de label -> input
        label_to_input: Dict[str, Dict[str, Any]] = {}
        for label in self.labels:
            label_text = label.get("text", "")
            input_selector = label.get("for")
            if input_selector:
                # Buscar el input correspondiente
                for inp in self.inputs:
                    if inp.get("selector") == input_selector or inp.get("id") == input_selector.lstrip("#"):
                        label_to_input[label_text] = inp
                        break
        
        # Para cada campo semántico, encontrar el mejor match
        for semantic_field in semantic_fields:
            if semantic_field not in SEMANTIC_FIELD_KEYWORDS:
                logger.warning(f"[form-mapper] Semantic field '{semantic_field}' not supported")
                results[semantic_field] = None
                continue
            
            keywords = SEMANTIC_FIELD_KEYWORDS[semantic_field]
            positive_keywords = keywords["positive"]
            negative_keywords = keywords["negative"]
            
            # Evaluar cada label
            best_match: Optional[MappedField] = None
            best_score = -1.0
            
            for label in self.labels:
                label_text = label.get("text", "")
                if not label_text:
                    continue
                
                score = calculate_score(label_text, positive_keywords, negative_keywords)
                
                if score > best_score:
                    best_score = score
                    
                    # Obtener el selector del input asociado
                    input_selector = label.get("for")
                    if not input_selector:
                        # Buscar input adyacente o en el mismo contenedor
                        # Por ahora, intentar encontrar por proximidad
                        input_selector = None
                        for inp in self.inputs:
                            # Heurística simple: si el input tiene un name/id similar
                            inp_name = inp.get("name", "").lower()
                            inp_id = inp.get("id", "").lower()
                            if semantic_field.replace("_", "") in inp_name or semantic_field.replace("_", "") in inp_id:
                                input_selector = inp.get("selector")
                                break
                    
                    if input_selector and best_score > 0:
                        confidence = min(1.0, best_score / 2.0)
                        best_match = MappedField(
                            semantic_field=semantic_field,
                            selector=input_selector,
                            label_text=label_text,
                            score=best_score,
                            confidence=confidence,
                        )
            
            # Si no encontramos por label, intentar buscar directamente en inputs
            if not best_match:
                for inp in self.inputs:
                    inp_name = inp.get("name", "")
                    inp_id = inp.get("id", "")
                    combined_text = f"{inp_name} {inp_id}"
                    
                    score = calculate_score(combined_text, positive_keywords, negative_keywords)
                    
                    if score > best_score:
                        best_score = score
                        if best_score > 0:
                            selector = inp.get("selector")
                            confidence = min(1.0, best_score / 2.0)
                            best_match = MappedField(
                                semantic_field=semantic_field,
                                selector=selector,
                                label_text=None,
                                score=best_score,
                                confidence=confidence,
                            )
            
            results[semantic_field] = best_match if best_match and best_match.score > 0 else None
        
        return results

















