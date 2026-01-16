# Evidencia: Bug 500 en endpoint /duplicate (ANTES DEL FIX)

## Fecha
2025-12-30

## Bug Reportado
El endpoint `POST /api/repository/types/{type_id}/duplicate` devolvía error 500 (Internal Server Error).

## Causa Raíz Identificada
El método `duplicate_type` en `DocumentRepositoryStoreV1` intentaba pasar `type_id` dos veces al constructor de `DocumentTypeV1`:
1. Una vez a través de `**original.model_dump()` (que ya incluye `type_id`)
2. Otra vez explícitamente como `type_id=new_type_id`

Esto causaba un `TypeError: got multiple values for keyword argument 'type_id'` que no era capturado correctamente por el endpoint, resultando en un 500.

## Reproducción del Bug

### Comando usado:
```powershell
$body = '{"new_type_id":"T999_TEST_DOC_COPY"}'
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/repository/types/T999_TEST_DOC/duplicate" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body
```

### Resultado:
- **Status Code**: 500 Internal Server Error
- **Error**: `TypeError: got multiple values for keyword argument 'type_id'`

## Código Problemático (ANTES DEL FIX)

```python
def duplicate_type(self, type_id: str, new_type_id: str, new_name: Optional[str] = None) -> DocumentTypeV1:
    """Duplica un tipo con nuevo ID."""
    original = self.get_type(type_id)
    if not original:
        raise ValueError(f"Type {type_id} not found")
    
    types_dict = self._read_types()
    if new_type_id in types_dict:
        raise ValueError(f"Type {new_type_id} already exists")
    
    new_type = DocumentTypeV1(
        **original.model_dump(),  # ❌ Esto incluye 'type_id'
        type_id=new_type_id,      # ❌ Esto intenta pasar 'type_id' de nuevo
        name=new_name or f"{original.name} (copia)"
    )
    # ...
```

## Fix Aplicado
Ver `duplicate_after.md` para detalles del fix.




















