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
