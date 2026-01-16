"""
Endpoints de seed para tests E2E.
Solo habilitados cuando E2E_SEED_ENABLED=1
"""

from __future__ import annotations

import os
import uuid
import json
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# SPRINT C2.5.2: Lock global para serializar operaciones de seed
# Usar threading.Lock porque FastAPI puede ejecutar handlers sync
SEED_LOCK = threading.Lock()


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
    NMonthsValidityConfigV1,
    DocumentScopeV1,
    ExtractedMetadataV1,
    DocumentStatusV1,
    PeriodKindV1,
    ValidityPolicyV1,
    ValidityModeV1,
    MonthlyValidityConfigV1,
    NMonthsValidityConfigV1,
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
    
    # SPRINT C2.5.2: Lock global para evitar condiciones de carrera
    with SEED_LOCK:
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
    
    # SPRINT C2.5.2: Lock global para evitar condiciones de carrera
    with SEED_LOCK:
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


class BasicRepositorySeedResponse(BaseModel):
    """Respuesta del seed básico de repositorio."""
    company_key: str
    person_key: str
    type_ids: list[str]
    doc_ids: list[str]
    period_keys: list[str]
    message: str


@router.post("/reset", response_model=dict)
async def seed_reset() -> dict:
    """
    Limpia datos E2E creados (docs, snapshots, jobs persistidos).
    Requiere E2E_SEED_ENABLED=1
    """
    check_seed_enabled()
    
    # SPRINT C2.5.2: Lock global para evitar condiciones de carrera
    with SEED_LOCK:
        store = DocumentRepositoryStoreV1()
        deleted_types = []
        deleted_docs = []
        deleted_snapshots = []
        deleted_jobs = []
        
        # 1. Limpiar tipos y documentos con prefijo E2E_
        types = store.list_types(include_inactive=True)
        for doc_type in types:
            if doc_type.type_id.startswith("E2E_"):
                try:
                    docs = store.list_documents(type_id=doc_type.type_id)
                    for doc in docs:
                        if doc.doc_id.startswith("E2E_"):
                            pdf_path = store._get_doc_pdf_path(doc.doc_id)
                            if pdf_path.exists():
                                pdf_path.unlink()
                            deleted_docs.append(doc.doc_id)
                    store.delete_type(doc_type.type_id)
                    deleted_types.append(doc_type.type_id)
                except Exception:
                    pass
        
        # 2. Limpiar snapshots E2E (docs/evidence/cae_snapshots/)
        snapshots_dir = Path(DATA_DIR) / "docs" / "evidence" / "cae_snapshots"
        if snapshots_dir.exists():
            for snapshot_file in snapshots_dir.glob("CAESNAP-*.json"):
                try:
                    # Verificar si es E2E (leer y verificar scope)
                    with open(snapshot_file, 'r', encoding='utf-8') as f:
                        snapshot_data = json.load(f)
                        if snapshot_data.get('scope', {}).get('company_key', '').startswith('E2E_') or \
                           snapshot_data.get('scope', {}).get('person_key', '').startswith('E2E_'):
                            snapshot_file.unlink()
                            deleted_snapshots.append(snapshot_file.name)
                except Exception:
                    pass
        
        # 3. Limpiar jobs E2E de data/cae_jobs.json
        jobs_file = Path(DATA_DIR) / "cae_jobs.json"
        if jobs_file.exists():
            try:
                with open(jobs_file, 'r', encoding='utf-8') as f:
                    jobs_data = json.load(f)
                
                # Filtrar jobs E2E (verificar scope en plan_id o job_id)
                jobs_to_keep = []
                for job_id, job_data in jobs_data.items():
                    # Si el job_id contiene E2E o el scope contiene E2E, eliminarlo
                    if 'E2E' not in job_id and 'E2E' not in str(job_data.get('scope', {})):
                        jobs_to_keep.append((job_id, job_data))
                    else:
                        deleted_jobs.append(job_id)
                
                # Reescribir solo los jobs que no son E2E
                if len(jobs_to_keep) < len(jobs_data):
                    with open(jobs_file, 'w', encoding='utf-8') as f:
                        json.dump(dict(jobs_to_keep), f, indent=2, default=str)
            except Exception:
                pass
        
        return {
            "deleted_types": deleted_types,
            "deleted_docs": deleted_docs,
            "deleted_snapshots": deleted_snapshots,
            "deleted_jobs": deleted_jobs,
            "message": f"Reset: {len(deleted_types)} types, {len(deleted_docs)} docs, {len(deleted_snapshots)} snapshots, {len(deleted_jobs)} jobs",
        }


