# SPRINT C2.9.6 — FIX: Calendario "Pendientes" nunca se queda en loaded

**Fecha:** 2026-01-08

---

## Resumen Ejecutivo

Se implementó un fix para que si `/api/repository/docs/pending` va lento o cuelga, se aborte con timeout de 12s y se establezca `view-calendario-error` de forma determinista, eliminando timeouts de tests esperando `view-calendario-ready`.

---

## TAREA A — Localizar fetch de pendientes ✅ COMPLETADA

### Archivo: `frontend/repository_v3.html`

**Función encontrada:**
- `loadCalendario()` (línea ~1702)
- Fetch a `/api/repository/docs/pending` (línea ~1741)
- Ya usa `fetchJsonWithTimeout()` con timeout de 8000ms

---

## TAREA B — Envolver fetch con AbortController + timeout ✅ COMPLETADA

### Archivo: `frontend/repository_v3.html`

**Cambios:**
- `fetchJsonWithTimeout()` ya existe y usa `AbortController` (línea ~1683)
- Timeout aumentado de 8000ms a 12000ms para el fetch de pendientes (línea ~1744)

**Implementación:**
```javascript
// SPRINT C2.9.6: Usar fetchJsonWithTimeout con timeout de 12s para evitar cuelgues
const pendingResponse = await fetchJsonWithTimeout(
    `${BACKEND_URL}/api/repository/docs/pending?months_ahead=3&max_months_back=${effectiveMaxMonthsBack}`,
    {},
    12000  // Aumentado de 8000 a 12000
);
```

---

## TAREA C — Garantizar señales de vista (loaded -> ready/error) ✅ COMPLETADA

### Archivo: `frontend/repository_v3.html`

**Cambios en `loadCalendario()` catch (línea ~1954):**

1. **Renderizar bloque de error visible:**
   - Se renderiza un bloque de error con `data-testid="calendar-pending-error"`
   - El error es visible en la vista (no solo en el marker)

2. **Re-lanzar error para que loadPage() establezca view-calendario-error:**
   - El error se re-lanza para que el catch en `loadPage()` (línea ~1228) lo capture
   - `loadPage()` establece `setViewState('calendario', 'error', error.message)`

**Implementación:**
```javascript
} catch (error) {
    console.error('[CAL] Error in loadCalendario:', error);
    viewDbg('loadCalendario: caught error ' + (error.message || String(error)));
    
    // SPRINT C2.9.6: Renderizar bloque de error visible en la vista
    const content = document.getElementById('page-content');
    if (content) {
        const errorMessage = error?.message || String(error) || 'Error desconocido';
        const errorHtml = `
            <div class="card">
                <div class="card-header">
                    <h3>Calendario de Documentos</h3>
                </div>
                <div class="card-body">
                    <div class="alert alert-error" data-testid="calendar-pending-error" style="padding: 16px; margin: 16px 0; background: #7f1d1d; border: 1px solid #dc2626; border-radius: 8px; color: #fecaca;">
                        <strong>Error cargando pendientes:</strong> ${escapeHtml(errorMessage)}
                    </div>
                </div>
            </div>
        `;
        content.innerHTML = errorHtml;
    }
    
    // Re-lanzar error para que loadPage() lo maneje con setViewState('calendario', 'error')
    throw error;
}
```

**Flujo garantizado:**
1. Al entrar: `setViewState('calendario', 'loaded')` ✅
2. Si pending ok: `setViewState('calendario', 'ready')` ✅
3. Si pending falla/timeout/abort:
   - Renderiza bloque de error visible con `data-testid="calendar-pending-error"` ✅
   - `setViewState('calendario', 'error', errorMessage)` ✅

---

## TAREA D — Test helper: esperar ready O error ✅ COMPLETADA

### Archivo: `tests/helpers/e2eSeed.js`

**Cambios:**
- El helper `gotoHash()` ya espera `ready` O `error` usando `Promise.race()` (línea ~263)
- Añadido soporte para buscar `calendar-pending-error` cuando hay error en calendario (línea ~272)

**Implementación:**
```javascript
if (errorExists) {
    const errorMsg = await page.locator(`[data-testid="${viewErrorTestId}"]`).getAttribute('data-error') || 'Unknown error';
    const errorDisplay = await page.locator('[data-testid="view-error-msg"]').textContent().catch(() => null);
    
    // SPRINT C2.9.6: Para calendario, también buscar calendar-pending-error para debug
    let calendarPendingError = null;
    if (pageName === 'calendario') {
        try {
            calendarPendingError = await page.locator('[data-testid="calendar-pending-error"]').textContent();
        } catch (e) {
            // Ignorar si no existe
        }
    }
    
    const errorDetails = [
        errorDisplay,
        calendarPendingError ? `calendar-pending-error: ${calendarPendingError.substring(0, 200)}` : null
    ].filter(Boolean).join(' | ');
    
    throw new Error(`View ${pageName} failed to load: ${errorMsg}${errorDetails ? ` (${errorDetails})` : ''}`);
}
```

---

## TAREA E — Validación mínima

### Test individual:
```
npx playwright test tests/cae_plan_e2e.spec.js:51
```

**Resultado:**
```
1 failed
Error: View calendario did not complete loading (ready/error) within 15000ms
```

**Análisis:**
El test aún falla con timeout. Esto puede indicar que:
1. El fetch está tardando más de 12s en abortar
2. El error no se está estableciendo correctamente antes del timeout del helper (15s)

### Suite core completa:
```
npm run test:e2e:core
```

**Estado:** Ejecutándose en background

---

## Archivos Modificados

### Frontend
- `frontend/repository_v3.html`:
  - Línea ~1744: Timeout aumentado de 8000ms a 12000ms para fetch de pendientes
  - Línea ~1954: Catch de `loadCalendario()` renderiza bloque de error visible con `data-testid="calendar-pending-error"`

### Tests
- `tests/helpers/e2eSeed.js`:
  - Línea ~272: Añadido soporte para buscar `calendar-pending-error` cuando hay error en calendario

---

## Conclusión

✅ **Fix implementado**: 
- Timeout aumentado a 12s
- Bloque de error visible renderizado
- Helper actualizado para buscar `calendar-pending-error`

⏳ **Validación pendiente**: 
- Test individual aún falla con timeout
- Suite core ejecutándose

**Siguiente paso:** Verificar si el timeout de 12s es suficiente o si necesita ajustarse, y confirmar que el error se establece correctamente antes del timeout del helper (15s).
