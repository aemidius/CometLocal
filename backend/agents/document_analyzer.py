"""
DocumentAnalyzer para análisis de documentos PDF CAE.

v4.4.0: Fase 1 - Extracción básica de fechas y trabajador.
"""

import re
import logging
from pathlib import Path
from typing import Optional, List
from datetime import date, datetime

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

from backend.shared.models import DocumentAnalysisResult
from backend.vision.ocr_service import OCRService

logger = logging.getLogger(__name__)


class DocumentAnalyzer:
    """
    Analizador de documentos PDF para extraer información relevante para CAE.
    
    v4.4.0: Fase 1 - Extrae fechas (emisión/caducidad) y nombre del trabajador.
    """
    
    def __init__(self, ocr_service: Optional[OCRService] = None):
        """
        Inicializa el analizador de documentos.
        
        Args:
            ocr_service: Servicio OCR opcional para fallback cuando el PDF no tiene texto embebido
        """
        self.ocr_service = ocr_service
    
    async def analyze(
        self,
        file_path: str,
        expected_doc_type: Optional[str] = None,
        worker_full_name: Optional[str] = None,
        company_name: Optional[str] = None,
    ) -> DocumentAnalysisResult:
        """
        Analiza un documento PDF y extrae información relevante.
        
        Args:
            file_path: Ruta al archivo PDF
            expected_doc_type: Tipo de documento esperado (ej: "reconocimiento_medico")
            worker_full_name: Nombre completo del trabajador esperado (para validación)
            company_name: Nombre de la empresa (opcional)
            
        Returns:
            DocumentAnalysisResult con la información extraída
        """
        file_path_obj = Path(file_path)
        source_path = str(file_path_obj.resolve())
        
        result = DocumentAnalysisResult(
            doc_type=expected_doc_type,
            worker_name=None,
            company_name=company_name,
            issue_date=None,
            expiry_date=None,
            raw_dates=[],
            warnings=[],
            confidence=0.0,
            source_path=source_path,
        )
        
        # Extraer texto del PDF
        full_text = await self._extract_text(file_path_obj, result)
        
        if not full_text or len(full_text.strip()) < 50:
            result.warnings.append("No se ha podido extraer texto útil del PDF")
            return result
        
        # Normalizar texto (trabajar en minúsculas para búsquedas)
        text_lower = full_text.lower()
        
        # Detectar fechas
        dates = self._extract_dates(full_text, text_lower, result)
        
        # Inferir issue_date y expiry_date
        self._infer_dates(dates, text_lower, result)
        
        # Detectar nombre del trabajador
        self._detect_worker_name(full_text, text_lower, worker_full_name, result)
        
        # Asignar doc_type si no viene dado
        if not result.doc_type:
            result.doc_type = self._detect_doc_type(text_lower)
        
        # Calcular confidence
        self._calculate_confidence(result, full_text)
        
        return result
    
    async def _extract_text(self, file_path: Path, result: DocumentAnalysisResult) -> str:
        """
        Extrae texto del PDF usando pypdf, con fallback a OCR si es necesario.
        
        Returns:
            Texto extraído o cadena vacía si falla
        """
        full_text = ""
        
        # Intentar con pypdf
        if PYPDF_AVAILABLE:
            try:
                reader = PdfReader(str(file_path))
                text_parts = []
                # Limitar a las primeras 10 páginas para evitar problemas con PDFs muy grandes
                for i, page in enumerate(reader.pages[:10]):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    except Exception as e:
                        logger.warning(f"[doc-analyzer] Error extrayendo texto de página {i}: {e}")
                
                full_text = "\n".join(text_parts)
                
                if len(full_text.strip()) < 50:
                    logger.debug(f"[doc-analyzer] Texto extraído muy corto ({len(full_text)} chars), intentando OCR")
                    # Intentar OCR como fallback
                    if self.ocr_service:
                        try:
                            # OCRService espera una imagen, pero podemos intentar con el PDF
                            # Por ahora, si el texto es muy corto, marcamos warning
                            result.warnings.append("Texto extraído muy corto, puede ser un PDF escaneado")
                        except Exception as e:
                            logger.warning(f"[doc-analyzer] Error en OCR fallback: {e}")
            except Exception as e:
                logger.warning(f"[doc-analyzer] Error extrayendo texto con pypdf: {e}")
                result.warnings.append(f"Error al extraer texto del PDF: {e}")
        else:
            result.warnings.append("pypdf no está disponible, no se puede extraer texto del PDF")
        
        return full_text
    
    def _extract_dates(self, full_text: str, text_lower: str, result: DocumentAnalysisResult) -> List[date]:
        """
        Extrae todas las fechas encontradas en el texto.
        
        Returns:
            Lista de objetos date encontrados
        """
        dates = []
        
        # Patrones de fecha comunes
        date_patterns = [
            # DD/MM/YYYY o DD-MM-YYYY
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',
            # YYYY/MM/DD o YYYY-MM-DD
            r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b',
            # DD/MM/YY o DD-MM-YY (años de 2 dígitos)
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b',
        ]
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, full_text)
            for match in matches:
                date_str = match.group(0)
                result.raw_dates.append(date_str)
                
                try:
                    # Intentar parsear la fecha
                    parts = re.split(r'[/-]', date_str)
                    if len(parts) == 3:
                        try:
                            if len(parts[2]) == 4:  # YYYY-MM-DD o DD-MM-YYYY
                                if int(parts[0]) > 31:  # Probablemente YYYY-MM-DD
                                    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                                else:  # Probablemente DD-MM-YYYY
                                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                            else:  # DD-MM-YY
                                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                                # Asumir años 20XX para años de 2 dígitos
                                if year < 50:
                                    year += 2000
                                else:
                                    year += 1900
                            
                            # Validar fecha
                            parsed_date = date(year, month, day)
                            dates.append(parsed_date)
                        except (ValueError, IndexError) as e:
                            logger.debug(f"[doc-analyzer] No se pudo parsear fecha {date_str}: {e}")
                except Exception as e:
                    logger.debug(f"[doc-analyzer] Error parseando fecha {date_str}: {e}")
        
        # Eliminar duplicados manteniendo orden
        seen = set()
        unique_dates = []
        for d in dates:
            if d not in seen:
                seen.add(d)
                unique_dates.append(d)
        
        return unique_dates
    
    def _infer_dates(self, dates: List[date], text_lower: str, result: DocumentAnalysisResult) -> None:
        """
        Infiere issue_date y expiry_date a partir de las fechas encontradas y el contexto.
        """
        if not dates:
            result.warnings.append("No se encontraron fechas en el documento")
            return
        
        # Buscar palabras clave para identificar fechas
        issue_keywords = [
            "fecha de reconocimiento", "fecha de emisión", "fecha de realización",
            "fecha de expedición", "fecha", "realizado el", "emitido el"
        ]
        expiry_keywords = [
            "fecha de caducidad", "válido hasta", "valido hasta", "caduca el",
            "válido hasta el", "valido hasta el", "expira el", "vencimiento"
        ]
        
        # Buscar fechas cerca de palabras clave
        issue_candidates = []
        expiry_candidates = []
        
        # Si hay contexto de palabras clave, intentar asociar fechas
        # Por ahora, usar heurística simple: la más antigua es issue, la más futura es expiry
        if len(dates) >= 2:
            sorted_dates = sorted(dates)
            result.issue_date = sorted_dates[0]
            result.expiry_date = sorted_dates[-1]
            
            # Verificar que expiry_date es posterior a issue_date
            if result.expiry_date <= result.issue_date:
                result.warnings.append("La fecha de caducidad no es posterior a la fecha de emisión")
                result.expiry_date = None
        elif len(dates) == 1:
            # Solo una fecha: intentar inferir si es issue o expiry
            single_date = dates[0]
            # Buscar contexto en el texto alrededor de la fecha
            date_str = single_date.strftime("%d/%m/%Y")
            date_idx = text_lower.find(date_str.lower())
            
            if date_idx >= 0:
                # Buscar contexto en un rango de 100 caracteres antes y después
                context_start = max(0, date_idx - 100)
                context_end = min(len(text_lower), date_idx + len(date_str) + 100)
                context = text_lower[context_start:context_end]
                
                # Si hay palabras clave de expiry cerca, asumir que es expiry
                if any(keyword in context for keyword in expiry_keywords):
                    result.expiry_date = single_date
                elif any(keyword in context for keyword in issue_keywords):
                    result.issue_date = single_date
                else:
                    # Por defecto, asumir que es issue_date
                    result.issue_date = single_date
                    result.warnings.append("Solo se encontró una fecha, se asume como fecha de emisión")
            else:
                result.issue_date = single_date
                result.warnings.append("Solo se encontró una fecha, se asume como fecha de emisión")
        else:
            result.warnings.append("No se pudieron inferir fechas de emisión/caducidad")
    
    def _detect_worker_name(self, full_text: str, text_lower: str, worker_full_name: Optional[str], result: DocumentAnalysisResult) -> None:
        """
        Detecta el nombre del trabajador en el documento.
        """
        if worker_full_name:
            # Normalizar nombre esperado para búsqueda
            worker_normalized = worker_full_name.lower().strip()
            worker_parts = worker_normalized.split()
            
            # Buscar el nombre completo o partes del nombre
            found = False
            if worker_normalized in text_lower:
                found = True
            else:
                # Buscar si todas las partes del nombre aparecen (pueden estar separadas)
                all_parts_found = all(part in text_lower for part in worker_parts if len(part) > 2)
                if all_parts_found:
                    found = True
            
            if found:
                result.worker_name = worker_full_name
                logger.debug(f"[doc-analyzer] Nombre del trabajador encontrado: {worker_full_name}")
            else:
                result.warnings.append(f"El nombre del trabajador esperado '{worker_full_name}' no se encontró en el documento")
        
        # Si no se encontró con el nombre esperado, intentar heurística simple
        if not result.worker_name:
            # Buscar líneas que parezcan nombres (palabras con inicial mayúscula)
            lines = full_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Patrón simple: 2-4 palabras con inicial mayúscula
                words = line.split()
                if 2 <= len(words) <= 4:
                    # Verificar que todas las palabras empiezan con mayúscula
                    if all(word and word[0].isupper() for word in words if word):
                        # Excluir líneas que parezcan títulos o encabezados
                        if not any(keyword in line.lower() for keyword in ["certificado", "documento", "reconocimiento", "formación", "fecha"]):
                            result.worker_name = line
                            logger.debug(f"[doc-analyzer] Nombre del trabajador inferido: {line}")
                            break
    
    def _detect_doc_type(self, text_lower: str) -> Optional[str]:
        """
        Detecta el tipo de documento a partir de palabras clave en el texto.
        """
        if "reconocimiento médico" in text_lower or "reconocimiento medico" in text_lower:
            return "reconocimiento_medico"
        elif "formación" in text_lower and "prl" in text_lower:
            return "formacion_prl"
        elif "formación" in text_lower or "formacion" in text_lower:
            return "formacion"
        elif "prl" in text_lower:
            return "prl"
        elif "cae" in text_lower:
            return "cae"
        elif "contrato" in text_lower:
            return "contrato"
        elif "dni" in text_lower or "documento nacional de identidad" in text_lower:
            return "dni"
        
        return None
    
    def _calculate_confidence(self, result: DocumentAnalysisResult, full_text: str) -> None:
        """
        Calcula la confianza del análisis basándose en la información extraída.
        """
        confidence = 0.0
        
        # +0.4 si se ha extraído texto decente
        if len(full_text.strip()) >= 50:
            confidence += 0.4
        
        # +0.2 si se ha encontrado worker_name
        if result.worker_name:
            confidence += 0.2
        
        # +0.2 si se han identificado claramente issue/expiry date
        if result.issue_date and result.expiry_date:
            confidence += 0.2
        elif result.issue_date or result.expiry_date:
            confidence += 0.1
        
        # Penalizar por warnings
        if len(result.warnings) > 0:
            confidence -= min(0.2, len(result.warnings) * 0.05)
        
        # Asegurar que está en [0.0, 1.0]
        result.confidence = max(0.0, min(1.0, confidence))

