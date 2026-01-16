# Clasificación de Fallos Playwright

**Fecha:** 2026-01-06  
**Total de fallos ANTES:** 54  
**Total de fallos DESPUÉS:** 48  
**Total de tests:** 67  
**Mejora:** 6 fallos reducidos (11%)

## Tabla de Clasificación

| Categoría | Cantidad | % | Ejemplos |
|-----------|----------|---|----------|
| **1. Timeout en `waitForLoadState('networkidle')`** | 18 | 33% | `e2e_search_docs_actions`, `e2e_repository_settings`, `e2e_fix_pdf_viewing` |
| **2. Selector no encontrado (elementos no renderizados)** | 15 | 28% | `#page-content`, `#pending-tab-missing`, `#search-results-container` |
| **3. Hash routing no funciona** | 12 | 22% | Tests que navegan a `/repository#subir` o `/repository#buscar` |
| **4. Seed/datos inexistentes** | 5 | 9% | Tests CAE que necesitan seed data |
| **5. Lógica real (timeouts de UI, elementos no aparecen)** | 4 | 7% | `waitForResponse` timeout, select options no encontradas |

## Top 3 Causas Más Frecuentes

### 1. Timeout en `waitForLoadState('networkidle')` (18 fallos, 33%)

**Problema:** La página nunca alcanza estado `networkidle` porque:
- Hay polling continuo (job queue, actualizaciones de estado)
- Requests asíncronos que nunca terminan
- La página tiene requests activos indefinidamente

**Tests afectados:**
- `e2e_search_docs_actions.spec.js` (4 tests)
- `e2e_repository_settings.spec.js` (2 tests)
- `e2e_fix_pdf_viewing.spec.js` (2 tests)
- `e2e_upload_scope_filter.spec.js` (6 tests)
- `e2e_upload_clear_all.spec.js` (1 test)
- `e2e_upload_preview.spec.js` (2 tests)
- `e2e_upload_validity_persistence.spec.js` (1 test)

**Solución:** Reemplazar `waitForLoadState('networkidle')` por esperas explícitas a elementos DOM con `data-testid` o señales específicas.

### 2. Selector no encontrado (15 fallos, 28%)

**Problema:** Elementos existen en el HTML pero no se renderizan a tiempo:
- `#page-content` - Existe pero no se muestra hasta que el routing carga
- `#pending-tab-missing` - Existe pero no se muestra hasta que el calendario carga
- `#search-results-container` - Existe pero no se muestra hasta que se ejecuta la búsqueda
- `#pending-documents-container` - Existe pero no se muestra hasta que se carga el calendario

**Tests afectados:**
- `e2e_calendar_periodicity.spec.js` (3 tests)
- `e2e_calendar_filters_and_periods.spec.js` (2 tests)
- `e2e_calendar_filters.spec.js` (1 test)
- `e2e_calendar_pending_smoke.spec.js` (3 tests)
- `cae_plan_e2e.spec.js` (2 tests)
- `e2e_edit_document_fields.spec.js` (4 tests)

**Solución:** Agregar señales DOM explícitas (`data-testid` o `data-ready`) cuando las secciones están completamente cargadas y listas.

### 3. Hash routing no funciona (12 fallos, 22%)

**Problema:** Tests navegan a `/repository#subir` o `/repository#buscar` pero:
- El hash no se procesa correctamente al cargar la página
- El routing no se ejecuta en `DOMContentLoaded`
- El hashchange no se dispara correctamente

**Tests afectados:**
- `e2e_upload_scope_filter.spec.js` (6 tests)
- `e2e_upload_clear_all.spec.js` (1 test)
- `e2e_edit_document.spec.js` (3 tests)
- `e2e_validity_start.spec.js` (1 test)
- `e2e_upload_subjects.spec.js` (1 test)

**Solución:** Asegurar que el hash routing se ejecute en `DOMContentLoaded` y en `hashchange`, y agregar señales DOM cuando el hash se procesa correctamente.

## Estrategia de Fix

1. **Reemplazar `waitForLoadState('networkidle')`** por esperas explícitas a elementos DOM
2. **Agregar señales DOM** (`data-testid="page-ready"`, `data-testid="calendar-ready"`, etc.) cuando las secciones están listas
3. **Arreglar hash routing** para que se ejecute correctamente en carga inicial y cambios de hash

