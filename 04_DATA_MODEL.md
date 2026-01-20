# 04_DATA_MODEL — CometLocal

## PersonV1
```json
{
  "worker_id": "string",
  "full_name": "string",
  "tax_id": "string",
  "role": "string",
  "relation_type": "string",
  "own_company_key": "string | null"
}
```

### Notas
- `own_company_key` es opcional (migración suave)
- `null` equivale a "Sin asignar"

## Principio clave
Toda persona pertenece (o no) a una empresa propia.
No existe trabajador sin contexto humano en operaciones reales.
