# Reporte de Pruebas E2E - Fix Clear All

## Fecha
2026-01-08T21:11:37.560Z

## Objetivo
Verificar que el botón "Limpiar todo" restaura correctamente el estado del uploader sin romper la funcionalidad de subida posterior.

## Problema Original
Tras pulsar "Limpiar todo", desaparecían los cards pero el dropzone quedaba "muerto" - no se podían subir más archivos hasta navegar fuera y volver.

## Fix Aplicado
1. **Reset completo del estado**:
   - `uploadFiles = []`
   - Reset del file input (`fileInput.value = ''`)
   - Re-render del DOM

2. **Re-inicialización de listeners**:
   - `setupUploadZone(force=true)` para re-instalar listeners
   - Guarda referencias a handlers para poder removerlos antes de re-instalar
   - Resetea el file input después de procesar archivos (permite seleccionar el mismo archivo de nuevo)

3. **Data-testids añadidos**:
   - `data-testid="upload-clear-all"` - Botón limpiar todo
   - `data-testid="upload-dropzone"` - Zona de drop
   - `data-testid="upload-file-input"` - Input de archivo
   - `data-testid="upload-card-{id}"` - Cards de archivos

## Pruebas Realizadas

### Test 1: Clear All + Upload
- ✅ Subir PDF => aparece card
- ✅ Click "Limpiar todo" => card desaparece
- ✅ Subir nuevo PDF => aparece nuevo card
- ✅ Dropzone sigue funcionando

### Test 2: Drag & Drop después de Clear All
- ✅ Drag & drop funciona después de limpiar

## Criterios de Aceptación Verificados

✅ Tras "Limpiar todo", subir un PDF vuelve a crear card al instante (sin navegar fuera)
✅ El test E2E pasa de forma estable
✅ No hay regresión en drag&drop ni click para seleccionar archivo

## Archivos de Evidencia

- `01_initial_state.png` - Estado inicial
- `02_card_visible.png` - Card visible después de subir
- `03_after_clear.png` - Después de limpiar
- `04_new_card_after_clear.png` - Nuevo card después de limpiar y subir de nuevo

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Función `clearAllUploadFiles()` mejorada (reset completo)
   - Función `setupUploadZone()` mejorada (manejo de listeners)
   - Data-testids añadidos

2. **`tests/e2e_upload_clear_all.spec.js`**:
   - Test E2E completo
