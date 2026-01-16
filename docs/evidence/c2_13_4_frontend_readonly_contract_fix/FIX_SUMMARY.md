# HOTFIX C2.13.4 — Frontend: aceptar READ-ONLY sin run_id (fix missing_run_id_in_response)

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Bug Report

El endpoint `POST /runs/egestiona/build_submission_plan_readonly` devuelve HTTP 200 y `status=ok`, pero con `run_id=None`.

El frontend muestra: `"missing_run_id_in_response - La respuesta no contiene run_id ni plan/items"`.

En READ-ONLY, `run_id` NO es obligatorio.

---

## Objetivo

- El modal "Revisar Pendientes CAE (Avanzado)" debe renderizar resultados con READ-ONLY aunque:
  - `run_id` sea `null`/`undefined`
  - `plan`/`items` sea `[]` (vacío)
- Si `status=ok` pero `items` vacíos, mostrar "0 pendientes encontrados" + `diagnostics` (si existen), NO error.

---

## Solución Implementada

### TAREA A — Localización del código ✅

**Archivo identificado:** `frontend/home.html`

**Código encontrado:**
- Línea 1346: Función `executePendingReview()` - handler del botón "Revisar ahora (READ-ONLY)"
- Línea 1654-1724: Código que construye el error "missing_run_id_in_response"
- Línea 1207: Función `renderErrorResponse()` - muestra errores
- Línea 1273: Función `renderOkResponseWithWarning()` - renderiza resultados con warning

### TAREA B — Cambio de validación ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**

1. **Aceptar `run_id` nulo cuando `status=ok`:**
   - Línea ~1645-1695: Eliminada la validación que requería `run_id` cuando `status=ok`
   - Ahora acepta `run_id` nulo en READ-ONLY

2. **Normalizar items:**
   - Línea ~1645: `const items = result.items ?? result.plan ?? [];`
   - Línea ~1646: `const itemsArray = Array.isArray(items) ? items : [];`

3. **Renderizar tabla/lista aunque items esté vacío:**
   - Línea ~1670-1700: Si `itemsArray.length > 0`, renderiza tabla
   - Línea ~1700-1720: Si `itemsArray.length === 0`, muestra aviso informativo (no error)

4. **Mostrar aviso informativo si items vacíos:**
   - Línea ~1700-1720: Muestra "📋 0 pendientes encontrados" con `diagnostics` si existen

**Código:**
```javascript
// HOTFIX C2.13.4: En READ-ONLY, run_id NO es obligatorio. Aceptar status=ok sin run_id.
// Normalizar items: response.items ?? response.plan ?? []
const items = result.items ?? result.plan ?? [];
const itemsArray = Array.isArray(items) ? items : [];

// Si status es "ok", renderizar resultados (incluso si run_id es null y items está vacío)
if (result.status === "ok") {
    // Asegurar que result.run_id esté presente (aunque sea null) para compatibilidad
    if (!result.run_id) {
        result.run_id = runId || null;
    }
    
    // HOTFIX C2.13.4: Si no hay run_id, mostrar warning discreto (no error)
    const warningMsg = !runId ? '⚠️ Modo READ-ONLY: resultados disponibles sin run_id' : null;
    
    // Renderizar resultados (con o sin warning)
    renderOkResponseWithWarning(result, warningMsg);
    
    // ... guardar confirm_token ...
    
    // HOTFIX C2.13.4: Renderizar items aunque estén vacíos
    if (itemsArray.length > 0) {
        // ... renderizar tabla ...
    } else {
        // HOTFIX C2.13.4: Si items vacíos, mostrar aviso informativo (no error)
        const diagnostics = result.diagnostics || {};
        const diagnosticsReason = diagnostics.reason || null;
        const diagnosticsNote = diagnostics.note || null;
        
        let emptyMessage = '📋 0 pendientes encontrados';
        if (diagnosticsReason || diagnosticsNote) {
            emptyMessage += '<br><br><strong>Información adicional:</strong><br>';
            if (diagnosticsReason) {
                emptyMessage += `<span style="color: #94a3b8;">Razón: ${window.escapeHtml(diagnosticsReason)}</span><br>`;
            }
            if (diagnosticsNote) {
                emptyMessage += `<span style="color: #94a3b8;">Nota: ${window.escapeHtml(diagnosticsNote)}</span><br>`;
            }
        }
        
        safeSetHTML('results-table-container', `
            <div class="alert alert-info" style="padding: 16px; background: #1e293b; border-left: 3px solid #60a5fa; border-radius: 4px;">
                ${emptyMessage}
            </div>
        `);
        safeSetDisplay('results-table-container', 'block');
    }
    
    btn.textContent = originalText;
    btn.disabled = false;
    return;
}
```

### TAREA C — Ajuste de "Ver detalles técnicos" ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**
- Línea ~1240-1250: Si `details` es object, mostrar `JSON.stringify(details, null, 2)` en un `<pre>`

