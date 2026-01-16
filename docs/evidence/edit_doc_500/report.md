# Evidencia — Fix 500 al guardar “Editar documento” (Buscar documentos)

## Repro (BEFORE)
- **UI**: `http://127.0.0.1:8000/repository#buscar`
- **Acción**:
  - Click **Editar** en un documento existente (ej: `T8447_RC_CERTIFICADO`)
  - Cambiar **Estado de tramitación**
  - Click **Guardar**
- **Resultado**: el backend responde **500 Internal Server Error** y la UI muestra `Error al guardar: Internal Server Error`.

### Evidencia capturada (BEFORE)
- **Screenshot BEFORE**: `docs/evidence/edit_doc_500/01_before.png`
- **Network BEFORE**: `docs/evidence/edit_doc_500/NETWORK.txt` (sección “BEFORE”)
- **Traceback completo**: `docs/evidence/edit_doc_500/TRACEBACK.txt`

## Causa raíz (exacta)
En `PUT /api/repository/docs/{doc_id}` el endpoint recalculaba la validez con una llamada incorrecta:
- Se llamaba `compute_validity(doc, doc_type)` pero `compute_validity()` espera `(policy, extracted)`.

Esto provocaba el traceback:
- `AttributeError: 'DocumentInstanceV1' object has no attribute 'basis'`

## Fix mínimo aplicado
Archivo: `backend/repository/document_repository_routes.py`

Cambio:
- Reemplazado:
  - `compute_validity(doc, doc_type)`
- Por:
  - `compute_validity(doc_type.validity_policy, doc.extracted)`

Con esto:
- El PUT deja de romper al recalcular `computed_validity`.
- Guardar desde el modal funciona y persiste.

## Validación (AFTER)
### Evidencia visual (AFTER)
- **Screenshot AFTER**: `docs/evidence/edit_doc_500/02_after.png`

### Network (AFTER)
- `docs/evidence/edit_doc_500/NETWORK.txt` (sección “AFTER”)
- Body completo del 200: `docs/evidence/edit_doc_500/NETWORK_AFTER.json`

### Tests E2E (Playwright) — salida real
- **Spec**: `tests/e2e_edit_document.spec.js`
- **Comando ejecutado**:
  - `npx playwright test tests/e2e_edit_document.spec.js --reporter=line`
- **Salida guardada**:
  - `docs/evidence/edit_doc_500/TEST_OUTPUT.txt`
- **Resultado**: `3 passed`

## Comandos exactos ejecutados (resumen)
- Crear evidencia:
  - `node docs/evidence/edit_doc_500/repro_edit_doc_500.js`
  - `node docs/evidence/edit_doc_500/repro_edit_doc_after.js`
- Reinicio backend (para cargar el fix):
  - Stop process en puerto 8000 y start:
    - `D:\Proyectos_Cursor\CometLocal\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`
- Ejecutar tests:
  - `npx playwright test tests/e2e_edit_document.spec.js --reporter=line`

## Archivos tocados
- `backend/repository/document_repository_routes.py`
- `tests/e2e_edit_document.spec.js`

## Archivos de evidencia generados
- `docs/evidence/edit_doc_500/01_before.png`
- `docs/evidence/edit_doc_500/02_after.png`
- `docs/evidence/edit_doc_500/TRACEBACK.txt`
- `docs/evidence/edit_doc_500/NETWORK.txt`
- `docs/evidence/edit_doc_500/NETWORK_AFTER.json`
- `docs/evidence/edit_doc_500/TEST_OUTPUT.txt`
- `docs/evidence/edit_doc_500/report.md`







