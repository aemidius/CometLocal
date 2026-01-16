# Playwright Seed Universal - Documentación

**Fecha:** 2026-01-06  
**Objetivo:** Reducir fallos Playwright de 48 a <20 mediante seed universal y helpers estandarizados.

## Resumen

Se implementó un sistema de seed universal y helpers reutilizables para estandarizar la creación de datos de prueba en tests E2E, eliminando dependencias de datos existentes y mejorando la determinística de los tests.

## Backend: Endpoints de Seed

### `POST /api/test/seed/reset`

Limpia datos E2E creados:
- Tipos y documentos con prefijo `E2E_`
- Snapshots E2E en `docs/evidence/cae_snapshots/`
- Jobs E2E en `data/cae_jobs.json`

**Respuesta:**
```json
{
  "deleted_types": ["E2E_TYPE_xxx"],
  "deleted_docs": ["E2E_DOC_xxx"],
  "deleted_snapshots": ["CAESNAP-xxx.json"],
  "deleted_jobs": ["CAEJOB-xxx"],
  "message": "Reset: X types, Y docs, Z snapshots, W jobs"
}
```

### `POST /api/test/seed/basic_repository`

Crea un set mínimo determinista:
- `company_key` y `person_key` con prefijo `E2E_`
- 2-3 tipos de documento (worker y company)
- 3-5 documentos con PDFs dummy
- Asegura que el calendario tiene al menos 2 pendientes "missing"

**Respuesta:**
```json
{
  "company_key": "E2E_COMPANY_xxx",
  "person_key": "E2E_PERSON_xxx",
  "type_ids": ["E2E_TYPE_xxx_0", "E2E_TYPE_xxx_1"],
  "doc_ids": ["E2E_DOC_xxx_0_0", "E2E_DOC_xxx_0_1", ...],
  "period_keys": ["2025-11", "2025-12"],
  "message": "Created basic repository: 2 types, 3 docs, 2 missing periods"
}
```

### `POST /api/test/seed/basic_cae_snapshot`

Crea snapshot FAKE con 2 pending_items para tests de coordinación CAE.

**Respuesta:**
```json
{
  "snapshot_id": "CAESNAP-20260106-120000-xxx",
  "created_at": "2026-01-06T12:00:00",
  "pending_items_count": 2,
  "message": "Created FAKE snapshot CAESNAP-xxx with 2 items"
}
```

**Nota:** Todos los endpoints requieren `E2E_SEED_ENABLED=1` en las variables de entorno.

## Frontend: Helpers Reutilizables

### `tests/helpers/e2eSeed.js`

Proporciona funciones reutilizables para tests E2E:

#### `seedReset(page)`
Resetea datos E2E creados.

#### `seedBasicRepository(page)`
Crea un set mínimo determinista de repositorio. Retorna `seedData` con IDs.

#### `seedBasicSnapshot(page)`
Crea snapshot FAKE con 2 pending_items. Retorna `snapshotData` con `snapshot_id`.

#### `gotoHash(page, hash, timeout = 10000)`
Navega a una ruta con hash y espera a que esté lista:
- Navega a `${BACKEND_URL}/repository#${hash}`
- Espera `[data-testid="page-ready"][data-page="${hash}"]`
- Espera señal específica según la página:
  - `calendario` → `[data-testid="calendar-ready"]`
  - `buscar` → `[data-testid="search-ready"]`
  - `subir` → `[data-testid="upload-ready"]`

#### `waitForTestId(page, testId, timeout = 10000)`
Espera a que un elemento con `data-testid` esté visible.

#### `waitForTestIdAttached(page, testId, timeout = 10000)`
Espera a que un elemento con `data-testid` esté attached (no necesariamente visible).

## Uso en Tests

### Patrón Estándar

```javascript
const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Mi Test Suite', () => {
    let seedData;
    
    test.beforeAll(async ({ page }) => {
        // Reset y seed básico
        await seedReset(page);
        seedData = await seedBasicRepository(page);
    });
    
    test.beforeEach(async ({ page }) => {
        // Navegar usando helper
        await gotoHash(page, 'calendario');
    });
    
    test('Mi test', async ({ page }) => {
        // Usar seedData para localizar elementos
        const typeId = seedData.type_ids[0];
        const docId = seedData.doc_ids[0];
        // ...
    });
});
```

## Specs Actualizados

Los siguientes specs fueron actualizados para usar los nuevos helpers:

1. `tests/e2e_calendar_pending_smoke.spec.js`
2. `tests/e2e_calendar_filters.spec.js`
3. `tests/e2e_calendar_periodicity.spec.js`
4. `tests/e2e_calendar_filters_and_periods.spec.js`
5. `tests/e2e_search_docs_actions.spec.js`
6. `tests/e2e_edit_document_fields.spec.js`
7. `tests/cae_plan_e2e.spec.js`
8. `tests/e2e_fix_pdf_viewing.spec.js`

## Beneficios

1. **Determinismo:** Cada test tiene datos conocidos y predecibles
2. **Independencia:** Tests no dependen de datos existentes en el repositorio
3. **Mantenibilidad:** Helpers centralizados facilitan cambios futuros
4. **Velocidad:** Seed básico es rápido y suficiente para la mayoría de tests
5. **Claridad:** Código de tests más limpio y fácil de entender

## Próximos Pasos

1. Actualizar specs restantes para usar helpers
2. Agregar más helpers según necesidades (ej: `seedWithCustomTypes`)
3. Documentar patrones específicos para diferentes tipos de tests
4. Considerar seed incremental para tests que necesitan datos adicionales


