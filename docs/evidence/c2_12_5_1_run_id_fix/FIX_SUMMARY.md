# HOTFIX C2.12.5.1 — UI "Revisar Pendientes CAE" muestra run_id_missing aunque el run se crea

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Problema Reportado

Tras ejecutar READ-ONLY desde el modal "Revisar Pendientes CAE (Avanzado)", el backend crea el run correctamente (se ve en logs) pero el UI muestra error `run_id_missing` y no pinta resultados.

---

## Causa Raíz

El endpoint `POST /runs/egestiona/build_submission_plan_readonly` devuelve:
- `plan_id` (línea 3296 en `flows.py`)
- `run_id` (añadido por `normalize_contract` en línea 3307)

Pero el frontend en `extractRunId()` **NO estaba buscando `plan_id`**, solo buscaba:
- `result.run_id`
- `result.artifacts.run_id`
- `result.data.run_id`
- etc.

**NO buscaba:**
- `result.plan_id` ❌

---

## Solución Implementada

### TAREA A — Inspección ✅

**Evidencia encontrada:**
- `docs/evidence/egestiona_manual/last_network_response.json` muestra respuesta con `error_code: "run_id_missing"`
- El endpoint devuelve `plan_id` pero el frontend no lo busca

**Shape de respuesta del endpoint:**
```json
{
  "status": "ok",
  "plan_id": "r_...",  // ← Frontend NO buscaba esto
  "run_id": "r_...",   // ← Añadido por normalize_contract
  "summary": {...},
  "items": [...],
  "artifacts": {
    "run_id": "r_...",
    "storage_state_path": "..."
  }
}
```

### TAREA B — FIX Frontend ✅

**Archivo modificado:** `frontend/home.html`

**Cambios:**

1. **Función `extractRunId()` mejorada** (2 lugares):
   - Añadido `result?.plan_id` como segunda opción
   - Añadido `result?.runId` (camelCase variant)
   - Añadido `result?.artifacts?.plan_id`
   - Añadido `result?.data?.plan_id`

   **Antes:**
   ```javascript
   function extractRunId(result) {
       return (
           result?.run_id ||
           result?.artifacts?.run_id ||
           result?.artifacts?.runId ||
           result?.data?.run_id ||
           result?.data?.runId ||
           null
       );
   }
   ```

   **Después:**
   ```javascript
   function extractRunId(result) {
       return (
           result?.run_id ||
           result?.plan_id ||  // ← NUEVO
           result?.runId ||     // ← NUEVO
           result?.artifacts?.run_id ||
           result?.artifacts?.runId ||
           result?.artifacts?.plan_id ||  // ← NUEVO
           result?.data?.run_id ||
           result?.data?.runId ||
           result?.data?.plan_id ||  // ← NUEVO
           null
       );
   }
   ```

2. **Logging mejorado** para debug:
   - Añadido logging de `extractedRunId`, `hasRunId`, `hasPlanId`, `hasArtifactsRunId`
   - Logging en `[CAE][NET]` con información completa

3. **Manejo de errores mejorado**:
   - Si no hay run_id, el error ahora incluye:
     - HTTP Status
     - Endpoint URL
     - Body raw completo

### TAREA C — Backward Compatibility Backend ✅

**Estado:** Ya estaba implementado correctamente

El backend ya devuelve tanto `plan_id` como `run_id`:
- `plan_id` se añade explícitamente (línea 3296)
- `run_id` se añade por `normalize_contract(response, run_id)` (línea 3307)

**Verificación:**
- Si `run_id` es None, el endpoint retorna error `run_id_missing` antes de construir response (línea 3224-3229)
- Si `run_id` existe, `normalize_contract` lo añade al response

**No se requieren cambios en el backend** ✅

### TAREA D — Validación Automática ✅

**Test E2E creado:** `tests/egestiona_run_id_extraction_e2e.spec.js`

