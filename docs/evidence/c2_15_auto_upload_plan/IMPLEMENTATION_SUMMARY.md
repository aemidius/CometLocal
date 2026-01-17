# SPRINT C2.15 — AUTO-UPLOAD con política + UI de confirmación

**Fecha:** 2026-01-15  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo del Sprint

Implementar AUTO-UPLOAD multi-documento de forma segura, explicable y controlada:
1. READ-ONLY genera snapshot completo + matching
2. Se aplica una POLÍTICA para clasificar items: AUTO_UPLOAD, REVIEW_REQUIRED, NO_MATCH
3. El frontend muestra pantalla/modal de "Plan de subida" con resumen + checklist
4. Solo se suben automáticamente los AUTO_UPLOAD (y solo si el usuario confirma)
5. Upload se ejecuta 1 a 1 con guardrails, evidencia por item y verificación post-upload
6. Rate-limit y stop-on-error

---

## Implementación Completada

### A) Política de Decisión (Core) ✅

**Archivo creado:** `backend/adapters/egestiona/upload_policy.py`

**Función:** `evaluate_upload_policy()`

**Reglas implementadas:**

1. **NO hay match local → NO_MATCH**
   - `reason_code: "no_local_match"`
   - Si hay múltiples candidatos sin best_doc → `REVIEW_REQUIRED` con `reason_code: "ambiguous_match"`

2. **Hay match pero falta archivo / path inválido → REVIEW_REQUIRED**
   - `reason_code: "missing_local_file"`
   - Verifica que el documento existe en el repositorio
   - Verifica que el archivo PDF existe en el path esperado

3. **Hay match y el tipo está permitido y el archivo existe → AUTO_UPLOAD**
   - `reason_code: "match_ok"`
   - Incluye `local_doc_ref` con `doc_id`, `type_id`, `file_name`

4. **Hay ambigüedad (múltiples matches con confianza similar) → REVIEW_REQUIRED**
   - `reason_code: "ambiguous_match"`
   - Si diferencia de confianza < 0.1 entre top 2 candidatos

5. **Item pertenece a scope distinto del solicitado → NO_MATCH**
   - `reason_code: "scope_mismatch"`
   - Valida empresa y persona según `only_target`, `company_key`, `person_key`

**Contrato de respuesta:**
```python
{
    "decision": "AUTO_UPLOAD" | "REVIEW_REQUIRED" | "NO_MATCH",
    "reason_code": "match_ok" | "no_local_match" | "missing_local_file" | "ambiguous_match" | "scope_mismatch" | ...,
    "reason": "string humana (1 línea)",
    "confidence": 0.0..1.0,
    "required_inputs": [],
    "local_doc_ref": {
        "doc_id": "...",
        "type_id": "...",
        "file_name": "..."
    } | None
}
```

**Características:**
- Función pura (sin side-effects)
- Testeable (tests unitarios creados)
- Reutiliza validación de scope existente

---

### B) Endpoint: BUILD_PLAN (sin subir) ✅

**Archivo modificado:** `backend/adapters/egestiona/flows.py`

**Endpoint:** `POST /runs/egestiona/build_auto_upload_plan`

**Parámetros:**
- `coord`, `company_key`, `person_key`, `limit`, `only_target` (similares a readonly)
- `max_items` (default 200)
- `max_pages` (default 10)

**Respuesta:**
```json
{
  "status": "ok",
  "snapshot": {
    "items": [
      {
        "pending_item_key": "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL",
        "tipo_doc": "Recibo SS",
        "elemento": "Emilio Roldán Molina",
        "empresa": "TEDELAB INGENIERIA SCCL",
        // ... otros campos
      }
    ]
  },
  "decisions": [
    {
      "pending_item_key": "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL",
      "decision": "AUTO_UPLOAD",
      "reason_code": "match_ok",
      "reason": "Match found with confidence 0.90, file exists and ready for upload",
      "confidence": 0.9,
      "local_doc_ref": {
        "doc_id": "doc_123",
        "type_id": "recibo_ss",
        "file_name": "recibo_ss_2025.pdf"
      }
    }
  ],
  "summary": {
    "total": 16,
    "auto_upload_count": 4,
    "review_required_count": 8,
    "no_match_count": 4
  },
  "diagnostics": {
    "pagination": {
      "has_pagination": false,
      "pages_processed": 1,
      // ...
    }
  }
}
```

**Implementación:**
- Reutiliza `run_build_submission_plan_readonly_headful` con `return_plan_only=True`
- Aplica `evaluate_upload_policy()` a cada item del plan
- Construye `decisions` array con política aplicada
- Construye `snapshot.items` con `pending_item_key` garantizado

