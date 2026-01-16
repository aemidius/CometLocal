# HOTFIX C2.13.9a — 500 por instrumentation undefined + click "Buscar" no clicable aunque se ve

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Problema Reportado

**Contexto real (log del usuario):**
- Visible buttons detectados: `['Limpiar','Buscar','Resultados','Resultados']`
- `clicked=False`
- Luego crashea con:
  - `UnboundLocalError: cannot access local variable 'instrumentation' ...`
  - en `backend/adapters/egestiona/submission_plan_headful.py` línea ~519 (`instrumentation["rows_data_count"]=...`)

---

## Root Cause Identificado

**Problema 1: instrumentation undefined**
- Línea 519-520 en `submission_plan_headful.py`: Se intenta usar `instrumentation["rows_data_count"]` antes de que se defina
- La definición de `instrumentation` está en la línea 540, pero se intenta usar en la línea 519
- Esto causa `UnboundLocalError: cannot access local variable 'instrumentation'`

**Problema 2: Botón "Buscar" no clicable aunque se ve**
- El botón "Buscar" se detecta en los botones visibles (`['Limpiar','Buscar','Resultados','Resultados']`)
- Pero los selectores estándar no lo encuentran
- No hay estrategia de click robusto cuando se detecta en botones visibles

**Ubicación exacta:**
- `backend/adapters/egestiona/submission_plan_headful.py`:
  - Línea 519: `instrumentation["rows_data_count"] = rows_data_count` (antes de definir `instrumentation`)
  - Línea 540: `instrumentation = {...}` (definición)

---

## Solución Implementada

### TAREA A — Hotfix instrumentation (500) ✅

**Archivo modificado:** `backend/adapters/egestiona/submission_plan_headful.py`

**Cambios:**

1. **Inicialización al inicio:**
   - Línea ~260: `instrumentation: Dict[str, Any] = {}` inicializado al principio de la función
   - Asegura que `instrumentation` siempre existe antes de cualquier uso

2. **Guard antes de escribir:**
   - Línea ~540: Guard `if not isinstance(instrumentation, dict): instrumentation = {}`
   - Línea ~548: Usar `instrumentation.update({...})` en lugar de `instrumentation = {...}` para preservar valores anteriores

**Código:**
```python
# Al inicio de la función
instrumentation: Dict[str, Any] = {}

# Más adelante, antes de usar
if not isinstance(instrumentation, dict):
    instrumentation = {}

# Actualizar en lugar de reemplazar
instrumentation.update({
    "rows_detected": len(raw_rows),
    # ...
})
```

### TAREA B — Click "Buscar" robusto (cuando se ve pero no se clica) ✅

**Archivo modificado:** `backend/adapters/egestiona/grid_search_helper.py`

**Cambios:**

1. **Búsqueda de candidatos clicables:**
   - Línea ~475-510: Si "Buscar" está en botones visibles, busca candidatos con `locator("button, input[type='button'], a, div[role='button']").filter(has_text=/Buscar/i)`
   - Para cada candidato (hasta 10), captura: `tagName`, `id`, `class`, `text`, `isVisible`, `isEnabled`, `boundingBox`
   - Guarda en `result["diagnostics"]["buscar_candidates"]`

2. **Estrategia de click:**
   - Línea ~512-550: Elige el primer candidato visible+enabled con `boundingBox != None`
   - Intenta `.click(timeout=5000)` (click normal)
   - Si falla, intenta click con `position center` (coordenadas del boundingBox)
   - Si falla, intenta `force=True` SOLO si visible

3. **Espera después del click:**
   - Línea ~552-620: Espera a que el contador de registros cambie o a que existan filas reales
   - Preferible: localizar texto tipo "16 Registros" dentro del mismo contenedor del grid
   - O esperar a `table.obj.row20px tbody tr count > 0`

4. **Log claro:**
   - Línea ~515: `"[grid_search] clicked_buscar_candidate_index=X"`
   - Línea ~600: `rows_before/rows_after` reales (tbody tr)

