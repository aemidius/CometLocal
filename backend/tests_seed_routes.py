"""
Endpoints de seed para tests E2E.
Solo habilitados cuando E2E_SEED_ENABLED=1
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


def add_months_to_period(period_key: str, months: int) -> str:
    """
    Suma o resta meses a un periodo YYYY-MM.
    
    Args:
        period_key: Periodo en formato "YYYY-MM"
        months: Número de meses a sumar (positivo) o restar (negativo)
    
    Returns:
        Nuevo periodo en formato "YYYY-MM"
    """
    year, month = map(int, period_key.split("-"))
    
    # Calcular nuevo mes y año
    total_months = (year * 12) + month + months - 1  # -1 porque enero es mes 1
    new_year = total_months // 12
    new_month = (total_months % 12) + 1  # +1 para volver a 1-12
    
    return f"{new_year:04d}-{new_month:02d}"


def ensure_unique_periods(periods: list[str]) -> list[str]:
    """
    Asegura que los periodos sean únicos y distintos.
    Si hay duplicados, ajusta el segundo añadiendo 1 mes.
    """
    if len(set(periods)) == len(periods):
        return periods
    
    # Hay duplicados, ajustar
    unique_periods = []
    seen = set()
    for period in periods:
        if period in seen:
            # Si ya está visto, sumar 1 mes
            period = add_months_to_period(period, 1)
        unique_periods.append(period)
        seen.add(period)
    
    return unique_periods

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.validity_calculator_v1 import compute_validity
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentScopeV1,
    ExtractedMetadataV1,
    DocumentStatusV1,
    PeriodKindV1,
    ValidityPolicyV1,
    ValidityModeV1,
    MonthlyValidityConfigV1,
    ValidityBasisV1,
)
from backend.config import DATA_DIR


router = APIRouter(
    prefix="/api/test/seed",
    tags=["test-seed"],
)


def check_seed_enabled():
    """Verifica que el seed esté habilitado."""
    if os.getenv("E2E_SEED_ENABLED") != "1":
        raise HTTPException(status_code=404, detail="Seed endpoints disabled. Set E2E_SEED_ENABLED=1")


class SeedCAESelectionResponse(BaseModel):
    """Respuesta del seed de CAE selection."""
    type_id: str
    company_key: str
    person_key: str
    period_keys: list[str]
    doc_ids: list[str]
    message: str


@router.post("/cae_selection_v1", response_model=SeedCAESelectionResponse)
async def seed_cae_selection_v1() -> SeedCAESelectionResponse:
    """
    Crea datos deterministas para E2E de CAE selection v1.5.
    
    Requiere E2E_SEED_ENABLED=1
    """
    check_seed_enabled()
    
    store = DocumentRepositoryStoreV1()
    
    # IDs únicos con prefijo E2E_
    run_id = str(uuid4())[:8]
    type_id = f"E2E_MONTHLY_{run_id}"
    company_key = "TEDELAB"
    person_key = "EMILIO"
    
    # Calcular periodos: crear documentos para periodos diferentes a los que aparecerán como "missing"
    # IMPORTANTE: El calendario busca periodos hacia atrás (hasta 24 meses), así que usamos periodos recientes
    # Los documentos se crearán con period_key diferente a missing_periods para que el calendario
    # muestre esos periodos como "missing". doc_candidates los devolverá cuando no haya documentos
    # con el period_key solicitado (fallback sin filtrar por period_key).
    today = date.today()
    current_period = today.strftime("%Y-%m")
    
    # Periodos que aparecerán como "missing" en el calendario
    # Usar periodos recientes que están dentro del rango del calendario
    # El calendario busca hasta 24 meses hacia atrás, así que usamos mes anterior y mes anterior-1
    missing_periods = [
        add_months_to_period(current_period, -1),  # Mes anterior
        add_months_to_period(current_period, -2),  # Mes anterior-1
    ]
    
    # Asegurar que son distintos
    missing_periods = ensure_unique_periods(missing_periods)
    assert len(set(missing_periods)) == 2, f"missing_periods debe tener 2 periodos distintos, tiene: {missing_periods}"
    
    # v1.9.1: Crear documentos con period_key DIFERENTE a missing_periods para que el calendario los muestre como "missing"
    # Los documentos estarán disponibles vía doc_candidates con allow_period_fallback=true
    # El plan será READY porque create_plan_from_selection re-resuelve las fechas usando el period_key del pendiente
    periods_with_docs = [
        add_months_to_period(missing_periods[0], -3),  # 3 meses antes del primer missing
        add_months_to_period(missing_periods[1], -3),  # 3 meses antes del segundo missing
    ]
    # Asegurar que periods_with_docs son distintos y diferentes de missing_periods
    periods_with_docs = ensure_unique_periods(periods_with_docs)
    assert len(set(periods_with_docs)) == 2, f"periods_with_docs debe tener 2 periodos distintos, tiene: {periods_with_docs}"
    assert set(periods_with_docs).isdisjoint(set(missing_periods)), f"periods_with_docs no debe solaparse con missing_periods: {periods_with_docs} vs {missing_periods}"
    
    # 1. Crear o reusar tipo de documento mensual
    doc_type = store.get_type(type_id)
    if not doc_type:
        # Crear tipo mensual usando el modelo completo (igual que en test_cae_submission_planner.py)
        doc_type = DocumentTypeV1(
            type_id=type_id,
            name=f"E2E Test Monthly Type {run_id}",
            description=f"Tipo mensual para E2E test {run_id}",
            scope=DocumentScopeV1.worker,
            active=True,
            validity_policy=ValidityPolicyV1(
                mode=ValidityModeV1.monthly,
                basis=ValidityBasisV1.issue_date,
                monthly=MonthlyValidityConfigV1(
                    month_source="issue_date",
                    valid_from="period_start",
                    valid_to="period_end",
                    grace_days=0
                )
            ),
            validity_start_mode="issue_date",
            required_fields=[],
            platform_aliases=[],
        )
        doc_type = store.create_type(doc_type)
    
    # 2. Crear PDFs dummy y documentos para los periodos con docs
    # Usar store.docs_dir para asegurar que el PDF se crea en la misma ubicación que el store lo busca
    pdfs_dir = store.docs_dir
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    
    doc_ids = []
    for i, period_key in enumerate(periods_with_docs):
        doc_id = f"E2E_DOC_{run_id}_{i}"
        doc_ids.append(doc_id)
        
        # Crear PDF dummy mínimo
        pdf_path = pdfs_dir / f"{doc_id}.pdf"
        if not pdf_path.exists():
            # PDF mínimo válido (solo header básico)
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 0\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
            pdf_path.write_bytes(pdf_content)
        
        # Calcular hash
        sha256 = store.compute_file_hash(pdf_path)
        
        # Parsear fecha del periodo
        period_date = datetime.strptime(f"{period_key}-01", "%Y-%m-%d").date()
        
        # Crear metadatos extraídos
        extracted = ExtractedMetadataV1(
            issue_date=period_date,
            validity_start_date=period_date,
        )
        
        # Calcular validez
        computed_validity = compute_validity(doc_type.validity_policy, extracted)
        
        # Crear documento
        doc = DocumentInstanceV1(
            doc_id=doc_id,
            file_name_original=f"e2e_test_{period_key}.pdf",
            stored_path=f"data/repository/docs/{doc_id}.pdf",
            sha256=sha256,
            type_id=type_id,
            scope=DocumentScopeV1.worker,
            company_key=company_key,
            person_key=person_key,
            extracted=extracted,
            computed_validity=computed_validity,
            period_kind=PeriodKindV1.MONTH,
            period_key=period_key,
            issued_at=period_date,
            needs_period=False,
            status=DocumentStatusV1.reviewed,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        # Guardar documento
        store.save_document(doc)
    
    # 3. NOTA v1.9.1: Los documentos se crean con period_key DIFERENTE a missing_periods.
    # Esto asegura que el calendario muestre missing_periods como "missing".
    # doc_candidates con allow_period_fallback=true devolverá estos documentos.
    # create_plan_from_selection re-resolverá las fechas usando el period_key del pendiente,
    # permitiendo que el plan sea READY.
    
    return SeedCAESelectionResponse(
        type_id=type_id,
        company_key=company_key,
        person_key=person_key,
        period_keys=missing_periods[:2],  # Los 2 periodos que deberían aparecer como missing
        doc_ids=doc_ids,  # IDs de documentos que estarán disponibles como candidatos (con period_key diferente, vía fallback)
        message=f"Created type {type_id} with {len(doc_ids)} documents for periods {periods_with_docs[0]} and {periods_with_docs[1]}. Missing periods (for selection): {missing_periods[0]} and {missing_periods[1]}. Documents have different period_key to ensure calendar shows missing periods.",
    )


@router.post("/cleanup")
async def cleanup_seed_data():
    """
    Limpia datos de seed E2E (opcional).
    Requiere E2E_SEED_ENABLED=1
    """
    check_seed_enabled()
    
    store = DocumentRepositoryStoreV1()
    
    # Buscar y eliminar tipos y documentos con prefijo E2E_
    types = store.list_types(include_inactive=True)
    deleted_types = []
    deleted_docs = []
    
    for doc_type in types:
        if doc_type.type_id.startswith("E2E_"):
            try:
                # Buscar documentos de este tipo
                docs = store.list_documents(type_id=doc_type.type_id)
                for doc in docs:
                    if doc.doc_id.startswith("E2E_"):
                        # Eliminar PDF
                        pdf_path = store._get_doc_pdf_path(doc.doc_id)
                        if pdf_path.exists():
                            pdf_path.unlink()
                        deleted_docs.append(doc.doc_id)
                
                # Eliminar tipo
                store.delete_type(doc_type.type_id)
                deleted_types.append(doc_type.type_id)
            except Exception as e:
                # Continuar aunque falle alguno
                pass
    
    return {
        "deleted_types": deleted_types,
        "deleted_docs": deleted_docs,
        "message": f"Cleaned up {len(deleted_types)} types and {len(deleted_docs)} documents",
    }
