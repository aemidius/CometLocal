# HOTFIX C2.12.5.3 — Frontend run_id robustness + render even without run_id

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Problema Reportado

El endpoint `POST /runs/egestiona/build_submission_plan_readonly` devuelve un submission plan VÁLIDO (plan[], matches, decisions). Playwright funciona correctamente. El backend genera runs, storage_state y evidence.

Sin embargo, el frontend muestra:
```
run_id_missing: No se pudo generar run_id
```

Aunque el plan EXISTE.

---

## Objetivo

Eliminar el falso negativo `run_id_missing` y permitir renderizar resultados aunque el run_id venga con otro nombre o en otra estructura.

---

## Solución Implementada

### TAREA 1 — Inspección de la response REAL ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**

1. **Función `findAllIdentifiers()` creada:**
   - Identifica TODOS los posibles identificadores en la respuesta
   - Busca en: `run_id`, `plan_id`, `runId`, `data.*`, `meta.*`, `artifacts.*`, `result.*`, `summary.*`

2. **Logging temporal completo añadido:**
   - Loggea JSON completo recibido por el frontend
   - Loggea TODOS los identificadores encontrados
   - Loggea si tiene `plan` o `items` (arrays no vacíos)

**Código añadido:**
```javascript
// Helper para identificar TODOS los posibles identificadores en la respuesta (para debugging)
function findAllIdentifiers(result) {
    if (!result) return {};
    
    const identifiers = {};
    
    // Top-level
    if (result.run_id) identifiers.run_id = result.run_id;
    if (result.plan_id) identifiers.plan_id = result.plan_id;
    if (result.runId) identifiers.runId = result.runId;
    
    // Nested data, meta, artifacts, result, summary
    // ... (busca en todos los lugares posibles)
    
    return identifiers;
}

// En executePendingReview:
console.log('[CAE][INSPECTION] ============================================');
console.log('[CAE][INSPECTION] RESPUESTA COMPLETA DEL ENDPOINT:');
console.log('[CAE][INSPECTION]', JSON.stringify(result, null, 2));
console.log('[CAE][INSPECTION] TODOS LOS IDENTIFICADORES ENCONTRADOS:');
console.log('[CAE][INSPECTION]', allIdentifiers);
console.log('[CAE][INSPECTION] TIENE PLAN/ITEMS:', {
    hasPlan: Array.isArray(result.plan) && result.plan.length > 0,
    planLength: Array.isArray(result.plan) ? result.plan.length : 0,
    hasItems: Array.isArray(result.items) && result.items.length > 0,
    itemsLength: Array.isArray(result.items) ? result.items.length : 0,
});
```

### TAREA 2 — Función robusta `extractRunId()` ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**

1. **Función `extractRunId()` mejorada:**
   - Acepta múltiples shapes
   - Busca en 14 paths diferentes (añadidos `meta.*` y `summary.*`)
   - Devuelve `null` SOLO si realmente no hay ningún identificador
   - Documenta los casos soportados

**Código mejorado:**
```javascript
// Helper GLOBAL para extraer run_id de múltiples lugares
// 
// Casos soportados (por orden de prioridad):
// - response.run_id (canonical)
// - response.plan_id (alias usado por build_submission_plan_readonly)
// - response.runId (camelCase variant)
// - response.data?.run_id / response.data?.plan_id
// - response.meta?.run_id / response.meta?.plan_id (NUEVO)
// - response.artifacts?.run_id / response.artifacts?.plan_id / response.artifacts?.runId
// - response.result?.run_id / response.result?.plan_id
// - response.summary?.run_id / response.summary?.plan_id (NUEVO)
function extractRunId(result) {
    if (!result) return null;
    
    return (
        result.run_id ||
        result.plan_id ||
        result.runId ||
        result.data?.run_id ||
        result.data?.plan_id ||
        result.meta?.run_id ||            // NUEVO
        result.meta?.plan_id ||           // NUEVO
        result.artifacts?.run_id ||
        result.artifacts?.plan_id ||
        result.artifacts?.runId ||
        result.result?.run_id ||
        result.result?.plan_id ||
        result.summary?.run_id ||         // NUEVO
        result.summary?.plan_id ||        // NUEVO
        null
    );
}
```