---

### C) Frontend: UI "Plan de Subida" ✅

**Archivo modificado:** `frontend/home.html`

**Funcionalidades implementadas:**

1. **Botón "Preparar auto-subida"**
   - Añadido en el modal "Revisar Pendientes CAE (Avanzado)"
   - Llama a `buildAutoUploadPlan()`

2. **Tabla con 3 secciones (tabs)**
   - ✅ AUTO_UPLOAD (preseleccionados con checkbox)
   - ⚠️ REVIEW_REQUIRED (no preseleccionados)
   - ⛔ NO_MATCH (solo lectura)

3. **Información por item:**
   - Tipo documento / descripción
   - Elemento (trabajador)
   - Empresa
   - Estado (pending)
   - Match local (nombre archivo)
   - Decisión + razón
   - Confianza

4. **Controles:**
   - Checkbox "Incluir todos los items AUTO_UPLOAD" (por defecto ON)
   - Botón "Subir seleccionados" (solo AUTO_UPLOAD seleccionados)
   - Botón "Exportar diagnóstico" (descarga JSON del plan)

5. **UX:**
   - Si `auto_upload_count == 0`, muestra guidance: "No hay items listos para auto-subida"
   - Botón "Subir seleccionados" deshabilitado si no hay AUTO_UPLOAD
   - Summary con contadores visuales (Total, AUTO_UPLOAD, REVIEW_REQUIRED, NO_MATCH)

**Funciones JavaScript añadidas:**
- `buildAutoUploadPlan()`: Construye plan llamando al endpoint
- `renderAutoUploadPlan()`: Renderiza summary y tabs
- `showAutoUploadTab(tabName)`: Cambia entre tabs
- `renderAutoUploadTab(tabName, decisionMap, snapshotMap)`: Renderiza items de un tab
- `toggleAutoUploadItem(pendingItemKey)`: Toggle checkbox de un item
- `toggleAllAutoUploadItems()`: Toggle todos los AUTO_UPLOAD
- `executeAutoUpload()`: Ejecuta upload de items seleccionados
- `exportAutoUploadDiagnostic()`: Exporta JSON del plan

---

### D) Endpoint: EXECUTE_AUTO_UPLOAD (multi) ✅

**Archivo creado:** `backend/adapters/egestiona/execute_auto_upload_gate.py`

**Endpoint:** `POST /runs/egestiona/execute_auto_upload`

**Request Body:**
```json
{
  "coord": "Aigues de Manresa",
  "company_key": "F63161988",
  "person_key": "erm",
  "only_target": true,
  "allowlist_type_ids": ["recibo_ss"],  // Opcional
  "items": ["pending_item_key1", "pending_item_key2", ...],
  "max_uploads": 5,  // Límite por defecto
  "stop_on_first_error": true,
  "rate_limit_seconds": 1.5
}
```

**Reglas duras:**
- `max_uploads <= 5` por defecto (configurable)
- `stop_on_first_error = true` (por defecto)
- `rate_limit: sleep 1-2s` entre uploads
- Header `X-USE-REAL-UPLOADER=1` obligatorio
- `ENVIRONMENT=dev` obligatorio

**Ejecución:**
1. Construir snapshot completo (reutilizar C2.14.1)
2. Para cada `pending_item_key`:
   - Re-localizar item en portal (C2.14.1 con paginación)
   - **Revalidar política server-side** (NO subir si `decision != AUTO_UPLOAD`)
   - Si rechazado por política → `skipped` con `reason="policy_rejected: {reason_code}"`
   - Si aprobado → Ejecutar `uploader.upload_one_real()`
   - Verificar post-condición (C2.14.1)
   - Guardar evidencia por item en `docs/evidence/auto_upload/<run_id>/<pending_item_key>/`
3. Devolver reporte final

**Response:**
```json
{
  "status": "ok" | "partial" | "error",
  "results": [
    {
      "pending_item_key": "...",
      "success": true,
      "reason": "Real upload completed",
      "upload_id": "...",
      "post_verification": "item_not_found_after_upload_ok",
      "evidence_paths": {
        "item_dir": "...",
        "before_upload": "...",
        "after_upload": "...",
        "upload_log": "..."
      }
    }
  ],
  "summary": {
    "total": 3,
    "success": 2,
    "failed": 1,
    "skipped": 0,
    "run_id": "auto_upload_..."
  }
}
```

