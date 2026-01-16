# SPRINT C1.3: Re-medición Suite Completa Playwright

**Fecha:** 2025-01-10  
**Comando:** `npx playwright test --reporter=line`

## Totales

- **Passed:** 39
- **Failed:** 26
- **Skipped:** 4
- **Total:** 69 tests
- **Tiempo:** 1.9m

## TOP 10 Specs por Nº de Fallos

| # | Spec | Fallos | Error Más Común |
|---|------|--------|-----------------|
| 1 | `tests/e2e_edit_document_fields.spec.js` | 4 | Modal no se abre: `waitForSelector('#edit-doc-modal-overlay') timeout` o modal no se cierra: `expect(modal).not.toBeVisible() failed` |
| 2 | `tests/e2e_calendar_filters_and_periods.spec.js` | 3 | Elementos no encontrados: `page.click timeout` esperando `[data-testid="calendar-scope-pill-company"]` o `[data-testid="calendar-filter-clear"]` |
| 3 | `tests/e2e_calendar_periodicity.spec.js` | 2 | Elementos no encontrados: `page.click timeout` esperando `[data-testid="calendar-filter-clear"]` |
| 4 | `tests/e2e_edit_document.spec.js` | 3 | Modal no se abre: `waitForSelector('#edit-doc-modal-overlay') timeout` o `waitForResponse timeout` esperando PUT |
| 5 | `tests/e2e_repository_settings.spec.js` | 3 | Routing falla: `View configuracion did not emit 'loaded' signal` o `Failed to fetch` en `/api/repository/settings` |
| 6 | `tests/e2e_fix_pdf_viewing.spec.js` | 2 | Modal no se abre o elementos no encontrados |
| 7 | `tests/cae_job_control_e2e.spec.js` | 2 | Timeouts en operaciones de job (cancel/retry) |
| 8 | `tests/cae_job_queue_e2e.spec.js` | 1 | Timeout esperando progreso de job |
| 9 | `tests/e2e_calendar_pending_smoke.spec.js` | 1 | Routing falla: `View calendario did not complete loading` |
| 10 | `tests/e2e_debug_minimal.spec.js` | 1 | Routing falla: `View calendario did not complete loading` |

## Análisis de Errores Comunes

### 1. Routing / View Loading (8 fallos)
**Error:** `View X did not emit 'loaded' signal within 15000ms`  
**Especs afectados:**
- `e2e_repository_settings.spec.js` (3 tests)
- `e2e_calendar_pending_smoke.spec.js` (1 test)
- `e2e_debug_minimal.spec.js` (1 test)
- `e2e_edit_document_fields.spec.js` (3 tests - buscar view)

**Causa probable:** 
- Views `buscar` y `configuracion` no emiten señal `loaded` correctamente
- Error en `loadBuscar()` o `loadConfiguracion()` que impide `setViewState(view, "loaded")`
- Errores de red (404) que bloquean la carga

### 2. Modal Edit Document (7 fallos)
**Error:** `waitForSelector('#edit-doc-modal-overlay') timeout` o `expect(modal).not.toBeVisible() failed`  
**Especs afectados:**
- `e2e_edit_document_fields.spec.js` (4 tests)
- `e2e_edit_document.spec.js` (3 tests)

**Causa probable:**
- Botón "Editar" no abre el modal correctamente
- Modal no se cierra después de guardar
- Falta `data-testid` o selector incorrecto

### 3. Calendar Filters / Elements (5 fallos)
**Error:** `page.click timeout` esperando elementos con `data-testid`  
**Especs afectados:**
- `e2e_calendar_filters_and_periods.spec.js` (3 tests)
- `e2e_calendar_periodicity.spec.js` (2 tests)

**Causa probable:**
- Elementos no se renderizan después de `view-calendar-ready`
- `data-testid` incorrectos o faltantes
- Filtros no se cargan correctamente

### 4. Timeouts Generales (4 fallos)
**Error:** `Test timeout of 30000ms exceeded` o `waitForResponse timeout`  
**Especs afectados:**
- `e2e_edit_document.spec.js` (1 test)
- `cae_job_control_e2e.spec.js` (2 tests)
- `cae_job_queue_e2e.spec.js` (1 test)

**Causa probable:**
- Operaciones async que no completan
- Requests que no se envían o no reciben respuesta

### 5. Otros (2 fallos)
- `e2e_upload_aeat.spec.js`: `upload-card` no visible
- `e2e_fix_date_and_nmonths.spec.js`: Error en guardado de catálogo

## Recomendaciones: 3 Fixes con Máximo ROI

### Fix 1: Routing de Views `buscar` y `configuracion` (8 fallos → 0)
**Impacto:** Resolvería 8 fallos directamente  
**Especs afectados:** `e2e_repository_settings`, `e2e_edit_document_fields`, `e2e_calendar_pending_smoke`, `e2e_debug_minimal`

**Acciones:**
1. Revisar `loadBuscar()` y `loadConfiguracion()` en `frontend/repository_v3.html`
2. Asegurar que `setViewState(view, "loaded")` se ejecuta SIEMPRE, incluso si hay error
3. Manejar errores 404 en fetch de `/api/repository/settings` sin bloquear `loaded`
4. Añadir `try/catch` robusto y emitir `error` state si falla

**ROI:** Alto - Resuelve múltiples specs con un solo cambio

### Fix 2: Modal Edit Document - Apertura y Cierre (7 fallos → 0)
**Impacto:** Resolvería 7 fallos directamente  
**Especs afectados:** `e2e_edit_document_fields`, `e2e_edit_document`

**Acciones:**
1. Añadir `data-testid="edit-doc-button"` a botones "Editar"
2. Asegurar que el modal emite señal `data-testid="edit-doc-modal-open"` cuando se abre
3. Asegurar que el modal se cierra correctamente después de PUT exitoso
4. Añadir `data-testid="edit-doc-modal-closed"` cuando se cierra
5. Tests deben esperar estas señales en lugar de `waitForSelector` con timeout

**ROI:** Alto - Resuelve todos los tests de edición de documentos

### Fix 3: Calendar Filters - Elementos y Renderizado (5 fallos → 0)
**Impacto:** Resolvería 5 fallos directamente  
**Especs afectados:** `e2e_calendar_filters_and_periods`, `e2e_calendar_periodicity`

**Acciones:**
1. Verificar que `[data-testid="calendar-scope-pill-company"]` y `[data-testid="calendar-filter-clear"]` existen después de `view-calendar-ready`
2. Añadir señal `data-testid="calendar-filters-ready"` cuando los filtros están renderizados
3. Tests deben esperar `calendar-filters-ready` antes de hacer click
4. Asegurar que los filtros se renderizan incluso si no hay datos

**ROI:** Medio-Alto - Resuelve tests de calendario que dependen de filtros

## Resumen de Impacto Esperado

| Fix | Fallos Resueltos | Especs Afectados | ROI |
|-----|------------------|------------------|-----|
| Fix 1: Routing buscar/configuracion | 8 | 4 | ⭐⭐⭐⭐⭐ |
| Fix 2: Modal Edit Document | 7 | 2 | ⭐⭐⭐⭐⭐ |
| Fix 3: Calendar Filters | 5 | 2 | ⭐⭐⭐⭐ |

**Total esperado después de los 3 fixes:** 26 → 6 fallos (reducción del 77%)

## Notas Adicionales

- Los errores de routing (`View X did not emit 'loaded'`) son los más críticos porque afectan múltiples specs
- Los modales requieren señales explícitas (`data-testid`) en lugar de depender de clases CSS o IDs
- Los filtros del calendario necesitan una señal de "ready" específica después de que la vista esté lista
