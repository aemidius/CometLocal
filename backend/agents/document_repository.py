"""
Repositorio de documentos local para CometLocal.
v2.2.0: Gestión de documentos organizados por empresa/trabajador/tipo.
Versión simplificada según especificaciones v2.2.0.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class DocumentDescriptor:
    """
    Descriptor de un documento encontrado en el repositorio.
    """
    path: Path
    company: Optional[str] = None
    worker: Optional[str] = None
    doc_type: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)


class DocumentRepository:
    """
    Repositorio de documentos local con organización jerárquica.
    
    Layout por defecto: <base_dir>/<company>/<worker>/<doc_type>/archivo.pdf
    """
    
    def __init__(self, base_dir: Path):
        """
        Inicializa el repositorio.
        
        Args:
            base_dir: Directorio raíz del repositorio
        """
        self.base_dir = Path(base_dir).resolve()
        
        # Extensiones permitidas por defecto
        self.allowed_extensions = [".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".txt"]
        
        # Crear directorio base si no existe
        if not self.base_dir.exists():
            logger.info(f"[document-repo] Base directory does not exist: {self.base_dir}, will be created on first write")
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"[document-repo] Failed to create base directory: {e}")
        else:
            logger.debug(f"[document-repo] Initialized repository at: {self.base_dir}")
    
    def find_latest(
        self,
        company: Optional[str],
        worker: Optional[str],
        doc_type: Optional[str],
    ) -> Optional[DocumentDescriptor]:
        """
        Devuelve el documento 'mejor candidato' (el más reciente por fecha de modificación)
        o None si no hay coincidencias.
        
        Args:
            company: Nombre de la empresa (opcional)
            worker: Nombre del trabajador (opcional)
            doc_type: Tipo de documento (opcional)
            
        Returns:
            DocumentDescriptor del documento más reciente, o None si no se encuentra
        """
        all_docs = self.list_documents(company=company, worker=worker, doc_type=doc_type)
        if not all_docs:
            logger.debug(
                f"[document-repo] No documents found: company={company} worker={worker} doc_type={doc_type}"
            )
            return None
        
        # list_documents ya devuelve ordenado por fecha (más reciente primero)
        latest = all_docs[0]
        logger.info(
            f"[document-repo] Found latest document: {latest.path} "
            f"(company={company} worker={worker} doc_type={doc_type})"
        )
        return latest
    
    def list_documents(
        self,
        company: Optional[str] = None,
        worker: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> List[DocumentDescriptor]:
        """
        Devuelve una lista de documentos que coincidan con los filtros,
        ordenados por fecha de modificación (más reciente primero).
        
        Args:
            company: Nombre de la empresa (opcional)
            worker: Nombre del trabajador (opcional)
            doc_type: Tipo de documento (opcional)
            
        Returns:
            Lista de DocumentDescriptor ordenada por fecha de modificación (descendente)
        """
        if not self.base_dir.exists():
            logger.debug(f"[document-repo] Base directory does not exist: {self.base_dir}")
            return []
        
        documents: List[DocumentDescriptor] = []
        
        # Caso 1: company/worker/doc_type (todos especificados)
        if company and worker and doc_type:
            doc_path = self.base_dir / company / worker / doc_type
            if doc_path.exists() and doc_path.is_dir():
                documents.extend(self._scan_directory(doc_path, company, worker, doc_type))
        
        # Caso 2: company/worker/* (worker especificado, doc_type None)
        elif company and worker and not doc_type:
            worker_path = self.base_dir / company / worker
            if worker_path.exists() and worker_path.is_dir():
                for doc_type_dir in worker_path.iterdir():
                    if doc_type_dir.is_dir():
                        documents.extend(
                            self._scan_directory(doc_type_dir, company, worker, doc_type_dir.name)
                        )
        
        # Caso 3: company/*/doc_type (doc_type especificado, worker None)
        elif company and not worker and doc_type:
            company_path = self.base_dir / company
            if company_path.exists() and company_path.is_dir():
                for worker_dir in company_path.iterdir():
                    if worker_dir.is_dir():
                        doc_type_path = worker_dir / doc_type
                        if doc_type_path.exists() and doc_type_path.is_dir():
                            documents.extend(
                                self._scan_directory(doc_type_path, company, worker_dir.name, doc_type)
                            )
        
        # Caso 4: company/*/* (solo company especificado)
        elif company and not worker and not doc_type:
            company_path = self.base_dir / company
            if company_path.exists() and company_path.is_dir():
                for worker_dir in company_path.iterdir():
                    if worker_dir.is_dir():
                        for doc_type_dir in worker_dir.iterdir():
                            if doc_type_dir.is_dir():
                                documents.extend(
                                    self._scan_directory(doc_type_dir, company, worker_dir.name, doc_type_dir.name)
                                )
        
        # Ordenar por fecha de modificación (más reciente primero)
        documents.sort(key=lambda d: d.extra.get("modified_time", 0.0), reverse=True)
        
        return documents
    
    def _scan_directory(
        self,
        directory: Path,
        company: Optional[str],
        worker: Optional[str],
        doc_type: Optional[str],
    ) -> List[DocumentDescriptor]:
        """
        Escanea un directorio buscando archivos con extensiones permitidas.
        
        Args:
            directory: Directorio a escanear
            company: Nombre de la empresa
            worker: Nombre del trabajador (opcional)
            doc_type: Tipo de documento (opcional)
            
        Returns:
            Lista de DocumentDescriptor encontrados
        """
        documents = []
        
        try:
            for file_path in directory.iterdir():
                if not file_path.is_file():
                    continue
                
                # Verificar extensión
                file_ext = file_path.suffix.lower()
                if file_ext not in self.allowed_extensions:
                    continue
                
                # Obtener fecha de modificación
                try:
                    modified_time = file_path.stat().st_mtime
                except Exception:
                    modified_time = 0.0
                
                doc_descriptor = DocumentDescriptor(
                    path=file_path,
                    company=company,
                    worker=worker,
                    doc_type=doc_type,
                    extra={
                        "filename": file_path.name,
                        "modified_time": str(modified_time),
                        "size": str(file_path.stat().st_size if file_path.exists() else 0),
                    }
                )
                documents.append(doc_descriptor)
        except Exception as e:
            logger.warning(f"[document-repo] Error scanning directory {directory}: {e}")
        
        return documents









