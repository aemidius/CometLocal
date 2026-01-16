# HOTFIX C2.12.6 — build_submission_plan_readonly NO debe crear run ni tocar filesystem

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Problema Reportado

El endpoint `POST /runs/egestiona/build_submission_plan_readonly` estaba devolviendo:
```json
{
  "status": "error",
  "error_code": "run_id_missing",
  "message": "No se pudo generar run_id. El proceso falló antes de crear el directorio de runs."
}
```

Esto es **INCORRECTO** para un endpoint READ-ONLY. El frontend funciona bien y solo muestra el error recibido.

---

## Objetivo

Hacer que `build_submission_plan_readonly`:
- **NUNCA** intente crear `run_id`
- **NUNCA** cree directorios en `/runs`
- **NUNCA** inicialice estado persistente
- **NUNCA** falle por `run_id_missing`

---

## Solución Implementada

### TAREA 1 — Revisión de build_submission_plan_readonly ✅

**Problema identificado:**
- El endpoint llamaba a `run_build_submission_plan_readonly_headful` que:
  - Creaba `run_id` (línea 220)
  - Creaba directorios en `/runs` (línea 221-223)
  - Escribía archivos en el filesystem
  - Devolvía solo `run_id`
- El endpoint luego intentaba leer del filesystem basándose en ese `run_id`
- Si la función fallaba antes de crear el `run_id`, el endpoint devolvía `run_id_missing`

### TAREA 2 — Refactor: función con return_plan_only ✅

**Archivo modificado:** `backend/adapters/egestiona/submission_plan_headful.py`

**Cambios:**

1. **Parámetro `return_plan_only` añadido:**
   - Si `return_plan_only=True`, NO crea `run_id` ni directorios
   - NO escribe archivos en el filesystem
   - Devuelve el plan directamente como dict

2. **Lógica condicional para filesystem:**
   - Todas las operaciones de filesystem están protegidas con `if not return_plan_only:`
   - Screenshots, evidence paths, storage_state, etc. solo se crean si NO es `return_plan_only`

**Código:**
```python
def run_build_submission_plan_readonly_headful(
    *,
    ...
    return_plan_only: bool = False,  # Si True, devuelve plan directamente sin crear run
) -> str | Dict[str, Any]:
    # HOTFIX C2.12.6: Si return_plan_only=True, NO crear run ni tocar filesystem
    if return_plan_only:
        run_id = None
        run_dir = None
        evidence_dir = None
    else:
        run_id = f"r_{uuid.uuid4().hex}"
        run_dir = Path(base) / "runs" / run_id
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # ... (lógica de computación del plan)
    
    # HOTFIX C2.12.6: Si return_plan_only=True, devolver plan directamente
    if return_plan_only:
        summary = {
            "pending_count": len(pending_items),
            "matched_count": sum(1 for item in submission_plan if item.get("matched_doc") and item.get("matched_doc", {}).get("doc_id")),
            "unmatched_count": len(pending_items) - sum(1 for item in submission_plan if item.get("matched_doc") and item.get("matched_doc", {}).get("doc_id")),
            "duration_ms": duration_ms,
        }
        
        return {
            "plan": submission_plan,
            "summary": summary,
            "pending_items": pending_items,
            "match_results": match_results,
            "duration_ms": duration_ms,
        }
    
    # ... (lógica de escritura a filesystem solo si NO es return_plan_only)
    return run_id
```

### TAREA 3 — build_submission_plan_readonly refactorizado ✅

**Archivo modificado:** `backend/adapters/egestiona/flows.py`

**Cambios:**

1. **Endpoint usa `return_plan_only=True`:**
   - Llama a `run_build_submission_plan_readonly_headful` con `return_plan_only=True`
   - Captura el plan directamente sin leer del filesystem
   - NO intenta crear `run_id` ni directorios

2. **Lógica de respuesta:**
   - Si `plan_result` es dict (READ-ONLY puro): usa directamente, NO toca filesystem
   - Si `plan_result` es string (legacy/fixture): lee del filesystem (compatibilidad)
   - Genera `confirm_token` y `plan_checksum` sin `run_id` (usa placeholder)

3. **Si no hay pendientes:**
   - Devuelve `status: "ok"` con `plan: []`
   - **NO** devuelve error

**Código:**
```python
# HOTFIX C2.12.6: READ-ONLY NO debe crear run ni tocar filesystem
plan_result = await run_in_threadpool(
    lambda: run_build_submission_plan_readonly_headful(
        ...
        return_plan_only=True,  # NO crear run ni tocar filesystem
    )
)

# Si plan_result es un dict (return_plan_only=True), usar directamente
if isinstance(plan_result, dict):
    items = plan_result.get("plan", [])
    summary = plan_result.get("summary", {...})
    
    # Generar checksum y confirm_token sin run_id
    # ...
    
    response = {
        "status": "ok",
        "plan_id": None,  # READ-ONLY no tiene plan_id
        "runs_url": None,  # READ-ONLY no tiene runs_url
        "summary": summary,
        "items": items,
        "plan": items,  # Alias para compatibilidad
        ...
    }
    
    # NO normalizar contrato (no hay run_id)
    # NO guardar en filesystem
```

### TAREA 4 — Guardrails ✅

**Archivo modificado:** `backend/adapters/egestiona/flows.py`

**Cambios:**

