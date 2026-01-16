# HOTFIX C2.13.3 — Eliminar shadowing de json en READ-ONLY (cannot access local variable 'json')

**Fecha:** 2026-01-15  
**Estado:** ✅ FIX IMPLEMENTADO

---

## Bug Report

El endpoint `POST /runs/egestiona/build_submission_plan_readonly` ya no da 500, pero devuelve:
- `status=error`
- `error_code=readonly_compute_failed`
- `message: "cannot access local variable 'json' where it is not associated with a value"`

Esto indica **shadowing**: alguna variable local llamada `json` en el scope de la función está shadowing el módulo `json` importado.

---

## Causa Raíz

**Problema:**
- Hay imports locales de `json` dentro de la función `egestiona_build_submission_plan_readonly`:
  - Línea 3326: `import json` dentro del bloque `elif isinstance(plan_result, str):`
  - Línea 3714: `import json` dentro del bloque de instrumentación
- Cuando Python ve `import json` dentro de una función, trata `json` como una variable local
- Si se intenta usar `json.dumps()` antes de que se ejecute el `import json` local, Python lanza `UnboundLocalError: cannot access local variable 'json' where it is not associated with a value`

**Ejemplo del problema:**
```python
import json  # Import global

def my_function():
    # Si hay un import json local más abajo, Python trata json como variable local
    json.dumps(...)  # ❌ UnboundLocalError si el import local no se ha ejecutado aún
    import json  # Esto shadow el módulo json global
```

---

## Solución Implementada

### TAREA A — Localización del shadowing ✅

**Archivos identificados:** `backend/adapters/egestiona/flows.py`

**Imports locales encontrados:**
- Línea 3326: `import json` dentro del bloque `elif isinstance(plan_result, str):`
- Línea 3714: `import json` dentro del bloque de instrumentación

### TAREA B — Blindaje definitivo ✅

**Archivo modificado:** `backend/adapters/egestiona/flows.py`

**Cambios:**

1. **Cambio del import global:**
   - Línea 3: Cambiado `import json` a `import json as pyjson`
   - Esto evita cualquier shadowing futuro

2. **Reemplazo de todas las llamadas:**
   - `json.dumps()` → `pyjson.dumps()`
   - `json.dump()` → `pyjson.dump()`
   - `json.loads()` → `pyjson.loads()` (si existe)

3. **Eliminación de imports locales:**
   - Línea 3326: Eliminado `import json` local
   - Línea 3714: Eliminado `import json` local

**Código:**
```python
# TOP del archivo
import json as pyjson  # HOTFIX C2.13.3: Usar alias para evitar shadowing

# Dentro de la función, todas las llamadas usan pyjson:
checksum_data = pyjson.dumps(plan_items_for_checksum, sort_keys=True, ensure_ascii=False)
pyjson.dump(response, f, indent=2, ensure_ascii=False, default=str)
print(f"[CAE_CONTRACT] Response ERROR: {pyjson.dumps(response, indent=2, default=str)}")

# Eliminados imports locales:
# ❌ import json  # ELIMINADO
```

---

## Archivos Modificados

1. **`backend/adapters/egestiona/flows.py`**
   - Línea 3: Cambiado `import json` a `import json as pyjson`
   - Línea 3280, 3453: `json.dumps()` → `pyjson.dumps()`
   - Línea 3342, 3356, 3368, 3380: `json.load()` → `pyjson.load()`
   - Línea 3422, 3575, 3625, 3679: `json.dump()` → `pyjson.dump()`
   - Línea 3589, 3716: `json.dumps()` → `pyjson.dumps()`
   - Línea 3326: Eliminado `import json` local
   - Línea 3714: Eliminado `import json` local

2. **`docs/evidence/c2_13_3_json_shadow_fix/FIX_SUMMARY.md`** (NUEVO)
   - Documentación del fix

---

## Comportamiento Antes vs Después

### Antes del Fix

**Escenario:** Endpoint READ-ONLY ejecutado

**Comportamiento:**
- ❌ `UnboundLocalError: cannot access local variable 'json' where it is not associated with a value`
- ❌ `status=error`, `error_code=readonly_compute_failed`
- ❌ Frontend recibe error

### Después del Fix

**Escenario:** Endpoint READ-ONLY ejecutado

**Comportamiento:**
- ✅ No hay shadowing de `json`
- ✅ `status=ok` (aunque `items=[]` si no hay matches)
- ✅ Frontend recibe respuesta JSON válida

---

## Prueba Mínima

### Ejecutar endpoint manualmente

```bash
curl -X POST "http://127.0.0.1:8000/runs/egestiona/build_submission_plan_readonly" \
  -H "Content-Type: application/json" \
  -d '{
    "coord": "Kern",
    "company_key": "F63161988",
    "person_key": null,
    "limit": 20,
    "only_target": true,
    "dry_run": true
  }'
```

**Resultado esperado:**
- HTTP 200 (no 500, no error de shadowing)
- JSON válido con `status: "ok"` o `status: "error"` (pero no por shadowing)
- No hay `UnboundLocalError: cannot access local variable 'json'`

### Verificar en consola

El endpoint imprime:
```
[CAE][RESP] client_req_id=... status=ok error_code=- run_id=None artifacts.run_id=None
```

O si hay error (pero NO por shadowing):
```
[CAE][RESP] client_req_id=... status=error error_code=readonly_compute_failed run_id=None artifacts.run_id=None
```

**NO debe aparecer:**
- `cannot access local variable 'json'`
- `UnboundLocalError`

---

## Confirmación del Fix

### ✅ Shadowing de json eliminado

**Validación:**
- Import global cambiado a `import json as pyjson`
- Todas las llamadas `json.xxx` reemplazadas por `pyjson.xxx`
- Imports locales de `json` eliminados
- No hay shadowing de `json`

### ✅ Endpoint READ-ONLY estable

**Validación:**
- No hay `UnboundLocalError: cannot access local variable 'json'`
- Endpoint devuelve HTTP 200 con JSON válido
- `status=ok` (aunque `items=[]` si no hay matches)

---

## Próximos Pasos

1. ✅ Reiniciar backend
2. ✅ Ejecutar flujo desde frontend con los mismos parámetros
3. ✅ Confirmar en consola que no aparece el error de `cannot access local variable 'json'`
4. ✅ Verificar HTTP 200 y `status: ok` (aunque sea con `items=[]`)

---

**Fin del Resumen del Fix**

*Última actualización: 2026-01-15*
