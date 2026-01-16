# Evidencia — Error al subir/resubir documento (Internal Server Error)

## Qué fallaba
En “Subir documentos”, cuando el flujo entra en **reemplazar PDF** (por ejemplo desde **Buscar documentos → Resubir**, o por duplicado), el frontend llama:
- `PUT /api/repository/docs/{doc_id}/pdf`

Ese endpoint devolvía **500**.

## Causa raíz (exacta)
En `backend/repository/document_repository_routes.py` (`replace_document_pdf`) se intentaban escribir campos **inexistentes** en `DocumentInstanceV1`:
- `doc.file_hash = ...` (el modelo real usa `sha256`)
- además se usaba `doc.doc_file_name` (el modelo real usa `file_name_original`)

Pydantic lanzaba:
- `ValueError: "DocumentInstanceV1" object has no field "file_hash"`

Evidencia:
- `docs/evidence/upload_doc_500/BACKEND_LOG_SNAPSHOT.txt`
- `docs/evidence/upload_doc_500/TRACEBACK.txt`

## Fix mínimo aplicado
Archivo: `backend/repository/document_repository_routes.py`
- `doc.file_hash` → `doc.sha256`
- `doc.doc_file_name` → `doc.file_name_original`
- `doc.updated_at = datetime.utcnow()`

## Validación AFTER (evidencia real)
- Network real (request/response, status 200): `docs/evidence/upload_doc_500/NETWORK_AFTER.json`
- Screenshot AFTER: `docs/evidence/upload_doc_500/02_after.png`
- Backend log con 200: `c:\\Users\\emili\\.cursor\\projects\\d-Proyectos-Cursor-CometLocal\\terminals\\5.txt` (línea con `PUT ... /pdf 200 OK`)

## Test E2E (Playwright) — salida real
- Spec: `tests/e2e_resubmit_pdf.spec.js`
- Comando:
  - `npx playwright test tests/e2e_resubmit_pdf.spec.js --reporter=line`
- Output:
  - `docs/evidence/upload_doc_500/TEST_OUTPUT.txt` (**1 passed**)

## Archivos tocados
- `backend/repository/document_repository_routes.py`
- `tests/e2e_resubmit_pdf.spec.js`

## Comandos ejecutados
- (Backend) reinicio uvicorn:
  - `D:\\Proyectos_Cursor\\CometLocal\\.venv\\Scripts\\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`
- (Evidencia) script:
  - `node docs/evidence/upload_doc_500/repro_resubmit_pdf_after.js`
- (Tests)
  - `npx playwright test tests/e2e_resubmit_pdf.spec.js --reporter=line`







