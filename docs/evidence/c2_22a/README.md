# SPRINT C2.22A — Multi-tenant plumbing

**Fecha:** 2026-01-17  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Implementar soporte multi-tenant mínimo y retrocompatible:
- Aislamiento de datos por tenant
- Fallback automático a estructura legacy
- Compatibilidad total con código existente
- plan_id inmutable (no cambia con tenant)

---

## Implementación

### A) Módulos comunes

#### 1. `backend/shared/tenant_context.py`
- **TenantContext**: Dataclass con `tenant_id` y `source` (header/query/default)
- **get_tenant_from_request()**: Extrae tenant_id desde:
  1. Header `X-Tenant-ID` (prioridad)
  2. Query param `tenant_id`
  3. Default `"default"`
- **sanitize_tenant_id()**: Sanitiza a `[a-zA-Z0-9_-]`

#### 2. `backend/shared/tenant_paths.py`
Funciones para resolver paths multi-tenant:
- `tenants_root()`, `tenant_root()`, `tenant_runs_root()`, etc.
- `resolve_read_path()`: Prefiere tenant, fallback legacy
- `ensure_write_dir()`: Crea directorio si no existe
- `get_runs_root()`: Helper central con modo read/write

### B) Integración en rutas

Modificados para usar tenant paths:
- `backend/api/runs_summary_routes.py`
- `backend/api/auto_upload_routes.py`
- `backend/api/decision_pack_routes.py`
- `backend/api/metrics_routes.py`
- `backend/api/matching_debug_routes.py`
- `backend/shared/run_summary.py`
- `backend/shared/run_metrics.py`
- `backend/shared/evidence_helper.py`
- `backend/adapters/egestiona/execute_auto_upload_gate.py`

### C) Tests unitarios

- `tests/test_tenant_context.py`: 7 tests (todos PASS)
- `tests/test_tenant_paths.py`: 15 tests (todos PASS)

---

## Estructura de directorios

### Nueva estructura (tenant)
```
data/
  tenants/
    default/
      runs/
        plan_abc123/
          plan_response.json
          metrics.json
          ...
    tenantA/
      runs/
        plan_def456/
          plan_response.json
          ...
```

### Estructura legacy (fallback)
```
data/
  runs/
    plan_xyz789/
      plan_response.json
      ...
```

**Comportamiento:**
- **Lectura**: Busca primero en `data/tenants/<tenant>/runs/`, si no existe usa `data/runs/`
- **Escritura**: Siempre en `data/tenants/<tenant>/runs/`

---

## Uso

### 1. Sin tenant explícito (default)

```bash
# Sin header ni query → usa "default"
curl http://127.0.0.1:8000/api/runs/summary
```

**Resultado:**
- Lee/escribe en `data/tenants/default/runs/`
- Si no existe, lee desde `data/runs/` (fallback legacy)

### 2. Con header X-Tenant-ID

```bash
# Con header → usa tenant explícito
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/runs/summary
```

**Resultado:**
- Lee/escribe en `data/tenants/tenantA/runs/`
- Aislamiento completo de datos

### 3. Con query param tenant_id

```bash
# Con query param → usa tenant explícito
curl "http://127.0.0.1:8000/api/runs/summary?tenant_id=tenantB"
```

**Resultado:**
- Lee/escribe en `data/tenants/tenantB/runs/`
- Aislamiento completo de datos

### 4. Fallback legacy

```bash
# Plan existente solo en legacy
curl -H "X-Tenant-ID: legacytest" \
     http://127.0.0.1:8000/api/plans/plan_xyz789
```

**Resultado:**
- Busca en `data/tenants/legacytest/runs/plan_xyz789/` (no existe)
- Fallback a `data/runs/plan_xyz789/` (existe)
- Retorna plan correctamente
- **No se copia** automáticamente al tenant

---

## Ejemplos

### Ejemplo 1: Crear plan con tenant

```bash
# Crear plan con tenantA
curl -X POST \
     -H "X-Tenant-ID: tenantA" \
     -H "Content-Type: application/json" \
     http://127.0.0.1:8000/runs/auto_upload/plan \
     -d '{
       "company_key": "COMPANY123",
       "person_key": "PERSON123"
     }'
```

**Resultado:**
- Plan guardado en `data/tenants/tenantA/runs/plan_abc123/`
- plan_id generado normalmente (no incluye tenant)

### Ejemplo 2: Consultar plan con tenant

```bash
# Consultar plan con tenantA
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/plans/plan_abc123
```

**Resultado:**
- Busca en `data/tenants/tenantA/runs/plan_abc123/`
- Si no existe, fallback a `data/runs/plan_abc123/`

### Ejemplo 3: Aislamiento entre tenants

```bash
# Plan en tenantA
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/plans/plan_abc123
# ✅ Encuentra plan

# Mismo plan_id en tenantB
curl -H "X-Tenant-ID: tenantB" \
     http://127.0.0.1:8000/api/plans/plan_abc123
# ❌ No encuentra (aislamiento)
```

---

## Características

### ✅ Retrocompatibilidad
- Código existente sin tenant → funciona igual (usa "default")
- Planes legacy → se leen correctamente (fallback)
- plan_id → inmutable (no cambia con tenant)

### ✅ Aislamiento
- Datos por tenant → completamente aislados
- Escrituras → siempre en tenant path
- Lecturas → tenant con fallback legacy

### ✅ Sanitización
- tenant_id → sanitizado a `[a-zA-Z0-9_-]`
- Caracteres especiales → reemplazados por `_`
- Vacío → default a `"default"`

---

## Archivos modificados

### Nuevos archivos
- `backend/shared/tenant_context.py`
- `backend/shared/tenant_paths.py`
- `tests/test_tenant_context.py`
- `tests/test_tenant_paths.py`
- `docs/evidence/c2_22a/README.md`

### Archivos modificados
- `backend/shared/evidence_helper.py`
- `backend/shared/run_summary.py`
- `backend/shared/run_metrics.py`
- `backend/api/runs_summary_routes.py`
- `backend/api/auto_upload_routes.py`
- `backend/api/decision_pack_routes.py`
- `backend/api/metrics_routes.py`
- `backend/api/matching_debug_routes.py`
- `backend/adapters/egestiona/execute_auto_upload_gate.py`

---

## Tests

Ejecutar tests:
```bash
python -m pytest tests/test_tenant_context.py tests/test_tenant_paths.py -v
```

**Resultado esperado:**
```
22 passed in 1.17s
```

---

## Notas importantes

1. **plan_id inmutable**: El plan_id no incluye tenant, es global. El aislamiento se logra por path, no por ID.

2. **Fallback legacy**: Los planes legacy se leen automáticamente si no existen en tenant path. No se copian automáticamente.

3. **Escrituras**: Siempre van a tenant path. No se escriben en legacy.

4. **Default tenant**: Si no se especifica tenant, se usa `"default"`. Esto mantiene compatibilidad con código existente.

5. **Sanitización**: Los tenant_id se sanitizan automáticamente para evitar problemas de paths.

---

## Próximos pasos (futuro)

- [ ] Scoping de LearningStore por tenant
- [ ] Scoping de DecisionPresetStore por tenant
- [ ] Scoping de exports por tenant
- [ ] Migración de datos legacy a tenants (opcional)
