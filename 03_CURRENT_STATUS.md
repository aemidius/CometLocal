# Estado actual

## SPRINTs Completados

### C2.27 — Guardrails de contexto + E2E/CI (regresión obligatoria) ✅ CERRADO
- Guardrails backend: Bloquea operaciones WRITE sin contexto humano válido
- Tests unitarios: 10/10 pasando
- Tests E2E: 6/6 pasando (coordination_context_header.spec.js)
- UX frontend: Mensajes humanos cuando falta contexto
- Endpoint debug mejorado con información de tenant

### C2.28 — Hardening E2E + Señales de Operación ✅ CERRADO
- Suite E2E smoke obligatoria consolidada
- Señales operativas backend (logs estructurados JSON)
- Debug badge frontend (solo dev/test)
- Evidencias post-fallo configuradas (screenshots, console logs, network)

### C2.29 — Scheduler + runs audit-ready (operación diaria) ✅ CERRADO
- Modelo RunSummary con estructura audit-ready
- Lock por contexto (filesystem lock)
- Endpoints API: POST /api/runs/start, GET /api/runs/latest, GET /api/runs/<run_id>
- UI mínima: botón ejecutar, lista de runs, acceso a summary.md
- Tests unitarios: 12/12 pasando

### C2.30 — Scheduling real + notificaciones mínimas 🔄 EN CURSO
- Modelo ScheduleV1 con persistencia por contexto
- Tick endpoint + CLI para ejecución automática
- Endpoints CRUD: list, upsert, toggle, delete
- UI mínima: sección Programación en vista Ejecuciones
- Notificaciones mínimas al finalizar run
- Tests unitarios: 15/15 pasando

## Estado Técnico

eGestiona Kern:
- READ-ONLY y WRITE scoped funcionando en entorno real.
- Evidencia completa por run.

Repository:
- Multi-tenant plumbing funcionando
- Contexto humano de coordinación implementado
- Guardrails de contexto activos
- Tests E2E estabilizados