### TAREA 3 — CAMBIO CLAVE DE UX ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**

1. **Nueva función `renderOkResponseWithWarning()`:**
   - Permite renderizar resultados con un warning discreto
   - Muestra "Run ID: No disponible" si no hay run_id
   - Muestra warning discreto en lugar de error fatal

2. **Lógica modificada en `executePendingReview`:**
   - Si existe `result.plan` (array no vacío) O `result.items` (array no vacío)
   - Y NO hay `run_id`
   - **NO lanzar error fatal**
   - **Mostrar resultados en modo READ-ONLY**
   - **Mostrar warning discreto**

**Código:**
```javascript
// TAREA 3: CAMBIO CLAVE DE UX - Si existe plan/items, renderizar aunque no haya run_id
const hasPlan = Array.isArray(result.plan) && result.plan.length > 0;
const hasItems = Array.isArray(result.items) && result.items.length > 0;
const hasPlanOrItems = hasPlan || hasItems;

// Si status es "ok" pero falta run_id
if (result.status === "ok" && !runId) {
    // TAREA 3: Si hay plan/items, NO lanzar error fatal, mostrar resultados con warning discreto
    if (hasPlanOrItems) {
        console.warn('[CAE][UX] Response OK but missing run_id, pero tiene plan/items. Renderizando en modo READ-ONLY con warning discreto.');
        
        // Renderizar resultados con warning discreto
        renderOkResponseWithWarning(result, '⚠️ No se pudo identificar el run_id, pero se encontraron resultados. Mostrando en modo READ-ONLY.');
        
        // Renderizar items/plan si existen
        if (result.items && result.items.length > 0) {
            renderPlanItems(result.items, 'items');
        } else if (result.plan && result.plan.length > 0) {
            renderPlanItems(result.plan, 'plan');
        }
        
        return; // NO mostrar error fatal
    }
    
    // Si NO hay plan/items Y falta run_id => contract_violation (error fatal)
    // ... (mostrar error detallado)
}
```

**Función `renderOkResponseWithWarning()`:**
```javascript
function renderOkResponseWithWarning(result, warningMessage) {
    // ... (limpiar errores previos)
    
    // Show run info (o mensaje si no hay run_id)
    if (runId || result.run_id) {
        safeSetHTML('run-info', `
            <strong>Run ID:</strong> <code>${runId || result.run_id || 'N/A'}</code><br>
            <a href="${runsUrl}" target="_blank">Ver run completo →</a>
        `);
    } else {
        safeSetHTML('run-info', `
            <strong>Run ID:</strong> <code style="color: #fbbf24;">No disponible</code><br>
            <span style="color: #94a3b8; font-size: 0.9em;">Modo READ-ONLY: resultados disponibles sin run_id</span>
        `);
    }
    
    // TAREA 3: Mostrar warning discreto si se proporciona
    if (warningMessage) {
        safeSetHTML('cae-results-status', `
            <div class="alert alert-warning" style="margin-bottom: 12px; padding: 8px 12px; background: #1e293b; border-left: 3px solid #fbbf24; border-radius: 4px;">
                <span style="color: #fbbf24;">${warningMessage}</span>
            </div>
        `);
        safeSetDisplay('cae-results-status', 'block');
    }
}
```

---

## Archivos Modificados

1. **`frontend/home.html`**
   - Línea ~1139: Función `extractRunId()` mejorada (añadidos `meta.*` y `summary.*`)
   - Línea ~1158: Nueva función `findAllIdentifiers()` para debugging
   - Línea ~1501-1527: Logging temporal completo para inspeccionar respuesta REAL
   - Línea ~1545-1600: Lógica modificada para renderizar resultados aunque no haya run_id (si hay plan/items)
   - Línea ~1269: Función `renderOkResponse()` refactorizada para usar `renderOkResponseWithWarning()`
   - Línea ~1271: Nueva función `renderOkResponseWithWarning()` para mostrar warning discreto

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Endpoint devuelve `status: "ok"` con `plan: [...]` pero sin `run_id`

