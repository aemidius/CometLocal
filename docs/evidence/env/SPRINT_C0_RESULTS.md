# SPRINT C0: Re-medición Suite Completa Tras Fixes

**Fecha:** 2025-01-10  
**Ejecución:** `npx playwright test --reporter=line`

## Totales

- **Passed:** 37
- **Failed:** 29
- **Skipped:** 2
- **Total:** 68 tests

## TOP 15 Specs por Nº de Fallos

| Spec | Fallos | Error Más Común |
|------|--------|-----------------|
| `e2e_upload_scope_filter.spec.js` | 4 | `selectOption: did not find some options` - Select no tiene opciones disponibles |
| `e2e_calendar_filters_and_periods.spec.js` | 3 | `element not found` / `Timeout waiting for locator` - Selectores de filtros no encontrados |
| `e2e_edit_document.spec.js` | 3 | `waitForResponse timeout` / `View buscar did not complete loading` - Vista buscar no carga correctamente |
| `e2e_edit_document_fields.spec.js` | 2 | `element not found` - Modal de edición no muestra elementos esperados |
| `e2e_repository_settings.spec.js` | 3 | `View configuracion did not emit 'loaded' signal` - Routing de configuración no funciona |
| `cae_job_control_e2e.spec.js` | 2 | `Plan is not READY, decision: BLOCKED` - Plan generado no es READY |
| `e2e_calendar_periodicity.spec.js` | 2 | `element not found` / `Test timeout` - Selectores de filtros no encontrados |
| `e2e_upload_subjects.spec.js` | 1 | `selectOption: did not find some options` - Select no tiene opciones disponibles |
| `e2e_upload_type_select.spec.js` | 1 | `Target page closed` / `selectOption timeout` - Select no tiene opciones disponibles |
| `cae_coordination_e2e.spec.js` | 1 | `View coordinacion did not emit 'loaded' signal` - Routing de coordinación no funciona |
| `cae_job_queue_e2e.spec.js` | 1 | `Select 0 does not have a value selected` - Plan no READY por falta de selección |
| `cae_plan_e2e.spec.js` | 1 | `element not found` - Elementos del modal CAE no encontrados |
| `e2e_fix_pdf_viewing.spec.js` | 1 | `waitForSelector timeout: table tbody tr` - Vista buscar no carga resultados |
| `e2e_fix_date_and_nmonths.spec.js` | 1 | `element not found` - Selectores no encontrados |
| `e2e_debug_minimal.spec.js` | 1 | `element not found` - Selectores de calendario no encontrados |

## Clasificación de Fallos

### A) Missing Seed en Spec (no usa helpers)
**Cantidad:** ~8 fallos

**Específicos:**
- `e2e_upload_scope_filter.spec.js` (4 fallos) - No usa seed, depende de datos reales
- `e2e_upload_subjects.spec.js` - No usa seed, busca tipos específicos que no existen
- `e2e_upload_type_select.spec.js` - No usa seed, busca "Recibo Autónomos" que no existe
- `e2e_fix_pdf_viewing.spec.js` - No usa seed, espera documentos que no existen
- `e2e_edit_document.spec.js` (parcial) - Algunos tests no usan seed correctamente

**Síntoma:** Tests buscan elementos/tipos/documentos que no existen porque no hay seed.

### B) Selector Frágil (no data-testid)
**Cantidad:** ~10 fallos

**Específicos:**
- `e2e_calendar_filters_and_periods.spec.js` - Usa `[data-testid="calendar-scope-pill-company"]` pero elemento no existe
- `e2e_calendar_periodicity.spec.js` - Usa `[data-testid="calendar-filter-clear"]` pero elemento no existe
- `e2e_edit_document_fields.spec.js` - Usa selectores que no existen en el modal
- `e2e_fix_pdf_viewing.spec.js` - Usa `table tbody tr` sin data-testid
- `e2e_debug_minimal.spec.js` - Selectores de calendario no encontrados

**Síntoma:** Elementos no se encuentran porque no tienen data-testid o el selector es incorrecto.

### C) Bug Real Backend/Frontend
**Cantidad:** ~8 fallos

**Específicos:**
- `e2e_repository_settings.spec.js` - Routing de `#configuracion` no emite señal `loaded`
- `cae_coordination_e2e.spec.js` - Routing de `#coordinacion` no emite señal `loaded`
- `e2e_edit_document.spec.js` - Vista `buscar` no completa loading (ready/error)
- `cae_job_control_e2e.spec.js` - Plan generado es `BLOCKED` en lugar de `READY` (lógica backend)
- `cae_job_queue_e2e.spec.js` - Plan no READY por falta de selección de documentos
- `cae_plan_e2e.spec.js` - Modal CAE no muestra elementos esperados
- `e2e_repository_settings.spec.js` - Error 404 en recursos, FileNotFoundError en backend
- `e2e_upload_scope_filter.spec.js` - Select no tiene opciones porque el tipo no existe o no se carga

