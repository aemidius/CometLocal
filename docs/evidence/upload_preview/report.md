# Reporte de Pruebas E2E - Preview de Documentos

## Fecha
2026-01-12T19:36:41.178Z

## Objetivo
Verificar que el botón "Previsualizar" en cada card de archivo subido abre correctamente un modal con la previsualización del PDF.

## Funcionalidad Implementada

### Botón "Previsualizar"
- Ubicado en cada card junto al botón "Eliminar"
- Visible antes y después de guardar
- Data-testid: `preview-btn-{file.id}`

### Modal de Preview
- Modal centrado con título (nombre del archivo)
- Iframe embebido para mostrar PDF
- Botón "Cerrar" (✕)
- Cierre con Esc y click fuera del modal
- Bloqueo de scroll del fondo mientras está abierto

### Preview de Archivo Local
- Usa `URL.createObjectURL(file)` para archivos locales
- Revoca la URL al cerrar el modal (evita memory leaks)
- Limpia el iframe (src = about:blank) al cerrar

### Preview de Documento Guardado (opcional)
- Si el card tiene `doc_id`, usa endpoint: `/api/repository/docs/{doc_id}/pdf`
- Si no, usa el blob local

## Pruebas Realizadas

### Test 1: Preview de archivo local antes de guardar
- ✅ Subir PDF => aparece card con botón "Previsualizar"
- ✅ Click en "Previsualizar" => modal visible
- ✅ Iframe tiene src definido (no vacío)
- ✅ Cerrar modal => modal se oculta, iframe se limpia
- ✅ UI sigue operativa después de cerrar

### Test 2: Preview cierra con Esc
- ✅ Abrir preview
- ✅ Presionar Esc => modal se cierra

## Criterios de Aceptación Verificados

✅ Para cada card aparece el botón "Previsualizar"
✅ Abre modal y muestra el PDF del archivo local
✅ Cerrar modal libera URL (sin memory leak) y la UI sigue operativa
✅ E2E PASS

## Archivos de Evidencia

- `01_initial_state.png` - Estado inicial
- `02_card_with_preview_button.png` - Card con botón Previsualizar visible
- `03_preview_modal_open.png` - Modal abierto con preview
- `04_after_close.png` - Después de cerrar el modal

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Botón "Previsualizar" añadido en cada card (línea ~2467)
   - Modal de preview añadido (líneas ~1762-1785)
   - Función `previewUploadFile()` implementada (líneas ~3135-3210)
   - Función `closePreviewModal()` implementada (líneas ~3212-3240)
   - Estado global `previewState` para gestionar preview
   - Data-testids añadidos

2. **`tests/e2e_upload_preview.spec.js`**:
   - Test E2E completo con 2 casos de prueba