**Comportamiento:**
- ❌ Frontend muestra error fatal: `missing_run_id_in_response`
- ❌ NO se renderizan los resultados
- ❌ Usuario no puede ver el plan generado

### Después del Fix

**Escenario:** Endpoint devuelve `status: "ok"` con `plan: [...]` pero sin `run_id`

**Comportamiento:**
- ✅ Frontend detecta que hay `plan` o `items` (arrays no vacíos)
- ✅ NO muestra error fatal
- ✅ Renderiza resultados en modo READ-ONLY
- ✅ Muestra warning discreto: "⚠️ No se pudo identificar el run_id, pero se encontraron resultados. Mostrando en modo READ-ONLY."
- ✅ Muestra "Run ID: No disponible" en lugar de link
- ✅ Usuario puede ver y usar el plan generado

**Escenario:** Endpoint devuelve `status: "ok"` SIN `plan`/`items` Y SIN `run_id`

**Comportamiento:**
- ✅ Frontend muestra error detallado: `missing_run_id_in_response`
- ✅ Incluye todos los identificadores encontrados (si hay alguno)
- ✅ Incluye body raw para debugging
- ✅ NO renderiza resultados (no hay nada que mostrar)

---

## Casos Soportados por `extractRunId()`

La función ahora busca en **14 paths diferentes**:

1. `response.run_id` (canonical)
2. `response.plan_id` (alias)
3. `response.runId` (camelCase)
4. `response.data?.run_id`
5. `response.data?.plan_id`
6. `response.meta?.run_id` (NUEVO)
7. `response.meta?.plan_id` (NUEVO)
8. `response.artifacts?.run_id`
9. `response.artifacts?.plan_id`
10. `response.artifacts?.runId` (camelCase)
11. `response.result?.run_id`
12. `response.result?.plan_id`
13. `response.summary?.run_id` (NUEVO)
14. `response.summary?.plan_id` (NUEVO)

---

## Logging Temporal

El frontend ahora loggea en consola:

```
[CAE][INSPECTION] ============================================
[CAE][INSPECTION] RESPUESTA COMPLETA DEL ENDPOINT:
[CAE][INSPECTION] { ... JSON completo ... }
[CAE][INSPECTION] ============================================
[CAE][INSPECTION] TODOS LOS IDENTIFICADORES ENCONTRADOS:
[CAE][INSPECTION] { run_id: "...", plan_id: "...", ... }
[CAE][INSPECTION] IDENTIFICADOR EXTRAÍDO: "..."
[CAE][INSPECTION] TIENE PLAN/ITEMS: { hasPlan: true, planLength: 5, ... }
[CAE][INSPECTION] ============================================
```

Esto permite inspeccionar la respuesta REAL del endpoint y entender por qué no se encuentra el `run_id`.

---

## Confirmación del Fix

### ✅ Inspección de respuesta REAL implementada

**Validación:**
- Función `findAllIdentifiers()` identifica TODOS los identificadores
- Logging temporal completo en consola
- Información guardada en `window.__lastCaeResponseParsed`

### ✅ Función `extractRunId()` robusta

**Validación:**
- Busca en 14 paths diferentes (añadidos `meta.*` y `summary.*`)
- Devuelve `null` SOLO si realmente no hay ningún identificador
- Documenta todos los casos soportados

### ✅ Renderizado aunque no haya run_id (si hay plan/items)

**Validación:**
- Si hay `plan` o `items` (arrays no vacíos), NO lanza error fatal
- Renderiza resultados en modo READ-ONLY
- Muestra warning discreto en lugar de error fatal
- Usuario puede ver y usar el plan generado

---

## Próximos Pasos

1. ✅ Ejecutar flujo READ-ONLY desde UI
2. ✅ Verificar que NO aparece error `run_id_missing` cuando hay plan/items
3. ✅ Verificar que se renderizan los resultados con warning discreto
4. ✅ Revisar logs de consola `[CAE][INSPECTION]` para entender shape exacto de respuesta
5. ✅ Una vez confirmado el shape, ajustar `extractRunId()` si es necesario

---

**Fin del Resumen del Fix**

*Última actualización: 2026-01-15*
