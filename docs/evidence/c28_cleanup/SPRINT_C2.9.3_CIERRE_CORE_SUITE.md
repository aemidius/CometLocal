# SPRINT C2.9.3 — Cierre core suite 2x PASS (script + aislamiento + search determinista)

**Fecha:** 2026-01-08

---

## Resumen Ejecutivo

Se implementaron mejoras para asegurar que `npm run test:e2e:core` ejecute SOLO los tests core con `--workers=1` y `--retries=0`, se hizo `e2e_search_smoke` determinista usando datos del seed, y se mejoró `e2e_config_smoke` para ser más robusto ante markers ocultos.

---

## TAREA A — Asegurar script core EXPLÍCITO + workers=1 ✅ COMPLETADA

### Archivo: `package.json`

**Cambios:**
```json
"test:e2e:core": "playwright test --workers=1 --retries=0 tests/e2e_config_smoke.spec.js tests/e2e_search_smoke.spec.js tests/e2e_calendar_pending_smoke.spec.js tests/e2e_upload_preview.spec.js tests/e2e_edit_document.spec.js tests/cae_plan_e2e.spec.js"
```

**Características:**
- ✅ Ejecuta SOLO los 6 tests core explícitos (sin globs ni grep)
- ✅ `--workers=1`: Evita interferencias y seeds concurrentes
- ✅ `--retries=0`: Muestra verdad, no reintentos
- ✅ Orden explícito de archivos

---

## TAREA B — Hacer e2e_search_smoke determinista con datos del seed ✅ COMPLETADA

### Archivos modificados:
- `tests/e2e_search_smoke.spec.js`

### Cambios implementados:

#### 1. Validación del seed en `beforeAll`:
```javascript
// SPRINT C2.9.3: Validar que el seed devolvió datos esperados
expect(seedData).toBeDefined();
expect(seedData.doc_ids).toBeDefined();
expect(Array.isArray(seedData.doc_ids)).toBe(true);
expect(seedData.doc_ids.length).toBeGreaterThanOrEqual(1);
console.log(`[E2E] Seed validation: ${seedData.doc_ids.length} documents created`);
```

#### 2. Filtro determinista usando datos del seed:
```javascript
// 6. SPRINT C2.9.3: Aplicar filtro determinista usando datos del seed
// Todos los documentos del seed tienen "e2e_test" en el filename (garantizado por el backend)
const textInput = page.locator('[data-testid="buscar-text"]');
const searchText = 'e2e_test';
await textInput.fill(searchText);
console.log(`[E2E] Filtered by text "${searchText}" (deterministic from seed)`);

// SPRINT C2.9.3: Esperar marcador determinista después de aplicar filtro
await page.waitForSelector('[data-testid="buscar-results-ready"]', { timeout: 10000, state: 'attached' });
const filteredMarker = page.locator('[data-testid="buscar-results-ready"]');
const filteredCount = await filteredMarker.getAttribute('data-count');
const filteredEmpty = await filteredMarker.getAttribute('data-empty');
console.log(`[E2E] Filtered results marker: count=${filteredCount}, empty=${filteredEmpty}`);

// SPRINT C2.9.3: Validar que el count coincide con los docs del seed
// Todos los docs del seed tienen "e2e_test" en el filename, así que deberían aparecer todos
const expectedFilteredCount = seedData.doc_ids.length;
const actualFilteredCount = parseInt(filteredCount || '0', 10);

// El count puede ser mayor si hay otros docs con "e2e_test", pero debe ser >= al número de docs del seed
expect(filteredEmpty).not.toBe('true');
expect(actualFilteredCount).toBeGreaterThanOrEqual(expectedFilteredCount);
console.log(`[E2E] Filtered count validation: ${actualFilteredCount} >= ${expectedFilteredCount} (seed docs)`);
```

**Características:**
- ✅ Usa datos del seed de forma determinista (no condicional)
- ✅ Filtro de texto "e2e_test" garantizado (todos los docs del seed tienen este prefijo)
- ✅ Validación explícita: `actualFilteredCount >= expectedFilteredCount`
- ✅ Eliminado código condicional y suposiciones sobre datos disponibles

