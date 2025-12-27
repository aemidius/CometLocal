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
    
    # Validar sujeto según scope
    if scope == "company" and not company_key:
        raise HTTPException(status_code=400, detail="company_key required for scope=company")
    if scope == "worker" and not person_key:
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

