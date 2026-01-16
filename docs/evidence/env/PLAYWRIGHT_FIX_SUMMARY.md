# Resumen de Fixes Playwright - Reducción de Fallos

**Fecha:** 2026-01-06  
**Objetivo:** Reducir los 54 fallos Playwright atacando causas raíz, no test a test.

## Resultados

### Antes
- **Total de fallos:** 54
- **Total de tests:** 67
- **Tasa de fallo:** 80.6%

### Después
- **Total de fallos:** 48
- **Total de tests:** 67
- **Tasa de fallo:** 71.6%

### Mejora
- **Reducción:** 6 fallos (11% de mejora)
- **Tests que pasan:** 19 (antes: 13)

## Causas Raíz Identificadas y Corregidas

### 1. Timeout en `waitForLoadState('networkidle')` (18 fallos → reducidos)

**Problema:** La página nunca alcanza estado `networkidle` porque hay polling continuo (job queue, actualizaciones de estado).

**Solución:** 
- Agregadas señales DOM explícitas (`data-testid="page-ready"`, `data-testid="calendar-ready"`, `data-testid="search-ready"`, `data-testid="upload-ready"`)
- Reemplazado `waitForLoadState('networkidle')` por esperas a estas señales DOM en tests críticos

**Archivos modificados:**
- `frontend/repository_v3.html`: Agregadas señales DOM al final de `loadPage`, `loadCalendario`, `loadBuscar`, `loadSubir`
- `tests/e2e_search_docs_actions.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_calendar_pending_smoke.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_upload_scope_filter.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_repository_settings.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_fix_pdf_viewing.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_edit_document_fields.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/cae_plan_e2e.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_upload_clear_all.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_upload_preview.spec.js`: Reemplazado `waitForLoadState('networkidle')`
- `tests/e2e_calendar_periodicity.spec.js`: Corregida ruta y reemplazado `waitForSelector('#page-content')`
- `tests/e2e_calendar_filters_and_periods.spec.js`: Reemplazado `waitForSelector('#page-content')`
- `tests/e2e_calendar_filters.spec.js`: Reemplazado `waitForSelector('#pending-documents-container')`

### 2. Selector no encontrado (15 fallos → parcialmente reducidos)

**Problema:** Elementos existen en el HTML pero no se renderizan a tiempo.

**Solución:**
- Agregadas señales DOM explícitas cuando las secciones están completamente cargadas
- Tests ahora esperan estas señales en lugar de selectores genéricos

**Archivos modificados:**
- `frontend/repository_v3.html`: Agregadas señales DOM en `loadPage`, `loadCalendario`, `loadBuscar`, `loadSubir`

### 3. Hash routing no funciona (12 fallos → parcialmente reducidos)

**Problema:** Tests navegan a `/repository#subir` o `/repository#buscar` pero el hash no se procesa correctamente.

**Solución:**
- Tests ahora navegan directamente con hash en la URL (`/repository#subir` en lugar de `/repository` + click)
- Esperan señales DOM específicas cuando el hash routing está completo

**Archivos modificados:**
- `tests/e2e_search_docs_actions.spec.js`: Navegación directa con hash
- `tests/e2e_fix_pdf_viewing.spec.js`: Navegación directa con hash
- `tests/e2e_edit_document_fields.spec.js`: Navegación directa con hash
- `tests/cae_plan_e2e.spec.js`: Navegación directa con hash
- `tests/e2e_calendar_pending_smoke.spec.js`: Navegación directa con hash

## Archivos Modificados

### Frontend
1. `frontend/repository_v3.html`
   - Agregadas señales DOM (`data-testid="page-ready"`, `data-testid="calendar-ready"`, `data-testid="search-ready"`, `data-testid="upload-ready"`)
   - Señales se agregan al final de `loadPage`, `loadCalendario`, `loadBuscar`, `loadSubir`

### Tests
1. `tests/e2e_search_docs_actions.spec.js`
2. `tests/e2e_calendar_pending_smoke.spec.js`
3. `tests/e2e_upload_scope_filter.spec.js`
4. `tests/e2e_repository_settings.spec.js`
5. `tests/e2e_fix_pdf_viewing.spec.js`
6. `tests/e2e_edit_document_fields.spec.js`
7. `tests/cae_plan_e2e.spec.js`
8. `tests/e2e_upload_clear_all.spec.js`
9. `tests/e2e_upload_preview.spec.js`
10. `tests/e2e_calendar_periodicity.spec.js`
11. `tests/e2e_calendar_filters_and_periods.spec.js`
12. `tests/e2e_calendar_filters.spec.js`

## Próximos Pasos

1. **Continuar reemplazando `waitForLoadState('networkidle')`** en los tests restantes:
   - `tests/e2e_upload_validity_persistence.spec.js`
   - `tests/e2e_upload_validity_start_date.spec.js`
   - `tests/e2e_validity_start.spec.js`
   - `tests/cae_job_control_e2e.spec.js`

2. **Agregar más señales DOM** para otras secciones:
   - `data-testid="inicio-ready"`
   - `data-testid="plataformas-ready"`
   - `data-testid="catalogo-ready"`
   - `data-testid="coordinacion-ready"`

3. **Investigar fallos restantes** (48 fallos):
   - Tests que aún fallan por otras causas (seed, lógica real, etc.)
   - Tests que necesitan ajustes adicionales en las señales DOM

## Lecciones Aprendidas

1. **`waitForLoadState('networkidle')` es frágil** cuando hay polling continuo o requests asíncronos
2. **Señales DOM explícitas son más confiables** que esperar estados de red
3. **Navegación directa con hash** es más determinista que navegar + click
4. **Las señales deben agregarse al final** de las funciones de carga, no al inicio


