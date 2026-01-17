# SPRINT C2.16 — HARDENING & RESILIENCIA

**Fecha:** 2026-01-15  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo del Sprint

Hacer el sistema robusto en producción real:
1. Reintentos inteligentes por tipo de error (transitorio vs definitivo)
2. Timeouts adaptativos y "watchdogs" por fase
3. Clasificación y normalización de errores (error_code estable)
4. Métricas de fiabilidad y resumen histórico por runs
5. Modo opcional continue-on-error (seguro)
6. Evidencias automáticas en fallos

---

## Implementación Completada

### A) Taxonomía de Errores ✅

**Archivo creado:** `backend/shared/error_classifier.py`

**Error codes estables:**
- `timeout_login`, `timeout_navigation`, `timeout_grid_load`, `timeout_upload`, `timeout_verification`
- `grid_parse_mismatch`, `buscar_not_clickable`, `overlay_blocking`, `pagination_failed`
- `item_not_found_before_upload`, `upload_failed`, `upload_click_intercepted`, `upload_confirmation_failed`
- `verification_failed`, `item_still_present_after_upload`
- `network_transient`, `portal_transient`, `portal_error`
- `unexpected_exception`, `policy_rejected`, `missing_credentials`, `missing_storage_state`

**Clasificador:**
- `classify_exception(exc, phase, context)` → `{error_code, is_transient, retry_after_ms, details, message}`
- `classify_error_code(error_code, phase, context)` → Mismo formato

**Reglas de transient:**
- Timeouts / navigation / network → `transient=true`
- `item_not_found_before_upload` → `transient=true` (1 retry tras refresh)
- `verification_failed` → `transient=true` (1 retry por refresh tardío)
- `upload_click_intercepted` → `transient=true` (overlay temporal)
- `upload_failed` / `item_still_present_after_upload` → `transient=false`

---

### B) Retry Policy ✅

**Archivo creado:** `backend/shared/retry_policy.py`

**Configuración:**
- `max_retries_default = 2`
- Backoff exponencial suave: 500ms, 750ms, 1125ms...
- Jitter: 0-250ms aleatorio
- Overrides por fase:
  - `login`: 1 retry máximo
  - `navigation`: 2 retries
  - `grid_load`: 2 retries
  - `upload`: 0 retries por defecto (solo `upload_click_intercepted` permite 1)
  - `verification`: 1 retry

**Funciones:**
- `retry_with_policy(fn, phase, error_code, on_retry, on_final_failure, max_retries)`
- `retry_with_policy_async()` (versión async)
- `get_max_retries_for_phase(phase, error_code)`

**Logging:**
- Cada retry logueado con `attempt=N` y `phase=...`
- Evidencias guardadas en último intento o todos si DEBUG

---

### C) Watchdogs / Timeouts por Fase ✅

**Archivo creado:** `backend/shared/phase_timeout.py`

**Timeouts por defecto:**
- `login`: 60s
- `navigation`: 60s
- `grid_load`: 60s
- `upload`: 90s
- `verification`: 60s
- `pagination`: 60s

**Funciones:**
- `run_with_phase_timeout(phase, fn, timeout_s, on_timeout_evidence)`
- `run_with_phase_timeout_async()` (versión async)

**Comportamiento:**
- Si excede timeout: `PhaseTimeoutError` con `error_code=timeout_<phase>`
- Evidencia automática vía `on_timeout_evidence` callback
- Retry si aplica según política

---

### D) Evidencias Automáticas en Errores ✅

**Archivo creado:** `backend/shared/evidence_helper.py`

**Funciones:**
- `ensure_evidence_dir(evidence_dir, run_id)`: Crea directorio temporal si `evidence_dir` es None
- `generate_error_evidence(page, phase, attempt, error, evidence_dir, context, run_id)`: Genera evidencias completas
- `generate_timeout_evidence(page, phase, timeout_s, evidence_dir, context, run_id)`: Evidencias para timeout

**Evidencias generadas:**
- `screenshot_fullpage.png`: Screenshot completo de la página
- `screenshot_<phase>.png`: Screenshot específico de la fase (si hay selector)
- `html_snippet.html`: HTML del contenedor relevante (grid, form, etc.)
- `error_log.txt`: Log textual con timestamp, phase, attempt, error type, message, traceback, context

**Estructura:**
```
docs/evidence/c2_16/<run_id>/<phase>/<attempt>/
  - screenshot_fullpage.png
  - screenshot_<phase>.png
  - html_snippet.html
  - error_log.txt
```

---

### E) Métricas de Fiabilidad + Histórico de Runs ✅

**Archivo creado:** `backend/shared/run_summary.py`

**Función:** `save_run_summary(...)`