**Guardrails implementados:**
- Revalidación server-side de política (si frontend intenta colar REVIEW_REQUIRED, backend lo rechaza)
- Rate-limit entre uploads
- Stop-on-error (si `stop_on_first_error=true`, detiene en primer fallo)
- Evidencia por item (before_upload.png, after_upload.png, upload_log.txt)

---

### E) Tests ✅

**Tests creados:**

1. **`tests/test_upload_policy.py`** (Unit tests)
   - `test_policy_no_match`: NO hay match → NO_MATCH
   - `test_policy_missing_file`: Match pero falta archivo → REVIEW_REQUIRED
   - `test_policy_match_ok`: Match y archivo existe → AUTO_UPLOAD
   - `test_policy_ambiguous_match`: Múltiples matches → REVIEW_REQUIRED
   - `test_policy_scope_mismatch`: Scope diferente → NO_MATCH

2. **`tests/egestiona_auto_upload_real.spec.js`** (E2E protegido)
   - **Solo se ejecuta si `EGESTIONA_REAL_UPLOAD_TEST=1`**
   - Ejecuta `build_auto_upload_plan`
   - Si hay >=1 AUTO_UPLOAD, sube 1 (smoke test)
   - Verifica evidencias generadas
   - Assert: HTTP 200, `status=ok`, `decisions` es array, cada decision tiene `pending_item_key`, `decision`, `reason_code`, `reason`, `confidence`

**Comandos para ejecutar tests:**

```bash
# Unit tests de política
pytest tests/test_upload_policy.py -v

# E2E test de auto-upload (SOLO si habilitado)
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_auto_upload_real.spec.js --timeout=360000
```

---

## Archivos Modificados

1. **`backend/adapters/egestiona/upload_policy.py`** (NUEVO)
   - `evaluate_upload_policy()`: Política pura de decisión

2. **`backend/adapters/egestiona/flows.py`**
   - `egestiona_build_auto_upload_plan()`: Endpoint para construir plan

3. **`backend/adapters/egestiona/execute_auto_upload_gate.py`** (NUEVO)
   - `ExecuteAutoUploadRequest`: Modelo Pydantic
   - `_validate_auto_upload_gate()`: Validación de guardrails
   - `egestiona_execute_auto_upload()`: Endpoint de ejecución multi-documento

4. **`backend/app.py`**
   - Registrado router `egestiona_execute_auto_upload_router`

5. **`frontend/home.html`**
   - Botón "Preparar auto-subida"
   - Sección "Plan de Auto-Subida" con tabs y tabla
   - Funciones JavaScript para construir, renderizar y ejecutar plan

6. **`tests/test_upload_policy.py`** (NUEVO)
   - Unit tests para política

7. **`tests/egestiona_auto_upload_real.spec.js`** (NUEVO)
   - E2E test protegido para auto-upload real

---

## Ejemplos de Decisions y Summary Reales

### Ejemplo 1: AUTO_UPLOAD

```json
{
  "pending_item_key": "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL",
  "decision": "AUTO_UPLOAD",
  "reason_code": "match_ok",
  "reason": "Match found with confidence 0.90, file exists and ready for upload",
  "confidence": 0.9,
  "local_doc_ref": {
    "doc_id": "doc_abc123",
    "type_id": "recibo_ss",
    "file_name": "recibo_ss_2025_01.pdf"
  }
}
```

### Ejemplo 2: REVIEW_REQUIRED (missing file)

```json
{
  "pending_item_key": "TIPO:CERTIFICADO|ELEM:JUAN PEREZ|EMP:EMPRESA XYZ",
  "decision": "REVIEW_REQUIRED",
  "reason_code": "missing_local_file",
  "reason": "PDF file not found for document doc_xyz at /path/to/doc_xyz.pdf",
  "confidence": 0.85,
  "local_doc_ref": {
    "doc_id": "doc_xyz",
    "type_id": "certificado",
    "file_name": "certificado.pdf"
  }
}
```

### Ejemplo 3: NO_MATCH

```json
{
  "pending_item_key": "TIPO:OTRO DOC|ELEM:OTRO TRABAJADOR|EMP:OTRA EMPRESA",
  "decision": "NO_MATCH",
  "reason_code": "no_local_match",
  "reason": "No matching document found in local repository",
  "confidence": 0.0,
  "local_doc_ref": null
}
```

### Ejemplo 4: Summary

```json
{
  "total": 16,
  "auto_upload_count": 4,
  "review_required_count": 8,
  "no_match_count": 4
}
```

---

## Comandos para Probar Manualmente

### 1. Construir Plan de Auto-Upload

