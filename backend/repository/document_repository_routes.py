from __future__ import annotations

import shutil
import json
import re
import zipfile
import io
from pathlib import Path
from uuid import uuid4
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Response
from pydantic import BaseModel, field_validator
from typing import Optional, List, Union, Any

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.date_parser_v1 import parse_date_from_filename
from backend.repository.validity_calculator_v1 import compute_validity
from backend.repository.period_planner_v1 import PeriodPlannerV1, PeriodInfoV1
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentScopeV1,
    ExtractedMetadataV1,
    DocumentStatusV1,
    ValidityOverrideV1,
    PeriodKindV1,
)


router = APIRouter(
    prefix="/api/repository",
    tags=["repository"],
)


# ========== TIPOS DE DOCUMENTO ==========

class TypesListResponse(BaseModel):
    """Respuesta paginada para listado de tipos."""
    items: List[DocumentTypeV1]
    total: int
    page: int
    page_size: int


@router.get("/types", response_model=Union[List[DocumentTypeV1], TypesListResponse])
async def list_types(
    include_inactive: bool = False,
    query: Optional[str] = None,
    period: Optional[str] = None,  # "monthly", "annual", "quarter", "none"
    scope: Optional[str] = None,  # "worker", "company"
    active: Optional[bool] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    sort: Optional[str] = None,  # "name", "type_id", "period", "relevance"
) -> Union[List[DocumentTypeV1], TypesListResponse]:
    """
    Lista tipos de documento con filtros avanzados y paginación.
    
    Si se proporcionan page/page_size, devuelve TypesListResponse.
    Si no, devuelve List[DocumentTypeV1] (compatibilidad hacia atrás).
    """
    try:
        store = DocumentRepositoryStoreV1()
        types = store.list_types(include_inactive=True)  # Traer todos y filtrar después
        
        # Filtros
        if active is not None:
            types = [t for t in types if t.active == active]
        elif not include_inactive:
            types = [t for t in types if t.active]
        
        if scope:
            types = [t for t in types if t.scope.value == scope]
        
        if period:
            period_map = {
                "monthly": "monthly",
                "annual": "annual",
                "quarter": None,  # No existe en ValidityModeV1, pero podemos detectarlo
                "none": "fixed_end_date"  # Aproximación
            }
            if period in period_map:
                target_mode = period_map[period]
                if target_mode:
                    types = [t for t in types if t.validity_policy.mode.value == target_mode]
                elif period == "quarter":
                    # No hay modo quarter, filtrar por configuración especial si existe
                    pass  # Por ahora no filtramos quarter
        
        if query:
            query_lower = query.lower()
            filtered = []
            for t in types:
                # Buscar en nombre, type_id, aliases
                if (query_lower in t.name.lower() or 
                    query_lower in t.type_id.lower() or
                    any(query_lower in alias.lower() for alias in t.platform_aliases)):
                    filtered.append(t)
            types = filtered
        
        # Ordenación
        if sort == "name":
            types.sort(key=lambda t: t.name.lower())
        elif sort == "type_id":
            types.sort(key=lambda t: t.type_id)
        elif sort == "period":
            types.sort(key=lambda t: t.validity_policy.mode.value)
        elif sort == "relevance" and query:
            # Ordenar por relevancia (más matches primero)
            def relevance_score(t: DocumentTypeV1) -> int:
                score = 0
                query_lower = query.lower()
                if query_lower in t.type_id.lower():
                    score += 10
                if query_lower in t.name.lower():
                    score += 5
                for alias in t.platform_aliases:
                    if query_lower in alias.lower():
                        score += 3
                return -score  # Negativo para orden descendente
            types.sort(key=relevance_score)
        else:
            # Orden por defecto: nombre
            types.sort(key=lambda t: t.name.lower())
        
        # Paginación
        total = len(types)
        if page is not None and page_size is not None:
            start = (page - 1) * page_size
            end = start + page_size
            paginated = types[start:end]
            return TypesListResponse(
                items=paginated,
                total=total,
                page=page,
                page_size=page_size
            )
        
        # Sin paginación: devolver lista simple (compatibilidad)
        if not isinstance(types, list):
            return []
        return types
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Error al leer tipos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")


@router.get("/types/{type_id}", response_model=DocumentTypeV1)
async def get_type(type_id: str) -> DocumentTypeV1:
    """Obtiene un tipo por ID."""
    store = DocumentRepositoryStoreV1()
    doc_type = store.get_type(type_id)
    if not doc_type:
        raise HTTPException(status_code=404, detail=f"Type {type_id} not found")
    return doc_type


