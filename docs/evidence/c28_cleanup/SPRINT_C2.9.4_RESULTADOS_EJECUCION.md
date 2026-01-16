# SPRINT C2.9.4 — CIERRE (solo ejecución + output)

**Fecha:** 2026-01-08

---

## PRIMERA EJECUCIÓN

```
npm run test:e2e:core
```

### Resumen Final:
```
12 failed
3 passed (5.3m)
```

### Tests que pasaron:
1. ✅ `tests\e2e_config_smoke.spec.js:34:3` - Configuración - Smoke Test › should load configuracion view and show settings form (9.5s)
2. ✅ `tests\e2e_upload_preview.spec.js:21:5` - Upload Preview - Previsualizar Documentos › Preview de archivo local antes de guardar (12.2s)
3. ✅ `tests\e2e_upload_preview.spec.js:118:5` - Upload Preview - Previsualizar Documentos › Preview cierra con Esc (10.7s)

### Tests que fallaron:
1. ❌ `tests\cae_plan_e2e.spec.js:51:5` - CAE Plan E2E - Preparar envío CAE (filtrado) › Test 1: Abre modal de CAE plan desde tab Pendientes (16.1s)
2. ❌ `tests\cae_plan_e2e.spec.js:96:5` - CAE Plan E2E - Preparar envío CAE (filtrado) › Test 2: Genera plan con scope mínimo (16.2s)
3. ❌ `tests\cae_plan_e2e.spec.js:214:5` - CAE Plan E2E - Preparar envío CAE (filtrado) › Test 3: Verifica que decision y reasons son visibles (16.2s)
4. ❌ `tests\cae_plan_e2e.spec.js:271:5` - CAE Plan E2E - Preparar envío CAE (filtrado) › Test 4: Cierra modal correctamente (16.2s)
5. ❌ `tests\e2e_calendar_pending_smoke.spec.js:18:5` - Calendar Pending Documents - Smoke Tests › Test 1: Buscar documentos muestra estados reales (no "Desconocido") (16.3s)
6. ❌ `tests\e2e_calendar_pending_smoke.spec.js:53:5` - Calendar Pending Documents - Smoke Tests › Test 2: Calendario muestra tabs y renderiza correctamente (16.4s)
7. ❌ `tests\e2e_calendar_pending_smoke.spec.js:82:5` - Calendar Pending Documents - Smoke Tests › Test 3: Click en tab "Pendientes" renderiza lista (16.4s)
8. ❌ `tests\e2e_calendar_pending_smoke.spec.js:109:5` - Calendar Pending Documents - Smoke Tests › Test 4: Navegación a Upload desde botón de acción (16.2s)
9. ❌ `tests\e2e_edit_document.spec.js:71:3` - Buscar documentos - Editar documento › editar documento y guardar OK (200), modal cierra y persiste (15.7s)
10. ❌ `tests\e2e_edit_document.spec.js:108:3` - Buscar documentos - Editar documento › cambiar "Estado de tramitación" (Borrador <-> Revisado) y guardar (16.3s)
11. ❌ `tests\e2e_edit_document.spec.js:135:3` - Buscar documentos - Editar documento › cambiar "Fecha inicio de vigencia" y guardar; computed_validity coherente (16.2s)
12. ❌ `tests\e2e_search_smoke.spec.js:41:3` - Buscar documentos - Smoke Test › should load buscar view, show results, and filter correctly (16.2s)

### PRIMER ERROR COMPLETO (Stack Trace):

```
1) tests\cae_plan_e2e.spec.js:51:5 › CAE Plan E2E - Preparar envío CAE (filtrado) › Test 1: Abre modal de CAE plan desde tab Pendientes

   Error: View calendario did not complete loading (ready/error) within 15000ms: page.waitForSelector: Timeout 15000ms exceeded.
   Call log:
     - waiting for locator('[data-testid="view-calendario-ready"]')

      at D:\Proyectos_Cursor\CometLocal\tests\cae_plan_e2e.spec.js:48:9

   attachment #1: screenshot (image/png) ─────────────────────────
   test-results\cae_plan_e2e-CAE-Plan-E2E--73622-E-plan-desde-tab-Pendientes\test-failed-1.png
```

**Patrón de error:** La mayoría de los fallos (8 de 12) son por timeout esperando `view-calendario-ready`. Los otros 4 fallos son por timeout esperando `view-buscar-ready`.

---

## SEGUNDA EJECUCIÓN

```
npm run test:e2e:core
```

### Resumen Final:
```
13 failed
2 passed (6.3m)
```

### Análisis:
- La segunda ejecución tuvo **1 fallo más** que la primera (13 vs 12)
- Solo **2 tests pasaron** (vs 3 en la primera)
- El tiempo total fue similar (6.3m vs 5.3m)

---

## CONCLUSIÓN

**Estado:** ❌ **NO CERRADO** - Ambas pasadas tienen fallos

**Problemas identificados:**
1. **Timeout en `view-calendario-ready`**: 8 tests fallan esperando que la vista calendario se marque como ready
2. **Timeout en `view-buscar-ready`**: 4 tests fallan esperando que la vista buscar se marque como ready

**Tests estables (pasan en ambas ejecuciones):**
- `e2e_config_smoke.spec.js` - ✅ Pasa consistentemente
- `e2e_upload_preview.spec.js` - ✅ Pasa consistentemente (2 tests)

**Tests inestables:**
- Todos los tests de calendario (`cae_plan_e2e.spec.js`, `e2e_calendar_pending_smoke.spec.js`) - ❌ Timeout en `view-calendario-ready`
- Todos los tests de buscar (`e2e_search_smoke.spec.js`, `e2e_edit_document.spec.js`) - ❌ Timeout en `view-buscar-ready`

**Siguiente paso:** Investigar por qué `view-calendario-ready` y `view-buscar-ready` no se están estableciendo dentro del timeout de 15s.
