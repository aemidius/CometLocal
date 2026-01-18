# SPRINT C2.18B — Revisión humana (Overrides) sin romper PLAN/DECISION/EXECUTION

## Resumen

Implementación de un sistema de revisión humana que permite crear decisiones manuales (overrides) para items del plan sin modificar el `plan_id` congelado. El sistema mantiene la separación estricta PLAN → DECISION → EXECUTION.

## Archivos creados/modificados

### Nuevos archivos:
- `backend/shared/decision_pack.py` - Modelos Pydantic para Decision Pack
- `backend/shared/decision_pack_store.py` - Persistencia de Decision Packs
- `backend/api/decision_pack_routes.py` - Endpoints API para Decision Packs
- `tests/test_decision_pack.py` - Tests unitarios

### Archivos modificados:
- `backend/app.py` - Registro de router de decision_pack
- `backend/api/auto_upload_routes.py` - Acepta `decision_pack_id` opcional en ExecuteRequest
- `backend/adapters/egestiona/execute_auto_upload_gate.py` - Aplica Decision Pack en ejecución

## Funcionalidades

### 1. Decision Pack

Un Decision Pack es un conjunto de decisiones manuales que se aplican sobre un plan congelado:

- **MARK_AS_MATCH**: Vincular un documento local concreto como match
- **FORCE_UPLOAD**: Forzar la subida con un archivo local específico
- **SKIP**: Declarar que no se sube (con motivo)

### 2. Persistencia

Los Decision Packs se guardan en:
- `data/runs/{plan_id}/decision_packs/{decision_pack_id}.json` - Pack completo
- `data/runs/{plan_id}/decision_packs/index.json` - Índice de packs

### 3. Hash estable

El `decision_pack_id` se calcula como hash SHA256 del contenido canonizado:
- `plan_id`
- `decisions` (item_id, action, chosen_local_doc_id/file_path, reason)
- NO incluye `decided_by` ni `decided_at` para estabilidad

### 4. API Endpoints

- `POST /api/plans/{plan_id}/decision_packs` - Crear Decision Pack
- `GET /api/plans/{plan_id}/decision_packs` - Listar packs
- `GET /api/plans/{plan_id}/decision_packs/{decision_pack_id}` - Obtener pack completo

### 5. Ejecución con Decision Pack

El endpoint `POST /api/runs/auto_upload/execute` acepta opcionalmente `decision_pack_id`:

```json
{
  "plan_id": "plan_abc123",
  "decision_pack_id": "pack_def456",
  "max_uploads": 5
}
```

Cuando se proporciona `decision_pack_id`, las decisiones del plan se modifican aplicando los overrides antes de la ejecución.

## Guardrails y validaciones

### FORCE_UPLOAD
- El `chosen_file_path` debe estar dentro de `repository_root_dir` o su directorio padre (`data_dir`)
- El archivo debe existir

### MARK_AS_MATCH
- El `chosen_local_doc_id` debe existir en el repositorio
- El documento debe tener `stored_path` asociado

### SKIP
- El `reason` es requerido y no puede estar vacío

## Tests

```bash
python -m pytest tests/test_decision_pack.py -v
```

Tests incluidos:
- `test_create_decision_pack_stable_id` - Verifica que el `decision_pack_id` es estable
- `test_apply_mark_as_match_override` - Verifica que MARK_AS_MATCH convierte a AUTO_UPLOAD
- `test_apply_skip_override` - Verifica que SKIP convierte a DO_NOT_UPLOAD
- `test_apply_force_upload_override` - Verifica que FORCE_UPLOAD convierte a AUTO_UPLOAD
- `test_plan_id_stability_with_decision_pack` - Verifica que el `plan_id` no cambia
- `test_list_packs` - Verifica listado de packs

## Ejemplo de uso

### 1. Crear Decision Pack

```bash
curl -X POST "http://127.0.0.1:8000/api/plans/plan_abc123/decision_packs" \
  -H "Content-Type: application/json" \
  -d '{
    "decisions": [
      {
        "item_id": "item1",
        "action": "SKIP",
        "reason": "Documento ya subido manualmente"
      },
      {
        "item_id": "item2",
        "action": "MARK_AS_MATCH",
        "chosen_local_doc_id": "doc123",
        "reason": "Match manual confirmado"
      }
    ]
  }'
```

### 2. Ejecutar con Decision Pack

```bash
curl -X POST "http://127.0.0.1:8000/api/runs/auto_upload/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "plan_abc123",
    "decision_pack_id": "pack_def456",
    "max_uploads": 5
  }'
```

## Invariantes cumplidos

- ✅ El `plan_id` no cambia (el plan congelado permanece inmutable)
- ✅ Se pueden crear Decision Packs y reutilizarlos
- ✅ La ejecución aplica overrides sin redecidir
- ✅ Guardrails siguen impidiendo subidas sin decisión explícita AUTO_UPLOAD
- ✅ Tests verdes

## Compatibilidad

- ✅ No modifica el algoritmo de matching
- ✅ No modifica el `plan_id` ni su contenido
- ✅ La decisión manual es una capa separada con `decision_pack_id` propio
- ✅ La ejecución consume el plan + decision_pack (o decisiones AUTO existentes)
- ✅ Guardrails: sigue siendo imposible subir sin decisión explícita AUTO_UPLOAD
