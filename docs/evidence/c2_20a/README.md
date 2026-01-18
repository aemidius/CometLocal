# SPRINT C2.20A — Batch Review + Presets (operación masiva de Decision Packs)

## Resumen

Extensión de la UI de plan_review para permitir:
- Selección múltiple de items y aplicación de decisiones en lote
- Creación y reutilización de "Presets" (plantillas de decisiones)
- Generación rápida de Decision Packs a partir de presets + selecciones

## Archivos creados/modificados

### Nuevos archivos:
- `backend/shared/decision_preset.py` - Modelos Pydantic para DecisionPresetV1
- `backend/shared/decision_preset_store.py` - Store persistente para presets
- `backend/api/preset_routes.py` - API endpoints para presets
- `tests/test_decision_preset.py` - Tests unitarios
- `docs/evidence/c2_20a/README.md` - Esta documentación

### Archivos modificados:
- `backend/app.py` - Registro de preset_router
- `frontend/repository_v3.html` - Extendido con:
  - Batch selection (checkboxes + barra de acciones)
  - Modal batch actions
  - Presets manager
  - Integración de presets en tabla

## Funcionalidades implementadas

### 1. Batch Selection
- Checkbox por fila en la tabla de items
- Checkbox "Select all" en el header
- Barra de acciones batch (sticky) que aparece cuando hay items seleccionados
- Contador de items seleccionados

### 2. Batch Actions
- **Apply SKIP**: Aplica SKIP a todos los items seleccionados (requiere reason)
- **Apply FORCE_UPLOAD**: Aplica FORCE_UPLOAD (requiere file_path)
- **Apply MARK_AS_MATCH**: Aplica MARK_AS_MATCH (requiere local_doc_id)
- **Apply Preset…**: Aplica un preset seleccionado a los items que coincidan

### 3. Decision Presets
- **Modelo**: DecisionPresetV1 con scope (platform, type_id, subject_key, period_key), action, defaults
- **Store**: Persistencia en `data/presets/decision_presets_v1.json`
- **API**: GET, POST, disable endpoints
- **UI Manager**: Crear, listar, desactivar presets

### 4. Integración en Tabla
- Columna "Preset" que muestra badge si hay preset aplicable
- No auto-aplica: solo sugiere y permite aplicar manualmente

## Ejemplos

### Ejemplo 1: Crear un preset SKIP

```json
POST /api/presets/decision_presets
{
  "name": "Skip T104",
  "scope": {
    "platform": "egestiona",
    "type_id": "T104_AUTONOMOS_RECEIPT",
    "subject_key": null,
    "period_key": null
  },
  "action": "SKIP",
  "defaults": {
    "reason": "No disponible"
  }
}

Response:
{
  "preset_id": "preset_a1b2c3d4e5f6g7h8",
  "preset": {
    "preset_id": "preset_a1b2c3d4e5f6g7h8",
    "name": "Skip T104",
    "scope": {...},
    "action": "SKIP",
    "defaults": {
      "reason": "No disponible"
    },
    "is_enabled": true
  }
}
```

### Ejemplo 2: Aplicar preset en lote

1. Seleccionar 10 items del plan (checkboxes)
2. Clic en "Apply Preset…"
3. Seleccionar preset "Skip T104"
4. El sistema aplica el preset solo a los items que coincidan con el scope
5. Se actualizan las draft decisions
6. Guardar Decision Pack

### Ejemplo 3: Decision Pack generado con batch actions

```json
{
  "plan_id": "plan_abc123",
  "decision_pack_id": "pack_def456",
  "decisions": [
    {
      "item_id": "item_1",
      "action": "SKIP",
      "reason": "Batch SKIP applied",
      "decided_by": "human"
    },
    {
      "item_id": "item_2",
      "action": "SKIP",
      "reason": "Batch SKIP applied",
      "decided_by": "human"
    },
    // ... 8 más
  ]
}
```

## Pasos para reproducir manualmente

### 1. Crear un preset SKIP

```bash
# 1. Abrir navegador en http://localhost:8000
# 2. Navegar a "Revisión Plan (CAE)"
# 3. Cargar un plan_id
# 4. Clic en "📋 Presets"
# 5. Clic en "Crear Nuevo Preset"
# 6. Rellenar:
#    - Nombre: "Skip T104"
#    - Type ID: "T104_AUTONOMOS_RECEIPT"
#    - Action: SKIP
#    - Default Reason: "No disponible"
# 7. Clic en "Guardar Preset"
```

O vía API:

```bash
curl -X POST "http://127.0.0.1:8000/api/presets/decision_presets" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Skip T104",
    "scope": {
      "platform": "egestiona",
      "type_id": "T104_AUTONOMOS_RECEIPT"
    },
    "action": "SKIP",
    "defaults": {
      "reason": "No disponible"
    }
  }'
```

