# Changelog

Resumen de hitos alcanzados.

---

## SPRINT C2.27 — Guardrails de contexto + E2E/CI (regresión obligatoria)

**Fecha:** 2026-01-18  
**Estado:** ✅ COMPLETADO

### Objetivos
1. Implementar guardrails para prevenir operaciones WRITE sin contexto humano válido
2. Estabilizar tests E2E para que sean robustos y adaptativos
3. Asegurar regresión obligatoria en CI/local

### Implementación

#### Backend
- **Nuevo módulo:** `backend/shared/context_guardrails.py`
  - Lógica centralizada para validar contexto en operaciones WRITE
  - Middleware HTTP global registrado en `backend/app.py`
  - Bloquea WRITE sin contexto humano completo (3 headers) salvo legacy en dev/test
  - Responde `400 Bad Request` con mensaje humano claro

- **Tests unitarios:** `tests/test_context_guardrails.py`
  - 10 tests cubriendo todos los escenarios
  - WRITE sin contexto -> 400
  - WRITE con contexto -> OK
  - WRITE con legacy + dev/test -> OK
  - WRITE con legacy + prod -> 400
  - READ sin contexto -> OK

#### Frontend
- **UX mejorada:** `frontend/repository_v3.html`
  - Función `showContextRequiredMessage()`: Banner temporal con mensaje humano
  - Resalta visualmente los 3 selects con borde rojo
  - Intercepta error `missing_coordination_context` en `fetchWithContext()`

#### Endpoint Debug
- **Mejora:** `backend/repository/settings_routes.py`
  - Endpoint `GET /api/repository/debug/data_dir` mejorado
  - Incluye `tenant_id`, `tenant_source`, `tenant_data_dir` derivados del contexto
  - Gated por ENVIRONMENT (solo dev/test)

#### Tests E2E
- **Estabilización:** `tests/coordination_context_header.spec.js`
  - Tests adaptativos (skip si no hay suficientes opciones)
  - Verificación de aislamiento usando endpoint debug
  - Nuevo test: "should block WRITE operations without context"
  - Inclusión de headers de coordinación en peticiones directas
  - 6 tests pasando

### Resultados
- ✅ Tests unitarios: 10/10 pasando
- ✅ Tests E2E: 6/6 pasando
- ✅ Guardrail funcional en producción
- ✅ UX funcional con mensajes humanos

### Archivos Modificados
- `backend/shared/context_guardrails.py` (nuevo)
- `backend/app.py`
- `tests/test_context_guardrails.py` (nuevo)
- `frontend/repository_v3.html`
- `backend/repository/settings_routes.py`
- `tests/coordination_context_header.spec.js`
- `docs/evidence/c2_27/README.md` (nuevo)

---

## SPRINT C2.31 — Onboarding + Demo dataset (5-minute experience)

**Fecha:** 2026-01-18  
**Estado:** ✅ COMPLETADO

### Objetivos
1. Permitir que un usuario nuevo entienda y pruebe CometLocal en ≤5 minutos
2. Sin configurar datos reales ni tocar CAE de verdad
3. Experiencia guiada con dataset demo controlado

### Implementación

#### Dataset Demo Controlado
- **Nuevo módulo:** `backend/shared/demo_dataset.py`
  - `ensure_demo_dataset()`: Crea dataset completo automáticamente
  - Empresa propia: "Empresa Demo SL" (`DEMO_COMPANY`)
  - Plataforma: "Plataforma Demo" (`demo_platform`)
  - Empresa coordinada: "Cliente Demo SA" (`DEMO_CLIENT`)
  - 3 tipos de documentos: Recibo SS, Contrato, Seguro
  - 3 documentos demo: Metadata sin PDFs reales
  - 1 plan CAE demo: `demo_plan_001`
  - 1 schedule demo: Deshabilitado por defecto
  - Tests: 3/3 pasando

#### Modo Demo (flag)
- **Detección:** `ENVIRONMENT=demo`
  - Auto-selección de contexto demo en frontend
  - Badge discreto "Modo DEMO" en UI
  - Permite runs y scheduling (dry-run real)
  - NO permite integraciones reales (uploader deshabilitado)

#### Primer Run Guiado
- **UI:** `frontend/repository_v3.html`
  - Banner inicial: "Bienvenido a CometLocal — Ejecuta un run demo"
  - Botón: "⚡ Ejecutar run demo"
  - Al finalizar: Abre `summary.md` automáticamente
  - Resalta evidencias generadas

#### Documentación
- **Nuevo archivo:** `docs/ONBOARDING.md`
  - Requisitos
  - `python -m uvicorn ...` con `ENVIRONMENT=demo`
  - Qué probar (3 pasos)
  - Dónde ver resultados
- **README.md actualizado:** Apunta a onboarding