**Síntoma:** Problemas reales en el código que impiden que funcione correctamente.

### D) Waits Restantes (waitForTimeout) que son Síntoma
**Cantidad:** ~3 fallos

**Específicos:**
- Varios tests usan `waitForTimeout` después de acciones, indicando que esperan algo que no está sucediendo
- `e2e_calendar_filters_and_periods.spec.js` - Usa `waitForTimeout(500)` después de clicks
- `e2e_upload_scope_filter.spec.js` - Usa `waitForTimeout(1000)` esperando procesamiento

**Síntoma:** Tests usan timeouts fijos porque no hay señales DOM explícitas para esperar.

## Análisis de Patrones

### Patrón 1: Select sin Opciones (Más Frecuente)
**Frecuencia:** 6 fallos directos + varios indirectos

**Causa Raíz:** 
- Tests intentan seleccionar tipos/documentos que no existen porque no hay seed
- El select se renderiza pero las opciones no se cargan correctamente
- El tipo buscado no existe en el seed básico

**Ejemplos:**
- `e2e_upload_scope_filter.spec.js` - Busca `TEST_RC_CERTIFICATE`, `TEST_DATE_REQUIRED`
- `e2e_upload_subjects.spec.js` - Busca "Recibo Autónomos"
- `e2e_upload_type_select.spec.js` - Busca "Recibo Autónomos"

### Patrón 2: Routing No Emite Señales (Segundo Más Frecuente)
**Frecuencia:** 3 fallos directos

**Causa Raíz:**
- `#configuracion` y `#coordinacion` no emiten señal `loaded` correctamente
- `loadPage()` puede estar fallando silenciosamente
- `setViewState()` no se llama para estas vistas

**Ejemplos:**
- `e2e_repository_settings.spec.js` - `View configuracion did not emit 'loaded' signal`
- `cae_coordination_e2e.spec.js` - `View coordinacion did not emit 'loaded' signal`

### Patrón 3: Vista Buscar No Completa Loading
**Frecuencia:** 2-3 fallos

**Causa Raíz:**
- `loadBuscar()` puede estar fallando o no completando correctamente
- No emite señal `ready` o `error` dentro del timeout

**Ejemplos:**
- `e2e_edit_document.spec.js` - `View buscar did not complete loading (ready/error)`
- `e2e_fix_pdf_viewing.spec.js` - `waitForSelector timeout: table tbody tr`

## Recomendaciones: Top 3 Fixes con Mayor ROI

### Fix 1: Migrar Tests de Upload a Seed Determinista
**ROI:** ⭐⭐⭐⭐⭐ (Alto - Resuelve 6+ fallos)

**Acción:**
- Migrar `e2e_upload_scope_filter.spec.js`, `e2e_upload_subjects.spec.js`, `e2e_upload_type_select.spec.js` a usar `seedBasicRepository`
- Crear seed específico para upload que incluya tipos con nombres conocidos ("Recibo Autónomos", "TEST_RC_CERTIFICATE", etc.)
- Asegurar que el seed crea tipos con los `type_id` y nombres que los tests esperan

**Impacto:** Resuelve ~6 fallos directamente y estabiliza toda la suite de upload.

### Fix 2: Arreglar Routing de Configuración y Coordinación
**ROI:** ⭐⭐⭐⭐ (Alto - Resuelve 3 fallos + previene futuros)

**Acción:**
- Revisar `loadPage()` para `case 'configuracion'` y `case 'coordinacion'`
- Asegurar que `setViewState('configuracion', 'loaded')` se llama ANTES de `loadConfiguracion()`
- Asegurar que `setViewState('coordinacion', 'loaded')` se llama ANTES de `loadCoordinacion()`
- Verificar que estas funciones no tienen `try/catch` interno que silencie errores

**Impacto:** Resuelve 3 fallos directos y estabiliza routing para estas vistas.

### Fix 3: Arreglar Vista Buscar y Añadir Señales DOM Explícitas
**ROI:** ⭐⭐⭐⭐ (Alto - Resuelve 2-3 fallos + mejora estabilidad)

**Acción:**
- Revisar `loadBuscar()` para asegurar que siempre emite `ready` o `error`
- Añadir `data-testid="search-results-container"` o similar cuando los resultados están listos
- Asegurar que `table tbody tr` tenga un contenedor con `data-testid` para esperar resultados
- Revisar si hay errores silenciosos en `loadBuscar()` que impiden que complete

**Impacto:** Resuelve 2-3 fallos directos y mejora estabilidad de tests de búsqueda/edición.

## Métricas de Progreso

**Antes (Sprint B3):** ~62 fallos  
**Ahora (Sprint C0):** 29 fallos  
**Mejora:** 53% reducción de fallos

**Próximo Objetivo:** Reducir a <15 fallos con los 3 fixes recomendados.
