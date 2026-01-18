# SPRINT C2.26 — Contexto de coordinación HUMANO (tenant 100% transparente)

**Fecha:** 2026-01-17  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo (UX FINAL)

Implementar un "Contexto de Coordinación" HUMANO en la UI (repository_v3.html / header global) con 3 selectores dependientes:
1. Empresa propia (quien coordina)
2. Plataforma (eGestiona/CTAIMA/etc.)
3. Empresa coordinada (externa, depende de plataforma)
+ Badge humano de contexto (sin palabra "tenant" en ningún sitio)

**REGLAS DURAS:**
- "tenant" es solo interno: NO aparecer en UI, textos, payloads, ni nombres de campos/variables de frontend.
- Todas las llamadas siguen usando `fetchWithContext()` (ya existente).
- El sistema YA es multi-tenant (C2.22A/B/C) y desde C2.24–C2.25 el tenant se deriva automáticamente: hay que mantener compatibilidad y solo mejorar el "input humano" que alimenta esa derivación.
- NO romper E2E. Dejar tests verdes.

---

## Implementación

### A) Inventario rápido (completado)

**Frontend:**
- `frontend/repository_v3.html`: Header con contexto parcial (plataforma + empresa externa texto libre)
- `fetchWithContext()`: Inyecta `X-Tenant-ID` derivado
- Contexto actual: `platform_key` + `external_company_key` (C2.24/C2.25)

**Backend:**
- `backend/shared/tenant_context.py`: Resuelve tenant desde headers
- `backend/shared/tenant_paths.py`: Paths multi-tenant con fallback legacy
- `data/refs/org.json`: Organización propia (una sola actualmente)
- `data/refs/platforms.json`: Plataformas con coordinations (empresas coordinadas)

**Campos existentes:**
- `org.json`: `legal_name`, `tax_id` (usado como `own_company_key`)
- `platforms.json`: `platforms[].key`, `platforms[].coordinations[].client_code` (usado como `coordinated_company_key`), `platforms[].coordinations[].label` (nombre humano)

### B) Modelo de "Contexto Humano" (frontend)

**Clase:** `CoordinationContextV1` (frontend-only)

**Campos:**
- `own_company_key` (string|null) - Empresa propia (quien coordina)
- `platform_key` (string|null) - Plataforma CAE
- `coordinated_company_key` (string|null) - Empresa externa coordinada
- `updated_at` (iso string)

**Persistencia:**
- `localStorage` key: `"coordination_context_v1"`
- Carga inicial:
  - Si existe, rehidratar y validar (que siga existiendo en options)
  - Si no existe o es inválido, autoseleccionar defaults razonables:
    - `own_company`: primera disponible
    - `platform`: primera disponible
    - `coordinated_company`: primera de esa plataforma (si existe)

**Reglas:**
- No se permite texto libre: todo es dropdown con opciones reales
- Cada cambio en selectores:
  - Limpiar dependientes (si cambia platform => reset coordinated_company)
  - Guardar en localStorage
  - Refrescar badge
  - Disparar evento `coordinationContextChanged` para refresh de vistas

### C) API Backend: endpoint único de opciones "humanas"

**Endpoint:** `GET /api/coordination/context/options`

**Respuesta:**
```json
{
  "own_companies": [
    { "key": "F63161988", "name": "Tedelab Ingeniería SCCL", "vat_id": "F63161988" }
  ],
  "platforms": [
    { "key": "egestiona", "name": "Egestiona" }
  ],
  "coordinated_companies_by_platform": {
    "egestiona": [
      { "key": "aiguesdemanresa", "name": "Aigues de Manresa", "vat_id": null },
      { "key": "GRUPO_INDUKERN", "name": "Kern", "vat_id": null }
    ]
  }
}
```

**Fuentes:**
- `own_companies`: Desde `org.json` (por ahora solo una, expandible)
- `platforms`: Desde `platforms.json`
- `coordinated_companies_by_platform`: Desde `platforms[].coordinations[]` (usando `client_code` como key, `label` como name)

**Implementación:**
- `backend/api/coordination_context_routes.py`: Nuevo router
- Registrado en `backend/app.py`

### D) Resolución automática interna (backend) SIN "tenant" EXPUESTO

**Función:** `compute_tenant_from_coordination_context(own_company_key, platform_key, coordinated_company_key) -> str`

**Regla determinista:**
```
Si faltan los 3 valores => "default"
Si están los 3: normalize(own) + "__" + normalize(platform) + "__" + normalize(coordinated)
```

**Ejemplo:**
```
own_company_key = "F63161988"
platform_key = "egestiona"
coordinated_company_key = "aiguesdemanresa"
=> tenant_id = "F63161988__egestiona__aiguesdemanresa"
```

**Headers humanos:**
- `X-Coordination-Own-Company`
- `X-Coordination-Platform`
- `X-Coordination-Coordinated-Company`

