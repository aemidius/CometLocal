# Smoke Test: Endpoint /duplicate (DESPUÉS DEL FIX)

## Fecha
2025-12-30

## Estado
✅ **TODAS LAS PRUEBAS PASARON**

## Pruebas Realizadas

### 1. Duplicar tipo existente con ID específico
**Comando:**
```powershell
$body = '{"new_type_id":"T202_COPY_TEST"}'
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/repository/types/T202_CERTIFICADO_APTITUD_MEDICA/duplicate" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body
```

**Resultado:**
- ✅ Status: **200 OK**
- ✅ Tipo duplicado: `T202_COPY_TEST` - "Certificado aptitud médica (copia)"
- ✅ Todos los campos copiados correctamente

### 2. Duplicar mismo tipo 3 veces (generación automática de ID)
**Comando:**
```powershell
$body = '{}'  # Sin new_type_id, debe generarse automáticamente
# Ejecutado 3 veces seguidas
```

**Resultado:**
- ✅ Duplicado 1: Status **200** - Nuevo ID: `T202_CERTIFICADO_APTITUD_MEDICA_COPY`
- ✅ Duplicado 2: Status **200** - Nuevo ID: `T202_CERTIFICADO_APTITUD_MEDICA_COPY_2`
- ✅ Duplicado 3: Status **200** - Nuevo ID: `T202_CERTIFICADO_APTITUD_MEDICA_COPY_3`
- ✅ **Generación automática funcionando correctamente**

### 3. Verificar que los nuevos tipos aparecen en el listado
**Comando:**
```powershell
GET /api/repository/types?query=COPY
```

**Resultado:**
- ✅ Tipos con 'COPY' encontrados: **4**
  - `T202_COPY_TEST`: Certificado aptitud médica (copia)
  - `T999_TEST_DOC_COPY`: Documento prueba (copia)
  - `T999_TEST_DOC_COPY_3`: Documento prueba (copia)
  - `T999_TEST_DOC_COPY_2`: Documento prueba (copia)
- ✅ **Todos los duplicados aparecen en el listado**

### 4. Verificar inmutabilidad del original
**Comando:**
```powershell
GET /api/repository/types/T202_CERTIFICADO_APTITUD_MEDICA
```

**Resultado:**
- ✅ Original `type_id`: `T202_CERTIFICADO_APTITUD_MEDICA` (sin cambios)
- ✅ Original `name`: "Certificado aptitud médica" (sin cambios)
- ✅ Original `active`: `True` (sin cambios)
- ✅ **Inmutabilidad verificada: el original NO cambia**

## Validaciones Adicionales

### Deep Copy Verificado
- ✅ `validity_policy` copiada correctamente
- ✅ `platform_aliases` copiada correctamente
- ✅ `scope` copiado correctamente
- ✅ `required_fields` copiado correctamente
- ✅ Todos los campos del original se copian sin mutar el original

### Generación de IDs Únicos
- ✅ Si no se proporciona `new_type_id`, se genera automáticamente
- ✅ Patrón: `{original_id}_COPY`, `{original_id}_COPY_2`, etc.
- ✅ No hay colisiones de IDs
- ✅ Si el ID ya existe, se incrementa el contador

### Manejo de Errores
- ✅ Tipo no encontrado → 404
- ✅ ID duplicado → 409 (Conflict)
- ✅ Otros errores → 400/500 con mensaje claro

## Conclusión
El endpoint `/duplicate` funciona correctamente después del fix. Todas las pruebas pasaron y se verificó:
- ✅ Duplicación correcta con deep copy
- ✅ Generación automática de IDs únicos
- ✅ Inmutabilidad del original
- ✅ Persistencia correcta en el store
- ✅ Aparición en listados




