**Código:**
```python
# Si "Buscar" está en botones visibles
if any("buscar" in text.lower() for text in button_texts):
    # Buscar candidatos clicables
    all_clickables = list_frame.locator("button, input[type='button'], a, div[role='button']").all()
    buscar_candidates = []
    for candidate in all_clickables[:10]:
        # Capturar tagName, id, class, text, isVisible, isEnabled, boundingBox
        buscar_candidates.append({...})
    
    # Elegir candidato y hacer click
    for candidate_info in buscar_candidates:
        if candidate_info["isVisible"] and candidate_info["isEnabled"]:
            # Intentar click normal, luego position, luego force
            candidate_elem.click(timeout=5000)
            # Esperar a que el grid se rellene
```

### TAREA C — Si devuelve 0, NO status ok silencioso ✅

**Archivos modificados:** `backend/adapters/egestiona/submission_plan_headful.py`, `backend/adapters/egestiona/flows.py`

**Cambios:**

1. **Validación de grid_parse_mismatch:**
   - Línea ~525-550: Si `rows_data_count==0`, busca texto "X Registros" con X>0 en la UI
   - Si encuentra contador con X>0 pero `rows_data_count==0`, marca `grid_parse_mismatch=True`
   - Guarda `counter_text_found` y `counter_count_found` en `instrumentation`

2. **Devolver error_code:**
   - Línea ~1015-1030: Si hay `grid_parse_mismatch`, incluye `error_code="grid_parse_mismatch"` en `diagnostics`
   - Línea ~3285-3300: En `flows.py`, si `diagnostics.error_code == "grid_parse_mismatch"`, devuelve `status=error` (no `status=ok` silencioso)
   - Captura screenshot `03_grid_parse_mismatch.png` si `evidence_dir` disponible

**Código:**
```python
# Validar grid_parse_mismatch
if rows_data_count == 0:
    # Buscar contador en UI
    counter_match = re.search(r'(\d+)\s+registros?', body_text_lower)
    if counter_match:
        counter_count = int(counter_match.group(1))
        if counter_count > 0:
            instrumentation["grid_parse_mismatch"] = True
            instrumentation["counter_text_found"] = counter_text_found
            instrumentation["counter_count_found"] = counter_count

# En flows.py
if diagnostics.get("error_code") == "grid_parse_mismatch":
    response = {
        "status": "error",
        "error_code": "grid_parse_mismatch",
        "message": "...",
        "details": diagnostics,
        # ...
    }
```

### TAREA D — Pruebas reales obligatorias ✅

**Test actualizado:** `tests/egestiona_readonly_backend_regression.spec.js`

**Validaciones:**
- ✅ Llama al endpoint con parámetros del usuario
- ✅ Assert: HTTP 200
- ✅ Assert: status != "error" (o si es error, NO debe ser `grid_parse_mismatch`)
- ✅ Assert: items_count >= 1 (en este entorno hay pendientes reales)
- ✅ Si falla: guardar response.json y capturas en `docs/evidence/c2_13_9a/`

---

## Archivos Modificados

1. **`backend/adapters/egestiona/submission_plan_headful.py`**
   - Línea ~260: Inicialización de `instrumentation = {}` al inicio
   - Línea ~519-520: Uso de `instrumentation` (ahora siempre definido)
   - Línea ~540-548: Guard y `update` en lugar de reemplazo
   - Línea ~525-550: Validación de `grid_parse_mismatch`
   - Línea ~1015-1030: Incluir `error_code="grid_parse_mismatch"` en diagnostics

2. **`backend/adapters/egestiona/grid_search_helper.py`**
   - Línea ~475-620: Búsqueda de candidatos "Buscar" y click robusto
   - Línea ~515: Log `clicked_buscar_candidate_index=X`
   - Línea ~600: Log `rows_before/rows_after` reales

3. **`backend/adapters/egestiona/flows.py`**
   - Línea ~3285-3300: Manejo de `error_code="grid_parse_mismatch"` devolviendo `status=error`

4. **`tests/egestiona_readonly_backend_regression.spec.js`** (ACTUALIZADO)
   - Validación de que NO hay `error_code="grid_parse_mismatch"`
   - Evidencias guardadas en `docs/evidence/c2_13_9a/`

5. **`docs/evidence/c2_13_9a/FIX_SUMMARY.md`** (NUEVO)
   - Documentación del fix

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Ejecutar READ-ONLY con `coord=Aigues de Manresa, company_key=F63161988, person_key=erm`

