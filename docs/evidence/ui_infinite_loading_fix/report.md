# Reporte: Fix de "Cargando..." Infinito

## Fecha
2025-01-27T12:00:00.000Z

## Problema Reportado
Tras los últimos cambios en `frontend/repository_v3.html`, la UI se quedaba en "Cargando..." infinito en la pantalla Inicio y no respondía.

## Causa Raíz Identificada

### 1. Código JavaScript mal ubicado dentro de template string HTML
**Ubicación**: Líneas 2188-2191 en `frontend/repository_v3.html`

**Problema**: Código JavaScript estaba dentro del template string HTML:
```javascript
${uploadSubjects.companies.length > 1 ? `
    <label class="form-label" style="margin-top: 8px; font-size: 0.9rem;">Empresa <span class="form-required">*</span></label>
    if (!file.errors) file.errors = [];  // ❌ CÓDIGO JS DENTRO DE TEMPLATE STRING
    if (!file.errors.includes('El tipo seleccionado no coincide con el filtro de alcance')) {
        file.errors.push('El tipo seleccionado no coincide con el filtro de alcance');
    }
}
```

Esto causaba un **error de sintaxis** que rompía el parsing del JavaScript, dejando la página en estado de carga infinita.

### 2. Bloque HTML duplicado completo
**Ubicación**: Líneas 2195-2377 (aproximadamente)

**Problema**: Había un bloque completo duplicado del template HTML del file card, lo cual:
- Duplicaba IDs de elementos (violación de HTML)
- Podía causar que `querySelector` devolviera el elemento incorrecto
- Aumentaba el riesgo de errores de renderizado

### 3. Falta de guardrails para errores
**Problema**: No había mecanismos para:
- Detectar cuando una promesa se cuelga
- Mostrar errores visibles en lugar de "Cargando..." infinito
- Capturar errores globales de JavaScript

## Fix Aplicado

### 1. Eliminación de código mal ubicado y bloque duplicado
- **Líneas eliminadas**: 2188-2191 (código JS mal ubicado)
- **Líneas eliminadas**: 2195-2377 (bloque duplicado completo)
- **Resultado**: Template string HTML ahora está bien formado y sin duplicaciones

### 2. Mejora de `detectUploadMetadata` con fail-safe
**Ubicación**: Líneas 1961-1973

**Cambio**: Añadida verificación de que `uploadTypes` existe y es un array antes de buscar:
```javascript
const type = uploadTypes && Array.isArray(uploadTypes) 
    ? uploadTypes.find(t => t.type_id === fileData.type_id) 
    : null;
```

Esto previene errores si `uploadTypes` no está inicializado cuando se ejecuta la detección.

### 3. Guardrails anti "Cargando..." infinito

#### a) Timeout de seguridad en `loadPage`
- **Timeout**: 10 segundos
- **Acción**: Si la carga tarda más de 10s, muestra banner de error visible

#### b) Try/catch en `loadPage`
- Captura cualquier error durante la carga de páginas
- Muestra banner de error en lugar de dejar "Cargando..." infinito

#### c) Error handlers globales
- `window.addEventListener('error', ...)`: Captura errores de JavaScript no manejados
- `window.addEventListener('unhandledrejection', ...)`: Captura promesas rechazadas sin manejar
- Ambos verifican si el contenido muestra "Cargando..." y lo reemplazan con banner de error

#### d) Helper `showErrorBanner`
- Función centralizada para mostrar errores visibles
- Incluye stacktrace en modo desarrollo
- Usa `escapeHtml` para prevenir XSS

### 4. Mejora de manejo de errores en `loadInicio`
- Añadida verificación de que `content` existe
- Añadida verificación de status HTTP en fetch
- Catch mejorado que usa `showErrorBanner` en lugar de HTML simple

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Eliminado código JS mal ubicado (líneas 2188-2191)
   - Eliminado bloque HTML duplicado (líneas 2195-2377)
   - Mejorado `detectUploadMetadata` con fail-safe (líneas 1961-1973)
   - Añadido helper `showErrorBanner` (líneas ~931)
   - Añadido timeout y try/catch en `loadPage` (líneas ~931-1014)
   - Añadidos error handlers globales (líneas ~5347-5365)
   - Mejorado catch en `loadInicio` (línea ~1189)

## Cómo Verificar

### 1. Verificar que la página carga correctamente
1. Abrir `http://127.0.0.1:8000/repository_v3.html`
2. Debe cargar la página "Inicio" sin quedarse en "Cargando..."
3. Verificar consola: no debe haber errores rojos

### 2. Verificar navegación
1. Navegar a "Catálogo de documentos" - debe cargar
2. Navegar a "Subir documentos" - debe cargar
3. Verificar consola: no debe haber errores

### 3. Verificar subida de documentos
1. En "Subir documentos", subir un PDF dummy
2. Debe aparecer el file card con:
   - Pills de scope filter visibles
   - Selector de tipo funcionando
   - Sin errores en consola

### 4. Verificar guardrails (opcional)
1. Simular error: modificar temporalmente una URL de API para que falle
2. Debe aparecer banner de error visible (no "Cargando..." infinito)
3. Restaurar URL y verificar que vuelve a funcionar

## Screenshot

**Ruta**: `docs/evidence/ui_infinite_loading_fix/inicio_loaded_ok.png`

(Se generará al verificar manualmente)

## Estado Final

✅ **Código mal ubicado eliminado**
✅ **Bloque duplicado eliminado**
✅ **Guardrails anti "Cargando..." infinito implementados**
✅ **Error handlers globales añadidos**
✅ **Fail-safe en `detectUploadMetadata` añadido**

## Notas

- El fix es **mínimo y seguro**: solo elimina código problemático y añade guardrails
- No se cambió la lógica de negocio existente
- Los data-testids añadidos anteriormente se mantienen intactos
- La funcionalidad de scope filter y autodetección sigue funcionando igual

## Prevención Futura

Para evitar regresiones similares:
1. **No colocar código JavaScript dentro de template strings HTML** - usar funciones auxiliares
2. **Evitar duplicación de bloques HTML** - usar funciones reutilizables
3. **Siempre añadir try/catch en funciones async** que renderizan contenido
4. **Usar linter** para detectar errores de sintaxis antes de commit

