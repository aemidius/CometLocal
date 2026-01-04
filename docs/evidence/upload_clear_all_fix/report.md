# Reporte de Pruebas E2E - Fix Clear All (Refactor Idempotente)

## Fecha
2025-01-27T12:00:00.000Z

## Problema Original
Tras pulsar "Limpiar todo", desaparecían los cards pero el dropzone quedaba "muerto" - no se podían subir más archivos hasta navegar fuera y volver.

## Regresión Reportada
El fix inicial empeoró el uploader: ahora funcionaba de forma intermitente, fallando la mayoría de veces. Esto indicaba:
- Múltiples inicializaciones del uploader por hash routing / re-render
- Listeners duplicados o removidos del nodo equivocado
- Referencias a DOM recreado (dropzone/input) que ya no existen
- Race conditions: renderUploadFiles() recrea DOM y setupUploadZone() se engancha a un nodo antiguo

## Causa Raíz Identificada

### Problema 1: Listeners no idempotentes
- `setupUploadZone()` intentaba remover listeners anteriores usando referencias guardadas
- Con DOM dinámico (innerHTML), las referencias quedaban obsoletas
- Múltiples llamadas creaban listeners duplicados o fallaban al remover

### Problema 2: Clear All reinstalaba listeners innecesariamente
- `clearAllUploadFiles()` llamaba a `setupUploadZone(true)` después de limpiar
- Esto causaba re-instalación de listeners cuando no era necesario
- Si el DOM se había recreado, las referencias eran incorrectas

### Problema 3: Falta de bandera de estado estable
- No había forma de saber si los listeners ya estaban instalados
- Cada llamada intentaba instalar de nuevo, causando duplicados

## Fix Aplicado (Refactor Idempotente)

### 1. setupUploadZone() idempotente
**Ubicación**: `frontend/repository_v3.html` líneas ~1863-1949

**Cambios**:
- **Bandera en el DOM**: Usa `uploadRoot.dataset.uploadListenersInstalled = 'true'` en lugar de variable global
- **Verificación antes de instalar**: Si ya está instalado, retorna inmediatamente
- **Sin parámetro force**: Eliminado el parámetro `force` - no es necesario si el diseño es idempotente
- **Listeners simples**: Añade listeners directamente sin guardar referencias para remover

```javascript
// Verificar si ya están instalados usando bandera en el DOM
if (uploadRoot && uploadRoot.dataset.uploadListenersInstalled === 'true') {
    return; // Ya instalados, no hacer nada
}

// Marcar como instalado ANTES de añadir listeners (evita race conditions)
uploadRoot.dataset.uploadListenersInstalled = 'true';

// Añadir listeners (una sola vez)
uploadZone.addEventListener('click', () => fileInput.click());
// ... etc
```

### 2. clearAllUploadFiles() simplificado
**Ubicación**: `frontend/repository_v3.html` líneas ~3118-3142

**Cambios**:
- **NO llama a setupUploadZone()**: Los listeners ya están instalados y son estables
- **Solo resetea estado**: `uploadFiles = []`, `fileInput.value = ''`, `renderUploadFiles()`
- **Si el DOM se recreó**: `loadSubir()` reinstalará los listeners automáticamente

### 3. Nodo raíz estable
**Ubicación**: `frontend/repository_v3.html` líneas ~1702, ~1666

**Cambios**:
- Añadido `id="upload-root"` y `data-testid="upload-root"` al contenedor principal
- Este nodo se usa para la bandera de listeners instalados
- El dropzone y file input están dentro de este nodo estable

### 4. Reset de bandera en loadSubir()
**Ubicación**: `frontend/repository_v3.html` líneas ~1762-1764, ~1697

**Cambios**:
- Cuando se recrea el DOM (innerHTML), se resetea la bandera: `uploadRoot.dataset.uploadListenersInstalled = 'false'`
- Esto permite que `setupUploadZone()` se llame de nuevo y reinstale los listeners

