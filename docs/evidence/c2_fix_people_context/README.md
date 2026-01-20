# HOTFIX URGENTE: Config → Trabajadores no guarda (context guardrail bloquea POST)

## Problema

Al intentar guardar trabajadores desde Config → Trabajadores:
- La tabla "se queda en negro / desaparece"
- Al volver, los cambios no se guardaron
- Backend muestra: `context_guardrail_block reason: no_human_context_headers`
- POST /config/people devuelve 500 (debería ser 400)

**Causa raíz:** El formulario HTML en el iframe no incluye headers de contexto humano requeridos por el guardrail de escritura.

## Fix Aplicado

### 1. Frontend: Interceptar submit del formulario
- **Archivo:** `backend/executor/config_viewer.py`
- **Cambio:** Añadido JavaScript que intercepta el submit del formulario
- **Funcionalidad:**
  - Obtiene contexto del parent window (`window.parent.getCoordinationContext()`)
  - Verifica que el contexto es válido antes de enviar
  - Hace `fetch()` con headers de contexto en lugar de submit normal
  - Muestra mensaje de error claro si falta contexto
  - Maneja errores 400 correctamente

### 2. Backend: Corregir 400→500
- **Archivo:** `backend/app.py`
- **Cambio:** Middleware devuelve JSONResponse directamente en lugar de re-lanzar HTTPException
- **Resultado:** POST sin headers ahora devuelve 400 (no 500) con mensaje claro

### 3. UI: Corregir selector "-- Todas --"
- **Archivo:** `backend/executor/config_viewer.py`
- **Cambio:** Separar opciones de filtro (incluye "-- Todas --") de opciones de fila (solo empresas + "Sin asignar")
- **Resultado:** Las filas nunca usan "-- Todas --" como valor, solo "Sin asignar" o empresa real

### 4. Persistencia: Guardrail explícito
- **Archivo:** `backend/repository/config_store_v1.py`
- **Cambio:** Añadido guardrail explícito para asegurar que `own_company_key` se incluye en JSON
- **Resultado:** `own_company_key` se persiste correctamente incluso cuando es `None`

## Archivos Modificados

1. `backend/app.py`
   - Middleware devuelve JSONResponse directamente para HTTPException 400
   - Exception handler registrado antes del middleware

2. `backend/executor/config_viewer.py`
   - JavaScript que intercepta submit y añade headers de contexto
   - Separación de opciones de filtro vs fila
   - Manejo de errores UX

3. `backend/repository/config_store_v1.py`
   - Guardrail explícito para `own_company_key` en serialización

4. `tests/test_config_people_guardrail.py` (nuevo)
   - Tests unitarios para verificar guardrail 400

5. `tests/test_people_config_e2e.spec.js` (actualizado)
   - Test E2E para flujo completo con contexto

## Tests

### Unit Tests (pytest)
- ✅ `test_post_people_without_headers_returns_400_not_500`: Verifica que devuelve 400 (no 500)
- ✅ `test_post_people_with_headers_works`: Verifica que funciona con headers válidos
- ✅ `test_post_people_incomplete_headers_returns_400`: Verifica que headers incompletos devuelven 400
- ✅ `test_post_people_persists_own_company_key`: Verifica persistencia
- ✅ `test_post_people_persists_none_as_null`: Verifica que "unassigned" se guarda como null
- ✅ `test_save_people_includes_own_company_key_in_json`: Verifica serialización

**Resultado:** ✅ Todos los tests pasan (6/6)

## Verificación Manual

1. Levantar servidor: `uvicorn backend.app:app`
2. Abrir: `http://127.0.0.1:8000/repository_v3.html#configuracion?section=people`
3. **IMPORTANTE:** Seleccionar Empresa propia, Plataforma y Empresa coordinada en el header principal
4. En el iframe de Trabajadores, asignar Empresa propia a trabajadores
5. Click "Guardar"
6. Verificar que:
   - No aparece mensaje de error
   - La página se recarga
   - Los valores se mantienen tras recargar
   - `data/refs/people.json` contiene `own_company_key` correcto

## Comandos para Reproducir

```bash
# Levantar servidor
uvicorn backend.app:app

# Ejecutar tests unitarios
python -m pytest tests/test_config_people_guardrail.py tests/test_people_persistence_hotfix.py -v

# Ejecutar test E2E (requiere servidor corriendo)
npx playwright test tests/test_people_config_e2e.spec.js
```

## Commit Message Recomendado

```
fix: config people save requires human context headers + preserve 400

- Interceptar submit del formulario para añadir headers de contexto desde parent window
- Middleware devuelve JSONResponse 400 directamente (no 500)
- Separar opciones de filtro ("-- Todas --") de opciones de fila
- Guardrail explícito para persistencia de own_company_key
- Tests unitarios y E2E para verificar flujo completo
- Fix para bug donde POST /config/people fallaba sin headers de contexto
```
