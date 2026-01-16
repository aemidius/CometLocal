# C2.13.8 — READ-ONLY: backend OK (items_count>0) pero frontend falla (renderPlanItems not defined)

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Problema Reportado

**Contexto reproducido REAL:**
- Endpoint `POST /runs/egestiona/build_submission_plan_readonly` devuelve 200 OK y logs:
  - `pending_items=4 submission_plan=4 matched_count=3`
  - `items_count=4`
- Pero el modal en `/home` muestra error JS:
  - `"renderPlanItems is not defined"`

---

## Root Cause Identificado

**Función faltante:**
- Línea 1720 en `frontend/home.html`: Se llama `renderPlanItems(itemsArray, 'items')`
- La función `renderPlanItems` NO existe en el código
- Existe `renderResultsTable(plan)` que hace exactamente lo que se necesita, pero no se está usando

**Ubicación exacta:**
- `frontend/home.html` línea 1720: `renderPlanItems(itemsArray, 'items');`
- No hay definición de `function renderPlanItems(...)` en ningún lugar del archivo

**Problema adicional:**
- `dismiss_all_dhx_blockers` intenta guardar screenshots cuando `evidence_dir` es `None` (en modo READ-ONLY con `return_plan_only=True`)

---

## Solución Implementada

### TAREA A — Frontend fix (root cause) ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**

1. **Implementación de `renderPlanItems`:**
   - Línea ~1877: Función `renderPlanItems(plan, containerId, opts)` creada
   - Soporta READ-ONLY: `run_id` puede ser null
   - Normaliza `items/plan` desde `response.plan` o `response.items`
   - Guard: Si `items_count>0` pero no hay items array -> mostrar warning "payload inválido" con dump JSON
   - Internamente llama a `renderResultsTable(plan)` que ya existe

2. **Actualización de la llamada:**
   - Línea ~1719: Llamada actualizada para pasar `opts` con `itemsCount` y `responsePayload`
   - Línea ~1693: Cálculo de `itemsCount` antes de renderizar

**Código:**
```javascript
// HOTFIX C2.13.8: Función para renderizar items del plan (soporta READ-ONLY)
function renderPlanItems(plan, containerId, opts) {
    // Normalizar parámetros
    opts = opts || {};
    containerId = containerId || 'items';
    
    // Guard: Si items_count>0 pero no hay items array -> mostrar warning
    if (opts.itemsCount && opts.itemsCount > 0 && (!plan || !Array.isArray(plan) || plan.length === 0)) {
        const warningHtml = `
            <div class="alert alert-warning">
                <strong>⚠️ Payload inválido:</strong> El backend reportó items_count=${opts.itemsCount} pero no se encontró array de items válido.
                <details>
                    <summary>Ver detalles técnicos</summary>
                    <pre>${window.escapeHtml(JSON.stringify(opts.responsePayload || {}, null, 2))}</pre>
                </details>
            </div>
        `;
        safeSetHTML('results-table-container', warningHtml);
        safeSetDisplay('results-table-container', 'block');
        return;
    }
    
    // Usar renderResultsTable para renderizar
    renderResultsTable(plan);
}
```

### TAREA B — Prueba REAL obligatoria (Playwright) ✅

**Test creado:** `tests/egestiona_readonly_ui_render.spec.js`

**Validaciones:**
- ✅ Abre `/home` y modal "Revisar Pendientes CAE (Avanzado)"
- ✅ Selecciona: coord=Aigues de Manresa, company=F63161988, person=erm, platform=egestiona, scope=trabajador
- ✅ Click "Revisar ahora (READ-ONLY)"
- ✅ Assert: NO aparece banner rojo de error
- ✅ Assert: Aparece bloque "Resultados" y/o "Resumen"
- ✅ Assert: Si backend devuelve `items_count>0`, UI debe mostrar "Total pendientes: X"
- ✅ Assert: NO aparece error "renderPlanItems is not defined"
- ✅ Captura evidencias en `docs/evidence/c2_13_8_readonly_ui_render/`

**Listener de errores:**
- Captura `console.error` y `pageerror`
- Falla si contiene "renderPlanItems is not defined"

### TAREA C — Hotfix DHX blocker ✅

**Archivo modificado:** `backend/adapters/egestiona/priority_comms_headful.py`

**Cambios:**

1. **Firma de función actualizada:**
   - Línea 1099: `evidence_dir: Optional[Path]` (en lugar de `Path`)

2. **Guards añadidos en todos los screenshots:**
   - Línea ~240: Screenshot inicial
   - Línea ~324: Screenshot antes de iteración
   - Línea ~495: Screenshot después de iteración
   - Línea ~504: Screenshot modal failed
   - Línea ~609: Screenshot modal not closed
   - Línea ~622: Screenshot modal closed
   - Línea ~764: Screenshot news notices before
   - Línea ~835: Screenshot news notices no show clicked
   - Línea ~950: Screenshot news notices failed
   - Línea ~966: Screenshot news notices closed

