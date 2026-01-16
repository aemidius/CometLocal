"""
Servicio para planificación de períodos esperados para documentos periódicos.

Genera listas de períodos esperados basándose en el tipo de documento y el sujeto,
y calcula el estado de cada período (AVAILABLE, MISSING, LATE).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from enum import Enum

from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    ValidityModeV1,
    PeriodKindV1,
    MonthlyValidityConfigV1,
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1


class PeriodStatusV1(str, Enum):
    """Estado de un período."""
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    LATE = "LATE"


class PeriodInfoV1:
    """Información de un período esperado."""
    
    def __init__(
        self,
        period_key: str,
        period_kind: PeriodKindV1,
        period_start: date,
        period_end: date,
        status: PeriodStatusV1,
        doc_id: Optional[str] = None,
        doc_file_name: Optional[str] = None,
        days_late: Optional[int] = None,
    ):
        self.period_key = period_key
        self.period_kind = period_kind
        self.period_start = period_start
        self.period_end = period_end
        self.status = status
        self.doc_id = doc_id
        self.doc_file_name = doc_file_name
        self.days_late = days_late
    
    def to_dict(self) -> dict:
        return {
            "period_key": self.period_key,
            "period_kind": self.period_kind.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "status": self.status.value,
            "doc_id": self.doc_id,
            "doc_file_name": self.doc_file_name,
            "days_late": self.days_late,
        }


class PeriodPlannerV1:
    """Planificador de períodos para documentos periódicos."""
    
    def __init__(self, store: DocumentRepositoryStoreV1):
        self.store = store
    
    def is_periodic_submission(self, doc_type: DocumentTypeV1) -> bool:
        """
        Determina si un tipo de documento es de "entrega por período" (mensual/trimestral/anual)
        vs "renovación" (cada N meses con N>1).
        
        Reglas:
        - TRUE si mode=monthly SIN n_months override (o con n_months.n=1): mensual real
        - TRUE si mode=annual: anual
        - FALSE si mode=monthly CON n_months.n > 1: renovación (ej: cada 12 meses)
        - FALSE si mode=fixed_end_date: no es periódico
        - FALSE si no tiene periodicidad clara
        
        Returns:
            True si es tipo "por período", False si es "renovación" o no periódico
        """
        policy = doc_type.validity_policy
        
        # Si tiene n_months override con N > 1, es renovación, NO periódico
        if policy.n_months and policy.n_months.n > 1:
            return False
        
        # Si mode=monthly sin n_months (o n_months.n=1), es mensual real
        if policy.mode == ValidityModeV1.monthly:
            return True
        
        # Si mode=annual, es anual
        if policy.mode == ValidityModeV1.annual:
            return True
        
        # Cualquier otro caso: no es periódico
        return False
    
    def get_period_kind_from_type(self, doc_type: DocumentTypeV1) -> PeriodKindV1:
        """
        Deriva period_kind del validity_policy del tipo.
        
        IMPORTANTE: Solo retorna MONTH/YEAR si is_periodic_submission() == True.
        Tipos de renovación (cada N meses, N>1) retornan NONE.
        """
        # Si no es periódico (es renovación o no tiene periodicidad), retornar NONE
        if not self.is_periodic_submission(doc_type):
            return PeriodKindV1.NONE
        
        # Si es periódico, determinar el kind
        if doc_type.validity_policy.mode == ValidityModeV1.monthly:
            return PeriodKindV1.MONTH
        elif doc_type.validity_policy.mode == ValidityModeV1.annual:
            return PeriodKindV1.YEAR
        else:
            return PeriodKindV1.NONE
    
    def generate_expected_periods(
        self,
        doc_type: DocumentTypeV1,
        months_back: int = 24,
        company_key: Optional[str] = None,
        person_key: Optional[str] = None,
    ) -> List[PeriodInfoV1]:
        """
        Genera lista de períodos esperados para un tipo de documento y sujeto.
        
        IMPORTANTE: Solo genera períodos para tipos "por período" (mensual/anual real).
        Tipos de "renovación" (cada N meses, N>1) retornan lista vacía.
        
        Args:
            doc_type: Tipo de documento
            months_back: Cuántos meses hacia atrás generar (default: 24)
            company_key: Clave de empresa (si scope=company)
            person_key: Clave de persona (si scope=worker)
        
        Returns:
            Lista de PeriodInfoV1 ordenada por period_key descendente (más reciente primero)
        """
        # Verificar que es tipo periódico (no renovación)
        if not self.is_periodic_submission(doc_type):
            # Tipo de renovación o no periódico: no generar períodos mensuales
            return []
        
        period_kind = self.get_period_kind_from_type(doc_type)
        
        if period_kind == PeriodKindV1.NONE:
            # No es periódico, retornar lista vacía
            return []
        
        # Obtener documentos existentes para este tipo y sujeto
        existing_docs = self.store.list_documents(
            type_id=doc_type.type_id,
            company_key=company_key,
            person_key=person_key
        )
        
        # Crear mapa de period_key -> doc
        docs_by_period: Dict[str, Tuple[str, str]] = {}  # period_key -> (doc_id, file_name)
        for doc in existing_docs:
            if doc.period_key:
                docs_by_period[doc.period_key] = (doc.doc_id, doc.file_name_original)
        
        # Generar períodos esperados
        today = date.today()
        periods: List[PeriodInfoV1] = []
        
        if period_kind == PeriodKindV1.MONTH:
            # Generar meses hacia atrás
            for i in range(months_back):
                target_date = today - timedelta(days=30 * i)
                period_key = f"{target_date.year}-{target_date.month:02d}"
                period_start = date(target_date.year, target_date.month, 1)
                # Último día del mes
                if target_date.month == 12:
                    period_end = date(target_date.year, 12, 31)
                else:
                    period_end = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
                
                # Determinar estado
                status = PeriodStatusV1.MISSING
                doc_id = None
                doc_file_name = None
                days_late = None
                
                if period_key in docs_by_period:
                    status = PeriodStatusV1.AVAILABLE
                    doc_id, doc_file_name = docs_by_period[period_key]
                else:
                    # Verificar si está tardío (después de period_end + grace_days)
                    grace_days = 0
                    if doc_type.validity_policy.monthly:
                        grace_days = doc_type.validity_policy.monthly.grace_days
                    
                    days_since_end = (today - period_end).days
                    if days_since_end > grace_days:
                        status = PeriodStatusV1.LATE
                        days_late = days_since_end - grace_days
                
                periods.append(PeriodInfoV1(
                    period_key=period_key,
                    period_kind=period_kind,
                    period_start=period_start,
                    period_end=period_end,
                    status=status,
                    doc_id=doc_id,
                    doc_file_name=doc_file_name,
                    days_late=days_late,
                ))
        
        elif period_kind == PeriodKindV1.YEAR:
            # Generar años hacia atrás
            for i in range(months_back // 12 + 1):
                target_year = today.year - i
                period_key = str(target_year)
                period_start = date(target_year, 1, 1)
                period_end = date(target_year, 12, 31)
                
                status = PeriodStatusV1.MISSING
                doc_id = None
                doc_file_name = None
                days_late = None
                
                if period_key in docs_by_period:
                    status = PeriodStatusV1.AVAILABLE
                    doc_id, doc_file_name = docs_by_period[period_key]
                else:
                    days_since_end = (today - period_end).days
                    if days_since_end > 0:
                        status = PeriodStatusV1.LATE
                        days_late = days_since_end
                
                periods.append(PeriodInfoV1(
                    period_key=period_key,
                    period_kind=period_kind,
                    period_start=period_start,
                    period_end=period_end,
                    status=status,
                    doc_id=doc_id,
                    doc_file_name=doc_file_name,
                    days_late=days_late,
                ))
        
        # Ordenar por period_key descendente (más reciente primero)
        periods.sort(key=lambda p: p.period_key, reverse=True)
        
        return periods
    
    def infer_period_key(
        self,
        doc_type: DocumentTypeV1,
        issue_date: Optional[date] = None,
        name_date: Optional[date] = None,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        Infiere period_key a partir de metadatos disponibles.
        
        Args:
            doc_type: Tipo de documento
            issue_date: Fecha de emisión
            name_date: Fecha extraída del nombre
            filename: Nombre del archivo
        
        Returns:
            period_key (YYYY-MM, YYYY, YYYY-Qn) o None si no se puede inferir
        """
        period_kind = self.get_period_kind_from_type(doc_type)
        
        if period_kind == PeriodKindV1.NONE:
            return None
        
        # Determinar fecha base según configuración
        date_source = None
        if doc_type.validity_policy.mode == ValidityModeV1.monthly:
            if doc_type.validity_policy.monthly:
                if doc_type.validity_policy.monthly.month_source == "issue_date":
                    date_source = issue_date
                elif doc_type.validity_policy.monthly.month_source == "name_date":
                    date_source = name_date
        
        # Fallback: usar issue_date o name_date si están disponibles
        if not date_source:
            date_source = issue_date or name_date
        
        # Si no hay fecha, intentar parsear del filename
        if not date_source and filename:
            # Intentar extraer fecha del filename (ej: "recibo_2023-05.pdf", "mayo_2023.pdf")
            import re
            # Buscar patrones YYYY-MM, YYYY-MM-DD, etc.
            date_match = re.search(r'(\d{4})-(\d{2})(?:-(\d{2}))?', filename)
            if date_match:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3)) if date_match.group(3) else 1
                date_source = date(year, month, day)
        
        if not date_source:
            return None
        
        # Generar period_key según period_kind
        if period_kind == PeriodKindV1.MONTH:
            return f"{date_source.year}-{date_source.month:02d}"
        elif period_kind == PeriodKindV1.YEAR:
            return str(date_source.year)
        elif period_kind == PeriodKindV1.QUARTER:
            quarter = (date_source.month - 1) // 3 + 1
            return f"{date_source.year}-Q{quarter}"
        
        return None

















