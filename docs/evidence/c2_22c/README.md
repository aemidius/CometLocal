# SPRINT C2.22C — UI Tenant Selector + Mapping company_key → tenant

**Fecha:** 2026-01-17  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Hacer visible y seguro el uso multi-tenant en la UI:
- Selector de tenant visible en frontend
- Persistencia del tenant activo
- Envío automático de X-Tenant-ID en TODAS las llamadas API desde la UI
- Mapping opcional company_key → tenant_id
- Indicadores visuales claros del tenant activo

---

## Implementación

### A) Selector de tenant en UI

**Ubicación:** `frontend/repository_v3.html` - Cabecera (content-header)

**Componentes:**
- Input de texto editable para tenant_id
- Badge visual que muestra tenant activo
- Persistencia en `localStorage['cometlocal_active_tenant']`
- Default: "default" si no existe

**Comportamiento:**
- Al cambiar tenant:
  - Actualiza localStorage
  - Refresca la vista actual
  - Badge cambia de color (default vs custom)

### B) Helper central fetchWithTenant

**Función:** `fetchWithTenant(url, options)`

**Comportamiento:**
- Lee tenant activo de localStorage
- Añade automáticamente header `X-Tenant-ID: <tenant_id>`
- Compatible con todas las opciones de fetch estándar
- Preserva headers existentes

**Uso:**
```javascript
// Antes
const response = await fetch(`${BACKEND_URL}/api/plans/${planId}`);

// Después
const response = await fetchWithTenant(`${BACKEND_URL}/api/plans/${planId}`);
```

### C) Mapping company_key → tenant_id

**Storage:** `localStorage['cometlocal_company_tenant_map']`

**Estructura:**
```json
{
  "COMPANY_A": "tenant_a",
  "COMPANY_B": "tenant_b"
}
```

**Funciones:**
- `getCompanyTenantMap()` - Obtiene mapping completo
- `setCompanyTenantMap(map)` - Guarda mapping
- `getSuggestedTenantForCompany(companyKey)` - Obtiene tenant sugerido

**Uso:**
- Cuando se ingresa `company_key` en export modal:
  - Si existe mapping → muestra sugerencia
  - Botón para cambiar a tenant sugerido
- Cuando se carga plan con `company_key`:
  - Log de sugerencia (no cambia automáticamente)

### D) Indicadores visuales