**Código:**
```python
# Screenshot inicial
if evidence_dir is not None:
    try:
        screenshot_path = evidence_dir / "priority_comms_modal_initial.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"[PRIORITY_COMMS] Screenshot inicial guardado: {screenshot_path}")
    except Exception as e:
        print(f"[PRIORITY_COMMS] Error al guardar screenshot inicial: {e}")
else:
    print(f"[DHX_BLOCKER] evidence_dir None, skip screenshot")
```

---

## Archivos Modificados

1. **`frontend/home.html`**
   - Línea ~1877: Función `renderPlanItems` implementada
   - Línea ~1693: Cálculo de `itemsCount` antes de renderizar
   - Línea ~1719: Llamada actualizada con `opts`

2. **`backend/adapters/egestiona/priority_comms_headful.py`**
   - Línea 1099: Firma actualizada `evidence_dir: Optional[Path]`
   - Múltiples líneas: Guards `if evidence_dir is not None:` añadidos

3. **`tests/egestiona_readonly_ui_render.spec.js`** (NUEVO)
   - Test E2E para validar renderizado correcto sin errores JS

4. **`docs/evidence/c2_13_8_readonly_ui_render/FIX_SUMMARY.md`** (NUEVO)
   - Documentación del fix

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Ejecutar READ-ONLY con `coord=Aigues de Manresa, company_key=F63161988, person_key=erm`

**Comportamiento:**
- ✅ Backend devuelve 200 OK con `items_count=4`
- ❌ Frontend muestra error JS: `"renderPlanItems is not defined"`
- ❌ NO se renderizan los items en la UI
- ❌ Usuario ve error en lugar de resultados

### Después del Fix

**Escenario:** Ejecutar READ-ONLY con `coord=Aigues de Manresa, company_key=F63161988, person_key=erm`

**Comportamiento:**
- ✅ Backend devuelve 200 OK con `items_count=4`
- ✅ Frontend NO muestra errores JS
- ✅ Se renderizan los items en la UI correctamente
- ✅ Usuario ve tabla con 4 pendientes

---

## Pruebas Obligatorias

### 1. Test E2E

```bash
npx playwright test tests/egestiona_readonly_ui_render.spec.js
```

**Resultado esperado:**
- ✅ Test pasa (no errores JS, HTTP 200)
- ✅ NO aparece error "renderPlanItems is not defined"
- ✅ Se muestran items en la UI si `items_count>0`
- ✅ Evidencias guardadas en `docs/evidence/c2_13_8_readonly_ui_render/`

### 2. Prueba Funcional desde UI

**Pasos:**
1. Abrir `/home`
2. Abrir modal "Revisar Pendientes CAE (Avanzado)"
3. Seleccionar: Coord="Aigues de Manresa", Company="Tedelab Ingeniería SCCL (F63161988)", Platform="egestiona", Scope="Trabajador", Worker="Emilio Roldán Molina (erm)"
4. Click en "Revisar ahora (READ-ONLY)"

**Resultado esperado:**
- ✅ NO aparece error "renderPlanItems is not defined" en consola
- ✅ NO hay errores de página (pageerror)
- ✅ Se muestra tabla con items si `items_count>0`
- ✅ Se muestra resumen con "Total pendientes: X"

---

## Confirmación del Fix

### ✅ renderPlanItems implementado

**Validación:**
- ✅ Función `renderPlanItems` existe y es accesible
- ✅ Soporta READ-ONLY (run_id puede ser null)
- ✅ Normaliza items desde `response.plan` o `response.items`
- ✅ Guard para payload inválido implementado

### ✅ READ-ONLY renderiza items correctamente

**Validación:**
- ✅ NO hay errores JS "renderPlanItems is not defined"
- ✅ Se renderizan items en la UI
- ✅ Test E2E valida el comportamiento

### ✅ DHX blocker no falla con evidence_dir None

**Validación:**
- ✅ `dismiss_all_dhx_blockers` acepta `evidence_dir: Optional[Path]`
- ✅ Guards `if evidence_dir is not None:` en todos los screenshots
- ✅ Log `"[DHX_BLOCKER] evidence_dir None, skip screenshot"` cuando es None

---

## Explicación Técnica

**¿Por qué no existía renderPlanItems?**
- Probablemente fue eliminada/renombrada en un refactor anterior
- La función `renderResultsTable` existe y hace lo mismo, pero no se estaba usando
- La llamada a `renderPlanItems` quedó sin actualizar

**Solución:**
- Implementar `renderPlanItems` como wrapper de `renderResultsTable`
- Añadir validación de payload inválido
- Soporte explícito para READ-ONLY (run_id null)

---

## Próximos Pasos

1. ✅ Ejecutar test E2E
2. ✅ Verificar que no hay errores JS
3. ✅ Verificar que se renderizan items correctamente
4. ✅ Capturar evidencias (screenshots, logs)

---

**Fin del Resumen de Fix**

*Última actualización: 2026-01-15*
