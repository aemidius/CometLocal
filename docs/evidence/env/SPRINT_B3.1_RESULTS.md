# SPRINT B3.1: Fix Aplicado - Señales DOM Robustas

## Estado Actual

### Implementación Completada

1. ✅ **Helper `setViewState()` creado**: Función para establecer estados `loaded`, `ready`, `error`
2. ✅ **Código en `loadPage()` actualizado**: Todos los casos (`calendario`, `subir`, `buscar`, `coordinacion`, `settings`, `inicio`) usan `setViewState()`
3. ✅ **Helper `gotoHash()` actualizado**: Espera primero `loaded`, luego hace race entre `ready` y `error`
4. ✅ **`loadCalendario()` corregido**: Ahora propaga errores correctamente

### Problema Identificado

**Síntoma**: Los tests detectan `view-calendario-loaded` pero NO detectan `view-calendario-ready` ni `view-calendario-error` dentro del timeout.

**Posibles causas**:
1. `loadCalendario()` está completando sin errores pero `setViewState('calendario', 'ready')` no se ejecuta
2. Hay un problema de timing donde el atributo se establece pero se sobrescribe después
3. El código de `loadPage()` puede tener un problema de flujo de ejecución

### Próximos Pasos

1. Verificar logs de consola del navegador para ver si `setViewState()` se está llamando
2. Verificar que `loadCalendario()` realmente completa sin errores
3. Añadir más logging para entender el flujo de ejecución

## Archivos Modificados

- `frontend/repository_v3.html`: 
  - Función `setViewState()` añadida
  - Código de `loadPage()` actualizado para usar `setViewState()`
  - `loadCalendario()` corregido para propagar errores
- `tests/helpers/e2eSeed.js`: 
  - `gotoHash()` actualizado para esperar `loaded` primero, luego race entre `ready` y `error`

## Tests Ejecutados

- `tests/e2e_calendar_pending_smoke.spec.js`: ❌ Falla (detecta `loaded` pero no `ready`/`error`)
- `tests/e2e_upload_preview.spec.js`: ❌ Falla (mismo patrón)
- `tests/cae_plan_e2e.spec.js`: Pendiente


