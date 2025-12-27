# Troubleshooting: Validity Override PUT Endpoint

## Problema Original

El endpoint `PUT /api/repository/docs/{doc_id}` daba error 500 al actualizar `validity_override`.

## Solución Implementada

El endpoint ahora acepta `validity_override` en múltiples formatos:

1. **Objeto JSON (normal)**:
```json
{
  "validity_override": {
    "override_valid_from": "2025-11-01",
    "override_valid_to": "2025-12-31",
    "reason": "test"
  }
}
```

2. **String JSON (si el frontend lo manda serializado)**:
```json
{
  "validity_override": "{\"override_valid_from\":\"2025-11-01\",\"override_valid_to\":\"2025-12-31\",\"reason\":\"test2\"}"
}
```

3. **null (para limpiar override)**:
```json
{
  "validity_override": null
}
```

## Validaciones

- **Formato de fechas**: Debe ser `YYYY-MM-DD` (ej: `2025-11-01`)
- **Tipos aceptados**: `dict`, `str` (JSON), o `null`
- **Campos opcionales**: Todos los campos de `validity_override` son opcionales
- **Dict vacío**: Si se envía `{}` o todos los valores son `null`, se elimina el override

## Tests E2E

### Test A: Set override con objeto
```bash
curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d '{"validity_override":{"override_valid_from":"2025-11-01","override_valid_to":"2025-12-31","reason":"test"}}'
```
**Resultado esperado**: 200 OK, GET debe reflejar el override.

### Test B: Set override con string JSON
```bash
curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d '{"validity_override":"{\"override_valid_from\":\"2025-11-01\",\"override_valid_to\":\"2025-12-31\",\"reason\":\"test2\"}"}'
```
**Resultado esperado**: 200 OK, GET debe reflejar el override con reason="test2".

### Test C: Limpiar override
```bash
curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d '{"validity_override":null}'
```
**Resultado esperado**: 200 OK, GET debe mostrar `validity_override: null`.

## Errores Comunes

### Error 400: "Invalid validity_override format"
- **Causa**: El string JSON no es válido o no se puede parsear a dict
- **Solución**: Verificar que el JSON esté bien formado

### Error 400: "Invalid date format for override_valid_from"
- **Causa**: La fecha no está en formato `YYYY-MM-DD`
- **Solución**: Usar formato `YYYY-MM-DD` (ej: `2025-11-01`)

### Error 500: Internal Server Error
- **Causa**: Error en el procesamiento (antes del hotfix)
- **Solución**: Verificar que el servidor esté actualizado con el hotfix

## Implementación Técnica

El endpoint usa `DocumentUpdateRequest.normalize_validity_override()` para:
1. Detectar si `validity_override` es `dict`, `str`, o `None`
2. Si es `str`, hacer `json.loads()` para parsearlo a `dict`
3. Validar que el resultado sea `dict` o `None`
4. Rechazar otros tipos con error 400 claro

El modelo `ValidityOverrideV1` acepta todos los campos como `Optional`, por lo que `None` es válido.

