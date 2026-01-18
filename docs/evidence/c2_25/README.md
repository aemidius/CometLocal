# SPRINT C2.25 — Contexto global (Plataforma + Cliente) en toda la UI

**Fecha:** 2026-01-17  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Hacer que el "Contexto de coordinación" (Plataforma + Cliente) sea GLOBAL en toda la app:
- Visible siempre en el header
- Persistente (localStorage)
- Todas las llamadas API en TODO el frontend usan `fetchWithContext()`
- El usuario opera "dentro" de un cliente de forma consistente

**NO tocar backend.**  
**SÍ modificar frontend/repository_v3.html.**

---

## Implementación

### A) Auditoría y centralización del fetch

**Cambio principal:**
- Reemplazados **TODOS** los usos de `fetch()` directo por `fetchWithContext()`
- Ninguna llamada a `/api/*` usa `fetch()` directo
- Helper único: `fetchWithContext(url, options)`
  - Añade `X-Tenant-ID` derivado automáticamente
  - Mantiene headers previos
  - Compatible con todas las opciones de fetch estándar

**Scope:** TODO el archivo `repository_v3.html`

**Criterio cumplido:**
- ✅ Ninguna llamada a `/api/*` usa `fetch()` directo
- ✅ Todas usan `fetchWithContext()` o `fetchWithTenant()` (alias)

### B) Contexto global en header (todas las vistas)

**Ubicación:** Header de la aplicación (`content-header`)

**Componentes siempre visibles:**
1. **Selector de Plataforma:**
   - Dropdown con plataformas cargadas desde `/api/config/platforms`
   - `data-testid="context-platform-select"`

2. **Selector de Cliente externo:**
   - Input text libre (permite entrada manual)
   - Placeholder: "Ej: COMPANY_A"
   - `data-testid="context-client-select"`

3. **Badge de contexto:**
   - Muestra: "Plataforma | Cliente" cuando hay contexto
   - Muestra: "default" cuando no hay contexto
   - `data-testid="context-badge"`

**Comportamiento:**
- Al cambiar contexto:
  - Guarda en `localStorage`
  - Refresca la vista actual de forma segura
  - Re-ejecuta `loadPage()` sin romper el router hash
  - Limpia caches UI que dependen del tenant:
    - `planReviewState.debugCache = {}`
    - `planReviewState.presetsCache = null`

### C) Integración con Configuración existente

**Plataformas:**
- Cargadas desde `/api/config/platforms` (configuración existente)
- Si no hay datos: fallback a `[{ key: 'egestiona', label: 'eGestiona' }]`

**Clientes externos:**
- Por ahora: entrada manual (input text)
- Permite introducción manual marcada como "(manual)"
- Se guarda igual en `localStorage`
- En el futuro: se puede cargar desde configuración asociada a la plataforma

**Sin bloqueo:**
- Si no hay datos disponibles, permite entrada manual
- No bloquea la operación si la config no está completa

### D) UX de seguridad

**Operaciones críticas con confirmación:**

1. **Ejecutar auto_upload:**
   - Muestra confirm modal con:
     - Plataforma
     - Cliente
     - Tenant derivado
   - Si no hay contexto: muestra "default - sin contexto"

2. **Exportar CAE:**
   - Muestra confirm modal con contexto (ya implementado en C2.24)
   - Incluye Plataforma, Cliente, Tenant derivado

3. **Subir documento:**
   - Si hay contexto activo, muestra confirmación antes de subir
   - Permite cancelar por archivo

**Aviso sin contexto:**
- Si el usuario intenta operar sin contexto (default):
  - Permite operar
  - Muestra aviso: "Sin contexto seleccionado: operando en default"

### E) Data-testid (para futuro E2E)

**Testids añadidos en header:**
- `context-platform-select` - Selector de plataforma
- `context-client-select` - Input de cliente externo
- `context-badge` - Badge que muestra contexto activo
- `context-debug-toggle` - Toggle para modo debug
- `context-tenant-override` - Input de tenant override (modo debug)

---

## Vistas afectadas

**Todas las vistas** ahora usan `fetchWithContext()`:

1. **Inicio** - Carga tipos, docs, rules, platforms
2. **Calendario** - Carga docs, tipos, subjects
3. **Subir documentos** - Upload de docs
4. **Buscar documentos** - Búsqueda de docs
5. **Plataformas** - Configuración de plataformas
6. **Catálogo** - Gestión de tipos de documentos
7. **Configuración** - Settings del repositorio
8. **Plan Review** - Revisión de planes CAE
9. **Coordinación** - Coordinación CAE
10. **Actividad** - Actividad del sistema

**Todas las llamadas API** ahora incluyen `X-Tenant-ID` automáticamente.

---

## Cambios técnicos

### Funciones modificadas

1. **`fetchWithContext()`** - Helper central (ya existía, ahora usado en todas partes)
2. **`setCoordinationContext()`** - Mejorado para limpiar caches y refrescar vista
3. **`handleExecutePlan()`** - Añadida confirmación con contexto
4. **`handleExportCAE()`** - Ya tenía confirmación (C2.24)
5. **Upload de documentos** - Añadida confirmación si hay contexto

