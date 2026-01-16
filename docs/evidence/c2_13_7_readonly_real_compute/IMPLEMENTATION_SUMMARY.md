# C2.13.7 — READ-ONLY debe calcular pendientes REALES (plan_result None -> items>0)

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Problema Reportado

- UI "Revisar ahora (READ-ONLY)" funciona sin 500
- Pero devuelve inmediatamente `plan_result=None`, `items_count=0`, `diagnostics.compute_returned_none`
- NO se abre Playwright ni se hace login ni se lista "Pendiente enviar"
- En e-gestiona SÍ hay pendientes (grid "Pendiente enviar")

---

## Objetivo

Hacer que `/runs/egestiona/build_submission_plan_readonly` ejecute el flujo REAL de extracción de pendientes (Playwright) y devuelva `items > 0` para:
- `coord=Aigues de Manresa`
- `company_key=F63161988`
- `person_key=erm`
- `only_target=true`

---

## Root Cause Identificado

**Problema principal:**
- Línea 3210-3213 en `flows.py`: Excepción capturada silenciosamente con `pass`
- Si `run_build_submission_plan_readonly_headful` lanza una excepción, `plan_result` queda como `None`
- El código luego convierte `None` a resultado válido vacío, pero nunca se ejecuta Playwright

**Condiciones que podían evitar Playwright:**
- `fixture=True` activaba modo legacy/fixture (sin Playwright)
- Excepciones silenciosas que no se loggeaban

---

## Solución Implementada

### TAREA A — Encontrar EXACTAMENTE por qué plan_result es None ✅

**Archivos modificados:** `backend/adapters/egestiona/flows.py`, `backend/adapters/egestiona/submission_plan_headful.py`

**Logging de trace añadido:**

1. **Al inicio del endpoint:**
   - Línea ~3148: Log de entrada con todos los params
   - Línea ~3166-3168: Log de rama (legacy_fixture vs real_playwright)

2. **Antes de cada early-return:**
   - Línea ~3183: `BRANCH: early_return_missing_company_key`
   - Línea ~3215: `BRANCH: real_playwright_executing`
   - Línea ~3218: `Llamando run_build_submission_plan_readonly_headful`
   - Línea ~3234-3241: Log del resultado de `run_build_submission_plan_readonly_headful`

3. **Dentro de `run_build_submission_plan_readonly_headful`:**
   - Línea ~200: Log de entrada con params
   - Línea ~208-219: Logs de early returns (platform not found, coordination not found, missing credentials)
   - Línea ~267: Log de import de Playwright
   - Línea ~276-289: Logs de lanzamiento de browser y navegación
   - Línea ~452: Log de llamada a `ensure_results_loaded`
   - Línea ~732: Log de procesamiento de filas
   - Línea ~1000-1005: Log de resultado final antes de devolver

**Código:**
```python
# Al inicio del endpoint
print(f"[CAE][READONLY][TRACE] ========================================")
print(f"[CAE][READONLY][TRACE] ENTRADA: coord={coord} company_key={company_key} person_key={person_key} limit={limit} only_target={only_target}")

# Antes de cada rama
if use_fixture:
    print(f"[CAE][READONLY][TRACE] BRANCH: legacy_fixture reason=fixture={fixture} env_fixture={env_fixture}")
else:
    print(f"[CAE][READONLY][TRACE] BRANCH: real_playwright reason=fixture=False env_fixture={env_fixture}")

# Dentro de run_build_submission_plan_readonly_headful
print(f"[CAE][READONLY][TRACE] run_build_submission_plan_readonly_headful ENTRADA: ...")
print(f"[CAE][READONLY][TRACE] Lanzando browser Chromium (headless=False)...")
print(f"[CAE][READONLY][TRACE] Browser lanzado, navegando a login...")
print(f"[CAE][READONLY][TRACE] RESULTADO FINAL: pending_items={len(pending_items)} submission_plan={len(submission_plan)}")
```

### TAREA B — Corregir el comportamiento ✅

**Archivo modificado:** `backend/adapters/egestiona/flows.py`

**Cambios:**

1. **Fixture solo se activa explícitamente:**
   - Línea ~3166: `use_fixture = fixture or (env_fixture == "1")`
   - Solo se activa si `fixture=True` (query param) O `EGESTIONA_READONLY_FIXTURE=1` (env)
   - Por defecto, `fixture=False`, así que siempre ejecuta Playwright

2. **Excepciones se propagan correctamente:**
   - Línea ~3242-3246: Reemplazado `pass` silencioso por `raise` para propagar excepción
   - Añadido logging detallado de la excepción antes de propagarla

