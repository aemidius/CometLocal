# Testing Playbook — CometLocal

## Unitarios
pytest sobre lógica crítica.

## E2E
Smoke tests BLOQUEANTES:
- coordination_context_header.spec.js
- repo_basic_read.spec.js
- training_and_assisted_actions.spec.js (training + desbloqueo + wizard estable)
- training_no_overlap.spec.js
- impact_preview_e2e.spec.js (preview impacto + confirmación) (bloquea solape de training legacy vs C2.35)

## E2E (adicional)
- matching_debug_report_ui.spec.js (panel humano de diagnóstico cuando AUTO_UPLOAD=0)
