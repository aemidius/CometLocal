# C2.16.1 — Cierre Hardening: Ajustes Finales

**Fecha:** 2026-01-15  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Dejar C2.16 listo para producción con ajustes finales en política de reintentos y smoke real.

---

## Ajustes Implementados

### A) item_not_found_before_upload ✅

**Archivos modificados:**
- `backend/shared/error_classifier.py`
- `backend/shared/retry_policy.py`
- `backend/adapters/egestiona/execute_auto_upload_gate.py`

**Cambios:**
- `item_not_found_before_upload` permite SOLO 1 retry
- El retry fuerza: refresh del listado + volver a primera página
- Si vuelve a fallar → definitivo (no más retries)

**Implementación:**
- Añadido `SINGLE_RETRY_ERROR_CODES = ["item_not_found_before_upload"]`
- `get_max_retries_for_phase()` retorna 1 para este error code
- En `execute_auto_upload_gate.py`, cuando se detecta `item_not_found_before_upload`:
  - Busca frame del listado
  - Detecta paginación y va a primera página
  - Espera 1.5s para que se actualice
  - Reintenta upload
  - Si falla de nuevo, marca como definitivo

---

### B) Upload timeout seguro ✅

**Archivos modificados:**
- `backend/shared/error_classifier.py`
- `backend/shared/retry_policy.py`

**Cambios:**
- `timeout_upload` puede ser reintentable SOLO si `context.upload_attempted=false`
- Si `upload_attempted=true`, no retry

**Implementación:**
- En `classify_exception()` para fase "upload":
  - Lee `context.upload_attempted`
  - Si `upload_attempted=false`: `is_transient=True`, `retry_after_ms=2000`
  - Si `upload_attempted=true`: `is_transient=False`, `retry_after_ms=None`
- En `get_max_retries_for_phase()`:
  - Si `error_code == "timeout_upload"`:
    - Si `context.upload_attempted=true`: retorna 0 (no retry)
    - Si `context.upload_attempted=false`: retorna 1 (1 retry)

---

### C) run_summary: rutas de evidencia principales ✅

**Archivos modificados:**
- `backend/shared/run_summary.py`
- `backend/adapters/egestiona/execute_auto_upload_gate.py`

**Cambios:**
- Añadido `evidence_root` y `evidence_paths` en `run_summary.json`
- Endpoint `/api/runs/summary` lo incluye automáticamente

**Implementación:**
- `save_run_summary()` ahora acepta `evidence_root` y `evidence_paths`
- En `execute_auto_upload_gate.py`:
  - `evidence_root = str(execution_dir.parent)`
  - `evidence_paths = {"execution_dir": str(execution_dir), ...}`
  - Añade rutas de evidencias de errores si existen (`{phase}_evidence`)

**Ejemplo de run_summary.json:**
```json
{
  "run_id": "auto_upload_...",
  "platform": "egestiona",
  "evidence_root": "data/runs/auto_upload_...",
  "evidence_paths": {
    "execution_dir": "data/runs/auto_upload_.../execution",
    "upload_evidence": "data/runs/auto_upload_.../execution/upload/attempt_1"
  },
  ...
}
```

---

## Resultado de Tests

### Unit Tests ✅

**Comando:**
```bash
python -m pytest tests/test_error_classifier.py tests/test_retry_policy.py tests/test_run_summary.py -v
```

**Resultado:**
```
======================== 21 passed, 8 warnings in 2.91s =======================
```

**Tests pasados:**
- ✅ `test_error_classifier.py`: 8 tests
- ✅ `test_retry_policy.py`: 8 tests
- ✅ `test_run_summary.py`: 5 tests

---

### E2E Test (Protegido) ⏳

**Comando:**
```bash
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_hardening_e2e.spec.js --timeout=360000
```

**Estado:** Pendiente de ejecución manual (requiere `EGESTIONA_REAL_UPLOAD_TEST=1`)

**Resultado esperado:**
- ✅ HTTP 200 para `build_auto_upload_plan`
- ✅ HTTP 200 para `execute_auto_upload` (si hay AUTO_UPLOAD)
- ✅ `run_summary.json` existe en `data/runs/<run_id>/run_summary.json`
- ✅ HTTP 200 para `/api/runs/summary`
- ✅ Run encontrado en summary list con `evidence_root` y `evidence_paths`

---

## Archivos Modificados

1. **`backend/shared/error_classifier.py`**
   - Ajustado `timeout_upload` para depender de `upload_attempted`
   - Añadido `retry_action` en details de `item_not_found_before_upload`

2. **`backend/shared/retry_policy.py`**
   - Añadido `SINGLE_RETRY_ERROR_CODES`
   - `get_max_retries_for_phase()` ahora acepta `context` y maneja `timeout_upload` condicionalmente
   - `retry_with_policy()` y `retry_with_policy_async()` ahora aceptan `context`

3. **`backend/shared/run_summary.py`**
   - `save_run_summary()` ahora acepta `evidence_root` y `evidence_paths`

4. **`backend/adapters/egestiona/execute_auto_upload_gate.py`**
   - Implementado retry con refresh para `item_not_found_before_upload`
   - Añadido `evidence_root` y `evidence_paths` al guardar `run_summary`
   - Añadido `upload_attempted` al context de timeout evidence

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
      "error_code": "item_not_found_before_upload",
      "message": "Item not found before upload",
      "transient": true,
      "attempt": 1
    }
  ],
  "evidence_root": "data/runs/auto_upload_1705320000_abc12345",
  "evidence_paths": {
    "execution_dir": "data/runs/auto_upload_1705320000_abc12345/execution",
    "upload_evidence": "data/runs/auto_upload_1705320000_abc12345/execution/upload/attempt_1"
  }
}
```

---

## Confirmación del Cierre

### ✅ Ajuste item_not_found_before_upload
- Solo 1 retry permitido
- Retry fuerza refresh + primera página
- Si falla de nuevo → definitivo

### ✅ Upload timeout seguro
- Retry solo si `upload_attempted=false`
- Si `upload_attempted=true` → no retry

### ✅ run_summary con evidence_paths
- `evidence_root` y `evidence_paths` incluidos
- Endpoint `/api/runs/summary` lo expone

### ✅ Tests Unitarios
- 21 tests pasando
- Sin errores críticos

### ⏳ Smoke Real E2E
- Pendiente de ejecución manual (requiere `EGESTIONA_REAL_UPLOAD_TEST=1`)

---

**Fin del Resumen de Cierre**

*Última actualización: 2026-01-15*
