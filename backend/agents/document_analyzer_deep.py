"""
DocumentAnalyzer Deep: Análisis profundo de documentos CAE con extracción estructurada.

v4.8.0: Extiende el análisis básico con:
- Extracción de tablas
- Detección de múltiples fechas
- Códigos de documento
- Horas y nivel de formación
- Entidad emisora
- Fusión inteligente de campos
"""

import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date
from pathlib import Path

from backend.shared.models import DeepDocumentAnalysis, DeepDocumentField

logger = logging.getLogger(__name__)

# v4.8.0: Patrones regex para detección de campos
DATE_PATTERNS = {
    "issue": [
        r"(?:fecha|date|data)[\s:]*de[\s:]*(?:emisión|expedición|expedition|emisió|expedició)",
        r"(?:fecha|date|data)[\s:]*de[\s:]*(?:reconocimiento|realización)",
        r"expedido[\s:]*el",
        r"emitido[\s:]*el",
    ],
    "expiry": [
        r"(?:fecha|date|data)[\s:]*de[\s:]*(?:caducidad|vencimiento|expiración)",
        r"válido[\s:]*hasta",
        r"validez[\s:]*hasta",
        r"caduca[\s:]*el",
        r"expira[\s:]*el",
    ],
    "completion": [
        r"(?:fecha|date|data)[\s:]*de[\s:]*(?:finalización|completado|completion)",
        r"finalizado[\s:]*el",
        r"completado[\s:]*el",
    ],
    "revision": [
        r"(?:fecha|date|data)[\s:]*de[\s:]*(?:revisión|revision)",
        r"próxima[\s:]*revisión",
        r"next[\s:]*revision",
    ],
}

DOCUMENT_CODE_PATTERNS = [
    r"(?:código|code|ref\.?|referencia|nº|n°|numero)[\s:]*([A-Z0-9\-\/]+)",
    r"([A-Z]{1,3}[\-\/]\d{3,8})",  # Patrón genérico: letras + números con separador
]

TRAINING_HOURS_PATTERNS = [
    r"(\d{1,3})\s*(?:h|horas|hours)",
    r"(?:duración|duration)[\s:]*(\d{1,3})\s*(?:h|horas)",
]

TRAINING_LEVEL_KEYWORDS = [
    "básico", "basico", "avanzado", "específico", "especifico",
    "riesgo eléctrico", "altura", "carretilla", "tpc", "rera",
    "prl", "prevención", "prevencion",
]

ISSUER_KEYWORDS = [
    "servicio de prevención", "centro médico", "organismo",
    "empresa certificadora", "entidad formadora", "centro de formación",
]


def extract_date_from_text(text: str, date_type: str) -> Optional[str]:
    """
    Extrae una fecha de un texto usando patrones regex.
    
    Args:
        text: Texto a analizar
        date_type: Tipo de fecha ("issue", "expiry", "completion", "revision")
        
    Returns:
        Fecha en formato YYYY-MM-DD o None
    """
    patterns = DATE_PATTERNS.get(date_type, [])
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Buscar fecha después del match
            after_match = text[match.end():match.end()+50]
            # Patrones de fecha comunes
            date_patterns = [
                r"(\d{1,2})[\s\/\-](\d{1,2})[\s\/\-](\d{2,4})",  # DD/MM/YYYY
                r"(\d{4})[\s\/\-](\d{1,2})[\s\/\-](\d{1,2})",  # YYYY/MM/DD
            ]
            
            for date_pattern in date_patterns:
                date_match = re.search(date_pattern, after_match)
                if date_match:
                    try:
                        parts = date_match.groups()
                        if len(parts[2]) == 2:  # YY
                            year = 2000 + int(parts[2]) if int(parts[2]) < 50 else 1900 + int(parts[2])
                        else:
                            year = int(parts[2])
                        
                        if len(parts[0]) == 4:  # YYYY/MM/DD
                            d = date(year, int(parts[1]), int(parts[0]))
                        else:  # DD/MM/YYYY
                            d = date(year, int(parts[1]), int(parts[0]))
                        
                        return d.strftime("%Y-%m-%d")
                    except (ValueError, IndexError):
                        continue
    
    return None


def extract_document_code(text: str) -> Optional[str]:
    """
    Extrae código de documento del texto.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Código encontrado o None
    """
    for pattern in DOCUMENT_CODE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            code = match.group(1) if match.lastindex else match.group(0)
            if code and len(code) >= 3:  # Mínimo 3 caracteres
                return code.strip()
    
    return None