### Reemplazos realizados

**Total:** ~50+ llamadas `fetch()` reemplazadas por `fetchWithContext()`

**Categorías:**
- `/api/repository/*` - ~30 llamadas
- `/api/config/*` - ~10 llamadas
- `/api/cae/*` - ~10 llamadas
- `/api/runs/*` - ~5 llamadas
- `/api/export/*` - ~2 llamadas
- `/api/learning/*` - ~2 llamadas
- `/api/presets/*` - ~3 llamadas

---

## Validación manual

### 1) Arrancar server y abrir cualquier vista

**Pasos:**
1. Arrancar server: `python -m uvicorn backend.app:app --port 8000`
2. Abrir: `http://127.0.0.1:8000/repository_v3.html#inicio`
3. Verificar que el contexto está visible en el header
4. Navegar a "Buscar documentos"
5. Verificar que el contexto sigue visible

**Resultado esperado:**
- Contexto visible en todas las vistas
- Badge muestra "default" si no hay contexto

### 2) Cambiar contexto y comprobar persistencia

**Pasos:**
1. Seleccionar Plataforma: "egestiona"
2. Ingresar Cliente: "COMPANY_A"
3. Verificar badge muestra "egestiona | COMPANY_A"
4. Navegar entre vistas (Inicio → Buscar → Calendario)
5. Verificar que el contexto se mantiene
6. Recargar página (F5)
7. Verificar que el contexto se restaura desde localStorage

**Resultado esperado:**
- Contexto persiste entre navegaciones
- Contexto persiste después de recargar
- Badge muestra contexto correcto

### 3) Abrir Plan Review y verificar contexto

**Pasos:**
1. Navegar a Plan Review
2. Verificar que muestra contexto activo (o aviso si no hay)
3. Cargar un plan
4. Abrir Presets panel
5. Verificar que presets se cargan con tenant correcto
6. Abrir Learning panel
7. Verificar que hints se cargan con tenant correcto
8. Exportar CAE
9. Verificar confirmación muestra contexto

**Resultado esperado:**
- Contexto visible en Plan Review
- Presets/hints/export operan bajo contexto correcto
- Confirmaciones muestran contexto

### 4) Volver a default y verificar aviso

**Pasos:**
1. Limpiar selección de Plataforma y Cliente
2. Verificar badge muestra "default"
3. Intentar exportar CAE
4. Verificar aviso "Sin contexto seleccionado: operando en default"
5. Confirmar y verificar que funciona

**Resultado esperado:**
- Badge muestra "default"
- Aviso aparece en operaciones críticas
- Operaciones funcionan con tenant "default"

### 5) Verificar que no quedan fetch directos

**Pasos:**
1. Buscar en código: `fetch(\`${BACKEND_URL}/api/`
2. Verificar que no hay resultados (o solo en comentarios)

**Resultado esperado:**
- No hay `fetch()` directos a `/api/*`
- Todas usan `fetchWithContext()` o `fetchWithTenant()`

---

## Criterios de validación

- [x] Contexto visible siempre en header
- [x] Contexto persiste entre navegaciones
- [x] Contexto persiste después de recargar
- [x] Todas las llamadas API usan `fetchWithContext()`
- [x] No quedan `fetch()` directos a `/api/*`
- [x] Operaciones críticas muestran confirmación con contexto
- [x] Aviso cuando no hay contexto (default)
- [x] Data-testid añadidos en header
- [x] Caches UI se limpian al cambiar contexto
- [x] Vista se refresca al cambiar contexto sin romper router

---

## Notas técnicas

### Regla: "No usar fetch directo"

**Regla establecida:**
- ❌ NO: `fetch(\`${BACKEND_URL}/api/...\`)`
- ✅ SÍ: `fetchWithContext(\`${BACKEND_URL}/api/...\`)`

**Razón:**
- Asegura que todas las llamadas incluyen `X-Tenant-ID`
- Mantiene consistencia en toda la aplicación
- Facilita debugging y mantenimiento

### Compatibilidad

- `fetchWithTenant()` sigue funcionando (alias de `fetchWithContext()`)
- Código legacy que usa `fetchWithTenant()` no necesita cambios
- Backend multi-tenant no cambió (solo frontend)

### Performance

- Limpieza de caches al cambiar contexto evita datos obsoletos
- Refresco de vista es seguro (no rompe router hash)
- Persistencia en localStorage es instantánea

---

## Commit

**Hash:** (pendiente)  
**Mensaje:** `feat: C2.25 global coordination context across UI`

---

## Referencias

- **C2.24:** Tenant transparente (derivado de Plataforma + Empresa externa)
- **C2.22C:** UI Tenant Selector + Mapping company_key → tenant
- **C2.22B:** Scoping real de stores por tenant
- **C2.22A:** Multi-tenant plumbing (backend)
