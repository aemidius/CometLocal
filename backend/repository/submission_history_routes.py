from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from backend.repository.submission_history_store_v1 import SubmissionHistoryStoreV1
from backend.shared.document_repository_v1 import SubmissionRecordV1


router = APIRouter(
    prefix="/api/repository",
    tags=["submission_history"],
)


@router.get("/history", response_model=List[SubmissionRecordV1])
async def list_history(
    platform_key: Optional[str] = Query(None, description="Filtrar por plataforma"),
    coord_label: Optional[str] = Query(None, description="Filtrar por coordinación"),
    company_key: Optional[str] = Query(None, description="Filtrar por empresa"),
    person_key: Optional[str] = Query(None, description="Filtrar por persona"),
    doc_id: Optional[str] = Query(None, description="Filtrar por documento"),
    action: Optional[str] = Query(None, description="Filtrar por acción (planned, submitted, skipped, failed)"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
) -> List[SubmissionRecordV1]:
    """Lista el historial de envíos con filtros opcionales. Siempre devuelve un array (puede estar vacío)."""
    try:
        store = SubmissionHistoryStoreV1()
        records = store.list_records(
            platform_key=platform_key,
            coord_label=coord_label,
            company_key=company_key,
            person_key=person_key,
            doc_id=doc_id,
            action=action,
            limit=limit,
        )
        # Asegurar que siempre es una lista
        if not isinstance(records, list):
            return []
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer historial: {str(e)}")


@router.get("/history/{record_id}", response_model=SubmissionRecordV1)
async def get_history_record(record_id: str) -> SubmissionRecordV1:
    """Obtiene un registro de historial por ID."""
    store = SubmissionHistoryStoreV1()
    record = store.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return record




