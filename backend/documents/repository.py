"""
Repositorio de documentos local para CometLocal.
v2.2.0: Gestión de documentos organizados por empresa/trabajador/tipo.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Literal, Dict, Any
import os
import logging

logger = logging.getLogger(__name__)

DocType = Literal["dni", "contrato", "formacion", "prl", "reconocimiento_medico", "otro"]


@dataclass
class DocumentQuery:
    """
    Query lógica para buscar documentos.
    """
    company: str
    worker: Optional[str] = None
    doc_type: Optional[DocType] = None


@dataclass
class DocumentInfo:
    """
    Información de un documento encontrado.
    """
    path: Path
    company: str
    worker: Optional[str]
    doc_type: Optional[DocType]
    modified_time: float  # timestamp
    extra: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para serialización."""
        return {
            "path": str(self.path),
            "company": self.company,
            "worker": self.worker,
            "doc_type": self.doc_type,
            "modified_time": self.modified_time,
            "extra": self.extra,
        }


class DocumentRepository:
    """
    Repositorio de documentos local con organización jerárquica.
    
    Layout por defecto: <base_path>/<company>/<worker>/<doc_type>/*
    """
    
    def __init__(
        self,
        base_path: Path,
        pattern_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa el repositorio.
        
        Args:
            base_path: Ruta raíz del repositorio
            pattern_config: Configuración de organización (opcional)
                - layout: patrón de organización (por defecto "company/worker/doc_type")
                - extensions: extensiones permitidas (por defecto [".pdf", ".docx", ".jpg", ".png"])
        """
        self.base_path = Path(base_path).resolve()
        self.pattern_config = pattern_config or {}
        
        # Extensiones permitidas por defecto
        self.allowed_extensions = self.pattern_config.get(
            "extensions",
            [".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".txt"]
        )
        # Normalizar extensiones a minúsculas con punto
        self.allowed_extensions = [
            ext if ext.startswith(".") else f".{ext}"
            for ext in self.allowed_extensions
        ]
        self.allowed_extensions = [ext.lower() for ext in self.allowed_extensions]
        
        # Layout por defecto
        self.layout = self.pattern_config.get("layout", "company/worker/doc_type")
        
        # Crear directorio base si no existe
        if not self.base_path.exists():
            logger.warning(f"[document-repo] Base path does not exist: {self.base_path}, will be created on first write")
            try:
                self.base_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"[document-repo] Failed to create base path: {e}")
    
    def find_latest(self, query: DocumentQuery) -> Optional[DocumentInfo]:
        """
        Devuelve el documento más reciente que encaja con la query.
        
        Args:
            query: Query lógica para buscar documentos
            
        Returns:
            DocumentInfo del documento más reciente, o None si no se encuentra
        """
        all_docs = self.find_all(query)
        if not all_docs:
            return None
        # find_all ya devuelve ordenado por fecha (más reciente primero)
        return all_docs[0]
    
    def find_all(self, query: DocumentQuery) -> List[DocumentInfo]:
        """
        Devuelve todos los documentos que encajan con la query, ordenados por fecha (más reciente primero).
        
        Args:
            query: Query lógica para buscar documentos
            
        Returns:
            Lista de DocumentInfo ordenada por fecha de modificación (descendente)
        """
        if not self.base_path.exists():
            logger.debug(f"[document-repo] Base path does not exist: {self.base_path}")
            return []
        
        company_path = self.base_path / query.company
        if not company_path.exists():
            logger.debug(f"[document-repo] Company path does not exist: {company_path}")
            return []
        
        documents: List[DocumentInfo] = []
        
        # Caso 1: company/worker/doc_type (todos especificados)
        if query.worker and query.doc_type:
            worker_path = company_path / query.worker / query.doc_type
            if worker_path.exists() and worker_path.is_dir():
                documents.extend(self._scan_directory(worker_path, query.company, query.worker, query.doc_type))
        
        # Caso 2: company/worker/* (worker especificado, doc_type None)
        elif query.worker and not query.doc_type:
            worker_path = company_path / query.worker
            if worker_path.exists() and worker_path.is_dir():
                for doc_type_dir in worker_path.iterdir():
                    if doc_type_dir.is_dir():
                        # Intentar inferir doc_type del nombre del directorio
                        doc_type = self._infer_doc_type(doc_type_dir.name)
                        documents.extend(
                            self._scan_directory(doc_type_dir, query.company, query.worker, doc_type)
                        )
        
        # Caso 3: company/*/doc_type (doc_type especificado, worker None)
        elif not query.worker and query.doc_type:
            for worker_dir in company_path.iterdir():
                if worker_dir.is_dir():
                    doc_type_path = worker_dir / query.doc_type
                    if doc_type_path.exists() and doc_type_path.is_dir():
                        documents.extend(
                            self._scan_directory(doc_type_path, query.company, worker_dir.name, query.doc_type)
                        )
        
        # Caso 4: company/*/* (solo company especificado)
        elif not query.worker and not query.doc_type:
            for worker_dir in company_path.iterdir():
                if worker_dir.is_dir():
                    for doc_type_dir in worker_dir.iterdir():
                        if doc_type_dir.is_dir():
                            doc_type = self._infer_doc_type(doc_type_dir.name)
                            documents.extend(
                                self._scan_directory(doc_type_dir, query.company, worker_dir.name, doc_type)
                            )
        
        # Ordenar por fecha de modificación (más reciente primero)
        documents.sort(key=lambda d: d.modified_time, reverse=True)
        
        return documents
    
    def _scan_directory(
        self,
        directory: Path,
        company: str,
        worker: Optional[str],
        doc_type: Optional[DocType],
    ) -> List[DocumentInfo]:
        """
        Escanea un directorio buscando archivos con extensiones permitidas.
        
        Args:
            directory: Directorio a escanear
            company: Nombre de la empresa
            worker: Nombre del trabajador (opcional)
            doc_type: Tipo de documento (opcional)
            
        Returns:
            Lista de DocumentInfo encontrados
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
                
                doc_info = DocumentInfo(
                    path=file_path,
                    company=company,
                    worker=worker,
                    doc_type=doc_type,
                    modified_time=modified_time,
                    extra={
                        "filename": file_path.name,
                        "size": file_path.stat().st_size if file_path.exists() else 0,
                    }
                )
                documents.append(doc_info)
        except Exception as e:
            logger.warning(f"[document-repo] Error scanning directory {directory}: {e}")
        
        return documents
    
    def _infer_doc_type(self, dir_name: str) -> Optional[DocType]:
        """
        Intenta inferir el tipo de documento desde el nombre del directorio.
        
        Args:
            dir_name: Nombre del directorio
            
        Returns:
            DocType inferido o None
        """
        dir_lower = dir_name.lower()
        
        # Mapeo simple de nombres comunes a tipos
        type_mapping = {
            "dni": "dni",
            "contrato": "contrato",
            "contratos": "contrato",
            "formacion": "formacion",
            "formación": "formacion",
            "prl": "prl",
            "reconocimiento_medico": "reconocimiento_medico",
            "reconocimiento médico": "reconocimiento_medico",
            "reconocimientos": "reconocimiento_medico",
        }
        
        for key, doc_type in type_mapping.items():
            if key in dir_lower:
                return doc_type  # type: ignore
        
        return "otro"  # type: ignore



























