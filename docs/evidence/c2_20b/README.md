# SPRINT C2.20B — Métricas operativas CAE (valor y eficiencia)

## Resumen

Sistema de métricas operativas para entender el valor y eficiencia del proceso CAE:
- Volumen de items procesados
- Distribución de decisiones
- Impacto del learning y presets
- Esfuerzo humano evitado

## Archivos creados/modificados

### Nuevos archivos:
- `backend/shared/run_metrics.py` - Modelo RunMetricsV1 y funciones de recolección
- `backend/api/metrics_routes.py` - API endpoints para métricas
- `tests/test_run_metrics.py` - Tests unitarios
- `docs/evidence/c2_20b/README.md` - Esta documentación

### Archivos modificados:
- `backend/adapters/egestiona/flows.py` - Inicialización de métricas en plan creation
- `backend/api/decision_pack_routes.py` - Registro de decision pack y detección de presets
- `backend/adapters/egestiona/execute_auto_upload_gate.py` - Registro de ejecución
- `backend/app.py` - Registro de metrics_router
- `frontend/repository_v3.html` - Panel de métricas en plan_review

## Funcionalidades implementadas

### 1. Modelo RunMetricsV1
- `total_items`: Total de items en el plan
- `decisions_count`: Conteo por tipo (AUTO_UPLOAD, REVIEW_REQUIRED, NO_MATCH, SKIP)
- `source_breakdown`: Conteo por origen:
  - `auto_matching`: Matching automático
  - `learning_hint_resolved`: Resueltos por hints de learning
  - `preset_applied`: Aplicados mediante presets
  - `manual_single`: Decisiones manuales individuales
  - `manual_batch`: Decisiones manuales en lote
- `timestamps`: Timestamps clave (plan_created_at, decision_pack_created_at, execution_started_at, execution_finished_at)

### 2. Recolección automática
- **Plan creation**: Inicializa métricas y registra decisiones iniciales (auto_matching)
- **Decision pack creation**: Registra creación y detecta presets aplicados
- **Execution**: Registra inicio y fin de ejecución
- **Learning hints**: Detecta hints aplicados desde matching_debug reports
- **Presets**: Detecta presets aplicados desde razones de decisiones

### 3. API endpoints
- `GET /api/runs/{run_id}/metrics` - Obtiene métricas de un run/plan
- `GET /api/metrics/summary` - Resumen agregado de últimos N runs

### 4. UI Panel de Métricas
- Botón "📊 Métricas" en plan_review
- Panel expandible con:
  - Distribución de decisiones
  - Origen de decisiones
  - Valor generado (esfuerzo humano evitado)
  - Badges para learning y presets
  - Mensaje claro sobre % evitado

## Ejemplos

### Ejemplo 1: metrics.json generado

```json
{
  "run_id": "run_abc123",
  "plan_id": "plan_def456",
  "total_items": 25,
  "decisions_count": {
    "AUTO_UPLOAD": 18,
    "REVIEW_REQUIRED": 5,
    "NO_MATCH": 2,
    "SKIP": 0
  },
  "source_breakdown": {
    "auto_matching": 15,
    "learning_hint_resolved": 3,
    "preset_applied": 5,
    "manual_single": 1,
    "manual_batch": 1
  },
  "timestamps": {
    "plan_created_at": "2025-01-15T10:00:00Z",
    "decision_pack_created_at": "2025-01-15T10:15:00Z",
    "execution_started_at": "2025-01-15T10:20:00Z",
    "execution_finished_at": "2025-01-15T10:25:00Z"
  },
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:25:00Z"
}
```

### Ejemplo 2: Summary agregado

```json
{
  "total_runs": 10,
  "total_items": 250,
  "decisions_breakdown": {
    "AUTO_UPLOAD": 180,
    "REVIEW_REQUIRED": 50,
    "NO_MATCH": 20,
    "SKIP": 0
  },
  "source_breakdown": {
    "auto_matching": 150,
    "learning_hint_resolved": 20,
    "preset_applied": 30,
    "manual_single": 10,
    "manual_batch": 40
  },
  "percentages": {
    "auto_upload": 72.0,
    "skip": 0.0,
    "review_required": 20.0,
    "with_learning": 60.0,
    "with_presets": 80.0
  }
}
```

### Ejemplo 3: Panel UI

El panel muestra:
- **Distribución de Decisiones**: AUTO_UPLOAD: 18, REVIEW_REQUIRED: 5, etc.
- **Origen de Decisiones**: Auto Matching: 15, Learning Hints: 3, Presets: 5, etc.
- **Valor Generado**:
  - Total items: 25
  - Esfuerzo humano evitado: 72% (18 de 25 items resueltos automáticamente)
  - Learning: Resueltos por hints: 3 (12%)
  - Presets: Aplicados: 5 (20%)
  - Mensaje: "✅ Este plan ha evitado revisión manual en 72% de los items."

