# Playwright Test Results - Medición Actual

**Fecha:** 2026-01-07  
**Ejecución:** `npx playwright test --reporter=line`

## Totales ANTES

- **Failed:** 36
- **Passed:** 7
- **Skipped:** 0
- **Did not run:** 24 (probablemente por fallos en beforeEach/beforeAll)

## TOP 15 Specs por Nº de Tests Fallando

| # | Spec | Fallos | Error más común |
|---|------|--------|-----------------|
| 1 | `e2e_upload_scope_filter.spec.js` | 4 | selector (type-autocomplete options not found) |
| 2 | `e2e_repository_settings.spec.js` | 4 | selector (page-ready timeout) |
| 3 | `e2e_upload_clear_all.spec.js` | 3 | selector (upload-dropzone not found) |
| 4 | `e2e_edit_document.spec.js` | 3 | timeout (networkidle, waitForResponse) |
| 5 | `cae_job_control_e2e.spec.js` | 3 | selector (#pending-tab-missing not found) |
| 6 | `e2e_upload_preview.spec.js` | 2 | selector (page-ready timeout) |
| 7 | `e2e_fix_date_and_nmonths.spec.js` | 2 | timeout (setInputFiles, waitForTimeout) |
| 8 | `e2e_resubmit_pdf.spec.js` | 1 | timeout (waitForResponse) |
| 9 | `e2e_upload_subjects.spec.js` | 1 | seed/datos (depende de datos existentes) |
| 10 | `e2e_upload_type_select.spec.js` | 1 | seed/datos (depende de datos existentes) |
| 11 | `e2e_upload_validity_persistence.spec.js` | 1 | selector (upload-dropzone timeout) |
| 12 | `e2e_upload_validity_start_date.spec.js` | 1 | selector (upload-dropzone timeout) |
| 13 | `cae_job_queue_e2e.spec.js` | 1 | selector (#pending-tab-missing not found) |
| 14 | `cae_selection_e2e.spec.js` | 1 | selector (#pending-tab-missing not found) |
| 15 | `e2e_fix_pdf_viewing.spec.js` | 1 | beforeAll error (ya corregido) |

**Nota:** Los specs que ya usan e2eSeed pero tienen fallos por error de beforeAll (page fixture) están siendo corregidos.

## Tipos de Error Más Frecuentes

1. **Selector timeout** (18 fallos): Elementos no encontrados (#pending-tab-missing, upload-dropzone, page-ready)
2. **Timeout general** (10 fallos): networkidle, waitForResponse, waitForTimeout, setInputFiles
3. **Seed/datos** (3 fallos): Dependencias de datos existentes
4. **beforeAll error** (7 fallos): Uso de page fixture en beforeAll (ya corregido)

## Specs que NO usan e2eSeed.js (17 specs)

1. `e2e_upload_scope_filter.spec.js` - 4 fallos
2. `e2e_repository_settings.spec.js` - 4 fallos
3. `e2e_upload_clear_all.spec.js` - 3 fallos
4. `e2e_edit_document.spec.js` - 3 fallos
5. `cae_job_control_e2e.spec.js` - 3 fallos
6. `e2e_upload_preview.spec.js` - 2 fallos
7. `e2e_fix_date_and_nmonths.spec.js` - 2 fallos
8. `e2e_resubmit_pdf.spec.js` - 1 fallo
9. `e2e_upload_subjects.spec.js` - 1 fallo
10. `e2e_upload_type_select.spec.js` - 1 fallo
11. `e2e_upload_validity_persistence.spec.js` - 1 fallo
12. `e2e_upload_validity_start_date.spec.js` - 1 fallo
13. `cae_job_queue_e2e.spec.js` - 1 fallo
14. `cae_selection_e2e.spec.js` - 1 fallo
15. `cae_coordination_e2e.spec.js` - 0 fallos (probablemente)
16. `e2e_upload_aeat.spec.js` - 0 fallos (probablemente)
17. `e2e_validity_start.spec.js` - 0 fallos (probablemente)

## Próximos Pasos

Migrar los TOP 10 specs con más fallos al patrón e2eSeed.

---

## RE-MEDICIÓN DESPUÉS DE MIGRACIÓN PARCIAL

**Ejecución:** Después de migrar 8 specs principales

### Totales DESPUÉS (parcial)

- **Failed:** 46 (↑ +10 desde antes)
- **Passed:** 21 (↑ +14 desde antes)  
- **Skipped:** 0
- **Did not run:** 0

**Análisis:** 
- El aumento de fallos puede deberse a:
  1. Errores en las migraciones (beforeAll con request, helpers no disponibles)
  2. Specs que ahora se ejecutan pero antes no corrían (antes "did not run")
- El aumento de passed es positivo: de 7 a 21 (+14)
- Necesario revisar errores específicos de las migraciones

### Specs Migrados (8)

1. ✅ `e2e_edit_document.spec.js`
2. ✅ `e2e_repository_settings.spec.js`
3. ✅ `e2e_upload_clear_all.spec.js`
4. ✅ `e2e_upload_preview.spec.js`
5. ✅ `e2e_upload_scope_filter.spec.js`
6. ✅ `cae_job_control_e2e.spec.js`
7. ✅ `cae_selection_e2e.spec.js`
8. ✅ `cae_job_queue_e2e.spec.js`

### Próximos Specs a Migrar

9. `e2e_fix_date_and_nmonths.spec.js` - 2 fallos
10. `e2e_resubmit_pdf.spec.js` - 1 fallo
11. `e2e_upload_subjects.spec.js` - 1 fallo
12. `e2e_upload_type_select.spec.js` - 1 fallo