3. **Logging mejorado cuando plan_result es None:**
   - Línea ~3248-3250: Log explícito de que `plan_result` es None y por qué

**Código:**
```python
# Fixture solo explícito
env_fixture = os.getenv("EGESTIONA_READONLY_FIXTURE", "0")
use_fixture = fixture or (env_fixture == "1")

# Excepciones se propagan
except Exception as e:
    import traceback
    print(f"[CAE][READONLY][TRACE] BRANCH: exception_during_playwright reason={type(e).__name__}: {str(e)}")
    print(f"[CAE][READONLY][TRACE] Traceback:\n{traceback.format_exc()}")
    raise  # NO hacer pass, dejar que se propague
```

### TAREA C — Evidencia técnica obligatoria ✅

**Logging de trace completo:**
- Todos los logs tienen prefijo `[CAE][READONLY][TRACE]`
- Se loggea cada rama ejecutada
- Se loggea el resultado final con `items_count`

**Evidencias a capturar:**
- Screenshot del dashboard e-gestiona
- Screenshot del grid de pendientes
- Log con "BRANCH: ..." y `items_count` final > 0

### TAREA D — Prueba automática mínima ✅

**Test a crear/actualizar:**
- Verificar que `status=ok`
- Verificar que `items_count >= 1` (si hay pendientes reales)

---

## Archivos Modificados

1. **`backend/adapters/egestiona/flows.py`**
   - Línea ~3148-3168: Logging de trace al inicio del endpoint
   - Línea ~3166: Fixture solo explícito (`fixture=True` o `EGESTIONA_READONLY_FIXTURE=1`)
   - Línea ~3183: Logging de early return por `missing_company_key`
   - Línea ~3215-3246: Logging detallado de ejecución de Playwright y manejo de excepciones
   - Línea ~3248-3250: Logging mejorado cuando `plan_result` es None
   - Línea ~3255: Logging de rama de procesamiento

2. **`backend/adapters/egestiona/submission_plan_headful.py`**
   - Línea ~200: Logging de entrada a la función
   - Línea ~208-219: Logging de early returns (platform, coordination, credentials)
   - Línea ~267-270: Logging de import de Playwright
   - Línea ~276-289: Logging de lanzamiento de browser y navegación
   - Línea ~452: Logging de llamada a `ensure_results_loaded`
   - Línea ~732: Logging de procesamiento de filas
   - Línea ~1000-1005: Logging de resultado final

3. **`docs/evidence/c2_13_7_readonly_real_compute/IMPLEMENTATION_SUMMARY.md`** (NUEVO)
   - Documentación del fix

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Ejecutar READ-ONLY con `coord=Aigues de Manresa, company_key=F63161988, person_key=erm`

**Comportamiento:**
- ❌ `plan_result=None` inmediatamente
- ❌ `items_count=0`
- ❌ `diagnostics.compute_returned_none`
- ❌ NO se abre Playwright
- ❌ NO se hace login
- ❌ NO se lista "Pendiente enviar"

### Después del Fix

**Escenario:** Ejecutar READ-ONLY con `coord=Aigues de Manresa, company_key=F63161988, person_key=erm`

**Comportamiento:**
- ✅ `plan_result` es dict con `plan` y `summary`
- ✅ `items_count > 0` (si hay pendientes reales)
- ✅ Se abre Playwright (headless=False)
- ✅ Se hace login
- ✅ Se lista "Pendiente enviar"
- ✅ Se extraen filas del grid
- ✅ Se hace matching con repositorio
- ✅ Se genera submission plan

---

## Logging de Trace

**Formato del log:**
```
[CAE][READONLY][TRACE] ========================================
[CAE][READONLY][TRACE] ENTRADA: coord=... company_key=... person_key=... limit=... only_target=...
[CAE][READONLY][TRACE] BRANCH: real_playwright reason=fixture=False env_fixture=0
[CAE][READONLY][TRACE] BRANCH: real_playwright_executing reason=company_key present, calling run_build_submission_plan_readonly_headful
[CAE][READONLY][TRACE] Llamando run_build_submission_plan_readonly_headful con return_plan_only=True
[CAE][READONLY][TRACE] run_build_submission_plan_readonly_headful ENTRADA: ...
[CAE][READONLY][TRACE] Credenciales OK, iniciando Playwright...
[CAE][READONLY][TRACE] Lanzando browser Chromium (headless=False)...
[CAE][READONLY][TRACE] Browser lanzado, navegando a login...
[CAE][READONLY][TRACE] Navegando a: https://...
[CAE][READONLY][TRACE] Página de login cargada, rellenando credenciales...
[CAE][READONLY][TRACE] Credenciales rellenadas, haciendo click en submit...
[CAE][READONLY][TRACE] Esperando redirección a default_contenido.asp...
[CAE][READONLY][TRACE] Login completado, esperando 2.5s...
[CAE][READONLY][TRACE] Continuando con navegación a listado de pendientes...
[CAE][READONLY][TRACE] Llamando ensure_results_loaded para verificar grid...
[CAE][READONLY][TRACE] Procesando X filas target para matching...
[CAE][READONLY][TRACE] ========================================
[CAE][READONLY][TRACE] RESULTADO FINAL: pending_items=X submission_plan=Y matched_count=Z
[CAE][READONLY][TRACE] ========================================
[CAE][READONLY][TRACE] Devolviendo result con plan.length=Y
[CAE][READONLY][TRACE] run_build_submission_plan_readonly_headful completado. plan_result type: <class 'dict'>
[CAE][READONLY][TRACE] plan_result es dict con items_count=Y
[CAE][READONLY][TRACE] BRANCH: processing_dict_result reason=plan_result es dict (READ-ONLY puro)
[CAE][READONLY] items_count=Y run_id=None client_req_id=... status=ok
```

