# Evidencia: Fix del endpoint /duplicate (DESPUÉS DEL FIX)

## Fecha
2025-12-30

## Estado
✅ **BUG CORREGIDO Y VALIDADO**

## Cambios Implementados

### 1. Fix del Deep Copy
**Archivo**: `backend/repository/document_repository_store_v1.py`

**Problema**: `model_dump()` incluye `type_id`, y luego se pasaba `type_id=new_type_id` explícitamente, causando conflicto.

**Solución**:
```python
# Deep copy: excluir type_id y name del dump para evitar conflictos
original_dict = original.model_dump()
original_dict.pop('type_id', None)
original_dict.pop('name', None)

new_type = DocumentTypeV1(
    **original_dict,
    type_id=new_type_id,
    name=new_name or f"{original.name} (copia)"
)
```

### 2. Generación Automática de IDs Únicos
**Archivo**: `backend/repository/document_repository_store_v1.py`

**Nuevo método**:
```python
def _generate_unique_type_id(self, base_type_id: str) -> str:
    """Genera un type_id único basado en el original: {base}_COPY, {base}_COPY_2, etc."""
    types_dict = self._read_types()
    candidate = f"{base_type_id}_COPY"
    if candidate not in types_dict:
        return candidate
    
    counter = 2
    while True:
        candidate = f"{base_type_id}_COPY_{counter}"
        if candidate not in types_dict:
            return candidate
        counter += 1
        if counter > 1000:
            raise ValueError(f"Cannot generate unique type_id for {base_type_id} after 1000 attempts")
```

**Uso**: Si `new_type_id` no se proporciona en el request, se genera automáticamente.

### 3. Manejo de Errores Mejorado
**Archivo**: `backend/repository/document_repository_routes.py`

**Cambios**:
- Tipo no encontrado → 404
- ID duplicado → 409 (Conflict)
- Otros errores → 400/500 con mensaje claro
- Logging de errores para debugging

### 4. Soporte para new_type_id Opcional
**Archivo**: `backend/repository/document_repository_routes.py`

**Cambio**:
```python
class DuplicateTypeRequest(BaseModel):
    new_type_id: Optional[str] = None  # Ahora es opcional
    new_name: Optional[str] = None
```

Si `new_type_id` es `None`, se genera automáticamente.

## Validación Completa

### Pruebas API ✅
Ver `api_duplicate_smoke.md` para detalles completos.

**Resumen**:
- ✅ Duplicar tipo existente → 200 OK
- ✅ Duplicar mismo tipo 3 veces → IDs únicos generados (`_COPY`, `_COPY_2`, `_COPY_3`)
- ✅ Los nuevos tipos aparecen en el listado
- ✅ Inmutabilidad del original verificada

### Pruebas UI ✅
- ✅ La UI muestra correctamente los tipos duplicados en la tabla
- ✅ Los IDs únicos se muestran correctamente (sufijos `_COPY`, `_COPY_2`, etc.)
- ✅ Los nombres incluyen "(copia)" para distinguirlos
- ✅ Todos los campos se copian correctamente (aliases, validity_policy, scope, etc.)

**Capturas**:
- `10_duplicate_action.png` - Tabla con tipos duplicados visibles
- `11_duplicate_created.png` - Confirmación visual de duplicados creados

## Invariantes Mantenidas

✅ **Atomic writes**: El store persiste con `_atomic_write_json`
✅ **Normalización**: Los tipos se normalizan correctamente al guardar
✅ **Compatibilidad UI**: El endpoint funciona con `frontend/repository_v3.html`
✅ **Deep copy**: El original NO se muta (inmutabilidad verificada)
✅ **Sin colisiones**: Los IDs generados son únicos

## Notas Técnicas

### Generación de IDs Únicos
- Patrón: `{original_id}_COPY`, `{original_id}_COPY_2`, `{original_id}_COPY_3`, etc.
- Verifica existencia antes de generar
- Protección contra loops infinitos (máximo 1000 intentos)

### Deep Copy
- Excluye `type_id` y `name` del dump original
- Copia todos los demás campos (validity_policy, platform_aliases, scope, etc.)
- El original permanece inalterado

### Manejo de Errores
- ValueError para errores de negocio (404, 409)
- Exception genérica para errores inesperados (500 con logging)
- Mensajes de error claros y descriptivos

## Conclusión

El endpoint `/duplicate` está **completamente funcional** después del fix. Todas las pruebas pasaron y se verificó:
- ✅ Corrección del bug 500
- ✅ Generación automática de IDs únicos
- ✅ Deep copy correcto sin mutar el original
- ✅ Persistencia atómica
- ✅ Compatibilidad con UI
- ✅ Manejo robusto de errores

**Estado**: ✅ LISTO PARA PRODUCCIÓN




















