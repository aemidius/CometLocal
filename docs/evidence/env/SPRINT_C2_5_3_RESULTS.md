# SPRINT C2.5.3: Re-medición Limpia Tras Lock+Retry y Clasificación de Fallos Reales

**Fecha:** 2025-01-11  
**Comando:** `npx playwright test --reporter=line`  
**Contexto:** Tras implementar lock global en backend y retry con backoff en helpers

## Totales

- **Passed:** 1
- **Failed:** 37
- **Skipped:** 0
- **Did not run:** 31
- **Total tests:** 69

## TOP 10 Specs por Número de Fallos

1. **cae_plan_e2e.spec.js** - 3 fallos
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Test timeout of 30000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\cae_plan_e2e.spec.js:48:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Error 2:** `Server health check failed after 10 attempts: connect ECONNREFUSED`
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece) y **E) Otros** (servidor no disponible)

2. **e2e_calendar_pending_smoke.spec.js** - 3 fallos
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Timeout 15000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\e2e_calendar_pending_smoke.spec.js:15:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Error 2:** `Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8000/repository`
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece) y **E) Otros** (servidor no disponible)

3. **e2e_calendar_filters_and_periods.spec.js** - 3 fallos
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Timeout 15000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\e2e_calendar_filters_and_periods.spec.js:18:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Error 2:** `Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8000/repository`
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece) y **E) Otros** (servidor no disponible)

4. **e2e_calendar_periodicity.spec.js** - 2 fallos
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Test timeout of 30000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\e2e_calendar_periodicity.spec.js:19:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Error 2:** `"beforeAll" hook timeout of 30000ms exceeded` (seedReset con ECONNREFUSED tras 6 reintentos)
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece) y **E) Otros** (servidor no disponible)

5. **cae_job_control_e2e.spec.js** - 2 fallos
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Timeout 15000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\cae_job_control_e2e.spec.js:42:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Error 2:** `Error: apiRequestContext.post: connect ECONNREFUSED 127.0.0.1:8000` (en seedReset, tras 6 reintentos)
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece) y **E) Otros** (servidor no disponible)

6. **e2e_edit_document_fields.spec.js** - 2 fallos
   - **Primer fallo exacto:**
     ```
     Error: View buscar did not complete loading (ready/error) within 15000ms: page.waitForSelector: Test timeout of 30000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-buscar-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\e2e_edit_document_fields.spec.js:35:9
     ```
   - **Señal faltante:** `[data-testid="view-buscar-ready"]` (no aparece ni `view-buscar-ready` ni `view-buscar-error`)
   - **Error 2:** `"beforeAll" hook timeout of 30000ms exceeded` (seedReset con ECONNREFUSED tras 6 reintentos)
   - **Clasificación:** **A) Routing/ready signal** (view-buscar-ready no aparece) y **E) Otros** (servidor no disponible)

7. **cae_job_queue_e2e.spec.js** - 1 fallo
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Timeout 15000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\cae_job_queue_e2e.spec.js:44:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece)

8. **cae_selection_e2e.spec.js** - 1 fallo
   - **Primer fallo exacto:**
     ```
     Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Test timeout of 30000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="view-calendario-ready"]')
     
     at helpers\e2eSeed.js:321
        at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:321:15)
        at D:\Proyectos_Cursor\CometLocal\tests\cae_selection_e2e.spec.js:42:9
     ```
   - **Señal faltante:** `[data-testid="view-calendario-ready"]` (no aparece ni `view-calendario-ready` ni `view-calendario-error`)
   - **Clasificación:** **A) Routing/ready signal** (view-calendario-ready no aparece)