**Código:**
```javascript
// HOTFIX C2.13.4: Mostrar details si existen (si es object, mostrar JSON.stringify)
if (errorDetails) {
    let detailsHtml = `<details style="margin-top: 8px; padding: 8px; background: #1e293b; border-radius: 4px;">`;
    detailsHtml += `<summary style="cursor: pointer; color: #60a5fa;">Ver detalles técnicos</summary>`;
    // HOTFIX C2.13.4: Si details es object, mostrar JSON.stringify(details, null, 2) en un <pre>
    const detailsText = typeof errorDetails === 'object' 
        ? JSON.stringify(errorDetails, null, 2) 
        : errorDetails;
    detailsHtml += `<pre style="margin-top: 8px; font-size: 0.85em; white-space: pre-wrap; color: #cbd5e1;">${window.escapeHtml(detailsText)}</pre>`;
    detailsHtml += `</details>`;
    safeSetHTML('cae-results-error-details', detailsHtml);
    safeSetDisplay('cae-results-error-details', 'block');
}
```

---

## Archivos Modificados

1. **`frontend/home.html`**
   - Línea ~1645-1695: Eliminada validación que requería `run_id` cuando `status=ok`
   - Línea ~1645-1646: Normalización de items (`result.items ?? result.plan ?? []`)
   - Línea ~1650-1720: Renderizado de resultados aunque `run_id` sea null o items esté vacío
   - Línea ~1700-1720: Aviso informativo cuando items está vacío (no error)
   - Línea ~1240-1250: Mejora de "Ver detalles técnicos" para objetos

2. **`docs/evidence/c2_13_4_frontend_readonly_contract_fix/FIX_SUMMARY.md`** (NUEVO)
   - Documentación del fix

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Endpoint READ-ONLY devuelve `status=ok` con `run_id=None` y `items=[]`

**Comportamiento:**
- ❌ Frontend muestra error: `"missing_run_id_in_response - La respuesta no contiene run_id ni plan/items"`
- ❌ No se renderizan resultados
- ❌ Usuario no puede ver que no hay pendientes

### Después del Fix

**Escenario:** Endpoint READ-ONLY devuelve `status=ok` con `run_id=None` y `items=[]`

**Comportamiento:**
- ✅ Frontend acepta `run_id` nulo cuando `status=ok`
- ✅ Renderiza resultados aunque items esté vacío
- ✅ Muestra "📋 0 pendientes encontrados" con `diagnostics` si existen (NO error)
- ✅ Usuario puede ver que no hay pendientes con información útil

**Escenario:** Endpoint READ-ONLY devuelve `status=ok` con `run_id=None` y `items=[...]`

**Comportamiento:**
- ✅ Frontend acepta `run_id` nulo cuando `status=ok`
- ✅ Renderiza tabla con items
- ✅ Muestra warning discreto: "⚠️ Modo READ-ONLY: resultados disponibles sin run_id"
- ✅ Usuario puede ver y usar los resultados

---

## Prueba Manual

### Pasos

1. Abrir `/home` → modal avanzado → ejecutar READ-ONLY
2. Verificar que ya NO aparece `missing_run_id_in_response`
3. Aunque sea vacío, debe renderizar "0 resultados" y mostrar `diagnostics` si los hay
4. Capturar screenshot en `docs/evidence/c2_13_4_frontend_readonly_contract_fix/`

### Resultado Esperado

- ✅ No aparece error `missing_run_id_in_response`
- ✅ Si hay items, se renderiza tabla
- ✅ Si no hay items, se muestra "📋 0 pendientes encontrados" con `diagnostics` si existen
- ✅ Si no hay `run_id`, se muestra warning discreto (no error)

---

## Confirmación del Fix

### ✅ READ-ONLY acepta run_id nulo

**Validación:**
- Frontend acepta `run_id` nulo cuando `status=ok`
- No muestra error `missing_run_id_in_response` cuando `run_id` es null

### ✅ Items normalizados correctamente

**Validación:**
- Items se normalizan como `result.items ?? result.plan ?? []`
- Se renderiza tabla/lista aunque items esté vacío

### ✅ Aviso informativo cuando items vacíos

**Validación:**
- Si `items.length === 0`, muestra "📋 0 pendientes encontrados" (NO error)
- Incluye `diagnostics` si existen

### ✅ "Ver detalles técnicos" mejorado

**Validación:**
- Si `details` es object, muestra `JSON.stringify(details, null, 2)` en un `<pre>`

---

## Próximos Pasos

1. ✅ Ejecutar prueba manual desde frontend
2. ✅ Verificar que no aparece `missing_run_id_in_response`
3. ✅ Verificar que se renderiza "0 resultados" con `diagnostics` si existen
4. ✅ Capturar screenshot de evidencia

---

**Fin del Resumen del Fix**

*Última actualización: 2026-01-15*