**Campos guardados:**
- `run_id`, `platform`, `coord`, `company_key`, `person_key`
- `started_at`, `finished_at`, `duration_ms`
- `counts`: `pending_total`, `auto_upload`, `review_required`, `no_match`
- `execution`: `attempted_uploads`, `success_uploads`, `failed_uploads`
- `errors`: `[{phase, error_code, message, transient, attempt}]`

**Endpoint:** `GET /api/runs/summary?limit=50&platform=egestiona`

**Response:**
```json
{
  "status": "ok",
  "summaries": [
    {
      "run_id": "...",
      "platform": "egestiona",
      "started_at": "2026-01-15T10:00:00",
      "duration_ms": 300000,
      "counts": {...},
      "execution": {...},
      "errors": [...]
    }
  ],
  "total": 10
}
```

---

### F) Continue-on-Error (Opcional) ✅

**Archivo modificado:** `backend/adapters/egestiona/execute_auto_upload_gate.py`

**Parámetro:** `continue_on_error: bool = False` (default)

**Lógica:**
- Si `continue_on_error=true`:
  - Continúa con siguiente item SOLO si error es "no side-effect":
    - `item_not_found_before_upload` (antes de upload)
    - `verification_failed` (después de upload, puede ser refresh tardío)
  - Si fallo es durante upload (acción ya realizada), aborta igualmente (por seguridad)
  - Registra `status="partial"` al final

---

### G) Pruebas ✅

**Tests creados:**

1. **`tests/test_error_classifier.py`** (Unit tests)
   - `test_classify_timeout`: Timeout → transient true
   - `test_classify_item_not_found`: item_not_found → transient true
   - `test_classify_verification_failed`: verification_failed → transient true (1 retry)
   - `test_classify_network_transient`: Network error → transient true
   - `test_classify_upload_click_intercepted`: Click intercepted → transient true
   - `test_classify_error_code_*`: Tests para `classify_error_code`

2. **`tests/test_retry_policy.py`** (Unit tests)
   - `test_get_max_retries_for_phase`: Valida retries por fase
   - `test_calculate_backoff`: Valida backoff exponencial
   - `test_add_jitter`: Valida jitter
   - `test_retry_with_policy_success_first_attempt`: No retry si éxito
   - `test_retry_with_policy_success_after_retry`: Retry y éxito
   - `test_retry_with_policy_fails_after_max_retries`: Falla después de max retries
   - `test_retry_with_policy_on_retry_callback`: Valida callback

3. **`tests/test_run_summary.py`** (Unit tests)
   - `test_save_run_summary`: Guarda summary correctamente
   - `test_load_run_summary`: Carga summary correctamente
   - `test_load_run_summary_not_found`: Retorna None si no existe
   - `test_list_run_summaries`: Lista summaries correctamente
   - `test_list_run_summaries_filter_platform`: Filtra por plataforma

4. **`tests/egestiona_hardening_e2e.spec.js`** (E2E protegido)
   - Solo se ejecuta si `EGESTIONA_REAL_UPLOAD_TEST=1`
   - Ejecuta auto-upload y verifica que `run_summary.json` se escribe
   - Verifica que endpoint `/api/runs/summary` lista el run

---

## Archivos Modificados

1. **`backend/shared/error_classifier.py`** (NUEVO)
   - `ErrorCode` enum con códigos estables
   - `classify_exception()`: Clasifica excepciones
   - `classify_error_code()`: Clasifica error codes conocidos

2. **`backend/shared/retry_policy.py`** (NUEVO)
   - `retry_with_policy()`: Retry con backoff y jitter
   - `get_max_retries_for_phase()`: Retries por fase

3. **`backend/shared/phase_timeout.py`** (NUEVO)
   - `run_with_phase_timeout()`: Timeout por fase con evidencias

4. **`backend/shared/evidence_helper.py`** (NUEVO)
   - `ensure_evidence_dir()`: Crea directorio si None
   - `generate_error_evidence()`: Evidencias automáticas
   - `generate_timeout_evidence()`: Evidencias para timeout

5. **`backend/shared/run_summary.py`** (NUEVO)
   - `save_run_summary()`: Guarda métricas de run
   - `load_run_summary()`: Carga summary
   - `list_run_summaries()`: Lista summaries recientes

6. **`backend/api/runs_summary_routes.py`** (NUEVO)
   - `GET /api/runs/summary`: Endpoint para histórico

7. **`backend/adapters/egestiona/execute_auto_upload_gate.py`**
   - Integrado retry policy, timeouts, clasificación de errores
   - Integrado evidencias automáticas
   - Añadido `continue_on_error` parameter
   - Guarda `run_summary.json` al finalizar

8. **`backend/app.py`**
   - Registrado router `runs_summary_router`

9. **`tests/test_error_classifier.py`** (NUEVO)
   - Unit tests para clasificador

