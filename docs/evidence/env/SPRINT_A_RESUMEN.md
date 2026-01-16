# Sprint A - Resumen Final

## 1) MEDICIÓN INICIAL

**Totales ANTES:**
- Failed: 36
- Passed: 7
- Skipped: 0
- Did not run: 24

## 2) MIGRACIÓN MASIVA

### Specs Migrados (8)

1. ✅ `e2e_edit_document.spec.js` - Migrado a e2eSeed helpers
2. ✅ `e2e_repository_settings.spec.js` - Migrado a e2eSeed helpers
3. ✅ `e2e_upload_clear_all.spec.js` - Migrado a e2eSeed helpers
4. ✅ `e2e_upload_preview.spec.js` - Migrado a e2eSeed helpers
5. ✅ `e2e_upload_scope_filter.spec.js` - Migrado a e2eSeed helpers
6. ✅ `cae_job_control_e2e.spec.js` - Migrado a e2eSeed helpers
7. ✅ `cae_selection_e2e.spec.js` - Migrado a e2eSeed helpers
8. ✅ `cae_job_queue_e2e.spec.js` - Migrado a e2eSeed helpers

### Cambios Realizados

- **beforeAll:** Cambiado de `async ({ page })` a `async ({ request })` para evitar error de Playwright
- **Helpers:** Uso de `seedReset`, `seedBasicRepository`, `gotoHash`, `waitForTestId`
- **Navegación:** Reemplazo de `page.goto` + `waitForLoadState('networkidle')` por `gotoHash(page, 'hash')`
- **Esperas:** Reemplazo de `waitForSelector` genéricos por `waitForTestId` con data-testid específicos

## 3) RE-MEDICIÓN

**Totales DESPUÉS (ejecución final):**
- Failed: 57 (↑ +21)
- Passed: 10 (↑ +3)
- Skipped: 0
- Did not run: 0

### Comparación

| Métrica | Antes | Después | Cambio |
|---------|-------|---------|--------|
| Failed | 36 | 57 | +21 |
| Passed | 7 | 10 | +3 |
| Did not run | 24 | 0 | -24 |

**Análisis:**
- ✅ **Mejora:** 24 specs que antes no corrían ahora se ejecutan
- ✅ **Mejora:** 3 specs adicionales pasan (de 7 a 10)
- ⚠️ **Regresión:** 21 specs adicionales fallan (de 36 a 57)
- 📊 **Neto:** -18 specs pasando (10 passed vs 7 passed, pero más specs ejecutándose)

**Nota:** El aumento de fallos puede deberse a:
1. Errores en las migraciones (helpers no disponibles, beforeAll con request)
2. Specs que ahora se ejecutan pero tienen dependencias faltantes
3. Necesidad de revisar errores específicos y corregir helpers

## 4) TOP 10 Specs Restantes con Más Fallos

(Por migrar o corregir)

1. `e2e_upload_scope_filter.spec.js` - 4 fallos (migrado pero aún falla)
2. `e2e_repository_settings.spec.js` - 4 fallos (migrado pero aún falla)
3. `e2e_upload_clear_all.spec.js` - 3 fallos (migrado pero aún falla)
4. `e2e_edit_document.spec.js` - 3 fallos (migrado pero aún falla)
5. `cae_job_control_e2e.spec.js` - 3 fallos (migrado pero aún falla)
6. `e2e_upload_preview.spec.js` - 2 fallos (migrado pero aún falla)
7. `e2e_fix_date_and_nmonths.spec.js` - 2 fallos (no migrado)
8. `e2e_resubmit_pdf.spec.js` - 1 fallo (no migrado)
9. `e2e_upload_subjects.spec.js` - 1 fallo (no migrado)
10. `e2e_upload_type_select.spec.js` - 1 fallo (no migrado)

## 5) Los 3 Tipos de Fallo Más Frecuentes

1. **Selector timeout** (~18 fallos): Elementos no encontrados (#pending-tab-missing, upload-dropzone, page-ready)
2. **Timeout general** (~10 fallos): networkidle, waitForResponse, waitForTimeout, setInputFiles
3. **Seed/datos** (~3 fallos): Dependencias de datos existentes o helpers no disponibles

## Archivos Modificados

- `tests/helpers/e2eSeed.js` - Actualizado para soportar request en beforeAll
- `tests/e2e_edit_document.spec.js` - Migrado
- `tests/e2e_repository_settings.spec.js` - Migrado
- `tests/e2e_upload_clear_all.spec.js` - Migrado
- `tests/e2e_upload_preview.spec.js` - Migrado
- `tests/e2e_upload_scope_filter.spec.js` - Migrado
- `tests/cae_job_control_e2e.spec.js` - Migrado
- `tests/cae_selection_e2e.spec.js` - Migrado
- `tests/cae_job_queue_e2e.spec.js` - Migrado
- `docs/evidence/env/PLAYWRIGHT_CURRENT_RESULTS.md` - Documentación de resultados

