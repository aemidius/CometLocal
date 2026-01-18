# SPRINT C2.24 — Tenant transparente (derivado de Plataforma + Empresa externa)

**Fecha:** 2026-01-17  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Eliminar el concepto "tenant" de la UI para usuario final:
- Ocultar el selector manual "Tenant"
- Derivar automáticamente `X-Tenant-ID` a partir de:
  - Plataforma seleccionada
  - Empresa externa (company_key) seleccionada
- Mantener compatibilidad:
  - Si no hay selección suficiente, usar tenant "default"
- Mantener modo avanzado (opcional) solo para debug, oculto por defecto.

**NO tocar backend multi-tenant** (ya está implementado).  
**SÍ modificar frontend** para que el header `X-Tenant-ID` se calcule automáticamente.

---

## Implementación

### A) Modelo "Contexto de coordinación" en frontend

**Ubicación:** `frontend/repository_v3.html`

**Objeto de contexto global:**
- `active_platform_key` (string|null)
- `active_external_company_key` (string|null)

**Persistencia en localStorage:**
- `cometlocal_active_platform_key`
- `cometlocal_active_external_company_key`

**Reglas:**
- Si faltan `platform_key` o `external_company_key` => `tenant_id = "default"`

**Funciones:**
```javascript
getCoordinationContext() -> { platform_key, external_company_key }
setCoordinationContext(platformKey, externalCompanyKey)
```

### B) Tenant ID derivado (interno)

**Función:** `computeTenantId(platform_key, external_company_key) -> string`

**Regla determinista:**
```
tenant_id = normalize(platform_key) + "__" + normalize(external_company_key)
```

**Normalización:**
- `lowercase`
- `trim`
- Reemplazar espacios por `-`
- Dejar solo `[a-z0-9_-]`
- Reemplazar múltiples `-` o `_` por uno solo
- Eliminar `-` o `_` al inicio/final

**Ejemplo:**
```
platform_key = "egestiona"
external_company_key = "COMPANY_A"
=> tenant_id = "egestiona__company_a"
```

Esto evita colisiones cross-plataforma.

### C) fetchWithTenant() -> fetchWithContext()

**Cambio:**
- Reemplazado `fetchWithTenant()` por `fetchWithContext()`
- Mantiene alias `fetchWithTenant = fetchWithContext` para compatibilidad
- NO lee tenant manual
- Calcula `tenant_id` automáticamente desde contexto

**Nuevo helper:**
```javascript
async function fetchWithContext(url, options = {}) {
    const tenantId = getActiveTenant(); // Derivado de contexto
    // Añade header X-Tenant-ID automáticamente
    // ...
}
```

**Todas las llamadas API** en plan_review / learning / presets / export / metrics / debug usan `fetchWithContext` (o el alias `fetchWithTenant`).

### D) UI: Seleccionar Plataforma y Empresa externa

**Ubicación:** Header de la aplicación (`content-header`)

**Componentes:**
1. **Selector de Plataforma:**
   - Dropdown con plataformas cargadas desde `/api/config/platforms`
   - Persiste en `localStorage`

2. **Selector de Empresa externa:**
   - Input text libre (permite entrada manual)
   - Placeholder: "Ej: COMPANY_A"
   - Persiste en `localStorage`

3. **Badge de contexto:**
   - Muestra: "Plataforma | Cliente" cuando hay contexto
   - Muestra: "default" cuando no hay contexto
   - Cambia de color según si hay contexto o no

**En modal de Export:**
- Sección "Contexto de coordinación" visible
- Selectores de Plataforma y Empresa externa
- Badge que muestra tenant derivado
- Al seleccionar, actualiza contexto global

**En vista Plan Review:**
- Alerta informativa mostrando contexto activo
- Si no hay contexto, muestra advertencia

**Selector manual de Tenant:**
- Oculto por defecto
- Accesible mediante toggle "Modo debug"
- Solo visible cuando `localStorage['cometlocal_debug_tenant_mode'] === 'true'`

### E) Compatibilidad con flujos existentes

**Comportamiento por defecto:**
- Si el usuario no selecciona nada en el Contexto:
  - `tenant_id = "default"`
- El comportamiento previo debe seguir funcionando (single-tenant) sin configurar nada.

**Modo debug:**
- Toggle "Modo debug" en header
- Muestra selector manual de tenant
- Permite override manual del tenant derivado
- Útil para testing y debugging

---

## Estructura de archivos