10. **`tests/test_retry_policy.py`** (NUEVO)
    - Unit tests para retry policy

11. **`tests/test_run_summary.py`** (NUEVO)
    - Unit tests para run_summary

12. **`tests/egestiona_hardening_e2e.spec.js`** (NUEVO)
    - E2E test protegido

---

## Lista de Error Codes y Reglas de Transient

### Error Codes Estables

| Error Code | Transient | Retry After (ms) | Fase |
|------------|-----------|------------------|------|
| `timeout_login` | ✅ | 2000 | login |
| `timeout_navigation` | ✅ | 2000 | navigation |
| `timeout_grid_load` | ✅ | 2000 | grid_load |
| `timeout_upload` | ❌ | - | upload |
| `timeout_verification` | ✅ | 3000 | verification |
| `grid_parse_mismatch` | ❌ | - | grid_load |
| `buscar_not_clickable` | ✅ | 2000 | grid_load |
| `overlay_blocking` | ✅ | 1500 | grid_load |
| `item_not_found_before_upload` | ✅ | 2000 | upload |
| `upload_failed` | ❌ | - | upload |
| `upload_click_intercepted` | ✅ | 1500 | upload |
| `verification_failed` | ✅ | 3000 | verification |
| `item_still_present_after_upload` | ❌ | - | verification |
| `network_transient` | ✅ | 3000 | todas |
| `portal_transient` | ✅ | 3000 | todas |
| `unexpected_exception` | ❌ | - | todas |

---

## Ejemplo Real de run_summary.json

```json
{
  "run_id": "auto_upload_1705320000_abc12345",
  "platform": "egestiona",
  "coord": "Aigues de Manresa",
  "company_key": "F63161988",
  "person_key": "erm",
  "started_at": "2026-01-15T10:00:00.000000",
  "finished_at": "2026-01-15T10:05:00.000000",
  "duration_ms": 300000,
  "counts": {
    "pending_total": 16,
    "auto_upload": 4,
    "review_required": 8,
    "no_match": 4
  },
  "execution": {
    "attempted_uploads": 3,
    "success_uploads": 2,
    "failed_uploads": 1
  },
  "errors": [
    {
      "phase": "upload",
      "error_code": "upload_failed",
      "message": "Upload failed: Item not found in grid",
      "transient": false,
      "attempt": 1
    }
  ]
}
```

---

## Comandos de Prueba

### Unit Tests

```bash
# Clasificador de errores
pytest tests/test_error_classifier.py -v

# Retry policy
pytest tests/test_retry_policy.py -v

# Run summary
pytest tests/test_run_summary.py -v
```

### E2E Test (Protegido)

```bash
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_hardening_e2e.spec.js --timeout=360000
```

### Prueba Manual Endpoint

```bash
# Listar summaries
curl "http://127.0.0.1:8000/api/runs/summary?limit=10&platform=egestiona"
```

---

## Evidencias Generadas en un Fallo Simulado

**Estructura:**
```
docs/evidence/c2_16/<run_id>/upload/attempt_1/
  - screenshot_fullpage.png
  - screenshot_upload.png
  - html_snippet.html
  - error_log.txt
```

**Ejemplo de error_log.txt:**
```
Error Evidence Report
========================
Timestamp: 2026-01-15T10:05:00.123456
Phase: upload
Attempt: 1
Error Type: Exception
Error Message: Upload failed: Item not found in grid

Context:
{
  "pending_item_key": "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL",
  "upload_attempted": false
}

Traceback:
Traceback (most recent call last):
  ...
```

---

## Confirmación del Sprint

### ✅ Taxonomía de Errores
- Error codes estables definidos
- Clasificador de excepciones y error codes
- Reglas de transient documentadas

### ✅ Retry Policy
- Backoff exponencial suave con jitter
- Límites por fase (login: 1, upload: 0 por defecto, etc.)
- Logging de attempts

### ✅ Watchdogs / Timeouts
- Timeouts por fase (60s-90s)
- Evidencias automáticas en timeout
- Integrado con retry policy

### ✅ Evidencias Automáticas
- Screenshot fullpage + fase específica
- HTML snippet del contenedor relevante
- Error log textual completo
- Directorio temporal si evidence_dir es None

### ✅ Métricas de Fiabilidad
- `run_summary.json` por run
- Endpoint `/api/runs/summary` para histórico
- Estructura completa de métricas

### ✅ Continue-on-Error
- Parámetro `continue_on_error` (default false)
- Lógica segura (solo errores "no side-effect")
- Status "partial" cuando aplica

### ✅ Tests
- Unit tests para clasificador, retry policy, run_summary
- E2E test protegido para validar run_summary

---

**Fin del Resumen de Implementación**

*Última actualización: 2026-01-15*