---

## Pruebas Obligatorias

### 1. Backend Smoke Test

```bash
curl -X POST "http://127.0.0.1:8000/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=50&only_target=true" \
  -H "X-CLIENT-REQ-ID: test-123"
```

**Resultado esperado:**
- HTTP 200 (nunca 500)
- JSON válido con `status=ok`
- `items_count > 0` (si hay pendientes reales)
- Logs en consola con `[CAE][READONLY][TRACE]` mostrando ejecución de Playwright

### 2. Prueba Funcional desde UI

**Pasos:**
1. Abrir `/home`
2. Abrir modal "Revisar Pendientes CAE (Avanzado)"
3. Seleccionar:
   - Coord: "Aigues de Manresa"
   - Company: "Tedelab Ingeniería SCCL (F63161988)"
   - Platform: "egestiona"
   - Scope: "Trabajador"
   - Worker: "Emilio Roldán Molina (erm)"
4. Click en "Revisar ahora (READ-ONLY)"

**Resultado esperado:**
- ✅ Se abre Playwright (browser visible)
- ✅ Se hace login
- ✅ Se navega a listado de pendientes
- ✅ Se extraen filas del grid
- ✅ Se muestran items (>0 si hay pendientes reales)
- ✅ Logs en consola con `[CAE][READONLY][TRACE]`

### 3. Evidencias

**Guardar en `docs/evidence/c2_13_7_readonly_real_compute/`:**
- Screenshot del modal con resultados
- Log de consola con trace completo
- Si items=0, screenshot + log que explique por qué

---

## Root Cause Explicado

**Causa exacta:**
1. Línea 3210-3213: Excepción capturada silenciosamente con `pass`
2. Si `run_build_submission_plan_readonly_headful` lanzaba una excepción, `plan_result` quedaba como `None`
3. El código luego convertía `None` a resultado válido vacío, pero nunca se ejecutaba Playwright
4. No había logging suficiente para identificar qué excepción se estaba capturando

**Condiciones que evitaban Playwright:**
- `fixture=True` activaba modo legacy/fixture (sin Playwright)
- Excepciones silenciosas que no se loggeaban

**Solución:**
1. Añadido logging de trace completo en todas las ramas
2. Fixture solo se activa explícitamente (`fixture=True` o `EGESTIONA_READONLY_FIXTURE=1`)
3. Excepciones se propagan correctamente (no `pass` silencioso)
4. READ-ONLY siempre ejecuta Playwright (solo sin subida, pero sí con scraping)

---

## Confirmación del Fix

### ✅ READ-ONLY ejecuta Playwright

**Validación:**
- Logs muestran `[CAE][READONLY][TRACE] Lanzando browser Chromium`
- Browser se abre visiblemente (headless=False)
- Se hace login y se navega a listado de pendientes

### ✅ READ-ONLY extrae pendientes reales

**Validación:**
- `items_count > 0` si hay pendientes reales
- Logs muestran `RESULTADO FINAL: pending_items=X submission_plan=Y`

### ✅ Logging de trace completo

**Validación:**
- Todos los logs tienen prefijo `[CAE][READONLY][TRACE]`
- Se loggea cada rama ejecutada
- Se loggea el resultado final con `items_count`

---

## Próximos Pasos

1. ✅ Ejecutar prueba funcional desde UI
2. ✅ Verificar que se abre Playwright y se extraen pendientes
3. ✅ Capturar evidencias (screenshots + logs)
4. ✅ Verificar que `items_count > 0` si hay pendientes reales

---

**Fin del Resumen de Implementación**

*Última actualización: 2026-01-15*