#### Tests
- **Tests unitarios:**
  - `tests/test_demo_dataset.py`: 3 tests
    - `test_is_demo_mode`: Detecta ENVIRONMENT=demo
    - `test_get_demo_context`: Retorna contexto demo
    - `test_ensure_demo_dataset`: Crea dataset completo
  - Total: 3/3 pasando

### Archivos Modificados/Creados
- `backend/shared/demo_dataset.py` (nuevo)
- `backend/app.py` (inicialización demo en startup)
- `backend/api/health` (añade campo `environment`)
- `frontend/repository_v3.html` (UI demo + banner onboarding)
- `docs/ONBOARDING.md` (nuevo)
- `README.md` (apunta a onboarding)
- `tests/test_demo_dataset.py` (nuevo)
- `03_CURRENT_STATUS.md` (actualizado)
- `08_CHANGELOG_SUMMARY.md` (esta entrada)

---

## SPRINT C2.30 — Scheduling real + notificaciones mínimas (por contexto humano)

**Fecha:** 2026-01-18  
**Estado:** ✅ COMPLETADO

### Objetivos
1. Añadir programación (cron-like) para ejecutar runs automáticamente por contexto humano
2. Implementar seguridad (locks/guardrails) en scheduling
3. Añadir notificación mínima del resultado

### Implementación

#### Modelo de Schedule
- **Nuevo módulo:** `backend/shared/schedule_models.py`
  - `ScheduleV1`: Modelo con schedule_id, enabled, plan_id, cadence, at_time, weekday
  - Guarda contexto humano (own_company_key, platform_key, coordinated_company_key)
  - `ScheduleStore`: Persistencia en `data/tenants/<tenant_id>/schedules/schedules.json`
  - Tests: 4/4 pasando

#### Tick Endpoint + CLI
- **Endpoint:** `POST /api/schedules/tick`
  - Gated a dev/test o API key local
  - Recorre schedules habilitados del tenant
  - Ejecuta los que "tocan ejecutar ahora"
  - Respeta locks (no ejecuta si hay run activo)

- **CLI:** `python -m backend.schedules.tick`
  - `--all-tenants`: Ejecuta para todos los tenants
  - `--tenant <tenant_id>`: Ejecuta para un tenant específico
  - Integrable con Windows Task Scheduler / cron

- **Lógica "toca ejecutar":**
  - Daily: Si hora >= at_time y no se ejecutó hoy
  - Weekly: Si es el día correcto, hora >= at_time, y no se ejecutó esta semana
  - Tests: 7/7 pasando

#### Endpoints CRUD
- **Nuevo módulo:** `backend/api/schedules_routes.py`
  - `GET /api/schedules/list`: Lista schedules del contexto
  - `POST /api/schedules/upsert`: Crea o actualiza schedule
  - `POST /api/schedules/toggle`: Habilita/deshabilita schedule
  - `POST /api/schedules/delete`: Elimina schedule
  - Todos requieren contexto humano válido
  - Tests: 4/4 pasando

#### Frontend
- **UI mínima:** `frontend/repository_v3.html`
  - Sección "Programación" en vista "Ejecuciones"
  - Formulario: cadence, hora, weekday, plan_id, dry_run, enabled
  - Lista de schedules con estado y última ejecución
  - Botones Activar/Desactivar y Eliminar

- **Notificaciones mínimas:**
  - Banner/toast al finalizar run (manual o schedule)
  - Muestra: "Run completado: SUCCESS/ERROR"
  - Incluye Run ID y link a summary.md
  - Auto-oculta después de 10 segundos

#### Tests
- **Tests unitarios:**
  - `tests/test_schedule_tick.py`: 7 tests (cálculo "toca ejecutar")
  - `tests/test_schedule_store.py`: 4 tests (persistencia)
  - `tests/test_schedules_routes.py`: 4 tests (endpoints)
  - Total: 15/15 pasando

### Archivos Modificados/Creados
- `backend/shared/schedule_models.py` (nuevo)
- `backend/shared/schedule_tick.py` (nuevo)
- `backend/api/schedules_routes.py` (nuevo)
- `backend/schedules/tick.py` (nuevo)
- `frontend/repository_v3.html` (UI Programación + notificaciones)
- `backend/app.py` (registro de schedules_router)
- `tests/test_schedule_tick.py` (nuevo)
- `tests/test_schedule_store.py` (nuevo)
- `tests/test_schedules_routes.py` (nuevo)
- `docs/evidence/c2_30/README.md` (nuevo)

---

## SPRINT C2.29 — Scheduler + runs audit-ready (operación diaria)

**Fecha:** 2026-01-18  
**Estado:** 🔄 EN CURSO

### Objetivos
1. Añadir scheduler local (dev-friendly) para ejecutar planes CAE por contexto humano
2. Generar "run pack" audit-ready por ejecución
3. Implementar lock por contexto para evitar ejecuciones concurrentes

