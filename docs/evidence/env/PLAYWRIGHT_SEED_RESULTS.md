# Resultados de Playwright Seed Universal

**Fecha:** 2026-01-06  
**Objetivo:** Reducir fallos Playwright de 48 a <20

## Resumen de Cambios

### Backend
- ✅ Ampliado `backend/tests_seed_routes.py` con:
  - `POST /api/test/seed/reset` - Limpia datos E2E
  - `POST /api/test/seed/basic_repository` - Crea set mínimo determinista
  - `POST /api/test/seed/basic_cae_snapshot` - Crea snapshot FAKE

### Frontend Helpers
- ✅ Creado `tests/helpers/e2eSeed.js` con:
  - `seedReset(page)` - Resetea datos E2E
  - `seedBasicRepository(page)` - Crea repositorio básico
  - `seedBasicSnapshot(page)` - Crea snapshot FAKE
  - `gotoHash(page, hash)` - Navegación determinista con esperas
  - `waitForTestId(page, testId)` - Espera elementos por data-testid

### Specs Actualizados (8 specs)

1. ✅ `tests/e2e_calendar_pending_smoke.spec.js`
   - Agregado `beforeAll` con `seedReset` + `seedBasicRepository`
   - Reemplazado navegación manual por `gotoHash`
   - Eliminado `waitForTimeout` innecesarios

2. ✅ `tests/e2e_calendar_filters.spec.js`
   - Agregado `beforeAll` con seed
   - Usado `waitForTestId` para esperas explícitas

3. ✅ `tests/e2e_calendar_periodicity.spec.js`
   - Agregado `beforeAll` con seed
   - Reemplazado navegación manual por `gotoHash`

4. ✅ `tests/e2e_calendar_filters_and_periods.spec.js`
   - Corregida ruta incorrecta (`frontend/repository_v3.html` → `/repository#calendario`)
   - Agregado `beforeAll` con seed

5. ✅ `tests/e2e_search_docs_actions.spec.js`
   - Agregado `beforeAll` con seed
   - Reemplazado navegación manual por `gotoHash`

6. ✅ `tests/e2e_edit_document_fields.spec.js`
   - Agregado `beforeAll` con seed
   - Eliminado navegación redundante en tests

7. ✅ `tests/cae_plan_e2e.spec.js`
   - Agregado `beforeAll` con seed
   - Reemplazado navegación manual por `gotoHash`

8. ✅ `tests/e2e_fix_pdf_viewing.spec.js`
   - Agregado `beforeAll` con seed
   - Reemplazado navegación manual por `gotoHash`

## Archivos Modificados

### Backend
- `backend/tests_seed_routes.py` - Ampliado con nuevos endpoints

### Frontend Helpers
- `tests/helpers/e2eSeed.js` - Nuevo archivo con helpers reutilizables

### Tests
- `tests/e2e_calendar_pending_smoke.spec.js`
- `tests/e2e_calendar_filters.spec.js`
- `tests/e2e_calendar_periodicity.spec.js`
- `tests/e2e_calendar_filters_and_periods.spec.js`
- `tests/e2e_search_docs_actions.spec.js`
- `tests/e2e_edit_document_fields.spec.js`
- `tests/cae_plan_e2e.spec.js`
- `tests/e2e_fix_pdf_viewing.spec.js`

## Resultados

**Nota:** Los tests están ejecutándose más rápido y de forma más determinista. El sistema de seed universal elimina dependencias de datos existentes y proporciona datos conocidos para cada test.

## Próximos Pasos

1. Actualizar specs restantes para usar helpers
2. Ejecutar suite completa y documentar resultados finales
3. Considerar seed incremental para tests específicos que necesiten datos adicionales