## Pasos para reproducir manualmente

### 1. Generar plan y ver métricas iniciales

```bash
# 1. Generar plan
curl -X POST "http://127.0.0.1:8000/api/runs/egestiona/build_auto_upload_plan" \
  -H "Content-Type: application/json" \
  -d '{
    "company_key": "COMPANY123",
    "person_key": "PERSON123"
  }'

# 2. Obtener plan_id del response
# 3. Ver métricas
curl "http://127.0.0.1:8000/api/runs/{plan_id}/metrics"
```

### 2. Aplicar presets y ver actualización

1. En plan_review, aplicar un preset a 5 items
2. Guardar decision pack
3. Abrir panel "📊 Métricas"
4. Verificar que `preset_applied` aumenta a 5
5. Verificar que el % de esfuerzo humano evitado se actualiza

### 3. Ver summary agregado

```bash
curl "http://127.0.0.1:8000/api/metrics/summary?limit=10"
```

### 4. Verificar detección de learning hints

1. Crear un plan donde algunos items tienen hints aplicados (effect="resolved")
2. Verificar que `learning_hint_resolved` se incrementa correctamente
3. Verificar en el panel UI que aparece el badge de Learning

## Tests

Ejecutar tests unitarios:

```bash
python -m pytest tests/test_run_metrics.py -v
```

Tests incluidos:
- `test_initialize_metrics` - Verifica inicialización
- `test_update_metrics_from_decisions` - Verifica actualización desde decisiones
- `test_record_decision_pack_created` - Verifica registro de decision pack
- `test_record_execution_lifecycle` - Verifica ciclo completo de ejecución
- `test_record_learning_and_preset` - Verifica registro de learning y presets
- `test_record_manual_decision` - Verifica registro de decisiones manuales

## Ubicación de datos

- **Métricas por plan**: `data/runs/{plan_id}/metrics.json`
- **Summary agregado**: Calculado on-demand desde todos los metrics.json

## Notas importantes

1. **Detección de presets**: Se detecta si la razón contiene "Applied preset" o "preset:". Esto es suficiente para el MVP.

2. **Detección de learning hints**: Se detecta desde matching_debug reports, contando hints con `effect="resolved"`.

3. **No recalcular**: Las métricas solo se registran, no se recalculan. Esto garantiza trazabilidad y rendimiento.

4. **Timestamps**: Todos los timestamps se guardan en ISO format UTC.

5. **Auto-refresh**: El panel de métricas se actualiza automáticamente después de guardar un decision pack.

## Comandos útiles

```bash
# Obtener métricas de un plan
curl "http://127.0.0.1:8000/api/runs/{plan_id}/metrics"

# Obtener summary agregado
curl "http://127.0.0.1:8000/api/metrics/summary?limit=20"

# Ver archivo de métricas directamente
cat data/runs/{plan_id}/metrics.json
```

## Evidencias generadas

Ejemplo de metrics.json:

```json
{
  "plan_id": "plan_abc123",
  "total_items": 25,
  "decisions_count": {
    "AUTO_UPLOAD": 18,
    "REVIEW_REQUIRED": 5,
    "NO_MATCH": 2,
    "SKIP": 0
  },
  "source_breakdown": {
    "auto_matching": 15,
    "learning_hint_resolved": 3,
    "preset_applied": 5,
    "manual_single": 1,
    "manual_batch": 1
  },
  "timestamps": {
    "plan_created_at": "2025-01-15T10:00:00Z",
    "decision_pack_created_at": "2025-01-15T10:15:00Z",
    "execution_started_at": "2025-01-15T10:20:00Z",
    "execution_finished_at": "2025-01-15T10:25:00Z"
  }
}
```

Ejemplo de summary:

```json
{
  "total_runs": 10,
  "total_items": 250,
  "decisions_breakdown": {
    "AUTO_UPLOAD": 180,
    "REVIEW_REQUIRED": 50,
    "NO_MATCH": 20,
    "SKIP": 0
  },
  "source_breakdown": {
    "auto_matching": 150,
    "learning_hint_resolved": 20,
    "preset_applied": 30,
    "manual_single": 10,
    "manual_batch": 40
  },
  "percentages": {
    "auto_upload": 72.0,
    "skip": 0.0,
    "review_required": 20.0,
    "with_learning": 60.0,
    "with_presets": 80.0
  }
}
```