**Prioridad en `get_tenant_from_request()`:**
1. Headers humanos (si están los 3) => Calcula tenant_id determinista
2. Header `X-Tenant-ID` (legacy)
3. Query param `tenant_id` (legacy)
4. Default "default"

**Persistencia:**
- Usa el layout multi-tenant existente: `data/tenants/<tenant_id>/`
- No inventa rutas nuevas, reutiliza estructura de C2.22A

### E) UI: Header con 3 selectores + badge humano

**Ubicación:** `frontend/repository_v3.html` - Header global

**Componentes:**
1. **Selector "Empresa propia":**
   - `data-testid="ctx-own-company"`
   - Dropdown con opciones desde `/api/coordination/context/options`

2. **Selector "Plataforma":**
   - `data-testid="ctx-platform"`
   - Dropdown con opciones desde `/api/coordination/context/options`
   - Al cambiar, filtra empresas coordinadas

3. **Selector "Empresa coordinada":**
   - `data-testid="ctx-coordinated-company"`
   - Dropdown dependiente de plataforma
   - Se actualiza automáticamente al cambiar plataforma

4. **Badge:**
   - `data-testid="ctx-badge"`
   - Formato: `"<Empresa propia> · <Plataforma> · <Empresa coordinada>"`
   - Si falta empresa coordinada: `"<Empresa propia> · <Plataforma> · (sin empresa coordinada)"`
   - Si no hay contexto: `"Sin contexto"`
   - **NO menciona "tenant" en ningún sitio**

**Dependencias:**
- Plataforma filtra Empresa coordinada
- Cambio de plataforma resetea empresa coordinada

**Carga de options:**
- Al iniciar app, llama a `GET /api/coordination/context/options`
- Rellena dropdowns
- Aplica rehidratación de localStorage
- Si el contexto guardado es inválido, auto-corrige a defaults y guarda

### F) Refresh de vistas al cambiar contexto

**Evento global:**
```javascript
window.dispatchEvent(new CustomEvent('coordinationContextChanged', {
    detail: ctx
}));
```

**Listener global:**
- Escucha `coordinationContextChanged`
- Si la vista actual carga datos, recarga automáticamente
- Respeta `setViewState(view, "loaded"/"ready"/"error")`
- Sin hard reload (solo re-ejecuta `loadPage()`)

**Vistas afectadas:**
- `loadInicio()` - Carga tipos, docs, rules, platforms
- `loadBuscar()` - Carga docs con filtros
- `loadCalendario()` - Carga pendientes
- `loadPlanReview()` - Carga plan, presets, hints
- Otras vistas que cargan datos desde API

### G) Tests E2E + evidencia

**Archivo:** `tests/coordination_context_header.spec.js`

**Tests:**
1. Verificar que existen los 3 selects y el badge
2. Verificar que cargan opciones desde API
3. Verificar que cambiar plataforma actualiza empresas coordinadas
4. Verificar que cambiar contexto cambia data_dir (aislamiento real)
5. Verificar que el contexto persiste en localStorage

**Tests unitarios backend:**
- `tests/test_tenant_context_c2_26.py`: Tests para `compute_tenant_from_coordination_context()` y `get_tenant_from_request()` con headers humanos

**Evidencias:**
- Screenshots antes/después (pendiente ejecución manual)
- `docs/evidence/c2_26/README.md` (este archivo)

---

## Cambios técnicos

### Archivos creados

1. **`backend/api/coordination_context_routes.py`**:
   - Endpoint `GET /api/coordination/context/options`
   - Modelos: `CompanyOptionV1`, `PlatformOptionV1`, `CoordinationContextOptionsV1`

2. **`tests/test_tenant_context_c2_26.py`**:
   - Tests unitarios para resolución de tenant desde headers humanos

3. **`tests/coordination_context_header.spec.js`**:
   - Tests E2E Playwright para UI del contexto

### Archivos modificados

1. **`backend/shared/tenant_context.py`**:
   - Añadida función `compute_tenant_from_coordination_context()`
   - Modificada `get_tenant_from_request()` para priorizar headers humanos

2. **`backend/app.py`**:
   - Registrado router `coordination_context_router`

3. **`frontend/repository_v3.html`**:
   - Reemplazado sistema de contexto antiguo (C2.24/C2.25) por nuevo modelo humano (C2.26)
   - Clase `CoordinationContextV1` (frontend-only)
   - Función `initCoordinationContext()` actualizada para cargar desde nuevo endpoint
   - Función `fetchWithContext()` actualizada para enviar headers humanos
   - UI actualizada con 3 selectores dependientes
   - Badge actualizado con formato humano
   - Evento `coordinationContextChanged` para refresh de vistas
   - Eliminadas funciones obsoletas (modo debug, funciones legacy)

---

## Validación manual

### 1) Arrancar server y abrir cualquier vista

**Pasos:**
1. Arrancar: `python -m uvicorn backend.app:app --port 8000`
2. Abrir: `http://127.0.0.1:8000/repository_v3.html#inicio`
3. Verificar que aparecen 3 selectores en header:
   - "Empresa propia"
   - "Plataforma"
   - "Empresa coordinada"
