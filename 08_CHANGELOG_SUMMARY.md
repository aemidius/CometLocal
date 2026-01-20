# 08_CHANGELOG_SUMMARY — CometLocal

## C2.32A
- Introducción de `own_company_key`
- Filtrado de trabajadores por empresa propia
- Migración suave de people.json

## C2.33
- UX unificada
- Config integrada en repository_v3.html
- Modo experto
- Training guiado (base UX)
- Vista de ejecuciones humanizada

## C2.34
- Informe determinista de matching (`matching_debug_report`) para items NO_MATCH/REVIEW_REQUIRED
- Panel UI humano “¿Por qué no se ha subido?” con acciones sugeridas + data-testid para E2E
- Nuevos tests: unitarios (reasons) + Playwright UI

## C2.35
- Training guiado persistente (5 pasos) que **desbloquea poder**
- Acciones asistidas (post-training):
  - Asignar a tipo existente (alias aditivo, idempotente)
  - Crear tipo nuevo desde solicitud (wizard)
- Logging append-only de acciones asistidas (`data/training/actions.log.jsonl`)
- Endpoints training: GET state / POST complete
- Tests: unitarios + E2E

## C2.35.1
- Estabilización del wizard (E2E): `data-testid` en Next/Previous, fix de click interception
- Training complete usa `fetchWithContext` (headers de coordinación)
- E2E aislado: reset del estado de training entre tests

## C2.35.2
- Unificación de training: evita solape entre tutorial legacy y training C2.35
- Legacy neutralizado cuando C2.35 está activo; no auto-start cuando C2.35 está completado
- Hard-guard visual `dismissLegacyTutorialIfPresent()`
- Nuevo E2E: `training_no_overlap.spec.js`

## C2.36
- Preview de impacto read-only antes de acciones asistidas
- Motor de sugerencias explicables y deterministas
- Confirmación reforzada previa a aplicar cambios