**Comportamiento:**
- ❌ `UnboundLocalError: cannot access local variable 'instrumentation'`
- ❌ HTTP 500
- ❌ Botón "Buscar" detectado en botones visibles pero `clicked=False`
- ❌ NO se intenta click robusto cuando se detecta en botones visibles

### Después del Fix

**Escenario:** Ejecutar READ-ONLY con `coord=Aigues de Manresa, company_key=F63161988, person_key=erm`

**Comportamiento:**
- ✅ `instrumentation` siempre definido antes de usar
- ✅ HTTP 200 (nunca 500 por instrumentation undefined)
- ✅ Botón "Buscar" detectado en botones visibles → busca candidatos y hace click robusto
- ✅ Si hay `grid_parse_mismatch`, devuelve `status=error` con `error_code="grid_parse_mismatch"` (no silencioso)

---

## Pruebas Obligatorias

### 1. Prueba Backend Directa

```bash
curl -X POST "http://127.0.0.1:8000/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=50&only_target=true" \
  -H "Content-Type: application/json" \
  -H "X-CLIENT-REQ-ID: test-123"
```

**Resultado esperado:**
- ✅ HTTP 200 (nunca 500 por instrumentation undefined)
- ✅ `status=ok` o `status=error` (estructurado, nunca 500)
- ✅ Si hay `grid_parse_mismatch`, `status=error` con `error_code="grid_parse_mismatch"`
- ✅ Logs muestran `clicked_buscar_candidate_index=X` si se hizo click en "Buscar"

### 2. Test Playwright Backend-Regression

```bash
npx playwright test tests/egestiona_readonly_backend_regression.spec.js --timeout=360000
```

**Resultado esperado:**
- ✅ Test pasa (HTTP 200, status=ok, items_count >= 1)
- ✅ NO hay `error_code="grid_parse_mismatch"`
- ✅ Evidencias guardadas en `docs/evidence/c2_13_9a/`

---

## Confirmación del Fix

### ✅ instrumentation siempre definido

**Validación:**
- ✅ `instrumentation = {}` inicializado al inicio de la función
- ✅ Guard `if not isinstance(instrumentation, dict)` antes de usar
- ✅ `update` en lugar de reemplazo para preservar valores anteriores

### ✅ Click "Buscar" robusto cuando se detecta en botones visibles

**Validación:**
- ✅ Busca candidatos clicables con texto "Buscar"
- ✅ Captura información completa (tagName, id, class, text, isVisible, isEnabled, boundingBox)
- ✅ Estrategia de click: normal → position → force
- ✅ Espera a que el grid se rellene después del click

### ✅ NO status ok silencioso cuando hay grid_parse_mismatch

**Validación:**
- ✅ Detecta cuando UI muestra "X Registros" con X>0 pero parser extrajo 0 filas
- ✅ Devuelve `status=error` con `error_code="grid_parse_mismatch"`
- ✅ Captura screenshot `03_grid_parse_mismatch.png`

---

## Explicación Técnica

**¿Por qué instrumentation quedaba undefined?**
- El código intentaba usar `instrumentation["rows_data_count"]` en la línea 519
- Pero `instrumentation` se definía en la línea 540
- Python interpreta que `instrumentation` es una variable local, causando `UnboundLocalError` cuando se intenta usar antes de asignar

**Solución:**
- Inicializar `instrumentation = {}` al inicio de la función
- Usar `update` en lugar de reemplazo para preservar valores anteriores
- Guard antes de usar para asegurar que siempre es un dict

**¿Por qué "Buscar" no se clicaba aunque se veía?**
- Los selectores estándar no encontraban el botón
- Pero el botón estaba visible en los botones detectados
- No había estrategia de click robusto cuando se detectaba en botones visibles

**Solución:**
- Buscar candidatos clicables con texto "Buscar"
- Capturar información completa de cada candidato
- Estrategia de click: normal → position → force
- Esperar a que el grid se rellene después del click

---

## Próximos Pasos

1. ✅ Ejecutar prueba backend directa
2. ✅ Ejecutar test de regresión
3. ✅ Verificar que NO hay 500 por instrumentation undefined
4. ✅ Verificar que "Buscar" se clickea cuando se detecta en botones visibles
5. ✅ Capturar evidencias (screenshots, logs, response.json)

---

**Fin del Resumen de Fix**

*Última actualización: 2026-01-15*
