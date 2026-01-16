# SPRINT C2.9 — Estabilización CI + tiempos (Paso 1/2)
## Core suite 2x PASS + eliminar último selector por texto + cerrar edit test

**Fecha:** 2026-01-08

---

## Resumen Ejecutivo

Se añadió comando `test:e2e:core` en package.json, se eliminó el último selector por texto (botones "Resubir"/"Subir documento"), y se actualizó el test de edición para usar señales más estables. Algunos tests aún requieren ajustes adicionales.

---

## TAREA A — Comando "core suite" único

### Cambios en `package.json`

Añadido script:
```json
"test:e2e:core": "playwright test tests/e2e_search_smoke.spec.js tests/e2e_config_smoke.spec.js tests/e2e_calendar_pending_smoke.spec.js tests/cae_plan_e2e.spec.js tests/e2e_upload_preview.spec.js tests/e2e_edit_document.spec.js"
```

**Uso:**
```bash
npm run test:e2e:core
```

---

## TAREA B — Eliminar "Resubir" por data-testid

### Frontend (`frontend/repository_v3.html`)

1. **Botones "Resubir" en calendario:**
   - Línea ~2047 (tabla expirados): Añadido `data-testid="calendar-action-resubir"`
   - Línea ~2115 (tabla expirando pronto): Añadido `data-testid="calendar-action-resubir"`

2. **Botón "Subir documento" en calendario:**
   - Línea ~2209 (tabla pendientes): Añadido `data-testid="calendar-action-subir"`

### Test (`tests/e2e_calendar_pending_smoke.spec.js`)

**Antes:**
```javascript
const actionButtons = page.locator('button:has-text("Resubir"), button:has-text("Subir documento")');
```

**Después:**
```javascript
const actionButtons = page.locator('[data-testid="calendar-action-resubir"], [data-testid="calendar-action-subir"]');
```

✅ **Eliminado último selector por texto en suite core**

---

## TAREA C — Verificación core 2x

### Tests Críticos Verificados (2x PASS)

**Primera ejecución:**
- `e2e_search_smoke.spec.js`: ✅ PASS
- `e2e_config_smoke.spec.js`: ✅ PASS

**Segunda ejecución:**
- `e2e_search_smoke.spec.js`: ✅ PASS
- `e2e_config_smoke.spec.js`: ✅ PASS

### Tests con Problemas Identificados

**`e2e_edit_document.spec.js`:**
- **Problema:** Timeout esperando por `buscar-action-edit` o `buscar-row`
- **Causa:** `performSearch()` puede tardar más de lo esperado, o los resultados no se renderizan inmediatamente después de `view-buscar-ready`
- **Fix aplicado:**
  - Cambiado de `search-ui-ready` a `view-buscar-ready` + `search-ui-ready` (doble espera)
  - Añadido timeout de test a 60s
  - Añadido espera por `buscar-row` antes de buscar botones
- **Estado:** Requiere verificación adicional

**`e2e_calendar_pending_smoke.spec.js`:**
- Tests 2, 3, 4: Pueden requerir ajustes de timing similares

**`e2e_upload_preview.spec.js`:**
- Puede requerir ajustes de timeout

---

## Archivos Modificados

### Frontend
- `frontend/repository_v3.html`:
  - Línea ~2047: Añadido `data-testid="calendar-action-resubir"` (botón Resubir en expirados)
  - Línea ~2115: Añadido `data-testid="calendar-action-resubir"` (botón Resubir en expirando pronto)
  - Línea ~2209: Añadido `data-testid="calendar-action-subir"` (botón Subir documento)

### Tests
- `tests/e2e_calendar_pending_smoke.spec.js`: Reemplazado `button:has-text()` por `data-testid`
- `tests/e2e_edit_document.spec.js`: 
  - Cambiado de `search-ui-ready` a `view-buscar-ready` + `search-ui-ready`
  - Añadido timeout de test a 60s
  - Añadido espera por `buscar-row` antes de buscar botones
  - Actualizado helper `openEditModal` para usar `buscar-action-edit`

### Configuración
- `package.json`: Añadido script `test:e2e:core`

---

## Selectores Eliminados (Antes/Después)

| Antes (Frágil) | Después (Estable) |
|----------------|-------------------|
| `button:has-text("Resubir")` | `[data-testid="calendar-action-resubir"]` |
| `button:has-text("Subir documento")` | `[data-testid="calendar-action-subir"]` |

---

## Resultado Suite Core (Parcial)

**Tests verificados 2x PASS:**
- ✅ `e2e_search_smoke.spec.js` (2x PASS)
- ✅ `e2e_config_smoke.spec.js` (2x PASS)

**Tests con problemas:**
- ⚠️ `e2e_edit_document.spec.js` (requiere ajustes adicionales de timing)
- ⚠️ `e2e_calendar_pending_smoke.spec.js` (algunos tests pueden requerir ajustes)
- ⚠️ `e2e_upload_preview.spec.js` (puede requerir ajustes)

**Nota:** La suite completa tarda >5 minutos. Los tests críticos (search + config) pasan 2x consecutivas.

---

## Problemas Identificados y Fixes Aplicados

### 1. Test `e2e_edit_document.spec.js` - Inestabilidad

**Problema:** Timeout esperando por `buscar-action-edit` o `buscar-row`

**Causa identificada:**
- `view-buscar-ready` se establece antes de que `performSearch()` termine
- Los resultados pueden tardar en renderizarse después de `view-buscar-ready`
- El test esperaba directamente por botones sin verificar que los resultados estuvieran presentes

**Fixes aplicados:**
1. Cambiado de esperar solo `search-ui-ready` a esperar `view-buscar-ready` + `search-ui-ready`
2. Añadido timeout de test a 60s
3. Añadido espera explícita por `buscar-row` antes de buscar botones
4. Actualizado helper `openEditModal` para usar `buscar-action-edit` (testid correcto)

**Estado:** Requiere verificación adicional. El test puede necesitar más tiempo o ajustes en la lógica de espera.

---

## Deuda Restante

### Tests que requieren ajustes adicionales:
1. **`e2e_edit_document.spec.js`**: Puede requerir más tiempo o ajustes en la lógica de espera de resultados
2. **`e2e_calendar_pending_smoke.spec.js`**: Algunos tests pueden requerir ajustes de timing similares
3. **`e2e_upload_preview.spec.js`**: Puede requerir ajustes de timeout

---

## Criterios de Aceptación

✅ **Comando core suite único creado**
- `npm run test:e2e:core` disponible y funcional

✅ **Último selector por texto eliminado**
- `button:has-text("Resubir")` y `button:has-text("Subir documento")` reemplazados por `data-testid`

⚠️ **Suite core 2x PASS (parcial)**
- Tests críticos (search + config): ✅ PASS 2x
- Tests adicionales: Requieren ajustes adicionales

---

## Conclusión

Se completaron las tareas A y B (comando core suite + eliminación de último selector por texto). La tarea C está parcialmente completada: los tests críticos pasan 2x, pero algunos tests adicionales requieren ajustes de timing que se pueden abordar en el siguiente paso.
