from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.date_parser_v1 import parse_date_from_filename
from backend.repository.validity_calculator_v1 import compute_validity
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentScopeV1,
    ExtractedMetadataV1,
    DocumentStatusV1,
)


router = APIRouter(
    prefix="/api/repository",
    tags=["repository"],
)


# ========== TIPOS DE DOCUMENTO ==========

@router.get("/types", response_model=List[DocumentTypeV1])
async def list_types(include_inactive: bool = False) -> List[DocumentTypeV1]:
    """Lista todos los tipos de documento."""
    store = DocumentRepositoryStoreV1()
    return store.list_types(include_inactive=include_inactive)


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
    """Actualiza un tipo existente."""
    store = DocumentRepositoryStoreV1()
    try:
        return store.update_type(type_id, doc_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class DuplicateTypeRequest(BaseModel):
    new_type_id: str
    new_name: Optional[str] = None


@router.post("/types/{type_id}/duplicate", response_model=DocumentTypeV1)
async def duplicate_type(
    type_id: str,
    request: DuplicateTypeRequest
) -> DocumentTypeV1:
    """Duplica un tipo con nuevo ID."""
    store = DocumentRepositoryStoreV1()
    try:
        return store.duplicate_type(type_id, request.new_type_id, request.new_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
        
        # Crear metadatos extraídos
        extracted = ExtractedMetadataV1(
            name_date=name_date
        )
        
        # Calcular validez
        computed_validity = compute_validity(doc_type.validity_policy, extracted)
        
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


@router.get("/docs", response_model=List[DocumentInstanceV1])
async def list_documents(
    type_id: Optional[str] = None,
    scope: Optional[str] = None,
    status: Optional[str] = None
) -> List[DocumentInstanceV1]:
    """Lista todos los documentos (con filtros opcionales)."""
    store = DocumentRepositoryStoreV1()
    return store.list_documents(type_id=type_id, scope=scope, status=status)


@router.get("/docs/{doc_id}", response_model=DocumentInstanceV1)
async def get_document(doc_id: str) -> DocumentInstanceV1:
    """Obtiene un documento por ID."""
    store = DocumentRepositoryStoreV1()
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return doc


class DocumentUpdateRequest(BaseModel):
    """Request para actualizar un documento."""
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    status: Optional[str] = None
    validity_override: Optional[dict] = None


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
    if request.validity_override is not None:
        # Verificar si es un dict vacío o todos los valores son None
        is_empty = False
        if isinstance(request.validity_override, dict):
            if request.validity_override == {}:
                is_empty = True
            else:
                # Verificar si todos los valores son None
                all_none = all(
                    v is None or (isinstance(v, str) and v.strip() == "")
                    for v in request.validity_override.values()
                )
                is_empty = all_none
        
        if is_empty:
            # Si es un dict vacío o todos los valores son None, eliminar override
            doc.validity_override = None
        else:
            # Validar formato de fechas YYYY-MM-DD
            override_valid_from = request.validity_override.get("override_valid_from")
            override_valid_to = request.validity_override.get("override_valid_to")
            reason = request.validity_override.get("reason")
            
            # Parsear fechas si son strings
            from datetime import date
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
    
    doc.updated_at = datetime.utcnow()
    
    # Guardar
    store.save_document(doc)
    
    return doc


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