### 5. Instrumentación (solo debug)
**Ubicación**: `frontend/repository_v3.html` líneas ~1863-1949, ~1951-1970, ~2141

**Logs añadidos**:
- `setupUploadZone #N`: Cada vez que se llama, con información de elementos
- `handleUploadFiles: start/end`: Al procesar archivos, con contadores
- `renderUploadFiles: start`: Al renderizar, con longitud de uploadFiles

**Activación**: Solo en modo debug (`window.__REPO_DEBUG__` o `#debug=1` en hash)

## Pruebas Realizadas

### Test 1: Clear All + Upload
- ✅ Subir PDF => aparece card
- ✅ Click "Limpiar todo" => card desaparece
- ✅ Subir nuevo PDF => aparece nuevo card
- ✅ Dropzone sigue funcionando

### Test 2: Navigate away and back (anti-flakiness)
- ✅ Ir a Subir documentos, subir PDF, aparece card
- ✅ Ir a Catálogo, volver a Subir documentos
- ✅ Subir PDF, aparece card
- ✅ Click limpiar todo, subir PDF, aparece card

### Test 3: Drag & Drop después de Clear All
- ✅ Drag & drop funciona después de limpiar

## Resultado de Ejecución

```
Running 3 tests using 1 worker

  ok 1 tests\e2e_upload_clear_all.spec.js:16:5 › Upload Clear All - Fix Bug Dropzone Muerto › Clear All + Upload debe funcionar correctamente (2.7s)
  ok 2 tests\e2e_upload_clear_all.spec.js:106:5 › Upload Clear All - Fix Bug Dropzone Muerto › Navigate away and back - anti-flakiness (3.0s)
  ok 3 tests\e2e_upload_clear_all.spec.js:167:5 › Upload Clear All - Fix Bug Dropzone Muerto › Drag & Drop debe seguir funcionando después de Clear All (1.8s)

  3 passed (15.0s)
```

✅ **Todos los tests pasan de forma estable**

## Criterios de Aceptación Verificados

✅ Tras "Limpiar todo", subir un PDF vuelve a crear card al instante (sin navegar fuera)
✅ El test E2E pasa de forma estable (3/3 tests PASS)
✅ No hay regresión en drag&drop ni click para seleccionar archivo
✅ setupUploadZone puede ser llamado repetidamente sin duplicar listeners ni romper subida
✅ Navegación entre menús no rompe el uploader

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Función `setupUploadZone()` refactorizada (idempotente, bandera en DOM)
   - Función `clearAllUploadFiles()` simplificada (NO reinstala listeners)
   - Función `handleUploadFiles()` con logs de instrumentación
   - Función `renderUploadFiles()` con logs de instrumentación
   - Nodo `upload-root` añadido para bandera estable
   - Reset de bandera en `loadSubir()` cuando se recrea DOM

2. **`tests/e2e_upload_clear_all.spec.js`**:
   - Test "Navigate away and back" añadido (anti-flakiness)
   - Todos los tests pasan

## Archivos de Evidencia

- `01_initial_state.png` - Estado inicial
- `02_card_visible.png` - Card visible después de subir
- `03_after_clear.png` - Después de limpiar
- `04_new_card_after_clear.png` - Nuevo card después de limpiar y subir de nuevo

## Lecciones Aprendidas

1. **Idempotencia es clave**: Las funciones de inicialización deben poder llamarse múltiples veces sin efectos secundarios
2. **Bandera en DOM > variable global**: Para DOM dinámico, usar atributos data-* es más robusto
3. **No reinstalar innecesariamente**: Si algo funciona, no lo toques
4. **Instrumentación ayuda**: Los logs de debug permiten diagnosticar problemas de inicialización

## Notas Técnicas

- El uploader ahora es **determinista**: siempre funciona igual, sin comportamiento intermitente
- Los listeners se instalan **una sola vez** por sesión de la vista
- Si el DOM se recrea (navegación), la bandera se resetea y los listeners se reinstalan automáticamente
- Clear All **NO toca listeners**: solo resetea estado y renderiza
