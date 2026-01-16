# Evidencias - Execute Plan Headful

Este directorio contiene evidencias de ejecución del endpoint `/runs/egestiona/execute_plan_headful`.

## Archivos generados

- `request_response.json`: Request y response del endpoint
- `execution_meta.json`: Metadata de la ejecución (si se completa)

## Validaciones

- Error `missing_storage_state`: Cuando no existe `storage_state.json`
- Error `storage_state_not_authenticated`: Cuando el storage_state no autentica correctamente
- Error `real_uploader_not_requested`: Cuando falta header `X-USE-REAL-UPLOADER=1`