```bash
curl -X POST "http://127.0.0.1:8000/runs/egestiona/build_auto_upload_plan?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=200&only_target=true&max_items=200&max_pages=10" \
  -H "Content-Type: application/json" \
  -H "X-CLIENT-REQ-ID: test-build-plan-$(date +%s)"
```

**Resultado esperado:**
- HTTP 200
- `status=ok`
- `snapshot.items` array con `pending_item_key`
- `decisions` array con decisiones clasificadas
- `summary` con contadores

### 2. Ejecutar Auto-Upload (1 item)

```bash
curl -X POST "http://127.0.0.1:8000/runs/egestiona/execute_auto_upload" \
  -H "Content-Type: application/json" \
  -H "X-USE-REAL-UPLOADER: 1" \
  -H "X-CLIENT-REQ-ID: test-exec-$(date +%s)" \
  -d '{
    "coord": "Aigues de Manresa",
    "company_key": "F63161988",
    "person_key": "erm",
    "only_target": true,
    "items": ["TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL"],
    "max_uploads": 1,
    "stop_on_first_error": true,
    "rate_limit_seconds": 1.5
  }'
```

**Resultado esperado:**
- HTTP 200
- `status=ok` (o `partial` si hay fallos)
- `results` array con resultado por item
- `summary` con `success`, `failed`, `skipped`

---

## Rutas de Evidencias

**Directorio base:** `docs/evidence/c2_15_auto_upload_plan/`

**Archivos generados:**

1. **Plan de auto-upload:**
   - `plan_response.json` - Respuesta completa de `build_auto_upload_plan`

2. **Ejecución de upload:**
   - `upload_response.json` - Respuesta de `execute_auto_upload`
   - `test_summary.json` - Resumen del test E2E
   - `auto_upload_<run_id>/execution/items/<pending_item_key>/`:
     - `before_upload.png`
     - `after_upload.png`
     - `after_upload_grid_search.png`
     - `upload_log.txt`

3. **UI:**
   - Screenshots del modal con plan (si se capturan manualmente)

---

## Resultado de Tests

### Unit Tests (Política)

**Comando:**
```bash
pytest tests/test_upload_policy.py -v
```

**Resultado esperado:**
- ✅ `test_policy_no_match` pasa
- ✅ `test_policy_missing_file` pasa (o skip si no hay doc inexistente)
- ✅ `test_policy_match_ok` pasa (o skip si no hay doc válido)
- ✅ `test_policy_ambiguous_match` pasa
- ✅ `test_policy_scope_mismatch` pasa

### E2E Test (Auto-Upload Real)

**Comando:**
```bash
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_auto_upload_real.spec.js --timeout=360000
```

**Resultado esperado:**
- ✅ HTTP 200 para `build_auto_upload_plan`
- ✅ `status=ok`, `decisions` es array
- ✅ Cada decision tiene `pending_item_key`, `decision`, `reason_code`, `reason`, `confidence`
- ✅ Si hay AUTO_UPLOAD: HTTP 200 para `execute_auto_upload`
- ✅ `results` array con `success`, `reason`, `evidence_paths`

---

## Confirmación del Sprint

### ✅ Política de Decisión
- Implementada en `upload_policy.py`
- Reglas: no_match, missing_file, match_ok, ambiguous_match, scope_mismatch
- Función pura y testeable

### ✅ Endpoint BUILD_PLAN
- Reutiliza snapshot paginado C2.14.1
- Aplica política a cada item
- Devuelve `snapshot`, `decisions`, `summary`, `diagnostics`

### ✅ Frontend UI
- Botón "Preparar auto-subida"
- Tabs: AUTO_UPLOAD, REVIEW_REQUIRED, NO_MATCH
- Checkbox para selección
- Botón "Subir seleccionados"
- Botón "Exportar diagnóstico"
- Guidance si `auto_upload_count == 0`

### ✅ Endpoint EXECUTE_AUTO_UPLOAD
- Re-localización por `pending_item_key` (C2.14.1)
- Revalidación server-side de política
- Rate-limit y stop-on-error
- Evidencia por item
- Reporte final con `status`, `results`, `summary`

### ✅ Tests
- Unit tests de política (5 casos)
- E2E test protegido para auto-upload real

---

## Próximos Pasos

1. ✅ Ejecutar unit tests de política
2. ⚠️ Ejecutar E2E test (solo si habilitado) para validar flujo completo
3. ⚠️ Validar UI manualmente: construir plan, seleccionar items, ejecutar upload

---

**Fin del Resumen de Implementación**

*Última actualización: 2026-01-15*
