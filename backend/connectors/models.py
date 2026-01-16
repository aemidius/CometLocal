"""
Modelos de datos para el Connector SDK.

Define los tipos normalizados que usan todos los conectores:
- PendingRequirement: requisito pendiente del portal
- UploadResult: resultado de una subida
- RunContext: contexto de ejecución
"""

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any
from datetime import datetime
import hashlib


@dataclass
class PendingRequirement:
    """
    Requisito pendiente normalizado del portal.
    
    Representa un documento que el portal requiere subir.
    """
    id: str  # ID interno determinista (hash)
    subject_type: Literal["empresa", "trabajador"]
    doc_type_hint: str  # Texto del portal (ej "TC2", "PRL", "RECONOCIMIENTO")
    subject_id: Optional[str] = None  # DNI, CIF, nombre normalizado, etc.
    period: Optional[str] = None  # "YYYY-MM" si aplica
    due_date: Optional[str] = None  # "YYYY-MM-DD" si portal lo expone
    status: Literal["missing", "expired", "expiring", "requested"] = "missing"
    portal_meta: Dict[str, Any] = field(default_factory=dict)  # Metadata específica del portal
    
    @classmethod
    def create_id(cls, platform_id: str, subject_type: str, doc_type_hint: str, subject_id: Optional[str] = None, period: Optional[str] = None) -> str:
        """
        Genera un ID determinista para un requisito.
        
        Args:
            platform_id: ID de la plataforma (ej "egestiona")
            subject_type: "empresa" o "trabajador"
            doc_type_hint: Tipo de documento
            subject_id: ID del sujeto (opcional)
            period: Período (opcional)
        
        Returns:
            ID hash determinista
        """
        parts = [platform_id, subject_type, doc_type_hint]
        if subject_id:
            parts.append(subject_id)
        if period:
            parts.append(period)
        content = "|".join(parts)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class UploadResult:
    """
    Resultado de una subida de documento.
    """
    success: bool
    requirement_id: str
    uploaded_doc_id: Optional[str] = None  # ID del documento del repo usado
    portal_reference: Optional[str] = None  # ID/folio si existe en el portal
    evidence: Dict[str, str] = field(default_factory=dict)  # paths a screenshots/logs
    error: Optional[str] = None


@dataclass
class RunContext:
    """
    Contexto de ejecución de un conector.
    """
    run_id: str
    base_url: Optional[str] = None
    platform_id: str = ""
    tenant_id: Optional[str] = None  # "subplugin" por empresa/contrata
    headless: bool = True
    dry_run: bool = False  # Si True, no subir documentos
    timeouts: Dict[str, int] = field(default_factory=lambda: {
        "navigation": 30000,
        "action": 10000,
        "network_idle": 5000,
    })
    evidence_dir: Optional[str] = None
    
    @classmethod
    def create_run_id(cls) -> str:
        """Genera un ID único para una ejecución."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        import random
        suffix = f"{random.randint(1000, 9999)}"
        return f"CONN-{timestamp}-{suffix}"