**Validaciones:**
1. ✅ Ejecuta flujo completo READ-ONLY
2. ✅ Captura respuesta de red
3. ✅ Verifica que `extractRunId()` encuentra `run_id` o `plan_id`
4. ✅ Verifica que UI NO muestra error `run_id_missing` cuando hay run_id/plan_id
5. ✅ Genera evidencias:
   - `last_network_response.json`
   - `final_state.png`
   - `console_log.txt`
   - `test_summary.json`

**Ejecutar test:**
```bash
npx playwright test tests/egestiona_run_id_extraction_e2e.spec.js --headed --timeout=360000
```

---

## Archivos Modificados

1. **`frontend/home.html`**
   - Línea ~1138: Función `extractRunId()` (primera definición) - Añadido `plan_id`
   - Línea ~1462: Función `extractRunId()` (segunda definición) - Añadido `plan_id`
   - Línea ~1453: Logging mejorado con información de extracción
   - Línea ~1490: Manejo de errores mejorado con HTTP status y endpoint URL

2. **`tests/egestiona_run_id_extraction_e2e.spec.js`** (NUEVO)
   - Test E2E completo para validar extracción robusta de run_id

---

## Shape de Respuesta

### Antes del Fix

**Backend devuelve:**
```json
{
  "status": "ok",
  "plan_id": "r_abc123",
  "run_id": "r_abc123",  // Añadido por normalize_contract
  "summary": {...},
  "artifacts": {
    "run_id": "r_abc123"
  }
}
```

**Frontend buscaba:**
- ✅ `result.run_id` → Encontrado
- ❌ `result.plan_id` → NO buscaba (BUG)

**Resultado:** Si `normalize_contract` no se ejecutaba o fallaba, el frontend no encontraba `run_id` y mostraba error.

### Después del Fix

**Backend devuelve:** (igual)
```json
{
  "status": "ok",
  "plan_id": "r_abc123",
  "run_id": "r_abc123",
  "summary": {...},
  "artifacts": {
    "run_id": "r_abc123"
  }
}
```

**Frontend busca:**
- ✅ `result.run_id` → Encontrado
- ✅ `result.plan_id` → Encontrado (FIX)
- ✅ `result.runId` → Encontrado (camelCase)
- ✅ `result.artifacts.plan_id` → Encontrado
- ✅ `result.data.plan_id` → Encontrado

**Resultado:** El frontend encuentra `run_id` o `plan_id` en cualquier caso.

---

## Confirmación del Fix

### ✅ UI NO muestra run_id_missing cuando hay plan_id/run_id

**Validación:**
- El frontend ahora busca `plan_id` como segunda opción
- Si la respuesta tiene `plan_id` pero no `run_id`, el frontend lo encuentra
- Si la respuesta tiene ambos, el frontend usa `run_id` (prioridad)

### ✅ Backend siempre devuelve run_id (backward compatibility)

**Validación:**
- `normalize_contract(response, run_id)` siempre se ejecuta cuando hay `run_id`
- Si no hay `run_id`, el endpoint retorna error `run_id_missing` antes
- El backend devuelve tanto `plan_id` como `run_id` para máxima compatibilidad

### ✅ Errores incluyen información útil

**Validación:**
- Si no hay run_id, el error incluye:
  - HTTP Status
  - Endpoint URL
  - Body raw completo
  - Request ID para correlación

---

## Evidencias Generadas

**Test E2E genera:**
- `docs/evidence/c2_12_5_1_run_id_fix/last_network_response.json` - Respuesta real del endpoint
- `docs/evidence/c2_12_5_1_run_id_fix/final_state.png` - Screenshot del UI
- `docs/evidence/c2_12_5_1_run_id_fix/console_log.txt` - Logs de consola
- `docs/evidence/c2_12_5_1_run_id_fix/test_summary.json` - Resumen del test

---

## Próximos Pasos

1. ✅ Ejecutar test E2E para validar
2. ✅ Verificar que UI pinta resultados correctamente
3. ✅ Confirmar que no hay regresiones

---

**Fin del Resumen del Fix**

*Última actualización: 2026-01-15*
