from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional, List
from enum import Enum

from pydantic import BaseModel, Field


class DocumentScopeV1(str, Enum):
    """Alcance del documento: empresa o trabajador."""
    company = "company"
    worker = "worker"


class ValidityBasisV1(str, Enum):
    """Base para calcular validez."""
    issue_date = "issue_date"
    name_date = "name_date"
    manual = "manual"


class ValidityModeV1(str, Enum):
    """Modo de validez."""
    monthly = "monthly"
    annual = "annual"
    fixed_end_date = "fixed_end_date"


class MonthlyValidityConfigV1(BaseModel):
    """Configuración para validez mensual."""
    month_source: Literal["issue_date", "name_date"] = Field(
        default="issue_date",
        description="Origen del mes para el período"
    )
    valid_from: Literal["period_start"] = Field(
        default="period_start",
        description="Inicio de validez"
    )
    valid_to: Literal["period_end"] = Field(
        default="period_end",
        description="Fin de validez"
    )
    grace_days: int = Field(
        default=0,
        ge=0,
        description="Días de gracia después del fin del período"
    )


class AnnualValidityConfigV1(BaseModel):
    """Configuración para validez anual."""
    months: int = Field(
        default=12,
        ge=1,
        description="Meses de validez desde la fecha base"
    )
    valid_from: Literal["issue_date"] = Field(
        default="issue_date",
        description="Inicio de validez"
    )
    valid_to: Literal["issue_date_plus_months"] = Field(
        default="issue_date_plus_months",
        description="Fin de validez"
    )


class FixedEndDateValidityConfigV1(BaseModel):
    """Configuración para validez con fecha fija."""
    valid_from: Literal["issue_date"] = Field(
        default="issue_date",
        description="Inicio de validez"
    )
    valid_to: Literal["manual_end_date"] = Field(
        default="manual_end_date",
        description="Fin de validez (requiere fecha manual)"
    )


class ValidityPolicyV1(BaseModel):
    """Política declarativa de validez (determinista)."""
    mode: ValidityModeV1 = Field(
        description="Modo de validez: monthly, annual, fixed_end_date"
    )
    basis: ValidityBasisV1 = Field(
        description="Base para calcular: issue_date, name_date, manual"
    )
    monthly: Optional[MonthlyValidityConfigV1] = Field(
        default=None,
        description="Configuración si mode=monthly"
    )
    annual: Optional[AnnualValidityConfigV1] = Field(
        default=None,
        description="Configuración si mode=annual"
    )
    fixed_end_date: Optional[FixedEndDateValidityConfigV1] = Field(
        default=None,
        description="Configuración si mode=fixed_end_date"
    )


class DocumentTypeV1(BaseModel):
    """Tipo de documento (editable por UI, persistido en JSON)."""
    type_id: str = Field(
        description="Identificador único del tipo (ej: T104_AUTONOMOS_RECEIPT)"
    )
    name: str = Field(
        description="Nombre legible del tipo"
    )
    description: str = Field(
        default="",
        description="Descripción opcional"
    )
    scope: DocumentScopeV1 = Field(
        description="Alcance: company o worker"
    )
    validity_policy: ValidityPolicyV1 = Field(
        description="Política de validez declarativa"
    )
    required_fields: List[str] = Field(
        default_factory=list,
        description="Campos requeridos (ej: ['valid_from', 'valid_to'])"
    )
    platform_aliases: List[str] = Field(
        default_factory=list,
        description="Aliases para matching con plataformas (ej: ['T104.0', 'recibo bancario'])"
    )
    active: bool = Field(
        default=True,
        description="Si está activo (desactivar en lugar de borrar)"
    )


class ExtractedMetadataV1(BaseModel):
    """Metadatos extraídos del documento."""
    issue_date: Optional[date] = Field(
        default=None,
        description="Fecha de emisión extraída"
    )
    name_date: Optional[date] = Field(
        default=None,
        description="Fecha parseada desde el nombre del archivo"
    )
    period_start: Optional[date] = Field(
        default=None,
        description="Inicio del período (si aplica)"
    )
    period_end: Optional[date] = Field(
        default=None,
        description="Fin del período (si aplica)"
    )


class ComputedValidityV1(BaseModel):
    """Validez calculada (determinista)."""
    valid_from: Optional[date] = Field(
        default=None,
        description="Fecha de inicio de validez"
    )
    valid_to: Optional[date] = Field(
        default=None,
        description="Fecha de fin de validez"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confianza en el cálculo (0..1)"
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Razones del cálculo (ej: ['parsed name_date 28-nov-25', 'monthly policy month_source=name_date'])"
    )


class DocumentStatusV1(str, Enum):
    """Estado del documento."""
    draft = "draft"
    reviewed = "reviewed"
    ready_to_submit = "ready_to_submit"
    submitted = "submitted"


class DocumentInstanceV1(BaseModel):
    """Instancia de documento (PDF + metadatos)."""
    doc_id: str = Field(
        description="UUID del documento"
    )
    file_name_original: str = Field(
        description="Nombre original del archivo"
    )
    stored_path: str = Field(
        description="Ruta relativa al PDF almacenado (data/repository/docs/<doc_id>.pdf)"
    )
    sha256: str = Field(
        description="Hash SHA256 del archivo"
    )
    type_id: str = Field(
        description="ID del tipo de documento"
    )
    scope: DocumentScopeV1 = Field(
        description="Alcance: company o worker"
    )
    company_key: Optional[str] = Field(
        default=None,
        description="Clave de empresa (si scope=company)"
    )
    person_key: Optional[str] = Field(
        default=None,
        description="Clave de persona (si scope=worker)"
    )
    extracted: ExtractedMetadataV1 = Field(
        default_factory=ExtractedMetadataV1,
        description="Metadatos extraídos"
    )
    computed_validity: ComputedValidityV1 = Field(
        default_factory=ComputedValidityV1,
        description="Validez calculada"
    )
    status: DocumentStatusV1 = Field(
        default=DocumentStatusV1.draft,
        description="Estado del documento"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Fecha de creación"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Fecha de última actualización"
    )


class SubmissionRuleV1(BaseModel):
    """Regla de envío (placeholder, solo storage básico por ahora)."""
    rule_id: str = Field(
        description="ID de la regla"
    )
    type_id: str = Field(
        description="ID del tipo de documento"
    )
    platform_key: str = Field(
        description="Clave de la plataforma destino"
    )
    active: bool = Field(
        default=True,
        description="Si está activa"
    )


class ValidityOverrideV1(BaseModel):
    """Override de validez (placeholder, solo storage básico por ahora)."""
    override_id: str = Field(
        description="ID del override"
    )
    doc_id: str = Field(
        description="ID del documento"
    )
    valid_from: Optional[date] = Field(
        default=None,
        description="Fecha de inicio override"
    )
    valid_to: Optional[date] = Field(
        default=None,
        description="Fecha de fin override"
    )
    reason: str = Field(
        default="",
        description="Razón del override"
    )



