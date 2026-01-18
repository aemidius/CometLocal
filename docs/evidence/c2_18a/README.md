# SPRINT C2.18A — Observabilidad determinista del matching

## Resumen

Implementación completa de observabilidad determinista para el proceso de matching. Cuando un pending requirement termina en `NO_MATCH` o tiene `local_docs_considered=0`, el sistema genera un "Matching Debug Report" estructurado que explica:

- Cuántos docs locales existían al inicio (sin filtros)
- Qué filtros se aplicaron y cuántos descartaron en cada paso
- Qué candidates fueron "top N" y por qué no llegaron al umbral
- Qué `data_dir` y rutas se usaron

## Archivos modificados/creados

### Nuevos archivos:
- `backend/shared/matching_debug_report.py` - Modelo Pydantic para MatchingDebugReportV1
- `backend/api/matching_debug_routes.py` - Endpoints API para acceder a reportes
- `tests/test_matching_debug_report.py` - Tests unitarios

### Archivos modificados:
- `backend/repository/document_matcher_v1.py` - Instrumentación del pipeline de matching
- `backend/adapters/egestiona/submission_plan_headful.py` - Integración con flujo de plan
- `backend/adapters/egestiona/flows.py` - Copia de matching_debug al plan_dir
- `backend/app.py` - Registro de router de matching_debug

## Cómo ejecutar

### Tests unitarios:
```bash
python -m pytest tests/test_matching_debug_report.py -v
```

### Ejemplo de uso en API:
```bash
# Obtener índice de matching debug para un run
curl "http://127.0.0.1:8000/api/runs/{run_id}/matching_debug"

# Obtener reporte completo de un item
curl "http://127.0.0.1:8000/api/runs/{run_id}/matching_debug/{item_id}"
```

## Evidencias

Los reportes se guardan en:
- `data/runs/{run_id}/matching_debug/index.json` - Índice con resumen
- `data/runs/{run_id}/matching_debug/{item_id}__debug.json` - Reporte completo por item

Para planes (C2.17):
- `data/runs/{plan_id}/matching_debug/index.json`
- `data/runs/{plan_id}/matching_debug/{item_id}__debug.json`

## Ejemplo de debug.json

```json
{
  "meta": {
    "created_at": "2024-01-15T10:30:00Z",
    "data_dir_resolved": "/path/to/data/repository",
    "repo_docs_total": 0,
    "request_context": {
      "platform": "egestiona",
      "company_key": "TEST123",
      "person_key": "worker123",
      "type_ids": [],
      "pending_label": "T205.0 | Test Worker"
    }
  },
  "pipeline": [
    {
      "step_name": "start: all_docs",
      "input_count": 0,
      "output_count": 0,
      "rule": "load_all_documents"
    },
    {
      "step_name": "filter: type_id",
      "input_count": 0,
      "output_count": 0,
      "rule": "type_match_by_alias: no match for 'T205.0'"
    }
  ],
  "candidates_top": [],
  "outcome": {
    "decision": "NO_MATCH",
    "local_docs_considered": 0,
    "primary_reason_code": "REPO_EMPTY",
    "human_hint": "El repositorio está vacío. No hay documentos disponibles."
  }
}
```

## Primary Reason Codes

- `REPO_EMPTY` - El repositorio está vacío
- `DATA_DIR_MISMATCH` - El data_dir no coincide con el esperado (SPRINT C2.18A.1)
- `TYPE_FILTER_ZERO` - No hay documentos del tipo requerido
- `SUBJECT_FILTER_ZERO` - No hay documentos para el company_key/person_key
- `PERIOD_FILTER_ZERO` - No hay documentos para el período
- `CONFIDENCE_TOO_LOW` - Hay candidatos pero no superan el umbral
- `UNKNOWN` - Causa no determinada

### SPRINT C2.18A.1: DATA_DIR_MISMATCH

Se detecta cuando:
- `repo_docs_total == 0`
- `data_dir_expected` existe (desde settings, ENV:COMETLOCAL_DATA_DIR, ENV:REPOSITORY_DATA_DIR, o default)
- `normpath(data_dir_resolved) != normpath(data_dir_expected)`

El reporte incluye:
- `meta.data_dir_resolved` - Ruta real usada
- `meta.data_dir_expected` - Ruta esperada (si está configurada)
- `meta.data_dir_expected_source` - Origen de la ruta esperada (settings, ENV, default)
- `meta.data_dir_exists` - Si el directorio existe
- `meta.data_dir_contents_sample` - Muestra de hasta 10 entradas del directorio

Ver ejemplo en `docs/evidence/c2_18a_1/example_data_dir_mismatch.json`.

## Compatibilidad

- ✅ No modifica la semántica del matching (solo observabilidad)
- ✅ No relaja guardrails ni decisión explícita
- ✅ El `plan_id` sigue siendo estable (matching_debug no afecta el hash)
- ✅ Funciona en runs reales eGestióna y escenarios simulados/tests
- ✅ Mantiene estilo del proyecto: evidencias por run, json legible