def extract_training_hours(text: str) -> Optional[str]:
    """
    Extrae horas de formación del texto.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Horas encontradas (ej: "60h") o None
    """
    for pattern in TRAINING_HOURS_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            hours = match.group(1)
            return f"{hours}h"
    
    return None


def extract_training_level(text: str) -> Optional[str]:
    """
    Extrae nivel de formación del texto.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Nivel encontrado o None
    """
    text_lower = text.lower()
    for keyword in TRAINING_LEVEL_KEYWORDS:
        if keyword in text_lower:
            # Capitalizar primera letra
            return keyword.capitalize()
    
    return None


def extract_issuer_name(text: str) -> Optional[str]:
    """
    Extrae nombre de entidad emisora del texto.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Nombre de entidad o None
    """
    # Buscar después de keywords de emisor
    for keyword in ISSUER_KEYWORDS:
        pattern = rf"{keyword}[\s:]+([A-Z][A-Za-z\s]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            issuer = match.group(1).strip()
            if len(issuer) >= 3:
                return issuer
    
    return None


def extract_tables_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extrae tablas simples del texto usando heurísticas.
    
    v4.8.0: Detecta patrones tipo tabla basándose en:
    - Múltiples columnas separadas por espacios
    - Encabezados comunes (Curso, Fecha, Horas, Centro, Código)
    
    Args:
        text: Texto completo del PDF
        
    Returns:
        Lista de tablas (cada tabla es un dict con headers y rows)
    """
    tables = []
    lines = text.split('\n')
    
    # Buscar líneas que parecen encabezados de tabla
    table_headers = ["curso", "fecha", "horas", "centro", "código", "code", "nivel"]
    
    current_table = None
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Detectar inicio de tabla
        if any(header in line_lower for header in table_headers):
            if current_table is None:
                current_table = {
                    "headers": line.split(),
                    "rows": [],
                }
            continue
        
        # Si hay tabla activa, intentar parsear filas
        if current_table:
            # Filas de tabla suelen tener múltiples columnas separadas por espacios
            parts = line.split()
            if len(parts) >= 2:  # Mínimo 2 columnas
                current_table["rows"].append(parts)
            else:
                # Fin de tabla
                if current_table["rows"]:
                    tables.append(current_table)
                current_table = None
    
    # Añadir última tabla si existe
    if current_table and current_table["rows"]:
        tables.append(current_table)
    
    return tables


def merge_fields(
    primary: DeepDocumentField,
    secondary: DeepDocumentField,
) -> DeepDocumentField:
    """
    Fusiona dos campos del mismo tipo.
    
    v4.8.0: Reglas de fusión:
    - Si ambos coinciden → confidence = max
    - Si difieren → penalizar
    - Si solo uno existe → confidence = half
    
    Args:
        primary: Campo primario
        secondary: Campo secundario
        
    Returns:
        Campo fusionado
    """
    if not primary.value and not secondary.value:
        return primary
    
    if not primary.value:
        secondary.confidence = secondary.confidence * 0.5
        return secondary
    
    if not secondary.value:
        primary.confidence = primary.confidence * 0.5
        return primary
    
    # Ambos tienen valor
    if primary.value == secondary.value:
        # Coinciden → alta confianza
        primary.confidence = max(primary.confidence, secondary.confidence)
        primary.raw_matches.extend(secondary.raw_matches)
    else:
        # Difieren → penalizar
        primary.confidence = min(primary.confidence, secondary.confidence) * 0.7
        primary.warnings.append(f"Conflicto de valores: '{primary.value}' vs '{secondary.value}'")
    
    return primary


class DeepDocumentAnalyzer:
    """
    Analizador profundo de documentos CAE.
    
    v4.8.0: Extiende el análisis básico con extracción estructurada avanzada.
    """
    
    def __init__(self):
        """Inicializa el analizador profundo."""
        pass
    
    async def analyze_pdf_deep(
        self,
        pdf_path: Path,
        ocr_service: Optional[Any] = None,
    ) -> DeepDocumentAnalysis:
        """
        Analiza un PDF en profundidad extrayendo campos estructurados y tablas.
        
        Args:
            pdf_path: Ruta al archivo PDF
            ocr_service: Servicio OCR opcional (para fallback)
            
        Returns:
            DeepDocumentAnalysis con todos los campos extraídos
        """
        analysis = DeepDocumentAnalysis(
            source_path=str(pdf_path),
            extracted_fields=[],
            tables=[],
            warnings=[],
        )
        
        # Extraer texto del PDF
        text = await self._extract_text_from_pdf(pdf_path, ocr_service)
        
        if not text:
            analysis.warnings.append("No se pudo extraer texto del PDF")
            return analysis
        
        # Extraer fechas múltiples
        analysis.issue_date = extract_date_from_text(text, "issue")
        analysis.expiry_date = extract_date_from_text(text, "expiry")
        analysis.completion_date = extract_date_from_text(text, "completion")
        analysis.revision_date = extract_date_from_text(text, "revision")
        
        # Extraer campos adicionales
        analysis.document_code = extract_document_code(text)
        analysis.training_hours = extract_training_hours(text)
        analysis.training_level = extract_training_level(text)
        analysis.issuer_name = extract_issuer_name(text)
        
        # Extraer tablas
        analysis.tables = extract_tables_from_text(text)
        
        # Construir extracted_fields
        if analysis.issue_date:
            analysis.extracted_fields.append(DeepDocumentField(
                field_name="issue_date",
                value=analysis.issue_date,
                confidence=0.8,
                source="pdf_text",
            ))
        
        if analysis.expiry_date:
            analysis.extracted_fields.append(DeepDocumentField(
                field_name="expiry_date",
                value=analysis.expiry_date,
                confidence=0.8,
                source="pdf_text",
            ))
        
        if analysis.document_code:
            analysis.extracted_fields.append(DeepDocumentField(
                field_name="document_code",
                value=analysis.document_code,
                confidence=0.7,
                source="pdf_text",
            ))
        
        if analysis.training_hours:
            analysis.extracted_fields.append(DeepDocumentField(
                field_name="training_hours",
                value=analysis.training_hours,
                confidence=0.7,
                source="pdf_text",
            ))
        
        # Calcular confianza global
        analysis.confidence = self._calculate_global_confidence(analysis)
        
        return analysis
    
    async def _extract_text_from_pdf(
        self,
        pdf_path: Path,
        ocr_service: Optional[Any] = None,
    ) -> str:
        """
        Extrae texto de un PDF usando pypdf o OCR como fallback.
        
        Args:
            pdf_path: Ruta al PDF
            ocr_service: Servicio OCR opcional
            
        Returns:
            Texto extraído
        """
        try:
            from pypdf import PdfReader
            
            reader = PdfReader(str(pdf_path))
            text_parts = []
            
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            
            if text_parts:
                return "\n".join(text_parts)
            
            # Si no hay texto, intentar OCR
            if ocr_service and ocr_service.enabled:
                logger.debug(f"[deep-analyzer] No text in PDF, trying OCR for {pdf_path}")
                # TODO: Implementar OCR a página completa
                # Por ahora, devolver texto vacío
                return ""
            
            return ""
            
        except Exception as e:
            logger.warning(f"[deep-analyzer] Error extracting text from PDF {pdf_path}: {e}")
            return ""
    
    def _calculate_global_confidence(self, analysis: DeepDocumentAnalysis) -> float:
        """
        Calcula confianza global del análisis.
        
        v4.8.0: Promedio ponderado:
        - Datos clave (issue+expiry) → peso 3
        - Datos secundarios → peso 1
        - Campos inferidos → peso 0.5
        
        Args:
            analysis: Análisis a evaluar
            
        Returns:
            Confianza global [0, 1]
        """
        weights = []
        confidences = []
        
        # Datos clave (peso 3)
        if analysis.issue_date:
            weights.append(3.0)
            confidences.append(0.8)
        if analysis.expiry_date:
            weights.append(3.0)
            confidences.append(0.8)
        
        # Datos secundarios (peso 1)
        if analysis.completion_date:
            weights.append(1.0)
            confidences.append(0.7)
        if analysis.document_code:
            weights.append(1.0)
            confidences.append(0.7)
        if analysis.training_hours:
            weights.append(1.0)
            confidences.append(0.7)
        if analysis.issuer_name:
            weights.append(1.0)
            confidences.append(0.6)
        
        # Campos inferidos (peso 0.5)
        if analysis.training_level:
            weights.append(0.5)
            confidences.append(0.6)
        if analysis.revision_date:
            weights.append(0.5)
            confidences.append(0.6)
        
        if not weights:
            return 0.0
        
        # Promedio ponderado
        total_weight = sum(weights)
        weighted_sum = sum(w * c for w, c in zip(weights, confidences))
        
        return min(1.0, weighted_sum / total_weight)

