# SPRINT C2.19A — Aprendizaje determinista del matching desde decisiones humanas

## Resumen

Implementación de un sistema de aprendizaje determinista que genera hints desde decisiones humanas (`MARK_AS_MATCH` en Decision Packs) y los aplica en futuros matchings para mejorar la precisión y reducir la necesidad de intervención manual.

## Archivos creados/modificados

### Nuevos archivos:
- `backend/shared/learning_store.py` - Store para hints aprendidos (JSONL + index)
- `backend/shared/learning_hints_generator.py` - Generador de hints desde Decision Packs
- `backend/api/learning_routes.py` - API de administración (listar, desactivar hints)
- `tests/test_learning_store.py` - Tests unitarios completos
- `docs/evidence/c2_19a/README.md` - Esta documentación

### Archivos modificados:
- `backend/repository/document_matcher_v1.py` - Aplicación de hints en el matching
- `backend/shared/matching_debug_report.py` - Añadido `AppliedHint` al outcome
- `backend/adapters/egestiona/execute_auto_upload_gate.py` - Integración de generación de hints
- `backend/app.py` - Registro de rutas de learning API

## Funcionalidades implementadas

### 1. Learning Store (`LearningStore`)
- Persistencia append-only en `data/learning/hints_v1.jsonl`
- Índice en `data/learning/index_v1.json`
- Tombstones para hints desactivados en `data/learning/tombstones_v1.json`
- Operaciones: `add_hints()`, `find_hints()`, `disable_hint()`, `list_hints()`

### 2. Modelo `LearnedHintV1`
- `hint_id`: Hash estable (SHA256 de contenido canonizado)
- `item_fingerprint`: Fingerprint determinista del pending item
- `learned_mapping`: Mapeo aprendido (type_id_expected, local_doc_id, opcional local_doc_fingerprint)
- `conditions`: Condiciones de aplicación (subject_key, person_key, period_key, portal_type_label_normalized)
- `strength`: `EXACT` (todas las condiciones presentes) o `SOFT` (algunas faltan)
- `disabled`: Flag para desactivar sin borrar

### 3. Generación automática de hints
- Se ejecuta automáticamente cuando se aplica un Decision Pack con `MARK_AS_MATCH`
- Genera `LearnedHintV1` por cada decisión `MARK_AS_MATCH` validada
- Idempotente: no duplica hints con el mismo `hint_id`
- Guarda evidencia en `data/runs/{plan_id}/decision_packs/{decision_pack_id}__learned_hints.json`

### 4. Aplicación de hints en matching
- Se ejecuta **ANTES** del ranking final de candidatos
- Busca hints aplicables por: platform, type_id, subject_key, person_key, period_key, portal_label_norm
- **Hint EXACT único**: Si hay exactamente 1 hint EXACT y el documento objetivo existe y cumple condiciones estrictas, resuelve directamente (confidence=1.0)
- **Múltiples hints**: Aplica boost suave (+0.2) a scores de candidatos que coinciden
- Registra hints aplicados en `MatchingDebugReportV1.outcome.applied_hints`

### 5. API de administración
- `GET /api/learning/hints` - Listar hints con filtros opcionales
- `POST /api/learning/hints/{hint_id}/disable` - Desactivar hint

## Ejemplos

### Ejemplo 1: Hint generado desde Decision Pack

Cuando un usuario crea un Decision Pack con `MARK_AS_MATCH` y se ejecuta, se genera automáticamente un hint:

```json
{
  "hint_id": "hint_a1b2c3d4e5f6g7h8",
  "created_at": "2025-01-15T10:30:00Z",
  "source": "decision_pack",
  "plan_id": "plan_abc123",
  "decision_pack_id": "pack_def456",
  "item_fingerprint": "egestiona_T104_AUTONOMOS_RECEIPT_COMPANY123_PERSON123_2025-01",
  "learned_mapping": {
    "type_id_expected": "T104_AUTONOMOS_RECEIPT",
    "local_doc_id": "doc_xyz789",
    "local_doc_fingerprint": "recibo_autonomos_2025-01.pdf:12345"
  },
  "conditions": {
    "subject_key": "COMPANY123",
    "person_key": "PERSON123",
    "period_key": "2025-01",
    "portal_type_label_normalized": "t1040 recibo autonomos"
  },
  "strength": "EXACT",
  "notes": "Usuario marcó como match correcto",
  "disabled": false
}
```

### Ejemplo 2: Matching Debug Report con hints aplicados

Cuando un hint se aplica durante el matching, aparece en el `MatchingDebugReportV1`:

```json
{
  "outcome": {
    "decision": "AUTO_UPLOAD",
    "local_docs_considered": 1,
    "primary_reason_code": "UNKNOWN",
    "human_hint": "Match resuelto mediante hint aprendido",
    "applied_hints": [
      {
        "hint_id": "hint_a1b2c3d4e5f6g7h8",
        "strength": "EXACT",
        "effect": "resolved",
        "reason": "EXACT hint matched, doc verified"
      }
    ]
  }
}
```

### Ejemplo 3: Múltiples hints (boost suave)

