# API Smoke Tests - Catálogo v4

## Fecha
2025-12-30

## Endpoint: GET /api/repository/types

### Test 1: Listado básico con paginación
```bash
curl "http://127.0.0.1:8000/api/repository/types?page=1&page_size=20&sort=name"
```
**Resultado**: ✅ Devuelve lista de tipos con paginación

### Test 2: Búsqueda por query
```bash
curl "http://127.0.0.1:8000/api/repository/types?query=autonomos"
```
**Resultado**: ✅ Filtra tipos que contienen "autonomos" en nombre, type_id o aliases

### Test 3: Filtros combinados
```bash
curl "http://127.0.0.1:8000/api/repository/types?period=monthly&scope=worker&active=true"
```
**Resultado**: ✅ Filtra por periodicidad mensual, scope trabajador y activos

### Test 4: Crear tipo
```bash
curl -X POST "http://127.0.0.1:8000/api/repository/types" \
  -H "Content-Type: application/json" \
  -d '{
    "type_id": "T999_TEST_DOC",
    "name": "Documento prueba",
    "description": "Prueba de creación",
    "scope": "worker",
    "validity_policy": {
      "mode": "monthly",
      "basis": "name_date",
      "monthly": {
        "month_source": "name_date",
        "grace_days": 0
      }
    },
    "platform_aliases": ["prueba", "testdoc"],
    "active": true
  }'
```
**Resultado**: ✅ Crea tipo correctamente

### Test 5: Actualizar tipo
```bash
curl -X PUT "http://127.0.0.1:8000/api/repository/types/T999_TEST_DOC" \
  -H "Content-Type: application/json" \
  -d '{
    "type_id": "T999_TEST_DOC",
    "name": "Documento prueba actualizado",
    "scope": "worker",
    "validity_policy": {
      "mode": "monthly",
      "basis": "name_date",
      "monthly": {
        "month_source": "name_date",
        "grace_days": 5
      }
    },
    "platform_aliases": ["prueba", "testdoc", "actualizado"],
    "active": true
  }'
```
**Resultado**: ✅ Actualiza tipo correctamente

### Test 6: Duplicar tipo
```bash
curl -X POST "http://127.0.0.1:8000/api/repository/types/T999_TEST_DOC/duplicate" \
  -H "Content-Type: application/json" \
  -d '{
    "new_type_id": "T999_TEST_DOC_COPY"
  }'
```
**Resultado**: ✅ Duplica tipo con nuevo ID

### Test 7: Eliminar tipo
```bash
curl -X DELETE "http://127.0.0.1:8000/api/repository/types/T999_TEST_DOC"
```
**Resultado**: ✅ Elimina tipo (si no tiene documentos asociados)

## Conclusión
Todos los endpoints funcionan correctamente con filtros avanzados y paginación.





















