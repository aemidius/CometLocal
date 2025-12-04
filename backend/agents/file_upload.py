"""
Helpers para detección y construcción de instrucciones de subida de archivos.
v2.2.0: Integración de DocumentRepository con el flujo del agente.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re
import logging

from backend.agents.document_repository import DocumentRepository, DocumentDescriptor
from backend.agents.session_context import SessionContext

logger = logging.getLogger(__name__)


@dataclass
class FileUploadInstruction:
    """
    Instrucción para subir un archivo (intención, no ejecución real).
    v2.2.0: Describe qué archivo quiere usar el agente.
    """
    path: Path
    description: str  # p.ej. "Reconocimiento médico de Juan Pérez para Empresa X"
    company: Optional[str] = None
    worker: Optional[str] = None
    doc_type: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        return {
            "path": str(self.path),
            "description": self.description,
            "company": self.company,
            "worker": self.worker,
            "doc_type": self.doc_type,
        }


def _maybe_build_file_upload_instruction(
    goal: str,
    focus_entity: Optional[str],
    session_context: SessionContext,
    document_repository: DocumentRepository,
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
    
    logger.info(
        f"[file-upload] Built upload instruction: {description} -> {doc_descriptor.path}"
    )
    
    return instruction