Si hay múltiples hints aplicables, se aplica un boost suave en lugar de resolver directamente:

```json
{
  "outcome": {
    "decision": "REVIEW_REQUIRED",
    "local_docs_considered": 2,
    "applied_hints": [
      {
        "hint_id": "hint_111",
        "strength": "EXACT",
        "effect": "boosted",
        "reason": "Multiple hints, soft boost applied"
      },
      {
        "hint_id": "hint_222",
        "strength": "SOFT",
        "effect": "boosted",
        "reason": "Multiple hints, soft boost applied"
      }
    ]
  }
}
```

## Pasos para reproducir en local

### 1. Crear un Decision Pack con MARK_AS_MATCH

```bash
# 1. Generar un plan (si no existe)
curl -X POST "http://127.0.0.1:8000/api/runs/egestiona/build_plan" \
  -H "Content-Type: application/json" \
  -d '{
    "company_key": "COMPANY123",
    "person_key": "PERSON123"
  }'

# 2. Obtener el plan_id del response
# 3. Crear un Decision Pack con MARK_AS_MATCH
curl -X POST "http://127.0.0.1:8000/api/plans/{plan_id}/decision_packs" \
  -H "Content-Type: application/json" \
  -d '{
    "decisions": [
      {
        "item_id": "item_123",
        "action": "MARK_AS_MATCH",
        "chosen_local_doc_id": "doc_xyz789",
        "reason": "Match correcto confirmado por usuario"
      }
    ]
  }'
```

### 2. Ejecutar con Decision Pack

```bash
# Ejecutar auto_upload con el decision_pack_id
curl -X POST "http://127.0.0.1:8000/api/runs/egestiona/execute_auto_upload" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "{plan_id}",
    "decision_pack_id": "{decision_pack_id}"
  }'
```

### 3. Verificar hints generados

```bash
# Listar hints generados
curl "http://127.0.0.1:8000/api/learning/hints?plan_id={plan_id}"

# Ver evidencia del hint generado
cat data/runs/{plan_id}/decision_packs/{decision_pack_id}__learned_hints.json
```

### 4. Generar nuevo plan y verificar aplicación de hints

```bash
# Generar nuevo plan (con items similares)
curl -X POST "http://127.0.0.1:8000/api/runs/egestiona/build_plan" \
  -H "Content-Type: application/json" \
  -d '{
    "company_key": "COMPANY123",
    "person_key": "PERSON123"
  }'

# Verificar que el matching ahora sugiere/resuelve usando el hint
# El matching_debug_report debería mostrar applied_hints
```

### 5. Verificar matching debug con hints aplicados

```bash
# Obtener matching debug de un item
curl "http://127.0.0.1:8000/api/runs/{plan_id}/matching_debug/{item_id}"

# El response debería incluir:
# {
#   "outcome": {
#     "applied_hints": [...]
#   }
# }
```

## Tests

Ejecutar tests unitarios:

```bash
python -m pytest tests/test_learning_store.py -v
```

Tests incluidos:
- `test_generate_hint_from_mark_as_match_idempotent` - Verifica idempotencia
- `test_apply_exact_hint_resolves_match` - Verifica que hint EXACT resuelve match
- `test_multiple_hints_no_auto_resolve` - Verifica que múltiples hints solo boost
- `test_disable_hint_stops_application` - Verifica que hints desactivados no se aplican

## Ubicación de datos

- **Hints almacenados**: `data/learning/hints_v1.jsonl`
- **Índice**: `data/learning/index_v1.json`
- **Tombstones**: `data/learning/tombstones_v1.json`
- **Evidencias de generación**: `data/runs/{plan_id}/decision_packs/{decision_pack_id}__learned_hints.json`
- **Matching debug con hints**: `data/runs/{run_id}/matching_debug/{item_id}__debug.json`

## Notas importantes

1. **Idempotencia**: El mismo hint (mismo `hint_id`) solo se almacena una vez, incluso si se intenta añadir múltiples veces.

2. **Determinismo**: El `hint_id` se calcula de forma determinista a partir del contenido canonizado, garantizando reproducibilidad.

3. **Reversibilidad**: Los hints se pueden desactivar sin borrarlos, permitiendo revertir cambios si es necesario.

4. **Seguridad**: Los hints EXACT solo se aplican si:
   - Hay exactamente 1 hint EXACT aplicable
   - El documento objetivo existe
   - Se cumplen todas las condiciones estrictas (type_id, subject_key, period_key)

5. **No relaja guardrails**: El sistema de hints no modifica los guardrails existentes ni cambia el `plan_id`.

## Comandos útiles

```bash
# Listar todos los hints activos
curl "http://127.0.0.1:8000/api/learning/hints"

# Listar hints de un plan específico
curl "http://127.0.0.1:8000/api/learning/hints?plan_id={plan_id}"

# Desactivar un hint
curl -X POST "http://127.0.0.1:8000/api/learning/hints/{hint_id}/disable"

# Ver hints desactivados
curl "http://127.0.0.1:8000/api/learning/hints?include_disabled=true"
```
