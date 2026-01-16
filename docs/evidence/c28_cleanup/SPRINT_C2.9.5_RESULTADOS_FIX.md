# SPRINT C2.9.5 — FIX estructural: view-ready/error invariantes

**Fecha:** 2026-01-08

---

## Resumen Ejecutivo

Se implementó un fix estructural para hacer que los markers `view-ready`/`view-error` sean invariantes usando un contenedor global `view-state-root` que nunca se re-renderiza.

---

## TAREA A — Crear "view-state-root" global ✅ COMPLETADA

### Archivo: `frontend/repository_v3.html`

**Cambios:**
- Añadido contenedor global `<div id="view-state-root" style="display: none;" aria-hidden="true"></div>` en el HTML (línea ~689)
- Este contenedor está fuera de `page-content` y nunca se re-renderiza

---

## TAREA B — Refactor mínimo de setViewState() (invariante) ✅ COMPLETADA

### Archivo: `frontend/repository_v3.html`

**Cambios:**
- Creada función `getViewStateRoot()` que obtiene o crea el contenedor global
- Refactorizada `setViewState()` para:
  - Usar `view-state-root` como contenedor único para todos los markers
  - Eliminar TODOS los markers previos de un viewName antes de crear uno nuevo
  - Crear EXACTAMENTE UN marker por estado (loaded/ready/error)
  - Los markers son `div` ocultos con `data-testid` y `data-view`

**Implementación:**
```javascript
function getViewStateRoot() {
    let root = document.getElementById('view-state-root');
    if (!root) {
        root = document.createElement('div');
        root.id = 'view-state-root';
        root.style.display = 'none';
        root.setAttribute('aria-hidden', 'true');
        document.body.appendChild(root);
    }
    return root;
}

function setViewState(viewName, state, errorMsg = null) {
    const viewStateRoot = getViewStateRoot();
    
    // Eliminar TODOS los markers previos de este viewName
    const existingMarkers = viewStateRoot.querySelectorAll(`[data-view="${viewName}"]`);
    existingMarkers.forEach(marker => marker.remove());
    
    // Crear EXACTAMENTE UN marker para el estado actual
    const marker = document.createElement('div');
    marker.setAttribute('data-testid', `view-${viewName}-${state}`);
    marker.setAttribute('data-view', viewName);
    marker.style.display = 'none';
    viewStateRoot.appendChild(marker);
    
    // ... alias y error handling ...
}
```

---

## TAREA C — Alias de nombres ✅ COMPLETADA

### Archivo: `frontend/repository_v3.html`

**Cambios:**
- Añadido alias bidireccional: `configuracion` <-> `settings`
- Cuando `viewName === 'settings'`, también se crea marker `view-configuracion-${state}`
- Cuando `viewName === 'configuracion'`, también se crea marker `view-settings-${state}`

---

## TAREA D — Ajuste mínimo tests ✅ NO NECESARIO

No se requirieron cambios en los tests. Los tests siguen esperando los mismos `data-testid` que antes.

---

## TAREA E — Validación (bloqueante)

### Primera ejecución:
```
npm run test:e2e:core
```

**Resumen:**
```
14 failed
1 passed (6.3m)
```

### Segunda ejecución:
```
npm run test:e2e:core
```

**Resumen:**
```
14 failed
1 passed (5.5m)
```

### Análisis:

**Problema identificado:**
Los errores NO son por los markers `view-ready`/`view-error`. Los errores son por **timeout en la API**:
- `Error: Timeout after 8000ms: http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3&max_months_back=12`

**Conclusión:**
El fix estructural de los markers está implementado correctamente. Los fallos actuales son por problemas de red/API, no por los markers de estado de vistas.

**Tests que pasaron:**
- `e2e_config_smoke.spec.js` - ✅ Pasa en ambas ejecuciones

**Tests que fallaron:**
- Todos los demás tests fallan por timeout en la API `/api/repository/docs/pending`

---

## Archivos Modificados

### Frontend
- `frontend/repository_v3.html`:
  - Línea ~689: Añadido contenedor `view-state-root`
  - Línea ~1369: Creada función `getViewStateRoot()`
  - Línea ~1370: Refactorizada función `setViewState()` para usar contenedor global

---

## Conclusión

✅ **Fix estructural completado**: Los markers `view-ready`/`view-error` ahora son invariantes y viven en un contenedor global que nunca se re-renderiza.

❌ **Tests aún fallan**: Pero NO por los markers, sino por timeouts en la API del backend.

**Siguiente paso:** Investigar por qué la API `/api/repository/docs/pending` está tardando más de 8s en responder.