@router.post("/basic_repository", response_model=BasicRepositorySeedResponse)
async def seed_basic_repository() -> BasicRepositorySeedResponse:
    """
    Crea un set mínimo determinista para tests E2E:
    - company_key/person_key (E2E)
    - 2-3 types
    - 3-5 docs con PDFs dummy
    - asegurar que el calendario tiene al menos 2 pendientes "missing"
    
    Requiere E2E_SEED_ENABLED=1
    """
    check_seed_enabled()
    
    # SPRINT C2.5.2: Lock global para evitar condiciones de carrera
    with SEED_LOCK:
        store = DocumentRepositoryStoreV1()
        run_id = str(uuid4())[:8]
    
    # IDs con prefijo E2E_
    company_key = f"E2E_COMPANY_{run_id}"
    person_key = f"E2E_PERSON_{run_id}"
    
    # Calcular periodos: crear documentos para periodos diferentes a los que aparecerán como "missing"
    today = date.today()
    current_period = today.strftime("%Y-%m")
    
    # Periodos que aparecerán como "missing" en el calendario
    missing_periods = [
        add_months_to_period(current_period, -1),
        add_months_to_period(current_period, -2),
    ]
    missing_periods = ensure_unique_periods(missing_periods)
    
    # Periodos con documentos (diferentes a missing_periods)
    periods_with_docs = [
        add_months_to_period(missing_periods[0], -3),
        add_months_to_period(missing_periods[1], -3),
        add_months_to_period(missing_periods[0], -4),  # Tercer documento
    ]
    periods_with_docs = ensure_unique_periods(periods_with_docs)
    
    # Crear 2-3 tipos
    type_ids = []
    doc_ids = []
    pdfs_dir = store.docs_dir
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    
    # SPRINT C2.3.1: Crear solo 1 tipo mensual con un solo sujeto para limitar períodos generados
    # El test espera máximo 24 períodos por tipo, así que solo creamos 1 tipo mensual
    for i in range(1):  # Solo crear 1 tipo mensual
        type_id = f"E2E_TYPE_{run_id}_{i}"
        type_ids.append(type_id)
        
        # Crear tipo mensual (genera períodos mensuales)
        doc_type = store.get_type(type_id)
        if not doc_type:
            doc_type = DocumentTypeV1(
                type_id=type_id,
                name=f"E2E Test Type {i+1}",
                description=f"Tipo de prueba E2E {i+1}",
                scope=DocumentScopeV1.worker,  # Solo worker para un solo sujeto
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
        
        # Crear documentos para este tipo
        for j, period_key in enumerate(periods_with_docs[:2]):
            doc_id = f"E2E_DOC_{run_id}_{i}_{j}"
            doc_ids.append(doc_id)
            
            # Crear PDF dummy
            pdf_path = pdfs_dir / f"{doc_id}.pdf"
            if not pdf_path.exists():
                pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 0\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
                pdf_path.write_bytes(pdf_content)
            
            sha256 = store.compute_file_hash(pdf_path)
            period_date = datetime.strptime(f"{period_key}-01", "%Y-%m-%d").date()
            
            extracted = ExtractedMetadataV1(
                issue_date=period_date,
                validity_start_date=period_date,
            )
            
            computed_validity = compute_validity(doc_type.validity_policy, extracted)
            
            doc = DocumentInstanceV1(
                doc_id=doc_id,
                file_name_original=f"e2e_test_{period_key}.pdf",
                stored_path=f"data/repository/docs/{doc_id}.pdf",
                sha256=sha256,
                type_id=type_id,
                scope=doc_type.scope,
                company_key=company_key if doc_type.scope == DocumentScopeV1.company else None,
                person_key=person_key if doc_type.scope == DocumentScopeV1.worker else None,
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
            
            store.save_document(doc)
        
        return BasicRepositorySeedResponse(
            company_key=company_key,
            person_key=person_key,
            type_ids=type_ids,
            doc_ids=doc_ids,
            period_keys=missing_periods,
            message=f"Created basic repository: {len(type_ids)} types, {len(doc_ids)} docs, {len(missing_periods)} missing periods",
        )


@router.post("/basic_cae_snapshot", response_model=dict)
async def seed_basic_cae_snapshot() -> dict:
    """
    Crea snapshot FAKE con 2 pending_items y devuelve snapshot_id.
    Requiere E2E_SEED_ENABLED=1
    """
    check_seed_enabled()
    
    # SPRINT C2.5.2: Lock global para evitar condiciones de carrera
    with SEED_LOCK:
        from backend.cae.coordination_routes import _create_fake_snapshot
        from backend.cae.coordination_models_v1 import CoordinationScopeV1
        
        # Crear scope básico
        scope = CoordinationScopeV1(
            platform_key="egestiona",
            company_key=f"E2E_COMPANY_{str(uuid4())[:8]}",
            person_key=f"E2E_PERSON_{str(uuid4())[:8]}",
        )
        
        # Crear snapshot FAKE con 2 items (modificar función para aceptar num_items)
        # Por ahora, crear directamente aquí
        snapshot_id = f"CAESNAP-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{str(uuid4())[:8]}"
        created_at = datetime.utcnow()
        
        from backend.cae.coordination_models_v1 import PlatformPendingItemV1, CoordinationSnapshotV1
        from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
        
        store = DocumentRepositoryStoreV1()
        e2e_types = [t for t in store.list_types(include_inactive=True) if t.type_id.startswith("E2E_")]
        
        pending_items = []
        for i in range(2):
            type_id = None
            type_alias_candidates = []
            if e2e_types and i < len(e2e_types):
                type_id = e2e_types[i].type_id
                type_alias_candidates = [type_id]
            else:
                type_alias_candidates = [f"E2E_MONTHLY_{i}", f"TEST_TYPE_{i+1}"]
            
            today = date.today()
            period_key = f"{today.year}-{today.month-i:02d}" if today.month > i else f"{today.year-1}-{12+i-today.month:02d}"
            
            item = PlatformPendingItemV1(
                platform_item_id=f"FAKE_ITEM_{i}",
                type_id=type_id,
                platform_type_label=f"Tipo Test {i+1}",
                type_alias_candidates=type_alias_candidates,
                company_key=scope.company_key or "TEDELAB",
                person_key=scope.person_key or "EMILIO",
                period_key=period_key,
                raw_label=f"Pendiente Test {i+1}",
                raw_metadata={"index": i, "fake": True},
                status="PENDING",
            )
            pending_items.append(item)
        
        snapshot = CoordinationSnapshotV1(
            snapshot_id=snapshot_id,
            created_at=created_at,
            scope=scope,
            platform={"label": scope.coordination_label or "FAKE", "client_code": "FAKE_CLIENT"},
            pending_items=pending_items,
            evidence_path=f"docs/evidence/cae_snapshots/{snapshot_id}.json",
        )
        
        # Guardar snapshot
        evidence_dir = Path(DATA_DIR).parent / "docs" / "evidence" / "cae_snapshots"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = evidence_dir / f"{snapshot_id}.json"
        
        snapshot_dict = snapshot.model_dump(exclude_none=True)
        snapshot_dict["created_at"] = snapshot.created_at.isoformat()
        
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_dict, f, indent=2, ensure_ascii=False)
        
        return {
            "snapshot_id": snapshot.snapshot_id,
            "created_at": snapshot.created_at.isoformat(),
            "pending_items_count": len(snapshot.pending_items),
            "message": f"Created FAKE snapshot {snapshot.snapshot_id} with {len(snapshot.pending_items)} items",
        }


class UploadPackSeedResponse(BaseModel):
    """Respuesta del seed de upload pack."""
    company_key: str
    person_key: str
    type_ids: dict[str, str]  # type_id -> name mapping
    doc_ids: list[str]
    message: str


@router.post("/upload_pack", response_model=UploadPackSeedResponse)
async def seed_upload_pack() -> UploadPackSeedResponse:
    """
    Crea tipos específicos para tests de upload con nombres exactos:
    - "Recibo Autónomos" (type_id: E2E_AUTONOMOS_RECEIPT)
    - TEST_RC_CERTIFICATE (con name visible coherente)
    - TEST_DATE_REQUIRED (con name visible coherente)
    
    También crea company_key="E2E_TEDELAB" y person_key="E2E_EMILIO".
    
    Requiere E2E_SEED_ENABLED=1
    """
    check_seed_enabled()
    
    # SPRINT C2.5.2: Lock global para evitar condiciones de carrera
    with SEED_LOCK:
        store = DocumentRepositoryStoreV1()
        pdfs_dir = store.docs_dir
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        
        # IDs fijos para determinismo
        company_key = "E2E_TEDELAB"
        person_key = "E2E_EMILIO"
        
        type_ids = {}
        doc_ids = []
        
        # 1. Crear tipo "Recibo Autónomos"
        autonomos_type_id = "E2E_AUTONOMOS_RECEIPT"
        autonomos_name = "Recibo Autónomos"
    
        if not store.get_type(autonomos_type_id):
            doc_type = DocumentTypeV1(
                type_id=autonomos_type_id,
                name=autonomos_name,
                description="Recibo de autónomos para tests E2E",
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
            store.create_type(doc_type)
        
        type_ids[autonomos_type_id] = autonomos_name
        
        # Crear 1 documento para este tipo
        doc_id_autonomos = f"E2E_DOC_AUTONOMOS_{str(uuid4())[:8]}"
        doc_ids.append(doc_id_autonomos)
        pdf_path = pdfs_dir / f"{doc_id_autonomos}.pdf"
        if not pdf_path.exists():
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 0\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
            pdf_path.write_bytes(pdf_content)
        
        sha256 = store.compute_file_hash(pdf_path)
        today = date.today()
        period_date = today.replace(day=1)
        
        extracted = ExtractedMetadataV1(
            issue_date=period_date,
            validity_start_date=period_date,
        )
        
        doc_type = store.get_type(autonomos_type_id)
        computed_validity = compute_validity(doc_type.validity_policy, extracted)
        
        doc = DocumentInstanceV1(
            doc_id=doc_id_autonomos,
            file_name_original=f"recibo_autonomos_{today.strftime('%Y-%m')}.pdf",
            stored_path=f"data/repository/docs/{doc_id_autonomos}.pdf",
            sha256=sha256,
            type_id=autonomos_type_id,
            scope=DocumentScopeV1.worker,
            company_key=None,
            person_key=person_key,
            extracted=extracted,
            computed_validity=computed_validity,
            period_kind=PeriodKindV1.MONTH,
            period_key=today.strftime("%Y-%m"),
            issued_at=period_date,
            needs_period=False,
            status=DocumentStatusV1.reviewed,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        store.save_document(doc)
        
        # 2. Crear tipo TEST_RC_CERTIFICATE (con n_months y period_kind NONE)
        rc_cert_type_id = "TEST_RC_CERTIFICATE"
        rc_cert_name = "Certificado RC"
        
        if not store.get_type(rc_cert_type_id):
            doc_type = DocumentTypeV1(
            type_id=rc_cert_type_id,
            name=rc_cert_name,
            description="Certificado RC cada 12 meses (no requiere periodo manual)",
            scope=DocumentScopeV1.company,
            active=True,
            validity_policy=ValidityPolicyV1(
                mode=ValidityModeV1.monthly,
                basis=ValidityBasisV1.issue_date,
                n_months=NMonthsValidityConfigV1(
                    n=12,
                    month_source="issue_date",
                    valid_from="period_start",
                    valid_to="period_end",
                    grace_days=0
                )
            ),
            validity_start_mode="issue_date",
            issue_date_required=True,
            required_fields=[],
            platform_aliases=[],
        )
            store.create_type(doc_type)
        
        type_ids[rc_cert_type_id] = rc_cert_name
        
        # Crear 1 documento para este tipo
        doc_id_rc = f"E2E_DOC_RC_{str(uuid4())[:8]}"
        doc_ids.append(doc_id_rc)
        pdf_path = pdfs_dir / f"{doc_id_rc}.pdf"
        if not pdf_path.exists():
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 0\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
            pdf_path.write_bytes(pdf_content)
        
        sha256 = store.compute_file_hash(pdf_path)
        
        extracted = ExtractedMetadataV1(
            issue_date=period_date,
            validity_start_date=period_date,
        )
        
        doc_type = store.get_type(rc_cert_type_id)
        computed_validity = compute_validity(doc_type.validity_policy, extracted)
        
        doc = DocumentInstanceV1(
            doc_id=doc_id_rc,
            file_name_original=f"certificado_rc_{today.strftime('%Y-%m')}.pdf",
            stored_path=f"data/repository/docs/{doc_id_rc}.pdf",
            sha256=sha256,
            type_id=rc_cert_type_id,
            scope=DocumentScopeV1.company,
            company_key=company_key,
            person_key=None,
            extracted=extracted,
            computed_validity=computed_validity,
            period_kind=PeriodKindV1.MONTH,
            period_key=today.strftime("%Y-%m"),
            issued_at=period_date,
            needs_period=False,
            status=DocumentStatusV1.reviewed,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        store.save_document(doc)
        
        # 3. Crear tipo TEST_DATE_REQUIRED (con n_months y issue_date_required)
        date_req_type_id = "TEST_DATE_REQUIRED"
        date_req_name = "Test Tipo con Fecha Requerida"
        
        if not store.get_type(date_req_type_id):
            doc_type = DocumentTypeV1(
            type_id=date_req_type_id,
            name=date_req_name,
            description="Tipo que requiere fecha de emisión",
            scope=DocumentScopeV1.company,
            active=True,
            validity_policy=ValidityPolicyV1(
                mode=ValidityModeV1.monthly,
                basis=ValidityBasisV1.issue_date,
                n_months=NMonthsValidityConfigV1(
                    n=12,
                    month_source="issue_date",
                    valid_from="period_start",
                    valid_to="period_end",
                    grace_days=0
                )
            ),
            validity_start_mode="issue_date",
            issue_date_required=True,
            required_fields=[],
            platform_aliases=[],
        )
            store.create_type(doc_type)
        
        type_ids[date_req_type_id] = date_req_name
        
        # Crear 1 documento para este tipo
        doc_id_date = f"E2E_DOC_DATE_{str(uuid4())[:8]}"
        doc_ids.append(doc_id_date)
        pdf_path = pdfs_dir / f"{doc_id_date}.pdf"
        if not pdf_path.exists():
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 0\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
            pdf_path.write_bytes(pdf_content)
        
        sha256 = store.compute_file_hash(pdf_path)
        
        extracted = ExtractedMetadataV1(
            issue_date=period_date,
            validity_start_date=period_date,
        )
        
        doc_type = store.get_type(date_req_type_id)
        computed_validity = compute_validity(doc_type.validity_policy, extracted)
        
        doc = DocumentInstanceV1(
            doc_id=doc_id_date,
            file_name_original=f"doc_fecha_{today.strftime('%Y-%m')}.pdf",
            stored_path=f"data/repository/docs/{doc_id_date}.pdf",
            sha256=sha256,
            type_id=date_req_type_id,
            scope=DocumentScopeV1.company,
            company_key=company_key,
            person_key=None,
            extracted=extracted,
            computed_validity=computed_validity,
            period_kind=PeriodKindV1.NONE,  # Sin periodo
            period_key=None,
            issued_at=period_date,
            needs_period=False,
            status=DocumentStatusV1.reviewed,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        store.save_document(doc)
        
        return UploadPackSeedResponse(
            company_key=company_key,
            person_key=person_key,
            type_ids=type_ids,
            doc_ids=doc_ids,
            message=f"Created upload pack: {len(type_ids)} types ({', '.join(type_ids.values())}), {len(doc_ids)} docs",
        )
