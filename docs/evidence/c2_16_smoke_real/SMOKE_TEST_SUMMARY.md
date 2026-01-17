# C2.16.1 — Smoke Test Real

**Fecha:** 2026-01-15  
**Estado:** ⏳ PENDIENTE DE EJECUCIÓN

---

## Objetivo

Validar que el hardening funciona en producción real con:
1. Unit tests pasando
2. E2E test protegido ejecutado
3. `run_summary.json` generado y listado por `/api/runs/summary`

---

## Comandos de Ejecución

### 1. Unit Tests

```bash
python -m pytest tests/test_error_classifier.py -v
python -m pytest tests/test_retry_policy.py -v
python -m pytest tests/test_run_summary.py -v
```

**Resultado esperado:** ✅ Todos los tests pasan

### 2. E2E Test (Protegido)

```bash
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_hardening_e2e.spec.js --timeout=360000
```

**Resultado esperado:**
- ✅ HTTP 200 para `build_auto_upload_plan`
- ✅ HTTP 200 para `execute_auto_upload` (si hay AUTO_UPLOAD)
- ✅ `run_summary.json` existe
- ✅ HTTP 200 para `/api/runs/summary`
- ✅ Run encontrado en summary list

---

## Evidencias Generadas

**Directorio:** `docs/evidence/c2_16_smoke_real/<run_id>/`

**Archivos esperados:**
- `plan_response.json`
- `upload_response.json` (si se ejecutó upload)
- `summary_list_response.json`
- `test_summary.json`
- `run_summary.json` (copiado desde `data/runs/<run_id>/run_summary.json`)

---

## Ajustes Implementados (C2.16.1)

### A) item_not_found_before_upload
- ✅ Solo 1 retry permitido
- ✅ Retry fuerza: refresh del listado + volver a primera página
- ✅ Si vuelve a fallar → definitivo (no más retries)

### B) Upload timeout seguro
- ✅ `timeout_upload` puede ser reintentable SOLO si `context.upload_attempted=false`
- ✅ Si `upload_attempted=true`, no retry

### C) run_summary: rutas de evidencia
- ✅ Añadido `evidence_root` y `evidence_paths` en `run_summary.json`
- ✅ Endpoint `/api/runs/summary` lo incluye

---

**Fin del Resumen**

*Última actualización: 2026-01-15*