```
frontend/repository_v3.html
  - Funciones de contexto (líneas ~800-1000)
  - computeTenantId() (líneas ~850-870)
  - fetchWithContext() (líneas ~950-990)
  - initCoordinationContext() (líneas ~1080-1140)
  - UI selectores (líneas ~800-820)
  - Modal export con contexto (líneas ~10630-10680)
  - Vista plan_review con contexto (líneas ~10413-10440)
```

---

## Uso

### Flujo normal (sin contexto):

1. Usuario abre aplicación
2. No selecciona Plataforma ni Cliente
3. `tenant_id = "default"` automáticamente
4. Todas las operaciones usan tenant "default"

### Flujo con contexto:

1. Usuario selecciona Plataforma: "egestiona"
2. Usuario ingresa Cliente: "COMPANY_A"
3. `tenant_id = "egestiona__company_a"` automáticamente
4. Todas las operaciones usan ese tenant
5. Datos aislados por tenant:
   - Learning/hints
   - Presets
   - Exports
   - Métricas

### Cambio de contexto:

1. Usuario cambia Cliente a "COMPANY_B"
2. `tenant_id = "egestiona__company_b"` automáticamente
3. Vista se refresca automáticamente
4. Datos mostrados corresponden al nuevo tenant

---

## Validación manual

### 1) Default sin seleccionar nada

**Pasos:**
1. Abrir `http://127.0.0.1:8000/repository_v3.html#plan_review`
2. No seleccionar Plataforma ni Cliente
3. Verificar badge muestra "default"
4. Cargar plan, operar normalmente
5. Verificar que funciona (tenant default)

**Resultado esperado:**
- Badge muestra "default"
- Operaciones funcionan normalmente
- Datos en `data/runs/` (legacy)

### 2) Seleccionar plataforma+cliente => cambia aislamiento

**Pasos:**
1. Seleccionar Plataforma: "egestiona"
2. Ingresar Cliente: "COMPANY_A"
3. Verificar badge muestra "egestiona | COMPANY_A"
4. Exportar CAE con company_key
5. Verificar ZIP en `data/tenants/egestiona__company_a/exports/`
6. Crear preset
7. Verificar preset solo aparece para ese contexto
8. Cambiar Cliente a "COMPANY_B"
9. Verificar preset anterior NO aparece
10. Verificar nuevo preset solo aparece para COMPANY_B

**Resultado esperado:**
- Badge muestra contexto activo
- Export en tenant path correcto
- Presets aislados por tenant
- Cambio de contexto refresca datos

### 3) Modo debug

**Pasos:**
1. Click en "Modo debug" en header
2. Verificar que aparece selector manual de tenant
3. Ingresar tenant manual: "test_tenant"
4. Verificar que badge muestra "test_tenant"
5. Operar normalmente
6. Verificar que usa tenant manual (override)

**Resultado esperado:**
- Selector manual visible
- Override funciona
- Datos en tenant especificado

---

## Criterios de validación

- [x] Selector manual de tenant oculto por defecto
- [x] Selectores de Plataforma y Cliente visibles en header
- [x] Badge muestra contexto o "default"
- [x] Tenant derivado automáticamente: `platform__company`
- [x] Sin contexto => tenant "default"
- [x] Con contexto => tenant derivado
- [x] Cambio de contexto refresca vista
- [x] Export usa tenant derivado
- [x] Presets aislados por tenant
- [x] Learning/hints aislados por tenant
- [x] Modo debug funciona (override manual)
- [x] Compatibilidad con flujos existentes (default funciona)

---

## Notas técnicas

### Normalización de tenant_id

La función `normalizeForTenant()` asegura que:
- No hay caracteres especiales
- No hay espacios
- Formato consistente: `[a-z0-9_-]`
- Separador: `__` (doble underscore)

Esto evita:
- Colisiones entre plataformas
- Problemas con caracteres especiales
- Inconsistencias en nombres

### Persistencia

El contexto se persiste en `localStorage`:
- `cometlocal_active_platform_key`
- `cometlocal_active_external_company_key`

Al recargar la página, el contexto se restaura automáticamente.

### Compatibilidad

- `fetchWithTenant` sigue funcionando (alias de `fetchWithContext`)
- Código legacy que usa `fetchWithTenant` no necesita cambios
- Backend multi-tenant no cambió (solo frontend)

---

## Commit

**Hash:** (pendiente)  
**Mensaje:** `feat: C2.24 tenant transparent via platform+client context`

---

## Referencias

- **C2.22A:** Multi-tenant plumbing (backend)
- **C2.22B:** Scoping real de stores por tenant
- **C2.22C:** UI Tenant Selector + Mapping company_key → tenant