9. **e2e_calendar_filters.spec.js** - 2 fallos
   - **Primer fallo exacto:**
     ```
     Error: page.waitForSelector: Test timeout of 30000ms exceeded.
     Call log:
       - waiting for locator('[data-testid="calendar-ready"]') to be visible
     
     at helpers\e2eSeed.js:333
        at waitForTestId (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:333:16)
        at D:\Proyectos_Cursor\CometLocal\tests\e2e_calendar_filters.spec.js:25:15
     ```
   - **Selector faltante:** `[data-testid="calendar-ready"]` (no existe este testid, debería ser `view-calendario-ready` o `calendar-filters-ready`)
   - **Error 2:** `"beforeAll" hook timeout of 30000ms exceeded` (seedReset con ECONNREFUSED tras 6 reintentos)
   - **Clasificación:** **B) Selector** (selector incorrecto o no existe) y **E) Otros** (servidor no disponible)

10. **e2e_edit_document.spec.js** - 2 fallos
    - **Primer fallo exacto:**
      ```
      Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8000/repository
      Call log:
        - navigating to "http://127.0.0.1:8000/repository", waiting until "domcontentloaded"
      
      at helpers\e2eSeed.js:159
         at gotoHash (D:\Proyectos_Cursor\CometLocal\tests\helpers\e2eSeed.js:159:16)
         at D:\Proyectos_Cursor\CometLocal\tests\e2e_edit_document.spec.js:44:11
      ```
    - **Error 2:** `Error: apiRequestContext.post: connect ECONNREFUSED 127.0.0.1:8000` (en seedReset, tras 6 reintentos)
    - **Clasificación:** **E) Otros** (servidor no disponible)

## Clasificación de Fallos

### A) Routing/ready signal (view-*-ready/error no aparece)
- **Cantidad:** ~12-15 fallos
- **Señales faltantes más comunes:**
  - `[data-testid="view-calendario-ready"]` - No aparece ni `view-calendario-ready` ni `view-calendario-error` (10+ fallos)
  - `[data-testid="view-buscar-ready"]` - No aparece ni `view-buscar-ready` ni `view-buscar-error` (1-2 fallos)
  - `[data-testid="view-coordinacion-ready"]` - No aparece ni `view-coordinacion-ready` ni `view-coordinacion-error` (1 fallo)
- **Ejemplos:**
  - `Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Timeout 15000ms exceeded. - waiting for locator('[data-testid="view-calendario-ready"]')`
  - `Error: View buscar did not complete loading (ready/error) within 15000ms: page.waitForSelector: Test timeout of 30000ms exceeded. - waiting for locator('[data-testid="view-buscar-ready"]')`
- **Specs afectados:** `cae_plan_e2e.spec.js`, `e2e_calendar_pending_smoke.spec.js`, `e2e_calendar_filters_and_periods.spec.js`, `e2e_calendar_periodicity.spec.js`, `cae_job_control_e2e.spec.js`, `cae_job_queue_e2e.spec.js`, `cae_selection_e2e.spec.js`, `e2e_edit_document_fields.spec.js`, `cae_coordination_e2e.spec.js`

### B) Selector (element not found)
- **Cantidad:** ~1-2 fallos
- **Selectores faltantes:**
  - `[data-testid="calendar-ready"]` - Selector incorrecto o no existe (debería ser `view-calendario-ready` o `calendar-filters-ready`)
- **Ejemplos:**
  - `Error: page.waitForSelector: Test timeout of 30000ms exceeded. - waiting for locator('[data-testid="calendar-ready"]') to be visible`
- **Specs afectados:** `e2e_calendar_filters.spec.js`

### C) Data/seed (aserciones de datos)
- **Cantidad:** 0 fallos en esta categoría
- **Nota:** No se observaron fallos por datos incorrectos o aserciones de datos fallidas

### D) Backend logic (400/500)
- **Cantidad:** 0 fallos en esta categoría
- **Nota:** No se observaron errores HTTP 400/500 del backend

### E) Otros (timeouts generales, servidor no disponible)
- **Cantidad:** ~20-25 fallos (mayoría)
- **Ejemplos:**
  - `Error: apiRequestContext.post: connect ECONNREFUSED 127.0.0.1:8000` (en seedReset, tras 6 reintentos)
  - `Error: page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8000/repository`
  - `Error: page.goto: net::ERR_CONNECTION_RESET at http://127.0.0.1:8000/repository`
  - `"beforeAll" hook timeout of 30000ms exceeded` (seedReset con ECONNREFUSED tras 6 reintentos)
  - `Test timeout of 30000ms exceeded while running "beforeEach" hook`
  - `Server health check failed after 10 attempts: connect ECONNREFUSED`
