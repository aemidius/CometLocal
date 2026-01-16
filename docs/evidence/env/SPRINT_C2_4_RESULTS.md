# SPRINT C2.4: Re-medición Suite Completa Playwright

**Fecha:** 2025-01-11  
**Comando:** `npx playwright test --reporter=line`

## Totales

- **Passed:** 2
- **Failed:** 44
- **Skipped:** 0
- **Did not run:** 23
- **Total tests:** 69

## TOP 10 Specs por Número de Fallos

1. **e2e_calendar_filters_and_periods.spec.js** - 3 fallos
   - Error más común: `View calendario did not complete loading (ready/error) within 15000ms`

2. **cae_plan_e2e.spec.js** - 3 fallos
   - Error más común: `Server health check failed after 10 attempts: connect ECONNREFUSED` o `ECONNRESET` en seed

3. **e2e_edit_document_fields.spec.js** - 3 fallos
   - Error más común: `View buscar did not complete loading (ready/error) within 15000ms`

4. **e2e_calendar_pending_smoke.spec.js** - 3 fallos
   - Error más común: `View calendario did not complete loading (ready/error) within 15000ms`

5. **e2e_calendar_periodicity.spec.js** - 3 fallos
   - Error más común: `View calendario did not complete loading (ready/error) within 15000ms`

6. **cae_job_control_e2e.spec.js** - 3 fallos
   - Error más común: `ECONNRESET` o `ECONNREFUSED` en seed, o timeout en `#pending-tab-missing`

7. **cae_job_queue_e2e.spec.js** - 1 fallo
   - Error más común: `ECONNRESET` o `ECONNREFUSED` en seed

8. **cae_selection_e2e.spec.js** - 1 fallo
   - Error más común: `ECONNRESET` o `ECONNREFUSED` en seed

9. **cae_coordination_e2e.spec.js** - 1 fallo
   - Error más común: `ECONNRESET` o `ECONNREFUSED` en seed

10. **e2e_calendar_filters.spec.js** - 3 fallos
    - Error más común: `View calendario did not complete loading (ready/error) within 15000ms`

## Errores Más Comunes (Global)

1. **View calendario did not complete loading (ready/error) within 15000ms** - 12 ocurrencias
   - Específico: `page.waitForSelector: Timeout 15000ms exceeded` esperando `[data-testid="view-calendario-ready"]`
   - Afecta principalmente a tests del calendario

2. **View buscar did not complete loading (ready/error) within 15000ms** - 5 ocurrencias
   - Específico: `page.waitForSelector: Timeout 15000ms exceeded` esperando `[data-testid="view-buscar-ready"]`
   - Afecta a tests de búsqueda y edición de documentos

3. **apiRequestContext.post: read ECONNRESET** - 10 ocurrencias
   - Error en `seedReset()`: conexión reseteada durante POST a `/api/test/seed/reset`
   - Afecta a múltiples specs que usan `beforeAll` con seed

4. **apiRequestContext.post: connect ECONNREFUSED** - 9 ocurrencias
   - Error en `seedReset()`: servidor no disponible durante POST a `/api/test/seed/reset`
   - Afecta a specs que se ejecutan cuando el servidor está caído o reiniciando

5. **Server health check failed after 10 attempts: connect ECONNREFUSED** - 1 ocurrencia
   - Error en `cae_plan_e2e.spec.js`: servidor no responde después de 10 intentos
   - Indica problemas de estabilidad del servidor durante ejecución paralela

## Recomendaciones: 3 Fixes con Mayor ROI

### 1. **Fix Timeout de Calendario (Alto ROI)**
**Problema:** 12 fallos por timeout esperando `view-calendario-ready`  
**Causa probable:** `loadCalendario()` no completa en 15s, posiblemente por:
- `ensureRepoDataLoaded()` bloqueando
- Fetch a `/api/repository/docs/pending` lento
- Renderizado de muchos períodos

**Fix sugerido:**
- Aumentar timeout a 20-30s para `view-calendario-ready`
- Optimizar `loadCalendario()` para no bloquear en `ensureRepoDataLoaded()`
- Añadir logging para identificar cuál paso tarda más

**Impacto:** Resolvería ~12 fallos (27% del total)

### 2. **Fix Conexiones Reseteadas en Seed (Alto ROI)**
**Problema:** 19 fallos por `ECONNRESET` o `ECONNREFUSED` en `seedReset()`  
**Causa probable:** 
- Ejecución paralela de tests (12 workers) satura el servidor
- Servidor se reinicia o cae durante ejecución
- Race conditions en `beforeAll` cuando múltiples specs llaman a seed simultáneamente

**Fix sugerido:**
- Implementar retry con backoff exponencial en `seedReset()`
- Añadir semáforo/queue para serializar llamadas a seed
- Aumentar timeout de conexión en helpers
- Verificar salud del servidor antes de seed

**Impacto:** Resolvería ~19 fallos (43% del total)

### 3. **Fix Timeout de Buscar (Medio ROI)**
**Problema:** 5 fallos por timeout esperando `view-buscar-ready`  
**Causa probable:** Similar a calendario, `loadBuscar()` no completa en tiempo

**Fix sugerido:**
- Aumentar timeout a 20s para `view-buscar-ready`
- Optimizar `loadBuscar()` para cargar datos de forma asíncrona
- Añadir logging para identificar cuál paso tarda más

**Impacto:** Resolvería ~5 fallos (11% del total)

## Notas Adicionales

- **23 tests no se ejecutaron:** Probablemente debido a fallos tempranos que impidieron su ejecución
- **Solo 2 tests pasaron:** Indica problemas sistémicos que afectan la mayoría de la suite
- **Problemas de infraestructura:** Muchos errores de conexión sugieren que el servidor no está manejando bien la carga paralela de 12 workers
