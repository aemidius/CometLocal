"""
Almacén de memoria persistente para trabajadores, empresas y plataformas.

v3.9.0: Gestiona la lectura y escritura de memoria persistente en formato JSON,
permitiendo al agente recordar información entre ejecuciones.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

from backend.shared.models import WorkerMemory, CompanyMemory, PlatformMemory

logger = logging.getLogger(__name__)


def _normalize_company_name(company_name: str) -> str:
    """
    Normaliza el nombre de una empresa para usarlo como nombre de archivo.
    
    v3.9.0: Convierte a lowercase y reemplaza espacios por guiones bajos.
    
    Args:
        company_name: Nombre de la empresa
        
    Returns:
        Nombre normalizado
    """
    # Convertir a lowercase
    normalized = company_name.lower()
    # Reemplazar espacios y caracteres especiales por guiones bajos
    normalized = re.sub(r'[^\w\-_]', '_', normalized)
    normalized = re.sub(r'[_\s]+', '_', normalized)
    # Eliminar guiones bajos al inicio y final
    normalized = normalized.strip('_')
    return normalized


class MemoryStore:
    """
    Almacén de memoria persistente.
    
    v3.9.0: Gestiona la lectura y escritura de memoria persistente para trabajadores,
    empresas y plataformas en formato JSON.
    """
    
    def __init__(self, base_dir: str):
        """
        Inicializa el almacén de memoria.
        
        Args:
            base_dir: Directorio base donde se almacenará la memoria
        """
        self.base_dir = Path(base_dir)
        self.workers_dir = self.base_dir / "workers"
        self.companies_dir = self.base_dir / "companies"
        self.platforms_dir = self.base_dir / "platforms"
        
        # Crear directorios si no existen
        try:
            self.workers_dir.mkdir(parents=True, exist_ok=True)
            self.companies_dir.mkdir(parents=True, exist_ok=True)
            self.platforms_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"[memory-store] Error al crear directorios: {e}")
    
    def load_worker(self, worker_id: str) -> Optional[WorkerMemory]:
        """
        Carga la memoria de un trabajador.
        
        Args:
            worker_id: ID del trabajador
            
        Returns:
            WorkerMemory si existe, None en caso contrario o si hay error
        """
        file_path = self.workers_dir / f"{worker_id}.json"
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convertir last_seen de string a datetime si existe
            if 'last_seen' in data and data['last_seen']:
                data['last_seen'] = datetime.fromisoformat(data['last_seen'])
            
            return WorkerMemory(**data)
        except Exception as e:
            logger.warning(f"[memory-store] Error al cargar memoria de trabajador {worker_id}: {e}")
            return None
    
    def save_worker(self, memory: WorkerMemory) -> None:
        """
        Guarda la memoria de un trabajador.
        
        Args:
            memory: WorkerMemory a guardar
        """
        file_path = self.workers_dir / f"{memory.worker_id}.json"
        
        try:
            # Convertir a dict y serializar datetime
            data = memory.model_dump()
            if data.get('last_seen') and isinstance(data['last_seen'], datetime):
                data['last_seen'] = data['last_seen'].isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[memory-store] Error al guardar memoria de trabajador {memory.worker_id}: {e}")
    
    def load_company(self, company_name: str, platform: Optional[str] = None) -> Optional[CompanyMemory]:
        """
        Carga la memoria de una empresa.
        
        Args:
            company_name: Nombre de la empresa
            platform: Plataforma opcional (para crear clave única)
            
        Returns:
            CompanyMemory si existe, None en caso contrario o si hay error
        """
        normalized_name = _normalize_company_name(company_name)
        if platform:
            # Si hay plataforma, incluirla en el nombre del archivo
            file_path = self.companies_dir / f"{normalized_name}_{_normalize_company_name(platform)}.json"
        else:
            file_path = self.companies_dir / f"{normalized_name}.json"
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convertir last_seen de string a datetime si existe
            if 'last_seen' in data and data['last_seen']:
                data['last_seen'] = datetime.fromisoformat(data['last_seen'])
            
            return CompanyMemory(**data)
        except Exception as e:
            logger.warning(f"[memory-store] Error al cargar memoria de empresa {company_name}: {e}")
            return None
    
    def save_company(self, memory: CompanyMemory) -> None:
        """
        Guarda la memoria de una empresa.
        
        Args:
            memory: CompanyMemory a guardar
        """
        normalized_name = _normalize_company_name(memory.company_name)
        if memory.platform:
            file_path = self.companies_dir / f"{normalized_name}_{_normalize_company_name(memory.platform)}.json"
        else:
            file_path = self.companies_dir / f"{normalized_name}.json"
        
        try:
            # Convertir a dict y serializar datetime
            data = memory.model_dump()
            if data.get('last_seen') and isinstance(data['last_seen'], datetime):
                data['last_seen'] = data['last_seen'].isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[memory-store] Error al guardar memoria de empresa {memory.company_name}: {e}")
    
    def load_platform(self, platform: str) -> Optional[PlatformMemory]:
        """
        Carga la memoria de una plataforma.
        
        Args:
            platform: Nombre de la plataforma
            
        Returns:
            PlatformMemory si existe, None en caso contrario o si hay error
        """
        normalized_name = _normalize_company_name(platform)
        file_path = self.platforms_dir / f"{normalized_name}.json"
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convertir last_seen de string a datetime si existe
            if 'last_seen' in data and data['last_seen']:
                data['last_seen'] = datetime.fromisoformat(data['last_seen'])
            
            return PlatformMemory(**data)
        except Exception as e:
            logger.warning(f"[memory-store] Error al cargar memoria de plataforma {platform}: {e}")
            return None
    
    def save_platform(self, memory: PlatformMemory) -> None:
        """
        Guarda la memoria de una plataforma.
        
        Args:
            memory: PlatformMemory a guardar
        """
        normalized_name = _normalize_company_name(memory.platform)
        file_path = self.platforms_dir / f"{normalized_name}.json"
        
        try:
            # Convertir a dict y serializar datetime
            data = memory.model_dump()
            if data.get('last_seen') and isinstance(data['last_seen'], datetime):
                data['last_seen'] = data['last_seen'].isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[memory-store] Error al guardar memoria de plataforma {memory.platform}: {e}")