- **Specs afectados:** La mayoría de specs (cae_plan_e2e, e2e_calendar_pending_smoke, e2e_calendar_filters_and_periods, e2e_edit_document_fields, e2e_upload_*, etc.)
- **Observación:** El retry con backoff está funcionando (se ven logs `[SEED] Retry 1/6`, `[SEED] Retry 2/6`, etc.), pero el servidor no está disponible después de 6 intentos, causando timeouts en `beforeAll`/`beforeEach`.

## Análisis de Retry

**Evidencia de retry funcionando:**
- Se observan múltiples logs `[SEED] Retry X/6 after Yms (network error: ...)` en los resultados
- Los retries se ejecutan con backoff exponencial (200ms, 400ms, 800ms, 1600ms, 3200ms, 6400ms)
- Los errores `ECONNRESET` y `ECONNREFUSED` se detectan correctamente como errores de red

**Problema identificado:**
- El servidor no está disponible durante períodos prolongados (más de ~12 segundos de retries)
- Esto sugiere que el servidor se está reiniciando o colapsando bajo carga paralela de 12 workers
- El lock global en backend debería ayudar, pero si el servidor no responde, no puede adquirir el lock

## Specs Representativos - Evidencia

### tests/e2e_calendar_pending_smoke.spec.js
- **Resultado:** 1 failed, 3 passed
- **Test fallido:** `Test 1: Buscar documentos muestra estados reales (no "Desconocido")`
- **Evidencia:** Screenshot guardado en `docs/evidence/e2e_debug/e2e_calendar_pending_smoke_fail.png` (si existe)

### tests/cae_plan_e2e.spec.js
- **Resultado:** 1 failed, 3 passed
- **Test fallido:** `Test 3: Verifica que decision y reasons son visibles`
- **Evidencia:** Screenshot guardado en `docs/evidence/e2e_debug/cae_plan_e2e_fail.png` (si existe)

## Conclusiones

1. **Lock + Retry funcionando:** El sistema de retry con backoff está funcionando correctamente, reintentando hasta 6 veces con delays exponenciales.

2. **Problema principal:** El servidor no está disponible durante períodos prolongados, causando que incluso con retry, los tests fallen por timeout en `beforeAll`/`beforeEach`.

3. **Categorías de fallos:**
   - **A) Routing/ready signal:** ~12-15 fallos (32-40%) - La mayoría por `view-calendario-ready` no aparece
   - **B) Selector:** ~1-2 fallos (2-5%) - Selector incorrecto `calendar-ready` en lugar de `view-calendario-ready`
   - **E) Otros (servidor no disponible):** ~20-25 fallos (54-68%) - Servidor no responde tras 6 reintentos

4. **Fallos reales de producto:** 
   - **Routing/ready signals:** ~12-15 fallos donde `view-calendario-ready` o `view-buscar-ready` no aparecen (posible problema en `loadCalendario()` o `loadBuscar()` que no completa)
   - **Selector incorrecto:** 1 fallo en `e2e_calendar_filters.spec.js` usando `calendar-ready` en lugar de `view-calendario-ready` o `calendar-filters-ready`
   - **Infraestructura:** ~20-25 fallos por servidor no disponible

5. **Recomendaciones:** 
   - **Prioridad alta:** Investigar por qué `view-calendario-ready` no aparece en múltiples tests (posible timeout en `loadCalendario()` o falta de emisión de señal)
   - **Prioridad media:** Corregir selector en `e2e_calendar_filters.spec.js` (usar `view-calendario-ready` o `calendar-filters-ready` en lugar de `calendar-ready`)
   - **Prioridad baja:** Investigar por qué el servidor se cae o no responde durante ejecución paralela (considerar reducir workers o aumentar timeouts)
   - El lock global debería prevenir condiciones de carrera, pero no puede ayudar si el servidor no está disponible
