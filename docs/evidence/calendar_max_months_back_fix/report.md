# Evidencia — Fix bug crítico “Máx. meses atrás” (Calendario → Pendientes de subir)

## Contexto / URL real en este entorno
- La UI del repositorio se sirve en `http://127.0.0.1:8000/repository` (ruta FastAPI).
- Internamente, el HTML servido es `frontend/repository_v3.html` y el tab del calendario se activa con `#calendario`.

## Causa raíz (Root Cause)
**El input “Máx. meses atrás” llamaba a `setCalendarMaxMonthsBack(...)` pero esa función NO existía en `frontend/repository_v3.html`.**

Efecto:
- Al escribir `3` el navegador lanzaba `ReferenceError: setCalendarMaxMonthsBack is not defined`.
- `calendarMaxMonthsBack` quedaba en el default (24).
- En “Pendientes de subir” se seguían mostrando periodos con `monthsDiff > 3` (ej. `2025-09`, `2025-08`).

## Auditoría del pipeline (PASO 1 obligatorio)
### Recepción del endpoint `/api/repository/docs/pending`
- **Función**: `loadCalendario()`
- **Recibe**:
  - `pendingData = await (await fetch(.../api/repository/docs/pending?...)).json()`
- **Raw arrays**:
  - `expiredRaw = pendingData.expired || []`
  - `expiringSoonRaw = pendingData.expiring_soon || []`
  - `missingRaw = pendingData.missing || []`
- **Estructuras globales**:
  - `window.pendingDocumentsDataRaw = { expired, expiring_soon, missing }`
  - `window.pendingDocumentsData = filtered`

### Filtro principal
- **Función**: `applyCalendarFilters(pendingData, filters, maxMonthsBack)`
- **Dónde se llama**:
  - En `loadCalendario()` (filtro inicial)
  - En `applyCalendarFiltersAndUpdate()` (cuando cambian filtros UI)
  - En `showPendingSection()` (al cambiar de tab)

### Render “Pendientes de subir”
- **Función de render**: `renderPendingDocuments(expired, expiringSoon, missing, activeSection)`
- **Array usado para renderizar**:
  - Siempre se le pasa `filtered.missing` (post-filtro), no el raw.
  - Además, `showPendingSection()` re-aplica filtros justo antes de renderizar.

## Instrumentación (logs reales con flag)
Se añadió flag opt-in:
- `window.__DEBUG_CALENDAR__ = true` **o**
- `?debug_calendar=1` (ej: `http://127.0.0.1:8000/repository?debug_calendar=1#calendario`)

Logs implementados:
- `console.log('[CAL] raw pending periods count', rawPeriods.length)`
- `console.log('[CAL] filtered pending periods count', filtered.length, 'max=', maxMonthsBack)`
- 10 muestras: `console.log('[CAL] sample', period, monthsDiff, include)`
- Periodos inválidos: `console.warn('[CAL] invalid period', period)`

## Evidencia BEFORE / AFTER (screenshots)
- BEFORE (bug): `docs/evidence/calendar_max_months_back_fix/01_before.png`
  - Con `Máx. meses atrás = 3` se ven periodos fuera de rango (ej. `2025-09`, `2025-08`).
- AFTER (fix): `docs/evidence/calendar_max_months_back_fix/02_after.png`
  - Con `Máx. meses atrás = 3` solo quedan `2026-01`, `2025-12`, `2025-10` (0..3 meses).

## Playwright (salida real)
- Comando ejecutado:
  - `npx playwright test tests/e2e_calendar_filters.spec.js --reporter=line`
- Salida guardada:
  - `docs/evidence/calendar_max_months_back_fix/TEST_OUTPUT.txt`
- Confirmación (extracto):
  - Aparece `"[CAL] raw pending periods count 23"`
  - Aparece `"[CAL] filtered pending periods count 3 max= 3"`
  - El run termina con `4 passed`.

## Qué cambié (diff conceptual / fix mínimo)
1. **Añadido `setCalendarMaxMonthsBack()`** para que el input actualice `calendarMaxMonthsBack` y re-renderice usando datos filtrados (sin recarga).
2. **Cálculo robusto de `monthsDiff`** para `YYYY-MM`:
   - \(monthsDiff = (Y_{today}-Y)*12 + (M_{today}-(m-1))\)
3. **Exclusión segura**: si parse falla o `monthsDiff` es `NaN` → excluir + `console.warn`.
4. **No regresión**: normalizado raw key `expiring_soon` para que el tab “Expiran pronto” reciba datos correctos.

## Archivos modificados
- `frontend/repository_v3.html`
- `tests/e2e_calendar_filters.spec.js`







