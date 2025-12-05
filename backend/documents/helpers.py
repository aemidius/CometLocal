"""
Helpers para integración de DocumentRepository con el agente (legacy).
v2.2.0: Este archivo mantiene compatibilidad con tests antiguos.
El nuevo sistema está en backend/agents/document_repository.py
"""

from pathlib import Path
from typing import Optional
import logging

from backend.config import DOCUMENT_REPOSITORY_BASE_DIR
from backend.agents.document_repository import DocumentRepository, DocumentDescriptor
from backend.shared.models import DocumentRequest

logger = logging.getLogger(__name__)

# Instancia global del repositorio (lazy initialization)
_repository_instance: Optional[DocumentRepository] = None


def get_document_repository(base_path: Optional[Path] = None) -> DocumentRepository:
    """
    Obtiene la instancia del repositorio de documentos (singleton).
    
    Args:
        base_path: Path opcional para sobrescribir la configuración (útil para tests)
    
    Returns:
        Instancia de DocumentRepository configurada
    """
    global _repository_instance
    
    if _repository_instance is None or base_path is not None:
        if base_path is None:
            base_path = Path(DOCUMENT_REPOSITORY_BASE_DIR)
        else:
            base_path = Path(base_path).resolve()
        
        _repository_instance = DocumentRepository(base_path)
        logger.debug(f"[document-repo] Initialized repository at: {base_path}")
    
    return _repository_instance


def resolve_document_request(
    doc_request: DocumentRequest,
    base_path: Optional[Path] = None
) -> Optional[DocumentDescriptor]:
    """
    Resuelve una petición lógica de documento a un DocumentDescriptor.
    
    Args:
        doc_request: Petición de documento (company/worker/doc_type)
        base_path: Path opcional para sobrescribir la configuración (útil para tests)
        
    Returns:
        DocumentDescriptor del documento más reciente encontrado, o None si no se encuentra
    """
    try:
        repo = get_document_repository(base_path=base_path)
        
        doc_descriptor = repo.find_latest(
            company=doc_request.company,
            worker=doc_request.worker,
            doc_type=doc_request.doc_type,
        )
        
        if doc_descriptor:
            logger.debug(
                f"[document-repo] Resolved document: company={doc_request.company} "
                f"worker={doc_request.worker} doc_type={doc_request.doc_type} -> {doc_descriptor.path}"
            )
        else:
            logger.debug(
                f"[document-repo] No document found: company={doc_request.company} "
                f"worker={doc_request.worker} doc_type={doc_request.doc_type}"
            )
        
        return doc_descriptor
    except Exception as e:
        logger.error(f"[document-repo] Error resolving document request: {e}", exc_info=True)
        return None