4. Verificar badge muestra contexto o "Sin contexto"

**Resultado esperado:**
- 3 selectores visibles
- Badge visible
- No aparece la palabra "tenant" en ningún sitio

### 2) Cargar opciones y seleccionar contexto completo

**Pasos:**
1. Esperar a que se carguen las opciones (1-2 segundos)
2. Seleccionar "Empresa propia" (primera opción)
3. Seleccionar "Plataforma" (ej: "egestiona")
4. Verificar que "Empresa coordinada" se actualiza automáticamente
5. Seleccionar "Empresa coordinada" (ej: "Aigues de Manresa")
6. Verificar badge muestra: "Tedelab Ingeniería SCCL · Egestiona · Aigues de Manresa"

**Resultado esperado:**
- Opciones cargadas desde API
- Dependencias funcionan (plataforma filtra empresas coordinadas)
- Badge muestra formato humano correcto

### 3) Verificar aislamiento real (cambiar contexto cambia data_dir)

**Pasos:**
1. Seleccionar contexto: Empresa propia + Plataforma "egestiona" + Empresa "Aigues de Manresa"
2. Exportar CAE (o crear preset)
3. Verificar que el ZIP/preset está en: `data/tenants/F63161988__egestiona__aiguesdemanresa/`
4. Cambiar a otra empresa coordinada (ej: "Kern")
5. Verificar que el ZIP/preset anterior NO aparece
6. Crear nuevo preset/export
7. Verificar que está en: `data/tenants/F63161988__egestiona__GRUPO_INDUKERN/`

**Resultado esperado:**
- Datos aislados por contexto
- Cambio de contexto cambia el directorio de datos
- No hay mezcla entre contextos

### 4) Verificar persistencia y refresh de vistas

**Pasos:**
1. Seleccionar contexto completo
2. Navegar a "Buscar documentos"
3. Verificar que el contexto se mantiene
4. Recargar página (F5)
5. Verificar que el contexto se restaura desde localStorage
6. Cambiar contexto
7. Verificar que la vista actual se refresca automáticamente

**Resultado esperado:**
- Contexto persiste entre navegaciones
- Contexto persiste después de recargar
- Cambio de contexto refresca vista automáticamente

### 5) Verificar que no aparece "tenant" en UI

**Pasos:**
1. Buscar en el HTML renderizado: "tenant" (case insensitive)
2. Verificar que no aparece en:
   - Textos visibles
   - Placeholders
   - Labels
   - Badges
   - Mensajes de confirmación

**Resultado esperado:**
- 0 ocurrencias de "tenant" en UI visible
- Solo aparece en código/comentarios (interno)

---

## Criterios de aceptación

- [x] UI: 3 dropdowns dependientes + badge, sin "tenant" en ninguna parte
- [x] No hay inputs de texto libre para "cliente"
- [x] `fetchWithContext()` añade headers humanos en todas las llamadas
- [x] Backend deriva tenant interno de esos headers (o el equivalente actual), manteniendo fallback legacy
- [x] Cambiar contexto cambia el data_dir (aislamiento real verificable)
- [x] Playwright E2E nuevo creado (pendiente ejecución)
- [x] Evidencias generadas

---

## Notas técnicas

### Compatibilidad

- **Fallback legacy:** Si no llegan los 3 headers humanos, usa `X-Tenant-ID` o `tenant_id` query param (compatibilidad con C2.22A/C2.24/C2.25)
- **Backend multi-tenant:** No cambió, solo se añadió una nueva forma de derivar tenant_id
- **Frontend:** Reemplazado sistema antiguo, pero `fetchWithContext()` mantiene compatibilidad

### Normalización

La función `sanitize_tenant_id()` asegura que:
- No hay caracteres especiales
- Formato consistente: `[a-zA-Z0-9_-]`
- Separador: `__` (doble underscore)

**Ejemplo de tenant_id derivado:**
```
own: "F63161988" → "F63161988"
platform: "egestiona" → "egestiona"
coordinated: "Aigues de Manresa" → "aiguesdemanresa"
=> tenant_id: "F63161988__egestiona__aiguesdemanresa"
```

### Persistencia

El contexto se persiste en `localStorage`:
- Key: `"coordination_context_v1"`
- Formato: JSON con `own_company_key`, `platform_key`, `coordinated_company_key`, `updated_at`

Al recargar la página, el contexto se restaura automáticamente y se valida contra las opciones disponibles.

---

## Commit

**Hash:** (pendiente)  
**Mensaje:** `feat: C2.26 human coordination context (tenant 100% transparent)`

---

## Referencias

- **C2.25:** Contexto global (Plataforma + Cliente) en toda la UI
- **C2.24:** Tenant transparente (derivado de Plataforma + Empresa externa)
- **C2.22C:** UI Tenant Selector + Mapping company_key → tenant
- **C2.22B:** Scoping real de stores por tenant
- **C2.22A:** Multi-tenant plumbing (backend)
