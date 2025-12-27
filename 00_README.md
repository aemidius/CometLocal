# CometLocal — Proyecto (CAE Agent)

CometLocal es un agente local para automatizar tareas CAE/PRL en portales empresariales reales usando Playwright + FastAPI, con trazabilidad y evidencia auditable por ejecución.

## Qué hace hoy (resumen)
- Backend FastAPI con endpoints de “runs” (escenarios).
- Playwright integrado (headless por defecto, headful para depuración).
- UI mínima (Home + navegación + monitor LLM + Runs viewer + Config).
- Evidencia por run: capturas PNG + dumps + manifests + run_finished.json.
- Plataforma CAE real: eGestiona (tenant coordinate.egestiona.es) con:
  - READ-ONLY: listar pendientes, abrir detalle (scoped).
  - WRITE (guardrails): subir documento pendiente para TEDELAB/Emilio, con confirmación inequívoca.

## Filosofía de seguridad
- SUCCESS es implícito si no hay excepción terminal.
- Guardrails estrictos: nunca ejecutar WRITE fuera de scope.
- Evidencia y metadatos siempre persistidos.
- Decisiones ambiguas (p.ej. fechas) se resuelven con reglas deterministas y/o asistencia operador.
