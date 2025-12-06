"""
Helpers para detección y construcción de instrucciones de subida de archivos.
v2.2.0: Integración de DocumentRepository con el flujo del agente.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re
import logging

from backend.agents.document_repository import DocumentRepository, DocumentDescriptor
from backend.agents.session_context import SessionContext
from backend.shared.models import DocumentAnalysisResult, FormFillInstruction, DeepDocumentAnalysis

logger = logging.getLogger(__name__)


@dataclass
class FileUploadInstruction:
    """
    Instrucción para subir un archivo (intención, no ejecución real).
    v2.2.0: Describe qué archivo quiere usar el agente.
    v4.4.0: Añade análisis del documento (fechas, trabajador, etc.)
    v4.5.0: Añade instrucción para rellenar formulario automáticamente
    """
    path: Path
    description: str  # p.ej. "Reconocimiento médico de Juan Pérez para Empresa X"
    company: Optional[str] = None
    worker: Optional[str] = None
    doc_type: Optional[str] = None
    document_analysis: Optional[DocumentAnalysisResult] = field(default=None)  # v4.4.0
    form_fill_instruction: Optional[FormFillInstruction] = field(default=None)  # v4.5.0
    deep_document_analysis: Optional[DeepDocumentAnalysis] = field(default=None)  # v4.8.0
    
    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        result = {
            "path": str(self.path),
            "description": self.description,
            "company": self.company,
            "worker": self.worker,
            "doc_type": self.doc_type,
        }
        # v4.4.0: Incluir análisis del documento si está disponible
        if self.document_analysis:
            result["document_analysis"] = self.document_analysis.model_dump()
        # v4.5.0: Incluir instrucción de rellenado de formulario si está disponible
        if self.form_fill_instruction:
            result["form_fill_instruction"] = self.form_fill_instruction.model_dump()
        # v4.8.0: Incluir análisis profundo si está disponible
        if self.deep_document_analysis:
            result["deep_document_analysis"] = self.deep_document_analysis.model_dump()
        return result


def _maybe_build_file_upload_instruction(
    goal: str,
    focus_entity: Optional[str],
    session_context: SessionContext,
    document_repository: DocumentRepository,
    expected_doc_type: Optional[str] = None,  # v4.4.0: Tipo de documento esperado (desde CAE)
    worker_full_name: Optional[str] = None,  # v4.4.0: Nombre completo del trabajador (desde CAE)
    company_name: Optional[str] = None,  # v4.4.0: Nombre de la empresa (desde CAE)
    ocr_service: Optional["OCRService"] = None,  # v4.4.0: Servicio OCR para análisis de documentos
) -> Optional[FileUploadInstruction]:
    """
    Detecta si el objetivo menciona subir documentos y construye una instrucción si encuentra un documento.
    
    Args:
        goal: Texto del objetivo
        focus_entity: Entidad focal (opcional)
        session_context: Contexto de sesión para obtener información de entidades
        document_repository: Repositorio de documentos
        
    Returns:
        FileUploadInstruction si se detecta intención de subida y se encuentra documento, None en caso contrario
    """
    goal_lower = goal.lower()
    
    # Detectar palabras clave de subida
    upload_keywords = [
        "sube", "subir", "adjunta", "adjuntar",
        "sube el", "sube la", "sube un", "sube una",
        "adjunta el", "adjunta la", "adjunta un", "adjunta una",
        "subir documento", "subir documentación", "adjuntar documento", "adjuntar documentación",
    ]
    
    has_upload_intent = any(keyword in goal_lower for keyword in upload_keywords)
    
    if not has_upload_intent:
        logger.debug(f"[file-upload] No upload intent detected in goal: {goal!r}")
        return None
    
    logger.debug(f"[file-upload] Upload intent detected in goal: {goal!r}")
    
    # Mapear doc_type desde palabras clave en el goal
    doc_type = None
    if "reconocimiento" in goal_lower or "reconocimiento médico" in goal_lower or "reconocimiento medico" in goal_lower:
        doc_type = "reconocimiento_medico"
    elif "formación" in goal_lower or "formacion" in goal_lower or "certificado de formación" in goal_lower:
        doc_type = "formacion"
    elif "cae" in goal_lower or "documentación cae" in goal_lower or "documentacion cae" in goal_lower:
        doc_type = "cae"
    elif "prl" in goal_lower:
        doc_type = "prl"
    elif "contrato" in goal_lower:
        doc_type = "contrato"
    elif "dni" in goal_lower:
        doc_type = "dni"
    
    # Determinar company y worker
    # Usar focus_entity como worker si está disponible
    worker = focus_entity
    
    # Si no hay focus_entity, intentar usar session_context
    if not worker:
        worker = session_context.current_focus_entity or session_context.last_valid_entity
    
    # Intentar extraer company del goal o usar una por defecto si es muy obvio
    # Por ahora, si no se especifica, usamos None (el repositorio buscará en todas las empresas)
    company = None
    
    # Buscar patrones como "de la empresa X" o "para empresa X"
    company_patterns = [
        r"empresa\s+(\w+)",
        r"de\s+la\s+empresa\s+(\w+)",
        r"para\s+empresa\s+(\w+)",
    ]
    for pattern in company_patterns:
        match = re.search(pattern, goal_lower)
        if match:
            company = match.group(1)
            break
    
    # Si no encontramos company explícita, intentar usar la primera entidad del historial si es una empresa
    # Por ahora, dejamos company como None para buscar en todas las empresas
    
    # Buscar documento en el repositorio
    doc_descriptor = document_repository.find_latest(
        company=company,
        worker=worker,
        doc_type=doc_type,
    )
    
    if not doc_descriptor:
        logger.debug(
            f"[file-upload] No document found: company={company} worker={worker} doc_type={doc_type}"
        )
        return None
    
    # Construir descripción en español
    description_parts = []
    if doc_descriptor.doc_type:
        # Mapear doc_type a descripción legible
        doc_type_names = {
            "reconocimiento_medico": "reconocimiento médico",
            "formacion": "certificado de formación",
            "cae": "documentación CAE",
            "prl": "documento PRL",
            "contrato": "contrato",
            "dni": "DNI",
        }
        doc_type_name = doc_type_names.get(doc_descriptor.doc_type, doc_descriptor.doc_type)
        description_parts.append(doc_type_name)
    
    if doc_descriptor.worker:
        description_parts.append(f"de {doc_descriptor.worker}")
    
    if doc_descriptor.company:
        description_parts.append(f"para {doc_descriptor.company}")
    
    description = " ".join(description_parts) if description_parts else "documento local"
    
    instruction = FileUploadInstruction(
        path=doc_descriptor.path,
        description=description,
        company=doc_descriptor.company,
        worker=doc_descriptor.worker,
        doc_type=doc_descriptor.doc_type,
    )
    
    # v4.4.0: Analizar el documento si es un PDF y tenemos contexto CAE
    # Nota: El análisis se hace de forma asíncrona, pero esta función es síncrona.
    # El análisis se ejecutará cuando se llame desde un contexto async, o se puede hacer lazy.
    # Por ahora, marcamos que el análisis debe hacerse más tarde si es necesario.
    # Para v4.4.0, haremos el análisis de forma lazy cuando se necesite.
    if doc_descriptor.path.suffix.lower() == '.pdf':
        try:
            from backend.agents.document_analyzer import DocumentAnalyzer
            import asyncio
            import sys
            
            analyzer = DocumentAnalyzer(ocr_service=ocr_service)
            
            # Usar expected_doc_type si está disponible, sino usar doc_descriptor.doc_type
            analysis_doc_type = expected_doc_type or doc_descriptor.doc_type
            
            # Usar worker_full_name si está disponible, sino usar doc_descriptor.worker
            analysis_worker = worker_full_name or doc_descriptor.worker
            
            # Usar company_name si está disponible, sino usar doc_descriptor.company
            analysis_company = company_name or doc_descriptor.company
            
            # Ejecutar análisis de forma síncrona usando asyncio.run solo si no hay event loop activo
            try:
                # Verificar si hay un event loop activo
                try:
                    loop = asyncio.get_running_loop()
                    # Si hay un loop activo, no podemos usar asyncio.run
                    # En este caso, creamos una tarea para ejecutar más tarde
                    # Por ahora, saltamos el análisis si hay un loop activo
                    logger.debug("[file-upload] Event loop activo, análisis de documento se hará más tarde")
                except RuntimeError:
                    # No hay loop activo, podemos usar asyncio.run
                    analysis_result = asyncio.run(analyzer.analyze(
                        file_path=str(doc_descriptor.path),
                        expected_doc_type=analysis_doc_type,
                        worker_full_name=analysis_worker,
                        company_name=analysis_company,
                    ))
                    instruction.document_analysis = analysis_result
                    logger.info(
                        f"[file-upload] Document analyzed: confidence={analysis_result.confidence:.2f}, "
                        f"issue_date={analysis_result.issue_date}, expiry_date={analysis_result.expiry_date}, "
                        f"worker_name={analysis_result.worker_name}"
                    )
            except Exception as e:
                logger.warning(f"[file-upload] Error analyzing document {doc_descriptor.path}: {e}", exc_info=True)
                # Continuar sin análisis, no debe romper la subida
        except ImportError:
            logger.debug("[file-upload] DocumentAnalyzer no disponible, saltando análisis")
        except Exception as e:
            logger.warning(f"[file-upload] Error inicializando DocumentAnalyzer: {e}", exc_info=True)
            # Continuar sin análisis
    
    logger.info(
        f"[file-upload] Built upload instruction: {description} -> {doc_descriptor.path}"
    )
    
    return instruction




