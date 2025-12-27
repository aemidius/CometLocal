# Troubleshooting: Validity Override PUT Endpoint

## Problema Original

El endpoint `PUT /api/repository/docs/{doc_id}` daba error 500 al actualizar `validity_override`.

## Solución Implementada

### Normalización de `validity_override`

El endpoint ahora acepta `validity_override` en múltiples formatos:

1. **Objeto JSON** (formato normal):
   ```json
   {
     "validity_override": {
       "override_valid_from": "2025-11-01",
       "override_valid_to": "2025-12-31",
       "reason": "test"
     }
   }
   ```

2. **String JSON** (si el frontend lo envía serializado):
   ```json
   {
     "validity_override": "{\"override_valid_from\":\"2025-11-01\",\"override_valid_to\":\"2025-12-31\",\"reason\":\"test2\"}"
   }
   ```

3. **null** (para limpiar el override):
   ```json
   {
     "validity_override": null
   }
   ```

### Implementación

Se usa un `field_validator` de Pydantic que normaliza el valor antes de la validación:

```python
@field_validator('validity_override', mode='before')
@classmethod
def normalize_validity_override(cls, v: Any) -> Optional[dict]:
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if not isinstance(parsed, dict):
                raise ValueError(...)
            return parsed
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    raise ValueError(f"Must be dict, str (JSON), or None")
```

### Validación de Fechas

Las fechas se validan con formato `YYYY-MM-DD`:
- Si el formato es incorrecto → `400 Bad Request` con mensaje claro
- Si es `None` o string vacío → se acepta (campo opcional)

## Tests E2E

### Test A: Set override con objeto

**Comando:**
```bash
curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d '{"validity_override":{"override_valid_from":"2025-11-01","override_valid_to":"2025-12-31","reason":"test"}}'
```

**O usando archivo JSON:**
```bash
# test_override_obj.json
{
  "validity_override": {
    "override_valid_from": "2025-11-01",
    "override_valid_to": "2025-12-31",
    "reason": "test"
  }
}

curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d "@test_override_obj.json"
```

**Resultado esperado:** `200 OK` y el GET debe reflejar el override.

**Nota:** Si el servidor no se ha recargado, puede dar `500 Internal Server Error`. Reiniciar el servidor.

### Test B: Set override con string JSON

**Comando:**
```bash
curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d '{"validity_override":"{\"override_valid_from\":\"2025-11-01\",\"override_valid_to\":\"2025-12-31\",\"reason\":\"test2\"}"}'
```

**O usando archivo JSON:**
```bash
# test_override_str.json
{
  "validity_override": "{\"override_valid_from\":\"2025-11-01\",\"override_valid_to\":\"2025-12-31\",\"reason\":\"test2\"}"
}

curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d "@test_override_str.json"
```

**Resultado esperado:** `200 OK` y el GET debe reflejar el override con `reason="test2"`.

**Nota:** Si el servidor no se ha recargado, puede dar `500 Internal Server Error`. Reiniciar el servidor.

### Test C: Limpiar override

**Comando:**
```bash
curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d '{"validity_override":null}'
```

**O usando archivo JSON:**
```bash
# test_override_null.json
{
  "validity_override": null
}

curl -X PUT http://127.0.0.1:8000/api/repository/docs/<DOC_ID> \
  -H "Content-Type: application/json" \
  -d "@test_override_null.json"
```

**Resultado esperado:** `200 OK` y el GET debe mostrar `validity_override: null`.

**Resultado verificado:** ✅ Funciona correctamente.

## Errores Comunes

### Error 500: Internal Server Error

**Causa:** El servidor no se ha recargado después de los cambios.

**Solución:** Reiniciar el servidor uvicorn.

### Error 400: Invalid date format

**Causa:** La fecha no está en formato `YYYY-MM-DD`.

**Solución:** Usar formato `YYYY-MM-DD` (ej: `2025-11-01`, no `01/11/2025`).

### Error 400: Invalid JSON in validity_override string

**Causa:** El string JSON está mal formado.

**Solución:** Verificar que el string JSON sea válido (escapar comillas correctamente).

## Logs

Si hay errores, revisar:
- Logs del servidor uvicorn
- `data/runs/r_*/evidence/` para runs de ejecución
- Respuestas HTTP con `curl -v` para ver detalles
