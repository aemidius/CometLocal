# Reporte de Pruebas E2E - Fix Persistencia Validity Start Date

## Fecha
2026-01-04T12:05:40.929Z

## Objetivo
Verificar que el valor de "Fecha de inicio de vigencia" persiste después de un fallo de validación al intentar guardar.

## Problema Original
- El usuario rellenaba "Fecha de inicio de vigencia"
- Al pulsar "Guardar todo" salía alerta "hay errores"
- Al cerrar la alerta, el campo se vaciaba
- El valor NO persistía en el estado del card

## Causa Raíz Identificada
1. **Re-render destructivo**: `renderUploadFiles()` recrea todo el DOM con `innerHTML`, perdiendo valores si el estado se muta.
2. **Estado mutado en validación**: La validación podía mutar el estado o `toISODate()` devolvía null.
3. **Input no completamente controlado**: El valor no se sincronizaba desde el DOM al estado antes de validar.

## Fix Aplicado

### 1. Sincronización DOM → Estado antes de validar
- Antes de validar, lee valores desde los inputs del DOM y actualiza el estado.
- Esto captura valores que el usuario escribió pero que no se guardaron (ej: escribió pero no hizo blur).

### 2. NO mutar estado en validación
- La validación solo marca errores, NO muta `file.validity_start_date`.
- `toISODate()` se usa solo para validar, no para sobrescribir el estado.

### 3. Input verdaderamente controlado
- El input tiene value desde el estado (file.validity_start_date).
- Handlers `onchange`, `oninput`, y `onblur` actualizan el estado inmediatamente.
- El estado es la única fuente de verdad.

### 4. Logs de diagnóstico
- Añadidos logs en modo debug para rastrear:
  - Cambios en el input
  - Estado antes de validar
  - Payload antes de enviar
  - Estado después de fallar

### 5. Mensaje de error mejorado
- En vez de solo "Hay X archivos con errores", muestra los errores específicos por archivo.

## Pruebas Realizadas

### Test: Validity start date persiste tras fallo
- ✅ Subir PDF => aparece card
- ✅ Seleccionar tipo con `validity_start_mode='manual'`
- ✅ Rellenar "Fecha de inicio de vigencia" con "2025-07-30"
- ✅ Click "Guardar todo" con error => aparece alerta
- ✅ Cerrar alerta => el input SIGUE conteniendo "2025-07-30" (no vacío)
- ✅ Completar campos faltantes
- ✅ Click "Guardar todo" => guarda correctamente

## Criterios de Aceptación Verificados

✅ El valor de "Fecha de inicio de vigencia" persiste siempre tras validar/guardar fallido
✅ El guardado valida correctamente y envía `validity_start_date` ISO al backend
✅ El render NO recrea inputs de forma que pierdan valores
✅ El estado es la única fuente de verdad (input controlado)

## Archivos de Evidencia

- `01_initial_state.png` - Estado inicial
- `02_fecha_rellena.png` - Fecha de vigencia rellena
- `03_despues_alert.png` - Después del alert de errores
- `04_valor_persiste.png` - Verificación de que el valor persiste
- `05_guardado_exitoso.png` - Guardado exitoso después de corregir errores

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Función `updateUploadValidityStartDate()` mejorada (líneas ~2993-3020)
   - Sincronización DOM → Estado antes de validar (líneas ~3407-3420)
   - Validación sin mutar estado (líneas ~3422-3445)
   - Sincronización antes de enviar payload (líneas ~3450-3460)
   - Logs de diagnóstico añadidos
   - Handlers `onblur` añadido al input

2. **`tests/e2e_upload_validity_persistence.spec.js`**:
   - Test E2E completo que reproduce el bug y verifica el fix
