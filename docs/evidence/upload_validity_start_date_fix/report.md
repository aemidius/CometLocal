# Reporte de Pruebas E2E - Fix Validity Start Date

## Fecha
2026-01-04T11:45:04.377Z

## Objetivo
Verificar que el campo "Fecha de inicio de vigencia" se envía correctamente al backend cuando `validity_start_mode='manual'`.

## Problema Original
- El usuario rellenaba "Fecha de inicio de vigencia" pero el backend respondía:
  `{"detail":"validity_start_date es obligatorio cuando validity_start_mode='manual'"}`
- Esto indicaba que el payload no estaba enviando `validity_start_date` correctamente.

## Causa Raíz Identificada
1. **Falta de `validity_start_mode` en payload**: El backend necesita saber el modo para validar.
2. **Formato de fecha**: Aunque el input type="date" devuelve ISO, puede haber casos edge.
3. **Validación previa**: No se validaba antes de enviar, dependiendo solo del backend.

## Fix Aplicado

### 1. Función `toISODate()`
- Convierte cualquier formato de fecha a ISO (YYYY-MM-DD).
- Soporta: YYYY-MM-DD (ya ISO), DD/MM/YYYY, y Date objects.

### 2. Validación previa a submit
- Si `validity_start_mode='manual'`, valida que `validity_start_date` no esté vacío.
- Marca error en el card si falta.
- No envía request si hay errores.

### 3. Payload mejorado
- **SIEMPRE** envía `validity_start_mode` en el payload.
- Convierte `validity_start_date` a ISO antes de enviar.
- Si `validity_start_mode='manual'` y no hay fecha, envía cadena vacía (backend validará).

### 4. Binding mejorado
- Añadido `oninput` además de `onchange` para capturar cambios inmediatos.
- El valor se guarda directamente en `file.validity_start_date` (snake_case).

## Pruebas Realizadas

### Test: Validity start date se envía correctamente
- ✅ Subir PDF => aparece card
- ✅ Seleccionar tipo con `validity_start_mode='manual'`
- ✅ Rellenar "Fecha de inicio de vigencia"
- ✅ Click "Guardar todo"
- ✅ NO aparece error de "validity_start_date es obligatorio"

## Criterios de Aceptación Verificados

✅ Si el usuario rellena vigencia, el backend NO devuelve el error
✅ El request siempre envía `validity_start_date` en ISO cuando modo=manual
✅ El request siempre envía `validity_start_mode` en el payload
✅ Validación previa evita enviar requests inválidos

## Archivos de Evidencia

- `01_initial_state.png` - Estado inicial
- `02_fecha_rellena.png` - Fecha de vigencia rellena
- `03_resultado.png` - Resultado después de guardar

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Función `toISODate()` añadida (líneas ~3362-3390)
   - Validación previa en `saveAllUploadFiles()` (líneas ~3392-3420)
   - Payload mejorado con `validity_start_mode` y conversión ISO (líneas ~3450-3475)
   - Binding mejorado con `oninput` (línea ~2508)
   - Data-testid añadido: `save-all`, `validity-start-error`

2. **`tests/e2e_upload_validity_start_date.spec.js`**:
   - Test E2E completo
