# Arquitectura — CometLocal

- Backend: FastAPI
- Frontend: HTML/JS (`repository_v3.html`)
- Storage: filesystem (`data/`)
- Automatización: Playwright
- Tests: pytest + Playwright E2E

## Runs audit-ready
Cada ejecución genera un paquete completo:
- input.json / result.json
- summary.md / summary.json
- evidencias
- export (si aplica)

## Scheduling
- Cron-like mediante tick endpoint o CLI
- Lock por contexto