# Evidencias - Headful Run Persistente (UX Operador Profesional)

Este directorio contiene evidencias de ejecución de los endpoints de run headful persistente con timeline y observabilidad.

## Endpoints

- `POST /runs/egestiona/start_headful_run`: Inicia un run headful persistente
- `POST /runs/egestiona/execute_action_headful`: Ejecuta una acción dentro de un run activo
- `POST /runs/egestiona/close_headful_run`: Cierra un run headful persistente
- `GET /runs/egestiona/headful_run_status`: Obtiene estado y timeline de un run activo

## Timeline de Eventos

El timeline registra automáticamente:
- `RUN_STARTED`: Run iniciado
- `INFO`: Eventos informativos (navegador iniciado, storage state cargado)
- `SUCCESS`: Operaciones exitosas (autenticación verificada, subida completada)
- `ACTION`: Acciones solicitadas o en ejecución
- `WARNING`: Advertencias
- `ERROR`: Errores durante ejecución
- `RUN_CLOSED`: Run cerrado

## Niveles de Riesgo

El sistema calcula automáticamente el nivel de riesgo:
- `low`: Sin errores, pocas advertencias/acciones
- `medium`: Múltiples advertencias o acciones
- `high`: Presencia de errores

## Archivos generados

- Request/response JSON de cada endpoint
- Timeline de eventos en tiempo real
- Evidencias de ejecución (si se completa una acción)

## Validaciones

- Error `missing_storage_state`: Cuando no existe `storage_state.json`
- Error `headful_run_not_found`: Cuando se intenta usar un run que no está activo
- Error `real_uploader_not_requested`: Cuando falta header `X-USE-REAL-UPLOADER=1`
- Error `environment_violation`: Cuando `ENVIRONMENT != dev`
