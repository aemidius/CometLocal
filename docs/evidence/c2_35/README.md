# SPRINT C2.35 — Evidencias de Training Guiado + Acciones Asistidas

## Objetivo
Introducir un TRAINING GUIADO OBLIGATORIO y, solo tras completarlo, habilitar ACCIONES ASISTIDAS humanas sobre NO_MATCH (asignar a tipo existente o crear tipo nuevo), de forma segura, explícita y auditada.

## Archivos de Evidencia

### training_state.json
Ejemplo del estado de training persistente en `data/training/state.json`.

**Estructura:**
```json
{
  "training_completed": false,
  "completed_at": null,
  "version": "C2.35"
}
```

### actions.log.jsonl
Ejemplo de log de acciones asistidas (append-only) en `data/training/actions.log.jsonl`.

**Formato:** Una línea JSON por acción.

**Ejemplo:**
```json
{"timestamp": "2024-01-20T12:00:00Z", "action": "assign_existing_type", "type_id": "T104_AUTONOMOS_RECEIPT", "details": {"platform_key": "egestiona", "alias": "T104.0", "source": "training_assisted_action", "result": "alias_added"}}
```

### 01_training_banner.png
Screenshot del banner de training cuando no está completado.

**Ubicación:** Se generará al ejecutar el flujo E2E o manualmente desde la UI.

### 02_training_wizard.png
Screenshot del wizard de training (paso 1 de 5).

**Ubicación:** Se generará al ejecutar el flujo E2E o manualmente desde la UI.

### 03_assisted_actions_panel.png
Screenshot del panel de acciones asistidas desbloqueadas (tras completar training).

**Ubicación:** Se generará al ejecutar el flujo E2E o manualmente desde la UI.

## Implementación

### Backend
- `backend/training/training_state_store_v1.py`: Store persistente para estado de training
- `backend/training/training_action_logger.py`: Logger de acciones asistidas (append-only)
- `backend/training/routes.py`: Endpoints GET /api/training/state, POST /api/training/complete, POST /api/training/log-action
- `backend/repository/document_repository_routes.py`: Endpoint POST /api/repository/types/{type_id}/add_alias

### Frontend
- `frontend/repository_v3.html`: 
  - Banner de training (`data-testid="training-banner"`)
  - Wizard de training (5 pasos, `data-testid="training-step-*"`)
  - Botones de acción asistida (`data-testid="action-assign-existing-type"`, `data-testid="action-create-new-type"`)
  - Bloqueo de acciones si training no completado

### Tests
- `backend/tests/test_training_state_store.py`: Unit tests para training_state_store
- `backend/tests/test_add_alias_endpoint.py`: Unit tests para add_alias
- `tests/training_and_assisted_actions.spec.js`: E2E test para training y acciones

## Verificación

Para verificar la implementación:

1. **Unit tests:**
   ```bash
   pytest backend/tests/test_training_state_store.py
   pytest backend/tests/test_add_alias_endpoint.py
   ```

2. **E2E test:**
   ```bash
   npx playwright test tests/training_and_assisted_actions.spec.js
   ```

3. **Manual - Cómo reproducir:**
   - Abrir `http://127.0.0.1:8000/repository_v3.html#inicio`
   - Verificar que aparece el banner de training
   - Click en "Iniciar Training"
   - Completar los 5 pasos del wizard
   - Verificar que el banner desaparece
   - Navegar a CAE Plan y generar un plan con items NO_MATCH
   - Verificar que aparecen los botones de acción asistida
   - Probar "Asignar a un tipo existente" o "Crear nuevo tipo"

## Guardrails Implementados

- ✅ Training obligatorio antes de desbloquear acciones
- ✅ Confirmación explícita requerida para completar training
- ✅ Acciones solo visibles si training completado
- ✅ Logging de todas las acciones asistidas (append-only)
- ✅ Añadir alias es aditivo (no borra aliases existentes)
- ✅ Crear tipo requiere wizard completo con confirmación
- ✅ No aprendizaje automático
- ✅ No acciones silenciosas
- ✅ Todo es explícito y reversible

## Notas

- El estado de training es persistente en `data/training/state.json`
- Las acciones se registran en `data/training/actions.log.jsonl` (append-only)
- El training solo se puede completar con `confirm: true` explícito
- Los botones de acción solo aparecen cuando `trainingState.completed === true`
- El endpoint `add_alias` es idempotente (alias duplicado → no-op)
