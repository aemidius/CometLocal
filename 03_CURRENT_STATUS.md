# 03_CURRENT_STATUS — CometLocal

## Estado general
Sprint C2.32A, C2.33, C2.34 y C2.35 (**incl. C2.35.1**) **COMPLETADOS**.

**C2.35.2 (unificación training, anti-solape legacy) COMPLETADO.**

El sistema se encuentra en estado **estable y operativo** para uso humano real.

## Funcionalidades verificadas
- Configuración de Trabajadores funcional
- Persistencia correcta de `own_company_key` en `people.json`
- Contexto humano obligatorio (empresa propia / plataforma / empresa coordinada)
- UX unificada en `repository_v3.html`
- Modo experto funcional
- Matching: informe explicativo determinista (`matching_debug_report`) cuando no hay AUTO_UPLOAD
- UI: panel humano “¿Por qué no se ha subido?” con acciones sugeridas
- Training guiado (5 pasos) persistente y **desbloquea** acciones asistidas
- Acciones asistidas (tras training):
  - Asignar a tipo existente (añade alias de forma aditiva)
  - Crear tipo nuevo desde solicitud (wizard)
- Logging append-only de acciones asistidas (`actions.log.jsonl`)
- Tests unit + E2E para training y acciones asistidas (wizard incluido)
- No solape de trainings: legacy bloqueado cuando C2.35 está activo (E2E anti-solape)

## Riesgos actuales
- Matching aún depende de aliases/configuración; el sistema **explica** pero no “autocorrige” (por diseño).
- Evidencias visuales (screenshots) no se generan en CI: se capturan manualmente cuando se requiera demo/auditoría.

## Próximo foco
- C2.36 — Sugerencias inteligentes + preview de impacto (antes de confirmar cambios en aliases/tipos)
- UX de “corrección” más guiada (sin auto-aprendizaje silencioso)