### 2. Seleccionar múltiples items y aplicar preset

1. En la tabla de items, marcar checkboxes de 10 items
2. Verificar que aparece la barra de acciones batch con contador
3. Clic en "Apply Preset…"
4. Seleccionar preset "Skip T104" (por número o ID)
5. Verificar que se aplica solo a items que coincidan con el scope
6. Verificar que las draft decisions se actualizan
7. La selección se limpia automáticamente

### 3. Aplicar SKIP en lote manualmente

1. Seleccionar múltiples items (checkboxes)
2. Clic en "Apply SKIP"
3. En el modal, introducir razón: "No disponible en este momento"
4. Clic en "Aplicar a N item(s)"
5. Verificar que todos los items seleccionados tienen decisión SKIP
6. Verificar que la barra de acciones desaparece

### 4. Guardar Decision Pack y ejecutar

1. Después de aplicar decisiones en lote, verificar que el contador de "Items decididos" aumenta
2. Clic en "Guardar Pack"
3. Verificar que aparece el `decision_pack_id`
4. Clic en "Ejecutar con Pack"
5. Verificar que el run se ejecuta correctamente

### 5. Verificar preset en tabla

1. En la tabla de items, verificar columna "Preset"
2. Items que coincidan con el scope del preset deberían mostrar badge "Preset"
3. Hacer hover para ver detalles

## Tests

Ejecutar tests unitarios:

```bash
python -m pytest tests/test_decision_preset.py -v
```

Tests incluidos:
- `test_preset_id_stable_hash` - Verifica que preset_id es estable
- `test_preset_store_upsert_and_list_filters` - Verifica store y filtros
- `test_disable_preset` - Verifica desactivación
- `test_preset_matches_item` - Verifica matching de items

## Ubicación de datos

- **Presets almacenados**: `data/presets/decision_presets_v1.json`
- **Decision Packs**: `data/runs/{plan_id}/decision_packs/{decision_pack_id}.json`

## Data test IDs añadidos

- `batch-select-all` - Checkbox select all
- `batch-action-skip` - Botón Apply SKIP
- `batch-action-force` - Botón Apply FORCE_UPLOAD
- `batch-action-mark` - Botón Apply MARK_AS_MATCH
- `batch-action-preset` - Botón Apply Preset
- `batch-selected-count` - Contador de seleccionados
- `presets-open` - Botón abrir presets
- `presets-save` - Botón crear preset
- `presets-disable-{preset_id}` - Botón desactivar preset

## Notas importantes

1. **Preset ID estable**: El `preset_id` se calcula de forma determinista a partir del scope, action y defaults, garantizando que el mismo preset tenga el mismo ID.

2. **No auto-aplica**: Los presets solo se sugieren en la tabla; el usuario debe aplicar manualmente.

3. **Matching estricto**: Un preset solo aplica a items que coincidan exactamente con su scope (type_id requerido, subject_key y period_key opcionales pero estrictos si se especifican).

4. **Batch actions**: Las acciones en lote aplican a todos los items seleccionados, pero el preset solo aplica a los que coincidan con su scope.

5. **Guardrails intactos**: FORCE_UPLOAD sigue validando paths en backend; SKIP requiere reason.

## Comandos útiles

```bash
# Listar presets
curl "http://127.0.0.1:8000/api/presets/decision_presets"

# Crear preset
curl -X POST "http://127.0.0.1:8000/api/presets/decision_presets" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Skip T104",
    "scope": {
      "platform": "egestiona",
      "type_id": "T104_AUTONOMOS_RECEIPT"
    },
    "action": "SKIP",
    "defaults": {
      "reason": "No disponible"
    }
  }'

# Desactivar preset
curl -X POST "http://127.0.0.1:8000/api/presets/decision_presets/{preset_id}/disable"
```

## Evidencias generadas

Ejemplo de preset creado:

```json
{
  "preset_id": "preset_a1b2c3d4e5f6g7h8",
  "name": "Skip T104",
  "scope": {
    "platform": "egestiona",
    "type_id": "T104_AUTONOMOS_RECEIPT",
    "subject_key": null,
    "period_key": null
  },
  "action": "SKIP",
  "defaults": {
    "reason": "No disponible"
  },
  "created_at": "2025-01-15T10:30:00Z",
  "is_enabled": true
}
```

Ejemplo de Decision Pack generado con batch actions:

```json
{
  "plan_id": "plan_abc123",
  "decision_pack_id": "pack_def456",
  "created_at": "2025-01-15T10:35:00Z",
  "decisions": [
    {
      "item_id": "item_1",
      "action": "SKIP",
      "reason": "Batch SKIP applied",
      "decided_by": "human",
      "decided_at": "2025-01-15T10:35:00Z"
    },
    // ... más decisiones
  ]
}
```
