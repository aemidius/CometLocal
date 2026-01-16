# SPRINT C2.9.22 — SALIR DEL BUCLE: Resultados del Diagnóstico

**Fecha:** 2026-01-12

---

## RESUMEN EJECUTIVO

✅ **ERROR JS TEMPRANO CONFIRMADO**: "Illegal return statement"
- El error ocurre ANTES de que `__REPO_SCRIPT_LOADED__` se establezca
- El script se corta en el parse/runtime, impidiendo que el resto del código se ejecute
- Esto explica por qué `gotoHash(calendario)` nunca completa: el script nunca termina de cargar

---

## PASO 0 — ESTADO DEL REPO

### Git Status
```
On branch feat/egestiona-cae-upload-v1
Changes not staged for commit:
  - frontend/repository_v3.html (modificado)
  - tests/helpers/e2eSeed.js (modificado)
  - Muchos otros archivos modificados (backend, tests, etc.)
```

### Últimos 20 commits
```
e055cee v1.9.1: Cerrar E2E de reintento (retry) de jobs
6d44641 Fix: Corregir Internal Server Error al resubir/reemplazar PDF de documento
29f114f Fix: Persistencia de validity_start_date en upload y validación mejorada
ed1791a repo-ui: v3 human-friendly repository UX (calendar, wizard, platforms)
76b17aa docs: update troubleshooting_override with test results
6ef5a40 fix(repo): robust parsing for validity_override PUT (object or string)
840fb1b fix(repo): change validity_override type to Any for proper validation
d6afef1 fix(repo): use Pydantic field_validator for validity_override normalization
dccfb03 fix(repo): robust parsing for validity_override PUT (object or string)
e03a8b6 feat(repo): grace policy + validity override + guardrails update
839617f feat(exec): self-test execute-from-plan + fin-date selector detection
02d031f feat(exec): self-test execute-from-plan + fin-date selector detection
852e55e feat(exec): execute submission plan scoped (write with guardrails)
d34686f feat(exec): execute submission plan scoped (write with guardrails)
39d1a9b feat(plan): build submission plan read-only (egestiona + repository)
c714307 feat(repo): document delete + edit actions UI
81f6147 feat(matching): match eGestiona pending docs to repository (read-only)
165ac40 feat(repo): docs subject assignment (company/person) + edit UI
5de443a chore: update .gitignore for document repository
c07c9a5 feat(repo): document repository v1 (types CRUD + doc upload + validity policy)
```

### Archivos modificados (diff --name-only)
- `frontend/repository_v3.html` (cambios extensos)
- `tests/helpers/e2eSeed.js` (añadido installBrowserErrorCapture, handlers de consola)
- Muchos otros archivos del backend y tests

---

## PASO 1 — CAPTURA DE ERRORES Y CONSOLA

✅ **COMPLETADO**: Se añadió captura completa de errores en `tests/helpers/e2eSeed.js`:

1. **installBrowserErrorCapture()** instalado ANTES de `page.goto()`
2. **Handlers de consola** (`page.on('console')`) instalados para capturar TODOS los logs
3. **Handlers de pageerror** (`page.on('pageerror')`) instalados
4. **window.__E2E_BROWSER_ERRORS__** inicializado con `addInitScript`

---

## PASO 2 — BARRERAS DE BOOT EN FRONTEND

✅ **CONFIRMADO**: Existe al principio del script:
```javascript
// SPRINT C2.9.20: Barrera ULTRA TEMPRANA que confirma que el script HA EMPEZADO A EJECUTARSE
window.__REPO_SCRIPT_LOADED__ = true;
try { console.log('[BOOT] __REPO_SCRIPT_LOADED__ = true'); } catch (e) {}
```

**PROBLEMA**: El log `[BOOT] __REPO_SCRIPT_LOADED__ = true` NO aparece en la consola durante los tests, lo que confirma que el script se corta ANTES de llegar a esta línea.

---

## PASO 3 — PRUEBA MÍNIMA (smoke_repository_boot.spec.js)

✅ **CREADO**: Test mínimo `tests/smoke_repository_boot.spec.js` que:
- Navega a `/repository` con `waitUntil: 'domcontentloaded'`
- Espera 3 señales en orden:
  1. `document.readyState === 'interactive'` o `'complete'` ✅
  2. `window.__REPO_SCRIPT_LOADED__ === true` ❌ (timeout)
  3. `[data-testid="app-ready"]` (opcional)
- Dump de `__E2E_BROWSER_ERRORS__` y `PAGE_STATE`
- Falla si hay errores JS

---

## PASO 4 — EJECUCIÓN AUTOMÁTICA

### 1. Smoke Boot Test

**Resultado:**
```
[BROWSER_ERROR] pageerror: Illegal return statement
[BROWSER_ERROR] stack: 

[PAGEERROR] Illegal return statement
[PAGEERROR] Stack: 

[SMOKE] document.readyState OK

Test timeout of 30000ms exceeded.
Error: page.waitForFunction: Test timeout of 30000ms exceeded.
  at page.waitForFunction(() => {
      return window.__REPO_SCRIPT_LOADED__ === true;
  }, { timeout: 10000 });
```

**Análisis:**
- ✅ `document.readyState` se establece correctamente
- ❌ `__REPO_SCRIPT_LOADED__` NUNCA se establece (timeout)
- ❌ Error JS temprano: "Illegal return statement"

### 2. CAE Plan Test