### Implementación

#### Modelo de Run
- **Nuevo módulo:** `backend/shared/run_summary.py`
  - `RunSummaryV1`: Modelo con run_id, status, context, counters, artifacts
  - `RunContextV1`: Contexto humano (own/platform/coordinated con nombres)
  - `create_run_dir()`: Crea estructura `data/tenants/<tenant_id>/runs/<YYYYMMDD_HHMMSS>__<run_id>/`
  - `save_run_summary()`: Guarda summary.json, summary.md, input.json, result.json
  - `generate_summary_md()`: Genera summary.md legible por humanos

#### Lock por Contexto
- **Nuevo módulo:** `backend/shared/run_lock.py`
  - Lock de filesystem: `data/tenants/<tenant_id>/locks/run.lock`
  - Bloquea nueva ejecución si existe lock activo
  - Permite override si lock está stale (> 2h)
  - Tests: 5/5 pasando

#### Endpoints API
- **Nuevo módulo:** `backend/api/runs_routes.py`
  - `POST /api/runs/start`: Inicia run (requiere contexto humano, crea run_dir, ejecuta plan)
  - `GET /api/runs/latest`: Obtiene último run del contexto
  - `GET /api/runs/<run_id>`: Obtiene run específico con summary, input, result
  - Integrado con `CAEExecutionRunnerV1` existente
  - Copia evidencias del executor al run_dir audit-ready

#### Frontend
- **UI mínima:** `frontend/repository_v3.html`
  - Nueva vista "Ejecuciones" en sidebar
  - Botón "Ejecutar plan ahora" con toggle "Dry-run"
  - Lista de últimas ejecuciones (última 1) con estado y timestamp
  - Acceso rápido a summary.md (abrir/descargar)
  - Usa mensaje humano existente si guardrail bloquea

#### Tests
- **Tests unitarios:**
  - `tests/test_run_lock.py`: 5 tests (lock normal, stale, release)
  - `tests/test_run_summary.py`: 3 tests (crear run_dir, guardar summary, generar MD)
  - `tests/test_runs_routes.py`: 4 tests (guardrail, endpoints)
  - Total: 12/12 pasando

### Archivos Modificados/Creados
- `backend/shared/run_summary.py` (nuevo)
- `backend/shared/run_lock.py` (nuevo)
- `backend/api/runs_routes.py` (nuevo)
- `frontend/repository_v3.html` (UI scheduler)
- `backend/app.py` (registro de runs_router)
- `tests/test_run_lock.py` (nuevo)
- `tests/test_run_summary.py` (nuevo)
- `tests/test_runs_routes.py` (nuevo)

---

## SPRINT C2.28 — Hardening E2E + Señales de Operación

**Fecha:** 2026-01-18  
**Estado:** 🔄 EN CURSO

### Objetivos
1. Consolidar suite E2E smoke obligatoria
2. Añadir señales operativas claras cuando algo va mal (sin exponer "tenant")
3. Dejar evidencias accionables para debugging post-fallo

### Implementación (en progreso)

#### Suite E2E Smoke Obligatoria
- `tests/coordination_context_header.spec.js` - Marcado como BLOQUEANTE
- `tests/repo_basic_read.spec.js` - Test básico de lectura (BLOQUEANTE)
  - Abrir app
  - Contexto humano válido
  - Listar documentos
  - Navegar a calendario
  - Volver a buscar documentos

#### Señales Operativas Backend
- **Logs estructurados:** `backend/shared/context_guardrails.py`
  - Función `_log_guardrail_block()` añadida
  - Log JSON con: event, reason, route, headers presentes, timestamp
  - NO incluye palabra "tenant"
  - Salida a stdout (JSON estructurado)

#### Señales Operativas Frontend
- **Debug badge:** `frontend/repository_v3.html`
  - Visible solo en dev/test (localhost/127.0.0.1 o flag debug=true)
  - Muestra: Empresa propia, Plataforma, Empresa coordinada, Estado
  - Esquina inferior derecha, discreto

#### Evidencias Post-Fallo
- **Helper:** `tests/helpers/e2e_evidence.js` (nuevo)
  - Guarda screenshot final
  - Guarda console_log.txt
  - Guarda last_network.json (últimos 50 requests)
  - Guarda test_info.json
  - Estructura: `docs/evidence/e2e_failures/<spec>/<test>_<timestamp>/`

### Archivos Modificados
- `tests/coordination_context_header.spec.js`
- `tests/repo_basic_read.spec.js`
- `backend/shared/context_guardrails.py`
- `frontend/repository_v3.html` (debug badge)
- `playwright.config.js`
- `tests/helpers/e2e_evidence.js` (nuevo)