1. **Todos los errores devuelven `readonly_compute_failed`:**
   - `ValueError` → `readonly_compute_failed`
   - `RuntimeError` → `readonly_compute_failed` (o error específico como `dhx_blocker_not_dismissed`)
   - `Exception` general → `readonly_compute_failed`
   - **NUNCA** `run_id_missing`

2. **NO se intenta preservar `run_id` en errores:**
   - READ-ONLY no crea runs, así que no hay `run_id` que preservar

**Código:**
```python
except ValueError as e:
    return {
        "status": "error",
        "error_code": "readonly_compute_failed",  # NUNCA run_id_missing
        "message": f"Validation error: {str(e)}",
        "details": None,
    }
except Exception as e:
    return {
        "status": "error",
        "error_code": "readonly_compute_failed",  # NUNCA run_id_missing
        "message": f"Error durante computación READ-ONLY: {str(e)}",
        "details": error_detail,
    }
```

### TAREA 5 — Tests (pendiente) ⚠️

**Nota:** Los tests deben ser creados/ajustados para verificar:
- READ-ONLY con pendientes → OK
- READ-ONLY sin pendientes → OK + plan vacío
- READ-ONLY nunca crea directorios en `/runs`

---

## Archivos Modificados

1. **`backend/adapters/egestiona/submission_plan_headful.py`**
   - Línea ~191: Parámetro `return_plan_only` añadido
   - Línea ~221-231: Lógica condicional para NO crear run/directorios si `return_plan_only=True`
   - Línea ~236-242: Evidence paths solo si NO es `return_plan_only`
   - Línea ~272-278: Storage state solo si NO es `return_plan_only`
   - Línea ~283-332: Screenshots y evidence solo si NO es `return_plan_only`
   - Línea ~838-851: Guardar evidence solo si NO es `return_plan_only`
   - Línea ~856-871: Devolver plan directamente si `return_plan_only=True`
   - Línea ~909: Token con placeholder si `return_plan_only=True`
   - Línea ~916-990: Guardar en filesystem solo si NO es `return_plan_only`

2. **`backend/adapters/egestiona/flows.py`**
   - Línea ~3187-3207: Endpoint usa `return_plan_only=True`
   - Línea ~3209-3407: Lógica para usar plan directamente sin leer del filesystem
   - Línea ~3409-3415: Errores devuelven `readonly_compute_failed` (NUNCA `run_id_missing`)
   - Línea ~3433-3457: Exception handler devuelve `readonly_compute_failed` (NUNCA `run_id_missing`)

3. **`backend/adapters/egestiona/submission_plan_compute.py`** (NUEVO, no usado aún)
   - Función pura para computar plan (reserva para futura refactorización)

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Endpoint READ-ONLY ejecuta y falla antes de crear `run_id`

**Comportamiento:**
- ❌ `run_build_submission_plan_readonly_headful` intenta crear `run_id` y directorios
- ❌ Si falla antes de crear `run_id`, el endpoint devuelve `run_id_missing`
- ❌ El endpoint intenta leer del filesystem basándose en `run_id` que no existe
- ❌ Crea directorios en `/runs` incluso en modo READ-ONLY

### Después del Fix

**Escenario:** Endpoint READ-ONLY ejecuta (con o sin pendientes)

**Comportamiento:**
- ✅ `run_build_submission_plan_readonly_headful` con `return_plan_only=True` NO crea `run_id` ni directorios
- ✅ Si falla, devuelve `readonly_compute_failed` (NUNCA `run_id_missing`)
- ✅ El endpoint captura el plan directamente sin leer del filesystem
- ✅ NO crea directorios en `/runs` en modo READ-ONLY
- ✅ Si no hay pendientes, devuelve `status: "ok"` con `plan: []` (NO error)

---

## Confirmación del Fix

### ✅ READ-ONLY NO crea run_id

**Validación:**
- `run_build_submission_plan_readonly_headful` con `return_plan_only=True` NO crea `run_id`
- `run_id = None` cuando `return_plan_only=True`
- NO se crean directorios en `/runs`

### ✅ READ-ONLY NO toca filesystem

**Validación:**
- Todas las operaciones de filesystem están protegidas con `if not return_plan_only:`
- Screenshots, evidence paths, storage_state, etc. solo se crean si NO es `return_plan_only`
- El endpoint NO lee del filesystem cuando `plan_result` es dict

### ✅ READ-ONLY NUNCA devuelve run_id_missing

**Validación:**
- Todos los errores devuelven `readonly_compute_failed` (o error específico)
- `ValueError` → `readonly_compute_failed`
- `Exception` general → `readonly_compute_failed`
- **NUNCA** `run_id_missing`

### ✅ READ-ONLY devuelve plan vacío si no hay pendientes

**Validación:**
- Si no hay pendientes, devuelve `status: "ok"` con `plan: []`
- **NO** devuelve error

---

## Próximos Pasos

1. ✅ Ejecutar flujo READ-ONLY desde UI
2. ✅ Verificar que NO aparece error `run_id_missing`
3. ✅ Verificar que NO se crean directorios en `/runs`
4. ⚠️ Crear/ajustar tests para validar:
   - READ-ONLY con pendientes → OK
   - READ-ONLY sin pendientes → OK + plan vacío
   - READ-ONLY nunca crea directorios en `/runs`

---

**Fin del Resumen del Fix**

*Última actualización: 2026-01-15*
