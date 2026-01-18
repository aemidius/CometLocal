"""
SPRINT C2.18A: Modelo de observabilidad determinista del matching.

MatchingDebugReportV1: Reporte estructurado que explica por qué un pending requirement
termina en NO_MATCH o tiene local_docs_considered=0.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class PrimaryReasonCode(str, Enum):
    """Códigos de razón primaria para NO_MATCH o local_docs_considered=0."""
    REPO_EMPTY = "REPO_EMPTY"
    DATA_DIR_MISMATCH = "DATA_DIR_MISMATCH"
    TYPE_FILTER_ZERO = "TYPE_FILTER_ZERO"
    SUBJECT_FILTER_ZERO = "SUBJECT_FILTER_ZERO"
    PERIOD_FILTER_ZERO = "PERIOD_FILTER_ZERO"
    CONFIDENCE_TOO_LOW = "CONFIDENCE_TOO_LOW"
    UNKNOWN = "UNKNOWN"


class PipelineStep(BaseModel):
    """Paso del pipeline de matching con contadores."""
    step_name: str = Field(..., description="Nombre estable del paso (ej: 'filter: type_id')")
    input_count: int = Field(..., description="Cantidad de documentos al inicio del paso")
    output_count: int = Field(..., description="Cantidad de documentos al final del paso")
    rule: Optional[str] = Field(None, description="Regla aplicada (ej: 'filter: type_id == T104_AUTONOMOS_RECEIPT')")
    dropped_sample: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Hasta 5 doc_ids descartados con reason"
    )


class CandidateTop(BaseModel):
    """Candidato top con score breakdown."""
    doc_id: str
    type_id: str
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    period_key: Optional[str] = None
    file_path: Optional[str] = Field(None, description="Ruta completa o basename del archivo")
    status: str
    score_breakdown: Optional[Dict[str, float]] = Field(
        None,
        description="Desglose de scores: alias_score, type_match, period_match, subject_match, final_confidence"
    )
    reject_reason: Optional[str] = Field(
        None,
        description="Razón de rechazo si no alcanzó threshold (ej: 'confidence_below_threshold')"
    )


class AppliedHint(BaseModel):
    """Hint aplicado durante el matching."""
    hint_id: str = Field(..., description="ID del hint")
    strength: str = Field(..., description="EXACT o SOFT")
    effect: str = Field(..., description="resolved, boosted, ignored")
    reason: Optional[str] = Field(None, description="Razón del efecto")


class MatchingOutcome(BaseModel):
    """Resultado final del matching."""
    decision: str = Field(..., description="NO_MATCH / REVIEW_REQUIRED / AUTO_UPLOAD")
    local_docs_considered: int = Field(..., description="Número final de documentos considerados")
    primary_reason_code: PrimaryReasonCode = Field(..., description="Código de razón primaria")
    human_hint: str = Field(..., description="Hint corto accionable para el usuario")
    applied_hints: List[AppliedHint] = Field(
        default_factory=list,
        description="Hints aplicados durante el matching (SPRINT C2.19A)"
    )


class MatchingDebugReportV1(BaseModel):
    """Reporte de debug determinista del matching."""
    
    meta: Dict[str, Any] = Field(..., description="Metadata del reporte")
    pipeline: List[PipelineStep] = Field(default_factory=list, description="Pasos del pipeline ordenados")
    candidates_top: List[CandidateTop] = Field(default_factory=list, description="Hasta N=5 candidatos top")
    outcome: MatchingOutcome = Field(..., description="Resultado final")
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
            Path: lambda v: str(v),
        }
    }
    
    @classmethod
    def create_empty(
        cls,
        data_dir_resolved: str,
        platform: str,
        company_key: str,
        person_key: Optional[str] = None,
        type_ids: Optional[List[str]] = None,
        period_key: Optional[str] = None,
        pending_label: Optional[str] = None,
        pending_text: Optional[str] = None,
    ) -> "MatchingDebugReportV1":
        """Crea un reporte vacío con metadata básica."""
        from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
        import os
        from pathlib import Path
        
        store = DocumentRepositoryStoreV1()
        all_docs = store.list_documents()  # Sin filtros
        all_types = store.list_types(include_inactive=False)
        active_types = store.list_types(include_inactive=True)
        
        # SPRINT C2.18A.1: Obtener data_dir_expected y source
        data_dir_expected = None
        data_dir_expected_source = None
        
        # Intentar obtener desde settings primero
        try:
            from backend.repository.settings_routes import load_settings
            settings = load_settings()
            if settings.repository_root_dir:
                # El repository_root_dir apunta al repo, el data_dir es el padre
                repo_root = Path(settings.repository_root_dir)
                # Si el repo_root termina en "repository", el data_dir es el padre
                # Si no, asumimos que repository_root_dir ya es el data_dir
                if repo_root.name == "repository":
                    expected = repo_root.parent
                else:
                    expected = repo_root
                data_dir_expected = str(expected.resolve())
                data_dir_expected_source = "settings.repository_root_dir"
        except Exception:
            pass
        
        # Si no hay settings, intentar desde variables de entorno
        if not data_dir_expected:
            env_cometlocal = os.getenv("COMETLOCAL_DATA_DIR")
            if env_cometlocal:
                data_dir_expected = str(Path(env_cometlocal).resolve())
                data_dir_expected_source = "ENV:COMETLOCAL_DATA_DIR"
            else:
                env_repo = os.getenv("REPOSITORY_DATA_DIR")
                if env_repo:
                    repo_path = Path(env_repo)
                    if not repo_path.is_absolute():
                        _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
                        repo_path = (_REPO_ROOT / repo_path).resolve()
                    else:
                        repo_path = repo_path.resolve()
                    data_dir_expected = str(repo_path)
                    data_dir_expected_source = "ENV:REPOSITORY_DATA_DIR"
                else:
                    # Fallback: usar default desde config.py (repo_root/data)
                    try:
                        from backend.config import DATA_DIR
                        data_dir_expected = str(Path(DATA_DIR).resolve())
                        data_dir_expected_source = "config.DATA_DIR (default)"
                    except Exception:
                        # Último fallback: calcular desde repo root
                        _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
                        default_data_dir = _REPO_ROOT / "data"
                        data_dir_expected = str(default_data_dir.resolve())
                        data_dir_expected_source = "default (calculated)"
        
        # SPRINT C2.18A.1: Self-check del data_dir
        data_dir_path = Path(data_dir_resolved)
        data_dir_exists = data_dir_path.exists() and data_dir_path.is_dir()
        data_dir_contents_sample = []
        if data_dir_exists:
            try:
                # Listar hasta 10 entradas (solo nombres)
                entries = list(data_dir_path.iterdir())[:10]
                data_dir_contents_sample = [entry.name for entry in entries]
            except Exception:
                pass
        
        from datetime import timezone
        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data_dir_resolved": data_dir_resolved,
            "data_dir_expected": data_dir_expected,  # SPRINT C2.18A.1
            "data_dir_expected_source": data_dir_expected_source,  # SPRINT C2.18A.1
            "data_dir_exists": data_dir_exists,  # SPRINT C2.18A.1
            "data_dir_contents_sample": data_dir_contents_sample,  # SPRINT C2.18A.1
            "repo_docs_total": len(all_docs),
            "repo_docs_loaded": len(all_docs),  # Por ahora igual, puede diferir si hay errores de lectura
            "types_total": len(active_types),
            "active_types_total": len(all_types),
            "request_context": {
                "platform": platform,
                "company_key": company_key,
                "person_key": person_key,
                "type_ids": type_ids or [],
                "period_key": period_key,
                "pending_label": pending_label,
                "pending_text": pending_text,
            }
        }
        
        return cls(
            meta=meta,
            pipeline=[],
            candidates_top=[],
            outcome=MatchingOutcome(
                decision="NO_MATCH",
                local_docs_considered=0,
                primary_reason_code=PrimaryReasonCode.UNKNOWN,
                human_hint="No se pudo determinar la causa"
            )
        )
