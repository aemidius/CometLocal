"""
Analizador CAE para extraer información de estado y caducidades desde texto (DOM + OCR).

v3.3.0: Analiza texto combinado (visible_text + ocr_text) para detectar:
- Estado del trabajador (apto / no apto / caducado / pendiente)
- Fechas de caducidad
- Mensajes de error típicos de plataformas CAE
"""

import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def extract_cae_status_from_text(text: str) -> Dict[str, Any]:
    """
    Analiza texto (DOM + OCR) y devuelve información útil para CAE.
    
    v3.3.0: Usa heurísticas básicas para detectar estado y fechas sin NLP complejo.
    
    Args:
        text: Texto combinado de visible_text_excerpt + ocr_text
        
    Returns:
        Dict con:
        {
            "status": "vigente" | "caducado" | "pendiente" | "no_apto" | "desconocido",
            "expiry_dates": ["2025-02-01", ...],  # fechas normalizadas
            "raw_dates": ["01/02/2025", ...],  # fechas tal como aparecen
            "evidence_snippets": ["Certificado apto vigente hasta 01/02/2025", ...],
        }
    """
    if not text:
        return {
            "status": "desconocido",
            "expiry_dates": [],
            "raw_dates": [],
            "evidence_snippets": [],
        }
    
    text_lower = text.lower()
    evidence_snippets: List[str] = []
    raw_dates: List[str] = []
    expiry_dates: List[str] = []
    
    # 1. Detectar estado general
    status = "desconocido"
    
    # Palabras clave para estado vigente/apto
    vigente_keywords = [
        "apto", "apta", "apto vigente", "vigente", "válido", "válida",
        "en vigor", "en curso", "activo", "activa", "correcto", "correcta",
    ]
    
    # Palabras clave para no apto
    no_apto_keywords = [
        "no apto", "no apta", "no válido", "no válida", "rechazado", "rechazada",
        "no superado", "no superada", "negativo", "negativa",
    ]
    
    # Palabras clave para caducado
    caducado_keywords = [
        "caducado", "caducada", "vencido", "vencida", "fuera de plazo", "expirado", "expirada",
        "no vigente", "sin vigencia", "ha expirado", "ha caducado",
    ]
    
    # Palabras clave para pendiente
    pendiente_keywords = [
        "pendiente", "en revisión", "en tramitación", "procesando", "en proceso",
        "a la espera", "esperando", "pendiente de", "por revisar",
    ]
    
    # Buscar evidencia de estado (orden de prioridad: caducado > no_apto > vigente > pendiente)
    # Priorizar estados más críticos primero
    for keyword in caducado_keywords:
        if keyword in text_lower:
            idx = text_lower.find(keyword)
            start = max(0, idx - 50)
            end = min(len(text), idx + len(keyword) + 50)
            snippet = text[start:end].strip()
            if snippet not in evidence_snippets:
                evidence_snippets.append(snippet)
            status = "caducado"
            break
    
    if status == "desconocido":
        for keyword in no_apto_keywords:
            if keyword in text_lower:
                idx = text_lower.find(keyword)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(keyword) + 50)
                snippet = text[start:end].strip()
                if snippet not in evidence_snippets:
                    evidence_snippets.append(snippet)
                status = "no_apto"
                break
    
    if status == "desconocido":
        for keyword in vigente_keywords:
            if keyword in text_lower:
                # Buscar contexto alrededor de la keyword
                idx = text_lower.find(keyword)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(keyword) + 50)
                snippet = text[start:end].strip()
                if snippet not in evidence_snippets:
                    evidence_snippets.append(snippet)
                status = "vigente"
                break
    
    if status == "desconocido":
        for keyword in pendiente_keywords:
            if keyword in text_lower:
                idx = text_lower.find(keyword)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(keyword) + 50)
                snippet = text[start:end].strip()
                if snippet not in evidence_snippets:
                    evidence_snippets.append(snippet)
                status = "pendiente"
                break
    
    # 2. Extraer fechas (múltiples formatos)
    date_patterns = [
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',  # DD/MM/YYYY o DD-MM-YYYY
        r'\b(\d{2,4})[/-](\d{1,2})[/-](\d{1,2})\b',  # YYYY/MM/DD o YYYY-MM-DD
    ]
    
    for pattern in date_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            date_str = match.group(0)
            if date_str not in raw_dates:
                raw_dates.append(date_str)
                
                # Intentar normalizar a YYYY-MM-DD
                try:
                    parts = re.split(r'[/-]', date_str)
                    if len(parts) == 3:
                        # Asumir formato DD/MM/YYYY si el primer número es <= 31
                        if len(parts[0]) <= 2 and int(parts[0]) <= 31:
                            day, month, year = parts[0], parts[1], parts[2]
                        else:
                            # Asumir YYYY/MM/DD
                            year, month, day = parts[0], parts[1], parts[2]
                        
                        # Normalizar año a 4 dígitos
                        if len(year) == 2:
                            year = "20" + year if int(year) < 50 else "19" + year
                        
                        normalized = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        if normalized not in expiry_dates:
                            expiry_dates.append(normalized)
                except (ValueError, IndexError):
                    # Si no se puede normalizar, continuar
                    pass
    
    logger.debug(
        "[cae-ocr] Extracted status: status=%r dates=%r evidence_count=%d",
        status, expiry_dates, len(evidence_snippets)
    )
    
    return {
        "status": status,
        "expiry_dates": expiry_dates,
        "raw_dates": raw_dates,
        "evidence_snippets": evidence_snippets[:5],  # Limitar a 5 snippets
    }