**Resultado:**
```
[BROWSER_ERROR] pageerror: Illegal return statement
[BROWSER_ERROR] stack: 

[BROWSER_ERRORS] Capturando errores del navegador después de timeout...
[BROWSER_ERRORS] No se pudieron capturar errores (página cerrada): page.evaluate: Target page, context or browser has been closed

Test timeout of 90000ms exceeded while running "beforeEach" hook.
Error: page.waitForFunction: Test timeout of 90000ms exceeded.
  at gotoHash (helpers\e2eSeed.js:239)
```

**Análisis:**
- ❌ Mismo error: "Illegal return statement"
- ❌ `gotoHash` nunca completa porque `__REPO_SCRIPT_LOADED__` nunca se establece
- ❌ La página se cierra antes de poder capturar errores

---

## PASO 5 — DECISIÓN GUIADA

### CASO A: ERROR JS TEMPRANO CONFIRMADO ✅

**Error detectado:**
- **Tipo**: `pageerror`
- **Mensaje**: "Illegal return statement"
- **Stack**: (vacío, indica error de parse)

**Ubicación:**
- El error ocurre durante el parse del script en `frontend/repository_v3.html`
- El error impide que el script continúe ejecutándose
- `__REPO_SCRIPT_LOADED__` nunca se establece porque el script se corta antes

**Búsqueda del origen:**
- Buscado en `frontend/repository_v3.html` por `return` statements
- Todos los `return` encontrados están dentro de funciones (correcto)
- El error "Illegal return statement" sugiere que hay un `return` fuera de una función, posiblemente:
  - Dentro de un template string mal formado
  - En código que se ejecuta en el nivel superior del script
  - En algún lugar donde hay código JavaScript mal estructurado

**Evidencia:**
- El error aparece inmediatamente después de `page.goto('/repository')`
- No hay logs de `[BOOT] __REPO_SCRIPT_LOADED__ = true` en la consola
- El script se corta antes de llegar a la línea 720 donde se establece `__REPO_SCRIPT_LOADED__`

---

## PASO 6 — PLAN DE ROLLBACK SEGURO

### Commit candidato para rollback

**Último commit "verde" conocido:**
- `ed1791a` - "repo-ui: v3 human-friendly repository UX (calendar, wizard, platforms)"
- Este commit parece ser el último antes de los cambios problemáticos

### Comandos sugeridos (NO EJECUTADOS)

```bash
# 1. Identificar commit candidato
git log --oneline --all -n 50 | grep -E "C2.9|C2.8|fix|Fix|repo-ui"

# 2. Verificar qué archivos cambiaron desde el commit candidato
git diff ed1791a -- frontend/repository_v3.html tests/helpers/e2eSeed.js

# 3. Rollback de SOLO los archivos problemáticos (sin tocar el resto)
git checkout ed1791a -- frontend/repository_v3.html tests/helpers/e2eSeed.js

# 4. Reejecutar tests
npx playwright test tests/smoke_repository_boot.spec.js --reporter=line
npx playwright test tests/cae_plan_e2e.spec.js --reporter=line
```

**NOTA**: El rollback NO se ejecutó en este sprint. Solo se preparó el plan.

---

## CONCLUSIÓN FACTUAL

### ¿Hay error JS temprano? **SÍ**

**Evidencia:**
1. ✅ Error `pageerror: Illegal return statement` capturado
2. ✅ El error ocurre inmediatamente después de `page.goto('/repository')`
3. ✅ `__REPO_SCRIPT_LOADED__` nunca se establece (timeout en waitForFunction)
4. ✅ No hay logs de `[BOOT] __REPO_SCRIPT_LOADED__ = true` en la consola
5. ✅ El script se corta antes de llegar a la línea 720

### ¿Cuál es el error?

**Error**: "Illegal return statement"
- **Tipo**: Error de parse/runtime
- **Ubicación**: `frontend/repository_v3.html` (durante el parse del script)
- **Causa probable**: Un `return` statement fuera de una función, posiblemente:
  - Dentro de un template string mal formado
  - En código que se ejecuta en el nivel superior
  - En algún lugar donde hay código JavaScript mal estructurado

### ¿app-ready se marca demasiado pronto?

**NO**: `app-ready` nunca se marca porque el script se corta antes de llegar a esa línea.

---

## ARCHIVOS MODIFICADOS EN ESTE SPRINT

### Tests
- `tests/smoke_repository_boot.spec.js`: Creado (test mínimo para capturar errores tempranos)

### Tests Helpers
- `tests/helpers/e2eSeed.js`:
  - Añadido `installBrowserErrorCapture` a exports
  - Añadido handler de consola (`page.on('console')`) para capturar TODOS los logs
  - Handler instalado ANTES de `page.goto()`

---

## PRÓXIMOS PASOS RECOMENDADOS

1. **Localizar el error exacto**:
   - Buscar en `frontend/repository_v3.html` por código que pueda tener un `return` fuera de una función
   - Revisar template strings y código que se ejecuta en el nivel superior
   - Usar un linter/parser de JavaScript para identificar el error exacto

2. **Corregir el error**:
   - Una vez localizado, corregir el `return` statement mal ubicado
   - Verificar que el script se ejecuta completamente

3. **Validar la corrección**:
   - Reejecutar `tests/smoke_repository_boot.spec.js`
   - Verificar que `__REPO_SCRIPT_LOADED__` se establece
   - Reejecutar `tests/cae_plan_e2e.spec.js`

4. **Si no se puede localizar rápidamente**:
   - Considerar el rollback a `ed1791a` para restaurar funcionalidad
   - Investigar el error en un branch separado

---

**Fin del Reporte**