---

## TAREA C — Config smoke robusto ante markers ocultos ✅ COMPLETADA

### Archivo: `tests/e2e_config_smoke.spec.js`

**Cambios:**
```javascript
test('should load configuracion view and show settings form', async ({ page }) => {
  test.setTimeout(20000);
  
  // 1. Navegar a Configuración
  await gotoHash(page, 'configuracion');
  
  // 2. SPRINT C2.9.3: Esperar view-configuracion-ready con state: 'attached'
  await page.waitForSelector('[data-testid="view-configuracion-ready"]', { timeout: 20000, state: 'attached' });
  console.log('[E2E] View configuracion marked as ready (via alias)');
  
  // 3. SPRINT C2.9.3: Esperar configuracion-view visible/attached
  await page.waitForSelector('[data-testid="configuracion-view"]', { timeout: 20000, state: 'attached' });
  const configView = page.locator('[data-testid="configuracion-view"]');
  await expect(configView).toBeVisible({ timeout: 5000 });
  console.log('[E2E] configuracion-view container found');
  // ... resto del test
});
```

**Características:**
- ✅ Timeout del test: 20s
- ✅ Espera `view-configuracion-ready` con `state: 'attached'` (para markers ocultos)
- ✅ Espera `configuracion-view` con `state: 'attached'` y luego verifica visibilidad
- ✅ Solo usa `data-testid` (sin fallbacks)

---

## TAREA D — Validación FINAL (bloqueante)

### Primera ejecución:
```
npm run test:e2e:core
```

**Estado:** Ejecutándose en background. Resultado pendiente de verificación.

### Segunda ejecución:
```
npm run test:e2e:core
```

**Estado:** Pendiente de ejecución tras completar la primera.

---

## Archivos Modificados

### Configuración
- `package.json`: Script `test:e2e:core` actualizado con `--workers=1` y `--retries=0`

### Tests
- `tests/e2e_search_smoke.spec.js`: 
  - Validación del seed en `beforeAll`
  - Filtro determinista usando "e2e_test" (garantizado por el seed)
  - Validación explícita: `actualFilteredCount >= expectedFilteredCount`
  - Eliminado código condicional y suposiciones

- `tests/e2e_config_smoke.spec.js`:
  - Timeout del test: 20s
  - Espera `view-configuracion-ready` con `state: 'attached'`
  - Espera `configuracion-view` con `state: 'attached'` y luego verifica visibilidad

---

## Criterios de Aceptación

✅ **TAREA A — Script core EXPLÍCITO + workers=1**
- Script ejecuta SOLO los 6 tests core explícitos
- `--workers=1` añadido
- `--retries=0` añadido
- Sin globs ni grep genérico

✅ **TAREA B — e2e_search_smoke determinista**
- Validación del seed en `beforeAll`
- Filtro determinista usando "e2e_test" (garantizado por el seed)
- Validación explícita: `actualFilteredCount >= expectedFilteredCount`
- Eliminado código condicional y suposiciones

✅ **TAREA C — Config smoke robusto**
- Timeout del test: 20s
- Espera `view-configuracion-ready` con `state: 'attached'`
- Espera `configuracion-view` con `state: 'attached'` y luego verifica visibilidad
- Solo usa `data-testid`

⏳ **TAREA D — Validación FINAL 2x PASS**
- Primera ejecución: En progreso
- Segunda ejecución: Pendiente

---

## Notas

- El filtro "e2e_test" es determinista porque todos los documentos creados por `seedBasicRepository` tienen `file_name_original: f"e2e_test_{period_key}.pdf"` (según el código del backend).
- El test valida que `actualFilteredCount >= expectedFilteredCount` porque puede haber otros documentos con "e2e_test" en el nombre, pero debe haber al menos los documentos del seed.
- `--workers=1` asegura que no haya interferencias entre tests y que los seeds no se ejecuten concurrentemente.