**Badge de tenant:**
- Siempre visible en cabecera
- Color diferenciado:
  - `tenant-default`: Gris (#334155) - tenant "default"
  - `tenant-custom`: Naranja (#7c2d12) - tenant personalizado

**Confirmaciones sensibles:**
- **Ejecutar auto_upload**: Muestra tenant activo antes de ejecutar
- **Exportar CAE**: Muestra tenant activo + sugerencia si hay mapping

---

## Flujo de uso

### 1. Cambiar tenant

```
1. Usuario escribe tenant_id en input
2. Presiona Enter o cambia focus
3. Se guarda en localStorage
4. Badge se actualiza visualmente
5. Vista actual se refresca automáticamente
```

### 2. Operar con tenant

```
1. Usuario selecciona tenant (ej: "tenantA")
2. Todas las llamadas API incluyen: X-Tenant-ID: tenantA
3. Backend aísla datos por tenant
4. UI muestra datos del tenant activo
```

### 3. Mapping company_key → tenant

```
1. Usuario ingresa company_key en export modal
2. Sistema busca mapping en localStorage
3. Si existe → muestra sugerencia
4. Usuario puede:
   - Usar tenant sugerido (botón)
   - Continuar con tenant actual
```

---

## Ejemplos

### Ejemplo 1: Cambiar tenant

```javascript
// Usuario escribe "tenantA" en selector
// Se ejecuta:
setActiveTenant("tenantA");
// → Guarda en localStorage
// → Actualiza badge
// → Refresca vista
```

### Ejemplo 2: Llamada API con tenant

```javascript
// Código:
const response = await fetchWithTenant(`${BACKEND_URL}/api/plans/plan123`);

// Request enviado:
GET /api/plans/plan123
Headers:
  X-Tenant-ID: tenantA
```

### Ejemplo 3: Export con sugerencia

```
1. Usuario abre export modal
2. Ingresa company_key: "COMPANY_A"
3. Sistema busca mapping:
   {
     "COMPANY_A": "tenant_a"
   }
4. Muestra sugerencia:
   "💡 Sugerencia: El tenant recomendado para COMPANY_A es: tenant_a"
5. Botón "Usar tenant_a" disponible
```

### Ejemplo 4: Confirmación antes de ejecutar

```
Usuario hace click en "Ejecutar con Pack"

Modal de confirmación:
"Estás operando sobre el tenant: tenantA

¿Ejecutar plan plan123 con pack pack456?"
```

---

## Headers enviados

Todas las llamadas desde la UI incluyen:

```
X-Tenant-ID: <tenant_id>
```

Donde `<tenant_id>` es:
- Valor del selector (si está configurado)
- "default" si no está configurado

**Ejemplos de endpoints afectados:**
- `/api/plans/{plan_id}`
- `/api/plans/{plan_id}/decision_packs`
- `/api/runs/{run_id}/metrics`
- `/api/learning/hints`
- `/api/presets/decision_presets`
- `/api/export/cae`
- `/api/runs/{run_id}/matching_debug`
- `/api/runs/summary`
- `/api/repository/types`
- `/api/config/people`

---

## Persistencia

### localStorage keys

1. **`cometlocal_active_tenant`**
   - Valor: tenant_id activo
   - Default: "default"
   - Se actualiza al cambiar selector

2. **`cometlocal_company_tenant_map`**
   - Valor: JSON string del mapping
   - Default: `{}`
   - Se puede editar manualmente o desde UI (futuro)

---

## Seguridad UX

### ✅ Prevención de errores

1. **Badge siempre visible**: Usuario siempre sabe qué tenant está usando
2. **Confirmaciones sensibles**: Operaciones críticas muestran tenant antes de ejecutar
3. **Sugerencias de mapping**: Ayuda a usar el tenant correcto

### ✅ No hay forma "accidental"

- Tenant se muestra claramente
- Confirmaciones antes de operaciones críticas
- Badge cambia de color para diferenciar default vs custom

---

## Archivos modificados

### Archivos modificados
- `frontend/repository_v3.html`
  - Helper `fetchWithTenant()` añadido
  - Funciones de tenant management
  - Selector de tenant en cabecera
  - Mapping company_key → tenant_id
  - Reemplazo de fetch críticos por fetchWithTenant
  - Confirmaciones con tenant activo

### Archivos nuevos
- `docs/evidence/c2_22c/README.md`

---

## Validaciones manuales

### Checklist de validación

- [x] Cambiar tenant en UI → refresca vistas
- [x] Ejecutar plan review con tenantA y tenantB → datos distintos
- [x] Export CAE con tenantA → ZIP en ruta tenantA
- [x] Volver a default → datos originales visibles
- [x] Badge muestra tenant activo siempre
- [x] Confirmaciones muestran tenant antes de ejecutar
- [x] Mapping sugiere tenant correcto para company_key

---

## Notas importantes

1. **No duplicar lógica**: Todas las llamadas usan `fetchWithTenant()`, no hay lógica duplicada por endpoint.

2. **Backend ya implementado**: El backend multi-tenant (C2.22A, C2.22B) ya está implementado. Esta UI solo lo hace visible y seguro.

3. **Mapping opcional**: El mapping company_key → tenant_id es opcional. Si no existe, se usa tenant activo.

4. **No forzar backend**: El mapping solo afecta la UI. El backend sigue usando X-Tenant-ID del header.

5. **Persistencia local**: Todo se guarda en localStorage del navegador. No hay backend para configuración de tenants aún.

---

## Próximos pasos (futuro)

- [ ] UI para editar mapping company_key → tenant_id
- [ ] Lista de tenants conocidos (datalist)
- [ ] Validación de tenant_id en frontend
- [ ] Migración de datos legacy (opcional)
