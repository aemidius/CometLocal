# SPRINT C2.27 — Guardrails de contexto + E2E/CI (regresión obligatoria)

**Fecha:** 2026-01-18  
**Estado:** ✅ IMPLEMENTADO Y VERIFICADO

---

## Objetivo

Implementar guardrails de contexto para prevenir operaciones WRITE sin contexto humano válido, estabilizar tests E2E y asegurar regresión obligatoria.

---

## Implementación

### A) Guardrails Backend

**Ubicación:** `backend/shared/context_guardrails.py` (nuevo módulo)

**Funciones principales:**
- `is_write_request(request)` - Identifica operaciones WRITE (POST, PUT, DELETE, PATCH)
- `has_human_coordination_context(request)` - Verifica presencia de los 3 headers humanos
- `has_legacy_tenant_header(request)` - Verifica header legacy X-Tenant-ID
- `is_dev_or_test_environment()` - Verifica entorno dev/test
- `validate_write_request_context(request)` - Aplica guardrail y lanza HTTPException si falta contexto

**Reglas:**
1. Operaciones WRITE requieren contexto humano completo (3 headers) O legacy + dev/test
2. Si no se cumple, responde `400 Bad Request` con:
   ```json
   {
     "error": "missing_coordination_context",
     "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
   }
   ```
3. Operaciones READ no se bloquean

**Middleware:** Registrado en `backend/app.py` como middleware HTTP global

### B) Tests Unitarios

**Ubicación:** `tests/test_context_guardrails.py` (nuevo archivo)

**Cobertura:**
- ✅ WRITE sin contexto -> 400
- ✅ WRITE con contexto -> OK
- ✅ WRITE con legacy + dev/test -> OK
- ✅ WRITE con legacy + prod -> 400
- ✅ READ sin contexto -> OK

**Resultado:** 10 tests pasando

### C) UX Frontend

**Ubicación:** `frontend/repository_v3.html`

**Funcionalidad:**
- Función `showContextRequiredMessage()`: Muestra banner temporal con mensaje humano
- Resalta visualmente los 3 selects con borde rojo por 2 segundos
- Intercepta error `missing_coordination_context` en `fetchWithContext()`
- Mensaje: "Selecciona Empresa propia, Plataforma y Empresa coordinada para continuar."

### D) Endpoint Debug Mejorado

**Ubicación:** `backend/repository/settings_routes.py`

**Endpoint:** `GET /api/repository/debug/data_dir`

**Mejoras SPRINT C2.27:**
- Incluye `tenant_id` derivado del contexto
- Incluye `tenant_source` (header/query/default)
- Incluye `tenant_data_dir` y `tenant_data_dir_resolved`
- Gated por ENVIRONMENT (solo dev/test)

### E) Tests E2E Estabilizados

**Ubicación:** `tests/coordination_context_header.spec.js`

**Mejoras:**
- ✅ Timeouts ajustados para estabilidad
- ✅ Tests adaptativos (skip si no hay suficientes opciones)
- ✅ Verificación de aislamiento usando endpoint debug
- ✅ Nuevo test: "should block WRITE operations without context"
- ✅ Inclusión de headers de coordinación en peticiones directas

**Resultado:** 6 tests pasando

---

## Archivos Modificados

1. **`backend/shared/context_guardrails.py`** (nuevo)
   - Lógica de guardrails centralizada

2. **`backend/app.py`**
   - Middleware de guardrail registrado
   - Import de HTTPException añadido

3. **`tests/test_context_guardrails.py`** (nuevo)
   - 10 tests unitarios completos

4. **`frontend/repository_v3.html`**
   - Función `showContextRequiredMessage()`
   - Interceptación de errores en `fetchWithContext()`

5. **`backend/repository/settings_routes.py`**
   - Endpoint debug mejorado con información de tenant

6. **`tests/coordination_context_header.spec.js`**
   - Tests estabilizados y mejorados
   - Nuevo test de guardrail WRITE

---

## Verificación

### Tests Unitarios
```bash
python -m pytest tests/test_context_guardrails.py -v
```
**Resultado:** ✅ 10 passed

### Tests E2E
```bash
npx playwright test tests/coordination_context_header.spec.js
```
**Resultado:** ✅ 6 passed

---

## Evidencias

- Tests unitarios: 10/10 pasando
- Tests E2E: 6/6 pasando
- Guardrail funcional: Bloquea WRITE sin contexto
- UX funcional: Muestra mensaje humano y resalta selects
- Endpoint debug: Retorna información de tenant correctamente

---

## Notas

- El mensaje de error **NO filtra** la palabra "tenant" (requisito cumplido)
- El guardrail permite legacy en dev/test para compatibilidad
- Los tests E2E son adaptativos y funcionan con datasets mínimos
- El endpoint debug está protegido (solo dev/test)