@router.post("/types", response_model=DocumentTypeV1)
async def create_type(doc_type: DocumentTypeV1) -> DocumentTypeV1:
    """Crea un nuevo tipo de documento."""
    store = DocumentRepositoryStoreV1()
    try:
        return store.create_type(doc_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/types/{type_id}", response_model=DocumentTypeV1)
async def update_type(type_id: str, doc_type: DocumentTypeV1) -> DocumentTypeV1:
    """Actualiza un tipo existente. El type_id no se puede cambiar."""
    store = DocumentRepositoryStoreV1()
    try:
        # Asegurar que el type_id del body coincide con el de la URL
        # Si no coincide, usar el de la URL (el type_id no se puede cambiar)
        if doc_type.type_id != type_id:
            # Crear nuevo objeto con el type_id correcto
            doc_type_dict = doc_type.model_dump()
            doc_type_dict['type_id'] = type_id
            doc_type = DocumentTypeV1(**doc_type_dict)
        return store.update_type(type_id, doc_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DuplicateTypeRequest(BaseModel):
    new_type_id: Optional[str] = None
    new_name: Optional[str] = None


@router.post("/types/{type_id}/duplicate", response_model=DocumentTypeV1)
async def duplicate_type(
    type_id: str,
    request: DuplicateTypeRequest
) -> DocumentTypeV1:
    """Duplica un tipo con nuevo ID."""
    store = DocumentRepositoryStoreV1()
    try:
        # Si no se proporciona new_type_id, generar uno automáticamente
        new_type_id = request.new_type_id
        if not new_type_id:
            new_type_id = store._generate_unique_type_id(type_id)
        return store.duplicate_type(type_id, new_type_id, request.new_name)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "already exists" in error_msg.lower():
            raise HTTPException(status_code=409, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        # Log error para debugging
        import traceback
        print(f"Error in duplicate_type: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/types/{type_id}")
async def delete_type(type_id: str) -> dict:
    """Elimina un tipo (hard delete)."""
    store = DocumentRepositoryStoreV1()
    try:
        store.delete_type(type_id)
        return {"status": "ok", "message": f"Type {type_id} deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== DOCUMENTOS ==========

@router.post("/docs/upload", response_model=DocumentInstanceV1)
async def upload_document(
    file: UploadFile = File(...),
    type_id: str = Form(...),
    scope: str = Form(...),
    company_key: Optional[str] = Form(None),
    person_key: Optional[str] = Form(None),
    period_key: Optional[str] = Form(None),
    issue_date: Optional[str] = Form(None),
    validity_start_date: Optional[str] = Form(None),
) -> DocumentInstanceV1:
    """
    Sube un PDF al repositorio y lo asocia a un tipo + sujeto.
    
    - file: PDF a subir
    - type_id: ID del tipo de documento
    - scope: "company" o "worker"
    - company_key: Clave de empresa (si scope=company)
    - person_key: Clave de persona (si scope=worker)
    """
    store = DocumentRepositoryStoreV1()
    
    # Validar tipo
    doc_type = store.get_type(type_id)
    if not doc_type:
        raise HTTPException(status_code=404, detail=f"Type {type_id} not found")
    
    if not doc_type.active:
        raise HTTPException(status_code=400, detail=f"Type {type_id} is inactive")
    
    # Validar scope
    if scope != doc_type.scope:
        raise HTTPException(
            status_code=400,
            detail=f"Type {type_id} requires scope={doc_type.scope}, got {scope}"
        )
    
    # Validar sujeto según scope (reglas estrictas)
    if scope == "company":
        if not company_key:
            raise HTTPException(status_code=400, detail="company_key required for scope=company")
        if person_key:
            raise HTTPException(status_code=400, detail="person_key must be null for scope=company")
    elif scope == "worker":
        if not company_key:
            raise HTTPException(status_code=400, detail="company_key required for scope=worker")
        if not person_key:
            raise HTTPException(status_code=400, detail="person_key required for scope=worker")
    
    # Validar que es PDF
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Generar doc_id
    doc_id = str(uuid4())
    
    # Guardar archivo temporalmente
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = Path(tmp_file.name)
    
    try:
        # Calcular hash
        sha256 = store.compute_file_hash(tmp_path)
        
        # Copiar al repositorio
        stored_path_rel = f"data/repository/docs/{doc_id}.pdf"
        store.store_pdf(tmp_path, doc_id)
        
        # Parsear fecha desde nombre
        name_date, name_date_confidence = parse_date_from_filename(file.filename)
        
        # Parsear issue_date si viene en el form
        parsed_issue_date = None
        if issue_date:
            try:
                parsed_issue_date = datetime.strptime(issue_date, "%Y-%m-%d").date()
            except ValueError:
                pass  # Si no se puede parsear, usar None
        
        # Resolver validity_start_date según el modo del tipo
        parsed_validity_start_date = None
        validity_start_mode = getattr(doc_type, 'validity_start_mode', 'issue_date')
        
        if validity_start_mode == "issue_date":
            # Inicio de vigencia = issue_date
            parsed_validity_start_date = parsed_issue_date or name_date
        elif validity_start_mode == "manual":
            # Inicio de vigencia viene del form (obligatorio)
            if validity_start_date:
                try:
                    parsed_validity_start_date = datetime.strptime(validity_start_date, "%Y-%m-%d").date()
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail="validity_start_date debe estar en formato YYYY-MM-DD"
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="validity_start_date es obligatorio cuando validity_start_mode=manual"
                )
        
        # Crear metadatos extraídos
        extracted = ExtractedMetadataV1(
            issue_date=parsed_issue_date,
            name_date=name_date,
            validity_start_date=parsed_validity_start_date
        )
        
        # Calcular validez
        computed_validity = compute_validity(doc_type.validity_policy, extracted)
        
        # Inferir period_key si el tipo es periódico
        planner = PeriodPlannerV1(store)
        period_kind = planner.get_period_kind_from_type(doc_type)
        period_key_param = period_key  # Guardar el parámetro del form
        needs_period = False
        
        if period_kind != PeriodKindV1.NONE:
            # Use provided period_key or try to infer
            if not period_key_param:
                # Usar validity_start_date como fecha base para calcular periodo si está disponible
                base_date = extracted.validity_start_date or extracted.issue_date or name_date
                period_key_param = planner.infer_period_key(
                    doc_type=doc_type,
                    issue_date=base_date,  # Usar validity_start_date como base
                    name_date=name_date,
                    filename=file.filename or "unknown.pdf",
                )
            if not period_key_param:
                needs_period = True
        
        # Crear instancia de documento
        doc = DocumentInstanceV1(
            doc_id=doc_id,
            file_name_original=file.filename or "unknown.pdf",
            stored_path=stored_path_rel,
            sha256=sha256,
            type_id=type_id,
            scope=DocumentScopeV1(scope),
            company_key=company_key,
            person_key=person_key,
            extracted=extracted,
            computed_validity=computed_validity,
            period_kind=period_kind,
            period_key=period_key_param,
            issued_at=extracted.issue_date or name_date,
            needs_period=needs_period,
            status=DocumentStatusV1.draft,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Guardar
        store.save_document(doc)
        
        return doc
    
    finally:
        # Limpiar archivo temporal
        tmp_path.unlink(missing_ok=True)


@router.get("/docs")
async def list_documents(
    type_id: Optional[str] = None,
    scope: Optional[str] = None,
    status: Optional[str] = None,
    validity_status: Optional[str] = None,  # VALID, EXPIRING_SOON, EXPIRED
    limit: Optional[int] = None,  # SPRINT C2.10.1: Límite de documentos a retornar
    sort: Optional[str] = None  # SPRINT C2.10.1: Ordenación ('date_desc', 'date_asc')
) -> List[dict]:
    """
    Lista todos los documentos (con filtros opcionales).
    Incluye estado de validez calculado (validity_status, validity_end_date, days_until_expiry).
    SPRINT C2.10.1: Soporta limit y sort para optimizar carga en UI.
    """
    from backend.repository.document_status_calculator_v1 import calculate_document_status
    
    try:
        store = DocumentRepositoryStoreV1()
        docs = store.list_documents(type_id=type_id, scope=scope, status=status)
        # Asegurar que siempre es una lista
        if not isinstance(docs, list):
            return []
        
        # SPRINT C2.10.1: Aplicar ordenación antes de calcular validez (más eficiente)
        if sort == 'date_asc':
            docs = sorted(docs, key=lambda d: d.created_at)
        elif sort == 'date_desc' or sort is None:
            # Por defecto: más recientes primero (ya viene ordenado así de list_documents)
            pass
        
        # SPRINT C2.10.1: Aplicar limit ANTES de calcular validez (optimización)
        if limit is not None and limit > 0:
            docs = docs[:limit]
        
        # Calcular estado de validez para cada documento
        result = []
        for doc in docs:
            doc_dict = doc.model_dump() if hasattr(doc, 'model_dump') else doc.dict()
            
            # Calcular estado de validez (con tipo de documento para cálculo correcto)
            doc_type = store.get_type(doc.type_id)
            validity_status_calc, validity_end_date, days_until_expiry, base_date, base_reason = calculate_document_status(
                doc, doc_type=doc_type
            )
            
            # Añadir campos calculados
            doc_dict['validity_status'] = validity_status_calc
            doc_dict['validity_end_date'] = validity_end_date.isoformat() if validity_end_date else None
            doc_dict['days_until_expiry'] = days_until_expiry
            # Campos de debug (opcional, se pueden quitar después)
            doc_dict['validity_base_date'] = base_date.isoformat() if base_date else None
            doc_dict['validity_base_reason'] = base_reason
            
            # Filtrar por validity_status si se especifica
            if validity_status and validity_status_calc != validity_status:
                continue
            
            result.append(doc_dict)
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Error al leer documentos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")


@router.get("/docs/pending")
async def get_pending_documents(
    months_ahead: int = 3,  # Meses hacia adelante para considerar "expira pronto"
    max_months_back: int = 24  # Máximo de meses hacia atrás para generar períodos faltantes
) -> dict:
    """
    Obtiene documentos pendientes, expirados y próximos a expirar.
    
    IMPORTANTE: Esta ruta debe ir ANTES de /docs/{doc_id} para evitar conflictos de routing.
    
    Retorna:
    - expired: Documentos expirados
    - expiring_soon: Documentos que expiran pronto (dentro de months_ahead meses)
    - missing: Períodos esperados sin documento (agrupados por tipo y sujeto)
    """
    import time
    import logging
    logger = logging.getLogger(__name__)
    
    t0 = time.time()
    from backend.repository.document_status_calculator_v1 import calculate_document_status, DocumentValidityStatus
    from backend.repository.period_planner_v1 import PeriodPlannerV1
    
    try:
        store = DocumentRepositoryStoreV1()
        planner = PeriodPlannerV1(store)
        
        t1 = time.time()
        # Obtener todos los documentos (usar la misma fuente que /docs)
        all_docs = store.list_documents()
        if not isinstance(all_docs, list):
            all_docs = []
        
        t2 = time.time()
        # SPRINT C2.9.24: Cachear tipos de documentos para evitar llamadas repetidas
        types_cache = {}
        all_types = store.list_types()
        for doc_type in all_types:
            types_cache[doc_type.type_id] = doc_type
        
        # Calcular estados usando la MISMA función que /docs
        expired = []
        expiring_soon = []
        
        # SPRINT C2.9.24: Optimización: usar computed_validity cuando esté disponible para evitar recálculo
        today = date.today()
        expiring_soon_threshold_days = months_ahead * 30
        
        for doc in all_docs:
            # Intentar usar computed_validity si existe y es reciente
            status = None
            validity_end_date = None
            days_until_expiry = None
            
            if doc.computed_validity and doc.computed_validity.valid_to:
                # Usar computed_validity existente (ya calculado)
                validity_end_date = doc.computed_validity.valid_to
                days_until_expiry = (validity_end_date - today).days
                
                if days_until_expiry < 0:
                    status = DocumentValidityStatus.EXPIRED
                elif days_until_expiry <= expiring_soon_threshold_days:
                    status = DocumentValidityStatus.EXPIRING_SOON
                else:
                    status = DocumentValidityStatus.VALID
            else:
                # Recalcular solo si no hay computed_validity
                doc_type = types_cache.get(doc.type_id)
                if not doc_type:
                    doc_type = store.get_type(doc.type_id)
                    if doc_type:
                        types_cache[doc.type_id] = doc_type
                
                status, validity_end_date, days_until_expiry, base_date, base_reason = calculate_document_status(
                    doc,
                    doc_type=doc_type,
                    expiring_soon_threshold_days=expiring_soon_threshold_days
                )
            
            doc_dict = doc.model_dump() if hasattr(doc, 'model_dump') else doc.dict()
            doc_dict['validity_status'] = status
            doc_dict['validity_end_date'] = validity_end_date.isoformat() if validity_end_date else None
            doc_dict['days_until_expiry'] = days_until_expiry
            
            # Clasificar usando el mismo enum
            if status == DocumentValidityStatus.EXPIRED:
                expired.append(doc_dict)
            elif status == DocumentValidityStatus.EXPIRING_SOON:
                expiring_soon.append(doc_dict)
        
        # Ordenar por fecha de caducidad
        expired.sort(key=lambda d: d.get('validity_end_date') or '9999-12-31')
        expiring_soon.sort(key=lambda d: d.get('validity_end_date') or '9999-12-31')
        
        t3 = time.time()
        # Obtener tipos periódicos y generar períodos faltantes
        types = store.list_types()
        missing = []
        
        for doc_type in types:
            period_kind = planner.get_period_kind_from_type(doc_type)
            if period_kind.value == 'NONE':
                continue  # Solo tipos periódicos
            
            # Obtener sujetos únicos de documentos existentes de este tipo
            type_docs = [d for d in all_docs if d.type_id == doc_type.type_id]
            subjects = set()
            for doc in type_docs:
                if doc.scope.value == 'worker' and doc.person_key:
                    subjects.add(('worker', doc.company_key, doc.person_key))
                elif doc.scope.value == 'company' and doc.company_key:
                    subjects.add(('company', doc.company_key, None))
            
            # Para cada sujeto, verificar períodos faltantes
            for scope, company_key, person_key in subjects:
                periods = planner.generate_expected_periods(
                    doc_type=doc_type,
                    months_back=max_months_back,
                    company_key=company_key,
                    person_key=person_key
                )
                
                for period in periods:
                    if period.status.value == 'MISSING' or period.status.value == 'LATE':
                        missing.append({
                            'type_id': doc_type.type_id,
                            'type_name': doc_type.name,
                            'scope': scope,
                            'company_key': company_key,
                            'person_key': person_key,
                            'period_key': period.period_key,
                            'period_start': period.period_start.isoformat() if period.period_start else None,
                            'period_end': period.period_end.isoformat() if period.period_end else None,
                            'status': period.status.value,
                            'days_late': period.days_late if hasattr(period, 'days_late') else None
                        })
        
        t4 = time.time()
        ms_total = int((t4 - t0) * 1000)
        ms_read = int((t2 - t1) * 1000)
        ms_calc = int((t3 - t2) * 1000)
        ms_missing = int((t4 - t3) * 1000)
        
        # SPRINT C2.9.24: Log de timing (usar print para asegurar que se vea)
        print(f"[PENDING] ms_total={ms_total}, ms_read={ms_read}, ms_calc={ms_calc}, ms_missing={ms_missing}, "
              f"counts=docs={len(all_docs)}, expired={len(expired)}, expiring={len(expiring_soon)}, missing={len(missing)}")
        
        return {
            'expired': expired,
            'expiring_soon': expiring_soon,
            'missing': missing
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener documentos pendientes: {str(e)}")


@router.get("/docs/{doc_id}", response_model=DocumentInstanceV1)
async def get_document(doc_id: str) -> DocumentInstanceV1:
    """Obtiene un documento por ID."""
    store = DocumentRepositoryStoreV1()
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return doc


@router.get("/docs/{doc_id}/pdf")
async def get_document_pdf(doc_id: str):
    """Sirve el PDF de un documento."""
    from fastapi.responses import FileResponse
    import logging
    
    logger = logging.getLogger(__name__)
    
    store = DocumentRepositoryStoreV1()
    
    # Verificar que el documento existe
    doc = store.get_document(doc_id)
    if not doc:
        logger.warning(f"Document {doc_id} not found in store")
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    
    # Intentar usar stored_path del documento si existe, sino usar la ruta estándar
    pdf_path = None
    if hasattr(doc, 'stored_path') and doc.stored_path:
        # stored_path puede ser relativo o absoluto
        stored_path = Path(doc.stored_path)
        if stored_path.is_absolute():
            pdf_path = stored_path
        else:
            # Si es relativo, intentar desde base_dir
            pdf_path = Path(store.base_dir) / stored_path
    else:
        # Fallback a ruta estándar
        pdf_path = store._get_doc_pdf_path(doc_id)
    
    logger.info(f"Looking for PDF at: {pdf_path}")
    
    # Verificar que el archivo existe
    if not pdf_path.exists():
        # Intentar también la ruta estándar como fallback
        fallback_path = store._get_doc_pdf_path(doc_id)
        logger.info(f"Primary path not found, trying fallback: {fallback_path}")
        if fallback_path.exists():
            pdf_path = fallback_path
        else:
            logger.error(f"PDF file not found for document {doc_id}. Tried: {pdf_path}, {fallback_path}")
            raise HTTPException(
                status_code=404, 
                detail=f"PDF file not found for document {doc_id}. Expected at: {pdf_path}"
            )
    
    # Servir el archivo
    # Usar file_name_original del modelo DocumentInstanceV1
    filename = doc.file_name_original if hasattr(doc, 'file_name_original') and doc.file_name_original else f"{doc_id}.pdf"
    logger.info(f"Serving PDF: {pdf_path} as {filename}")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )


@router.put("/docs/{doc_id}/pdf", response_model=DocumentInstanceV1)
async def replace_document_pdf(
    doc_id: str,
    file: UploadFile = File(...)
) -> DocumentInstanceV1:
    """
    Reemplaza el PDF de un documento existente.
    Conserva todos los metadatos, solo actualiza el archivo PDF y su hash.
    """
    store = DocumentRepositoryStoreV1()
    
    # Verificar que el documento existe
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    
    # Validar que es PDF
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Guardar archivo temporalmente
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = Path(tmp_file.name)
    
    try:
        # Calcular nuevo hash
        new_sha256 = store.compute_file_hash(tmp_path)
        
        # Reemplazar PDF
        store.store_pdf(tmp_path, doc_id)
        
        # Actualizar hash en el documento (campo real del modelo)
        doc.sha256 = new_sha256
        
        # Actualizar nombre de archivo si es diferente
        if file.filename and file.filename != doc.file_name_original:
            doc.file_name_original = file.filename

        # Actualizar timestamp
        doc.updated_at = datetime.utcnow()
        
        # Guardar documento actualizado
        store.save_document(doc)
        
        return doc
    
    finally:
        # Limpiar archivo temporal
        tmp_path.unlink(missing_ok=True)


class DocumentUpdateRequest(BaseModel):
    """Request para actualizar un documento."""
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    status: Optional[str] = None
    validity_override: Optional[Any] = None
    # Campos de metadatos editables
    issue_date: Optional[str] = None  # Fecha de emisión (YYYY-MM-DD)
    validity_start_date: Optional[str] = None  # Fecha inicio de vigencia (YYYY-MM-DD)
    period_key: Optional[str] = None  # Clave del período (YYYY-MM, YYYY, YYYY-Qn)
    
    @field_validator('validity_override', mode='before')
    @classmethod
    def normalize_validity_override(cls, v: Any) -> Optional[dict]:
        """
        Normaliza validity_override antes de la validación de Pydantic:
        - Si es None -> None
        - Si es dict -> dict
        - Si es str -> intenta json.loads() -> dict
        - Si falla -> lanza ValueError
        """
        if v is None:
            return None
        
        if isinstance(v, dict):
            return v
        
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if not isinstance(parsed, dict):
                    raise ValueError(f"validity_override string must parse to dict, got {type(parsed).__name__}")
                return parsed
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in validity_override string: {e}")
        
        raise ValueError(f"validity_override must be dict, str (JSON), or None, got {type(v).__name__}")


@router.put("/docs/{doc_id}", response_model=DocumentInstanceV1)
async def update_document(
    doc_id: str,
    request: DocumentUpdateRequest
) -> DocumentInstanceV1:
    """
    Actualiza campos editables de un documento.
    
    - company_key: Clave de empresa
    - person_key: Clave de persona
    - status: draft | reviewed | ready_to_submit | submitted
    """
    store = DocumentRepositoryStoreV1()
    
    # Obtener documento existente
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    
    # Obtener tipo para validar scope
    doc_type = store.get_type(doc.type_id)
    if not doc_type:
        raise HTTPException(status_code=404, detail=f"Type {doc.type_id} not found")
    
    # Validar cambios según scope
    new_company_key = request.company_key if request.company_key is not None else doc.company_key
    new_person_key = request.person_key if request.person_key is not None else doc.person_key
    
    if doc_type.scope == "company":
        if not new_company_key:
            raise HTTPException(status_code=400, detail="company_key required for scope=company")
        if new_person_key:
            raise HTTPException(status_code=400, detail="person_key must be null for scope=company")
    elif doc_type.scope == "worker":
        if not new_company_key:
            raise HTTPException(status_code=400, detail="company_key required for scope=worker")
        if not new_person_key:
            raise HTTPException(status_code=400, detail="person_key required for scope=worker")
    
    # Actualizar campos
    if request.company_key is not None:
        doc.company_key = request.company_key
    if request.person_key is not None:
        doc.person_key = request.person_key
    if request.status is not None:
        try:
            doc.status = DocumentStatusV1(request.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")
    
    # Actualizar validity_override si se proporciona
    # Nota: ya está normalizado por el field_validator de Pydantic
    if request.validity_override is not None:
        normalized_override = request.validity_override  # Ya es dict o None después del validator
        
        # Si después de normalizar es None, limpiar override
        if normalized_override is None:
            doc.validity_override = None
        else:
            # Verificar si es un dict vacío o todos los valores son None
            is_empty = False
            if normalized_override == {}:
                is_empty = True
            else:
                # Verificar si todos los valores son None o strings vacíos
                all_none = all(
                    v is None or (isinstance(v, str) and v.strip() == "")
                    for v in normalized_override.values()
                )
                is_empty = all_none
            
            if is_empty:
                # Si es un dict vacío o todos los valores son None, eliminar override
                doc.validity_override = None
            else:
                # Validar formato de fechas YYYY-MM-DD
                override_valid_from = normalized_override.get("override_valid_from")
                override_valid_to = normalized_override.get("override_valid_to")
                reason = normalized_override.get("reason")
                
                # Parsear fechas si son strings
                parsed_from = None
                parsed_to = None
                
                if override_valid_from:
                    if isinstance(override_valid_from, str):
                        try:
                            parsed_from = datetime.strptime(override_valid_from, "%Y-%m-%d").date()
                        except ValueError:
                            raise HTTPException(status_code=400, detail=f"Invalid date format for override_valid_from: {override_valid_from}. Expected YYYY-MM-DD")
                    elif isinstance(override_valid_from, date):
                        parsed_from = override_valid_from
                
                if override_valid_to:
                    if isinstance(override_valid_to, str):
                        try:
                            parsed_to = datetime.strptime(override_valid_to, "%Y-%m-%d").date()
                        except ValueError:
                            raise HTTPException(status_code=400, detail=f"Invalid date format for override_valid_to: {override_valid_to}. Expected YYYY-MM-DD")
                    elif isinstance(override_valid_to, date):
                        parsed_to = override_valid_to
                
                doc.validity_override = ValidityOverrideV1(
                    override_valid_from=parsed_from,
                    override_valid_to=parsed_to,
                    reason=reason
                )
    
    # Actualizar issue_date (fecha de emisión)
    if request.issue_date is not None:
        try:
            parsed_issue_date = datetime.strptime(request.issue_date, "%Y-%m-%d").date() if request.issue_date else None
            doc.issued_at = parsed_issue_date
            # También actualizar en extracted si existe
            if doc.extracted:
                doc.extracted.issue_date = parsed_issue_date
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format for issue_date: {request.issue_date}. Expected YYYY-MM-DD")
    
    # Actualizar validity_start_date (fecha inicio de vigencia)
    if request.validity_start_date is not None:
        try:
            parsed_validity_start = datetime.strptime(request.validity_start_date, "%Y-%m-%d").date() if request.validity_start_date else None
            # Actualizar en extracted
            if doc.extracted:
                doc.extracted.validity_start_date = parsed_validity_start
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format for validity_start_date: {request.validity_start_date}. Expected YYYY-MM-DD")
    
    # Actualizar period_key
    if request.period_key is not None:
        doc.period_key = request.period_key if request.period_key else None
        # Si se actualiza period_key, también actualizar issued_at si se puede inferir
        if request.period_key and not doc.issued_at:
            # Intentar inferir fecha desde period_key (YYYY-MM)
            try:
                if len(request.period_key) == 7 and request.period_key[4] == '-':  # YYYY-MM
                    year, month = request.period_key.split('-')
                    # Usar primer día del mes como issue_date por defecto
                    doc.issued_at = date(int(year), int(month), 1)
                    if doc.extracted:
                        doc.extracted.issue_date = doc.issued_at
            except (ValueError, IndexError):
                pass  # Si no se puede parsear, no hacer nada
    
    # Recalcular validez si se modificaron fechas relevantes
    if request.issue_date is not None or request.validity_start_date is not None or request.period_key is not None:
        from backend.repository.validity_calculator_v1 import compute_validity
        # Recalcular computed_validity
        doc.computed_validity = compute_validity(doc_type.validity_policy, doc.extracted)
    
    doc.updated_at = datetime.utcnow()
    
    # Guardar
    store.save_document(doc)
    
    return doc


@router.get("/types/{type_id}/expected")
async def get_expected_periods(
    type_id: str,
    company_key: Optional[str] = None,
    person_key: Optional[str] = None,
    months: int = 24,
) -> List[dict]:
    """
    Obtiene períodos esperados para un tipo de documento y sujeto.
    
    Args:
        type_id: ID del tipo de documento
        company_key: Clave de empresa (si scope=company)
        person_key: Clave de persona (si scope=worker)
        months: Cuántos meses hacia atrás generar (default: 24)
    
    Returns:
        Lista de períodos con estado (AVAILABLE, MISSING, LATE)
    """
    store = DocumentRepositoryStoreV1()
    doc_type = store.get_type(type_id)
    if not doc_type:
        raise HTTPException(status_code=404, detail=f"Type {type_id} not found")
    
    planner = PeriodPlannerV1(store)
    periods = planner.generate_expected_periods(
        doc_type=doc_type,
        months_back=months,
        company_key=company_key,
        person_key=person_key,
    )
    
    return [p.to_dict() for p in periods]


@router.get("/subjects")
async def get_subjects() -> dict:
    """
    Obtiene empresas y trabajadores agrupados por empresa propia.
    
    SPRINT C2.32A: Agrupa trabajadores por own_company_key.
    Trabajadores sin own_company_key (unassigned) se agrupan bajo "unassigned".
    
    Returns:
        {
            "companies": [{"id": "E1", "name": "Empresa 1", "tax_id": "..."}, ...],
            "workers_by_company": {
                "E1": [{"id": "W1", "name": "Juan", "tax_id": "..."}, ...],
                "E2": [...],
                "unassigned": [...]  # Trabajadores sin own_company_key
            }
        }
    """
    try:
        config_store = ConfigStoreV1()
        org = config_store.load_org()
        people = config_store.load_people()
        
        # Crear empresa desde org (empresa principal)
        company_id = org.tax_id if org.tax_id else "DEFAULT"
        company_name = org.legal_name if org.legal_name else "Empresa Principal"
        company_tax_id = org.tax_id if org.tax_id else ""
        
        companies = [{
            "id": company_id,
            "name": company_name,
            "tax_id": company_tax_id
        }]
        
        # SPRINT C2.32A: Agrupar trabajadores por own_company_key
        workers_by_company: dict[str, list] = {}
        
        for person in people.people:
            # Determinar la clave de empresa (own_company_key o "unassigned")
            person_company_key = person.own_company_key if person.own_company_key else "unassigned"
            
            if person_company_key not in workers_by_company:
                workers_by_company[person_company_key] = []
            
            workers_by_company[person_company_key].append({
                "id": person.worker_id,
                "name": person.full_name,
                "tax_id": person.tax_id,
                "role": person.role
            })
        
        # Si hay trabajadores sin asignar, añadir "unassigned" a companies si no existe
        if "unassigned" in workers_by_company:
            companies.append({
                "id": "unassigned",
                "name": "Sin asignar",
                "tax_id": ""
            })
        
        return {
            "companies": companies,
            "workers_by_company": workers_by_company
        }
    except Exception as e:
        # Fallback: devolver estructura vacía con log del error
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error loading subjects: {e}", exc_info=True)
        return {
            "companies": [],
            "workers_by_company": {}
        }


@router.delete("/docs/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    """
    Elimina un documento (PDF + sidecar JSON).
    
    - Si doc_id no existe → 404
    - Si status == "submitted" → 409 (no se puede borrar)
    """
    store = DocumentRepositoryStoreV1()
    
    try:
        store.delete_document(doc_id)
        return {"ok": True}
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "submitted" in error_msg.lower():
            raise HTTPException(status_code=409, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== SPRINT C2.11.1: CAE Pack Export (ZIP) ==========

class CAEPackRequest(BaseModel):
    """Request para generar pack CAE (ZIP)."""
    platform: str = "generic"  # "generic" | "cetaima" | "ecoordina"
    doc_ids: List[str] = []  # Lista de doc_ids a incluir
    missing: Optional[List[dict]] = None  # Items faltantes (opcional)
    meta: Optional[dict] = None  # Metadata adicional (opcional)


def normalize_filename(filename: str, max_length: int = 120) -> str:
    """
    Normaliza nombre de archivo para ser seguro en sistemas de archivos.
    
    - Quita caracteres peligrosos: / \\ : * ? " < > | y control chars
    - Espacios -> _
    - Limita longitud conservando extensión
    """
    # Obtener extensión
    ext = ""
    if "." in filename:
        parts = filename.rsplit(".", 1)
        if len(parts) == 2:
            ext = "." + parts[1]
            filename = parts[0]
    
    # Quitar caracteres peligrosos
    dangerous = r'[/\\:*?"<>|]'
    filename = re.sub(dangerous, '_', filename)
    
    # Quitar caracteres de control
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    
    # Espacios -> _
    filename = filename.replace(' ', '_')
    
    # Limitar longitud (reservando espacio para extensión)
    max_base = max_length - len(ext)
    if len(filename) > max_base:
        filename = filename[:max_base]
    
    return filename + ext


@router.post("/cae/pack")
async def generate_cae_pack(request: CAEPackRequest) -> Response:
    """
    SPRINT C2.11.1: Genera un pack CAE (ZIP) con documentos seleccionados.
    
    El ZIP contiene:
    - /CAE_PACK/docs/<SUBJECT>/<TYPE>/<PERIOD>/<normalized_filename>.pdf
    - README.txt con información del pack
    - checklist.json con metadata estructurada
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Validar platform
    valid_platforms = ["generic", "cetaima", "ecoordina"]
    if request.platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"platform debe ser uno de: {', '.join(valid_platforms)}"
        )
    
    # Validar que hay doc_ids
    if not request.doc_ids:
        raise HTTPException(
            status_code=400,
            detail="doc_ids no puede estar vacío"
        )
    
    store = DocumentRepositoryStoreV1()
    
    # Crear ZIP en memoria
    zip_buffer = io.BytesIO()
    zip_file = zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED)
    
    # Información para README y checklist
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    zip_filename = f"CAE_PACK_{request.platform}_{timestamp}.zip"
    
    included_docs = []
    missing_docs = []
    total_size = 0
    
    # Procesar cada doc_id
    for doc_id in request.doc_ids:
        try:
            # Obtener documento
            doc = store.get_document(doc_id)
            if not doc:
                missing_docs.append({
                    "doc_id": doc_id,
                    "reason": "Documento no encontrado en el repositorio"
                })
                continue
            
            # Obtener path del PDF
            pdf_path = store._get_doc_pdf_path(doc_id)
            if not pdf_path.exists():
                missing_docs.append({
                    "doc_id": doc_id,
                    "reason": f"PDF no encontrado en {pdf_path}"
                })
                continue
            
            # Obtener tipo de documento
            doc_type = store.get_type(doc.type_id)
            type_name = doc_type.name if doc_type else doc.type_id
            
            # Determinar subject (company o person)
            subject_key = doc.company_key or doc.person_key or "UNKNOWN"
            subject_label = f"COMPANY_{doc.company_key}" if doc.company_key else f"PERSON_{doc.person_key}" if doc.person_key else "UNKNOWN"
            
            # Period
            period_key = doc.period_key or "NO_PERIOD"
            
            # Normalizar nombre de archivo
            original_filename = doc.file_name_original or f"{doc_id}.pdf"
            normalized_name = normalize_filename(original_filename)
            
            # Ruta dentro del ZIP
            zip_path = f"CAE_PACK/docs/{subject_label}/{type_name}/{period_key}/{normalized_name}"
            
            # Añadir PDF al ZIP
            zip_file.write(str(pdf_path), zip_path)
            
            # Información del documento incluido
            file_size = pdf_path.stat().st_size
            total_size += file_size
            
            included_docs.append({
                "doc_id": doc_id,
                "type_id": doc.type_id,
                "type_name": type_name,
                "subject": subject_label,
                "period": period_key,
                "filename": normalized_name,
                "size_bytes": file_size,
                "scope": doc.scope,
                "status": doc.status
            })
            
        except Exception as e:
            logger.warning(f"Error procesando doc_id {doc_id}: {e}")
            missing_docs.append({
                "doc_id": doc_id,
                "reason": f"Error: {str(e)}"
            })
    
    # Generar README.txt
    readme_lines = [
        f"CAE PACK - {request.platform.upper()}",
        f"Generado: {now.isoformat()}",
        f"",
        f"=== RESUMEN ===",
        f"Plataforma: {request.platform}",
        f"Documentos incluidos: {len(included_docs)}",
        f"Documentos no incluidos: {len(missing_docs)}",
        f"Tamaño total: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)",
        f"",
        f"=== DOCUMENTOS INCLUIDOS ===",
    ]
    
    for doc_info in included_docs:
        readme_lines.append(
            f"{doc_info['subject']} | {doc_info['type_name']} | {doc_info['period']} | {doc_info['filename']}"
        )
    
    if missing_docs:
        readme_lines.extend([
            f"",
            f"=== DOCUMENTOS NO INCLUIDOS ===",
        ])
        for missing in missing_docs:
            readme_lines.append(f"{missing['doc_id']}: {missing['reason']}")
    
    if request.missing:
        readme_lines.extend([
            f"",
            f"=== FALTANTES DETECTADOS POR EL PLAN ===",
        ])
        for missing_item in request.missing:
            type_id = missing_item.get('type_id', 'N/A')
            subject = missing_item.get('company_key') or missing_item.get('person_key', 'N/A')
            period = missing_item.get('period_key', 'N/A')
            readme_lines.append(f"{subject} | {type_id} | {period}")
    
    readme_content = "\n".join(readme_lines)
    zip_file.writestr("CAE_PACK/README.txt", readme_content.encode('utf-8'))
    
    # Generar checklist.json
    checklist = {
        "generated_at": now.isoformat(),
        "platform": request.platform,
        "summary": {
            "included_count": len(included_docs),
            "missing_count": len(missing_docs),
            "total_size_bytes": total_size
        },
        "included_documents": included_docs,
        "missing_documents": missing_docs,
        "plan_missing": request.missing or [],
        "meta": request.meta or {}
    }
    zip_file.writestr("CAE_PACK/checklist.json", json.dumps(checklist, indent=2, ensure_ascii=False).encode('utf-8'))
    
    # Cerrar ZIP
    zip_file.close()
    zip_buffer.seek(0)
    
    # Verificar tamaño (warning si > 200MB)
    zip_size = len(zip_buffer.getvalue())
    if zip_size > 200 * 1024 * 1024:
        logger.warning(f"CAE Pack generado es muy grande: {zip_size / 1024 / 1024:.2f} MB")
    
    # Devolver ZIP como respuesta
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        }
    )

