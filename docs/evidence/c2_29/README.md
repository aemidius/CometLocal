# SPRINT C2.29 — Scheduler + runs audit-ready (operación diaria)

**Fecha:** 2026-01-18  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Añadir un scheduler local (dev-friendly) para ejecutar planes CAE por contexto humano y generar un "run pack" audit-ready por ejecución.

---

## Implementación

### A) Modelo de Run (Backend)

**Ubicación:** `backend/shared/run_summary.py` (nuevo módulo)

**Estructura de directorios:**
```
data/tenants/<tenant_id>/runs/<YYYYMMDD_HHMMSS>__<run_id>/
├── input.json          # Plan/preset/decision pack
├── result.json         # Resultado de ejecución
├── summary.md          # Resumen legible por humanos
├── summary.json        # Resumen para máquina
├── evidence/           # Evidencias (screenshots, logs, etc.)
└── export/             # Exports CAE (si aplica)
```

**Modelo RunSummaryV1:**
- `run_id`: ID único del run
- `started_at` / `finished_at`: Timestamps
- `status`: success|error|blocked|partial_success|canceled
- `context`: RunContextV1 (own/platform/coordinated con nombres humanos)
- `plan_id` / `preset_id` / `decision_pack_id`: ID del input ejecutado
- `dry_run`: Si fue simulación
- `steps_executed`: Lista de pasos ejecutados
- `counters`: docs_processed, uploads_attempted, uploads_ok, uploads_failed
- `artifacts`: Paths relativos a evidencias y exports
- `error`: Mensaje de error si aplica
- `run_dir_rel`: Ruta relativa del run_dir

### B) Lock por Contexto

**Ubicación:** `backend/shared/run_lock.py` (nuevo módulo)

**Implementación:**
- Lock de filesystem: `data/tenants/<tenant_id>/locks/run.lock`
- Si existe y no está stale: bloquea nueva ejecución
- Si stale (> 2h): permite override y loggea warning
- 1 run activo por contexto (lock)

**Tests:** 5/5 pasando

### C) Endpoints API

**Ubicación:** `backend/api/runs_routes.py` (nuevo módulo)

**Endpoints:**
1. **POST /api/runs/start**
   - Body: `{ "plan_id": "...", "dry_run": false }`
   - Requiere contexto humano válido (headers humanos)
   - Crea run_dir
   - Ejecuta plan (reutiliza `CAEExecutionRunnerV1`)
   - Copia evidencias al run_dir
   - Devuelve `{ run_id, status, run_dir_rel }`

2. **GET /api/runs/latest**
   - Devuelve último run summary del contexto actual
   - Requiere contexto humano válido

3. **GET /api/runs/<run_id>**
   - Devuelve summary + paths de artifacts
   - Requiere contexto humano válido
   - Incluye input.json y result.json si existen

**Guardrails:**
- Todos los endpoints requieren contexto humano válido
- Si falta contexto: `400 Bad Request` con mensaje humano
- Lock previene ejecuciones concurrentes por contexto

### D) Frontend (UI Mínima)

**Ubicación:** `frontend/repository_v3.html`

**Funcionalidad:**
- Nueva vista "Ejecuciones" en sidebar (ícono ⚡)
- Botón "Ejecutar plan ahora" con toggle "Dry-run"
- Input para Plan ID
- Lista de "Últimas ejecuciones" (última 1) con:
  - Estado (badge visual)
  - Timestamp de inicio/fin
  - Plan ID
  - Acceso rápido a summary.md
- Si guardrail bloquea: muestra mensaje humano existente

**Integración:**
- Usa `fetchWithContext()` para incluir headers de coordinación
- Maneja errores de contexto con mensaje humano
- No introduce conceptos técnicos ("tenant")

### E) Tests

**Tests Unitarios:**
- `tests/test_run_lock.py`: 5 tests
  - Lock acquire success
  - Lock acquire blocked
  - Lock release
  - Lock stale override
  - Lock release wrong run_id

- `tests/test_run_summary.py`: 3 tests
  - Crear run_dir con estructura correcta
  - Guardar summary y archivos relacionados
  - Generar summary.md legible

- `tests/test_runs_routes.py`: 4 tests
  - POST /api/runs/start sin contexto -> 400
  - POST /api/runs/start con contexto (plan no existe -> 404)
  - GET /api/runs/latest sin contexto -> 400
  - GET /api/runs/<run_id> sin contexto -> 400

**Total:** 12/12 tests pasando

**Tests E2E:**
- Suite smoke bloqueante: 7/7 pasando
- Test E2E específico para scheduler: Opcional (no implementado en esta entrega)

---

## Archivos Modificados/Creados

### Nuevos
1. `backend/shared/run_summary.py` - Modelo RunSummary y funciones de gestión
2. `backend/shared/run_lock.py` - Lock por contexto
3. `backend/api/runs_routes.py` - Endpoints API
4. `tests/test_run_lock.py` - Tests de lock
5. `tests/test_run_summary.py` - Tests de run summary
6. `tests/test_runs_routes.py` - Tests de endpoints
7. `docs/evidence/c2_29/README.md` - Esta documentación

### Modificados
1. `backend/app.py` - Registro de runs_router
2. `frontend/repository_v3.html` - UI scheduler
3. `03_CURRENT_STATUS.md` - Estado actualizado
4. `08_CHANGELOG_SUMMARY.md` - Entrada C2.29

---

## Verificación

### Tests Unitarios
```bash
python -m pytest tests/test_run_lock.py tests/test_run_summary.py tests/test_runs_routes.py -v
```
**Resultado:** ✅ 12 passed

### Tests E2E Smoke
```bash
npx playwright test tests/coordination_context_header.spec.js tests/repo_basic_read.spec.js
```
**Resultado:** ✅ 7 passed

---

## Uso

### Ejecutar un Plan

1. Seleccionar contexto humano (Empresa propia, Plataforma, Empresa coordinada)
2. Navegar a vista "Ejecuciones"
3. Introducir Plan ID
4. Activar/desactivar "Dry-run" según necesidad
5. Click en "Ejecutar plan ahora"
6. Ver resultado en "Últimas ejecuciones"

### Acceder a Evidencias

- Click en "📄 Ver summary.md" para abrir el resumen legible
- Los archivos están en: `data/tenants/<tenant_id>/runs/<YYYYMMDD_HHMMSS>__<run_id>/`

---

## Notas

- El scheduler es **dev-friendly**: no requiere configuración compleja
- Cada run genera un **pack audit-ready** completo
- El **lock previene ejecuciones concurrentes** por contexto
- Los **guardrails aseguran contexto humano** antes de ejecutar
- La estructura de directorios es **compatible con multi-tenant** existente
