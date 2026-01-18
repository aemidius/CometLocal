# SPRINT C2.30 — Scheduling real + notificaciones mínimas (por contexto humano)

**Fecha:** 2026-01-18  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Añadir programación (cron-like) para ejecutar runs automáticamente por contexto humano, con seguridad (locks/guardrails) y notificación mínima del resultado.

---

## Implementación

### A) Modelo de Schedule por Contexto

**Ubicación:** `backend/shared/schedule_models.py` (nuevo módulo)

**Estructura persistente:**
```
data/tenants/<tenant_id>/schedules/schedules.json
```

**Modelo ScheduleV1:**
- `schedule_id`: ID único
- `enabled`: bool (activo/inactivo)
- `plan_id`: Plan a ejecutar
- `dry_run`: bool
- `cadence`: "daily" | "weekly"
- `at_time`: "HH:MM" (formato 24h)
- `weekday`: 0-6 (solo si weekly, 0=lunes, 6=domingo)
- `own_company_key`, `platform_key`, `coordinated_company_key`: Contexto humano guardado
- `created_at` / `updated_at`: Timestamps
- `last_run_id`, `last_run_at`, `last_status`: Tracking de última ejecución

**ScheduleStore:**
- `list_schedules()`: Lista todos los schedules del tenant
- `save_schedule()`: Guarda o actualiza schedule
- `delete_schedule()`: Elimina schedule

### B) Tick Endpoint + CLI

**Endpoint:** `POST /api/schedules/tick`
- Gated a dev/test o API key local (`SCHEDULE_TICK_API_KEY`)
- Recorre schedules habilitados del tenant actual
- Decide si "toca ejecutar ahora" usando `should_execute_now()`
- Si toca: adquiere lock, ejecuta run, actualiza `last_run_*`

**CLI:** `python -m backend.schedules.tick`
- `--all-tenants`: Ejecuta tick para todos los tenants
- `--tenant <tenant_id>`: Ejecuta tick para un tenant específico
- Permite que Windows Task Scheduler / cron lo llame cada 1-5 min

**Lógica "toca ejecutar":**
- **Daily**: Si hora actual >= `at_time` y no se ejecutó hoy
- **Weekly**: Si es el día correcto (`weekday`), hora actual >= `at_time`, y no se ejecutó esta semana

### C) Endpoints CRUD

**Ubicación:** `backend/api/schedules_routes.py` (nuevo módulo)

**Endpoints:**
1. **GET /api/schedules/list** - Lista schedules del contexto
2. **POST /api/schedules/upsert** - Crea o actualiza schedule
3. **POST /api/schedules/toggle** - Habilita/deshabilita schedule
4. **POST /api/schedules/delete** - Elimina schedule
5. **POST /api/schedules/tick** - Ejecuta tick (gated)

**Todos requieren contexto humano válido** (headers humanos)

### D) Frontend: UI Mínima

**Ubicación:** `frontend/repository_v3.html`

**Sección "Programación" en vista "Ejecuciones":**
- Selector cadence (daily/weekly)
- Input hora HH:MM
- Selector weekday (solo si weekly)
- Input plan_id
- Toggle dry_run
- Toggle enabled
- Botón "Guardar programación"
- Lista de schedules con:
  - Estado (Activa/Inactiva)
  - Plan ID, cadencia, hora
  - Última ejecución y estado
  - Botones Activar/Desactivar y Eliminar

**Notificaciones mínimas:**
- Banner/toast al finalizar run (manual o schedule)
- Muestra: "Run completado: SUCCESS/ERROR"
- Incluye Run ID y link a summary.md
- Auto-oculta después de 10 segundos

### E) Tests

**Tests Unitarios:**
- `tests/test_schedule_tick.py`: 7 tests
  - Cálculo "toca ejecutar" para daily (enabled, already run today, before time, disabled)
  - Cálculo "toca ejecutar" para weekly (correct day, wrong day, already run this week)

- `tests/test_schedule_store.py`: 4 tests
  - Guardar y cargar schedule
  - Actualizar schedule existente
  - Eliminar schedule
  - Eliminar schedule inexistente

- `tests/test_schedules_routes.py`: 4 tests
  - GET /api/schedules/list sin contexto -> 400
  - POST /api/schedules/upsert sin contexto -> 400
  - POST /api/schedules/tick sin contexto -> 400
  - POST /api/schedules/tick en prod sin API key -> 403

**Total:** 15/15 tests pasando

---

## Uso

### Activar Tick en Windows Task Scheduler

1. Abrir "Programador de tareas" (Task Scheduler)
2. Crear tarea básica
3. Trigger: "Diariamente" o "Cada 5 minutos"
4. Acción: "Iniciar un programa"
   - Programa: `python`
   - Argumentos: `-m backend.schedules.tick --all-tenants`
   - Iniciar en: `<ruta_del_proyecto>`

### Activar Tick en Cron (Linux/Mac)

```bash
# Ejecutar cada 5 minutos
*/5 * * * * cd /ruta/proyecto && python -m backend.schedules.tick --all-tenants
```

### Ejemplo de curl al Tick Endpoint (dev/test)

```bash
curl -X POST http://127.0.0.1:8000/api/schedules/tick \
  -H "X-Coordination-Own-Company: F63161988" \
  -H "X-Coordination-Platform: egestiona" \
  -H "X-Coordination-Coordinated-Company: test_co"
```

---

## Archivos Modificados/Creados

### Nuevos
1. `backend/shared/schedule_models.py` - Modelo ScheduleV1 y ScheduleStore
2. `backend/shared/schedule_tick.py` - Lógica de tick y "toca ejecutar"
3. `backend/api/schedules_routes.py` - Endpoints CRUD y tick
4. `backend/schedules/tick.py` - CLI para tick
5. `backend/schedules/__init__.py` - Módulo schedules
6. `tests/test_schedule_tick.py` - Tests de lógica tick
7. `tests/test_schedule_store.py` - Tests de persistencia
8. `tests/test_schedules_routes.py` - Tests de endpoints
9. `docs/evidence/c2_30/README.md` - Esta documentación

### Modificados
1. `backend/api/runs_routes.py` - Función `_execute_schedule_run()` para ejecución desde schedule
2. `backend/app.py` - Registro de schedules_router
3. `frontend/repository_v3.html` - UI de Programación y notificaciones
4. `03_CURRENT_STATUS.md` - Estado actualizado
5. `08_CHANGELOG_SUMMARY.md` - Entrada C2.30

---

## Verificación

### Tests Unitarios
```bash
python -m pytest tests/test_schedule_tick.py tests/test_schedule_store.py tests/test_schedules_routes.py -v
```
**Resultado:** ✅ 15 passed

### Tests E2E Smoke
```bash
npx playwright test tests/coordination_context_header.spec.js tests/repo_basic_read.spec.js
```
**Resultado:** ✅ 7 passed

---

## Notas

- El scheduling es **dev-friendly**: no requiere daemon complejo
- El **tick respeta locks**: no ejecuta si hay run activo
- Los **guardrails aseguran contexto humano** antes de crear/ejecutar schedules
- La **notificación mínima** informa al usuario sin ser intrusiva
- El **CLI permite integración** con Windows Task Scheduler / cron
