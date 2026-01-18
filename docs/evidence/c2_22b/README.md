# SPRINT C2.22B — Tenant-scoped Learning, Presets and Exports

**Fecha:** 2026-01-17  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo

Aislar completamente por tenant:
- **LearningStore**: Hints de aprendizaje por tenant
- **DecisionPresetStore**: Presets de decisiones por tenant
- **Exports**: ZIPs de exportación por tenant

Manteniendo:
- Fallback legacy SOLO lectura
- Escritura SIEMPRE en tenant
- Sin migración automática
- plan_id INMUTABLE

---

## Implementación

### A) LearningStore por tenant

**Archivos modificados:**
- `backend/shared/learning_store.py`
- `backend/api/learning_routes.py`
- `backend/shared/learning_hints_generator.py` (pendiente tenant_id)

**Estructura:**
- **Escritura**: `data/tenants/<tenant_id>/learning/hints_v1.jsonl`
- **Lectura**: 
  - Prefiere `data/tenants/<tenant_id>/learning/`
  - Fallback a `data/learning/` (legacy) si tenant no existe

**Comportamiento:**
- Si tenant tiene carpeta `learning/` creada, legacy NO se consulta
- Legacy solo sirve para tenants sin carpeta creada
- NO mezcla hints entre tenants

### B) DecisionPresetStore por tenant

**Archivos modificados:**
- `backend/shared/decision_preset_store.py`
- `backend/api/preset_routes.py`

**Estructura:**
- **Escritura**: `data/tenants/<tenant_id>/presets/decision_presets_v1.json`
- **Lectura**:
  - Prefiere `data/tenants/<tenant_id>/presets/`
  - Fallback a `data/presets/` (legacy) si tenant no existe

**Comportamiento:**
- Escritura SIEMPRE en tenant
- Lectura: tenant con fallback legacy
- `preset_id` sigue siendo hash estable del contenido (sin tenant en el hash)

### C) Exports por tenant

**Archivos modificados:**
- `backend/api/export_routes.py`
- `backend/export/cae_exporter.py` (usa output_dir pasado)

**Estructura:**
- **Escritura**: `data/tenants/<tenant_id>/exports/`
- **Store**: `_exports_store` ahora es `dict[tenant_id, dict[export_id, Path]]`

**Comportamiento:**
- ZIPs se guardan en exports del tenant
- `export_id` puede seguir siendo global, pero la ruta física es por tenant
- Descarga solo accede a exports del tenant del request
- NO permite descargar exports de otro tenant

---

## Estructura de directorios

### Nueva estructura (tenant)
```
data/
  tenants/
    default/
      learning/
        hints_v1.jsonl
        index_v1.json
        tombstones_v1.json
      presets/
        decision_presets_v1.json
      exports/
        export_abc123.zip
    tenantA/
      learning/
        hints_v1.jsonl
        ...
      presets/
        decision_presets_v1.json
      exports/
        export_def456.zip
```

### Estructura legacy (fallback)
```
data/
  learning/
    hints_v1.jsonl
    ...
  presets/
    decision_presets_v1.json
  exports/
    export_xyz789.zip
```

**Comportamiento:**
- **Lectura**: Busca primero en tenant path, si no existe usa legacy
- **Escritura**: Siempre en tenant path

---

## Uso

### 1. Learning Store

```bash
# Listar hints con tenantA
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/learning/hints

# Desactivar hint con tenantA
curl -X POST \
     -H "X-Tenant-ID: tenantA" \
     -H "Content-Type: application/json" \
     http://127.0.0.1:8000/api/learning/hints/hint_abc123/disable \
     -d '{"reason": "Incorrecto"}'
```

**Resultado:**
- Hints guardados en `data/tenants/tenantA/learning/`
- Aislamiento completo entre tenants
- Fallback legacy si tenant no tiene carpeta creada

### 2. Decision Presets

```bash
# Listar presets con tenantA
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/presets/decision_presets

# Crear preset con tenantA
curl -X POST \
     -H "X-Tenant-ID: tenantA" \
     -H "Content-Type: application/json" \
     http://127.0.0.1:8000/api/presets/decision_presets \
     -d '{
       "name": "Skip T104",
       "scope": {
         "platform": "egestiona",
         "type_id": "T104_AUTONOMOS_RECEIPT"
       },
       "action": "SKIP",
       "defaults": {
         "reason": "No disponible"
       }
     }'
```

**Resultado:**
- Presets guardados en `data/tenants/tenantA/presets/`
- Aislamiento completo entre tenants
- Fallback legacy si tenant no tiene carpeta creada
- `preset_id` es hash del contenido (mismo contenido = mismo ID, sin importar tenant)

### 3. Exports

```bash
# Crear export con tenantA
curl -X POST \
     -H "X-Tenant-ID: tenantA" \
     -H "Content-Type: application/json" \
     http://127.0.0.1:8000/api/export/cae \
     -d '{
       "company_key": "COMPANY123",
       "period": "2025"
     }'
```

**Resultado:**
- ZIP guardado en `data/tenants/tenantA/exports/`
- `export_id` generado normalmente
- Descarga solo accesible con mismo tenant

```bash
# Descargar export (solo funciona con mismo tenant)
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/export/cae/download/export_abc123
```

---

## Ejemplos

### Ejemplo 1: Aislamiento de Learning

```bash
# Crear hint en tenantA
curl -X POST \
     -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/plans/plan123/decision_packs \
     -d '{"decisions": [...]}'
# → Hint guardado en data/tenants/tenantA/learning/

# Listar hints en tenantA
curl -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/learning/hints
# → Solo hints de tenantA

# Listar hints en tenantB
curl -H "X-Tenant-ID: tenantB" \
     http://127.0.0.1:8000/api/learning/hints
# → Solo hints de tenantB (o legacy si no tiene carpeta)
```

### Ejemplo 2: Fallback Legacy

```bash
# Legacy tiene hints en data/learning/
# tenantC no tiene carpeta learning/ creada

# Listar hints en tenantC
curl -H "X-Tenant-ID: tenantC" \
     http://127.0.0.1:8000/api/learning/hints
# → Lee desde data/learning/ (fallback legacy)

# Crear hint en tenantC
curl -X POST \
     -H "X-Tenant-ID: tenantC" \
     http://127.0.0.1:8000/api/plans/plan456/decision_packs \
     -d '{"decisions": [...]}'
# → Crea data/tenants/tenantC/learning/ y guarda ahí
# → A partir de ahora, solo lee de tenant path (no legacy)
```

### Ejemplo 3: Preset ID estable

```bash
# Mismo preset en diferentes tenants
# tenantA
curl -X POST \
     -H "X-Tenant-ID: tenantA" \
     http://127.0.0.1:8000/api/presets/decision_presets \
     -d '{"name": "Skip T104", "scope": {...}, "action": "SKIP"}'
# → preset_id: "preset_abc123..."

# tenantB (mismo contenido)
curl -X POST \
     -H "X-Tenant-ID: tenantB" \
     http://127.0.0.1:8000/api/presets/decision_presets \
     -d '{"name": "Skip T104", "scope": {...}, "action": "SKIP"}'
# → preset_id: "preset_abc123..." (mismo hash)
```

---

## Características

### ✅ Aislamiento completo
- Learning NO cruza tenants
- Presets NO cruzan tenants
- Exports NO cruzan tenants

### ✅ Fallback legacy
- Legacy solo lectura
- Si tenant tiene carpeta creada, legacy NO se consulta
- Legacy solo sirve para tenants sin carpeta creada

### ✅ Escritura siempre en tenant
- Todas las escrituras van a tenant path
- Se crea directorio automáticamente al escribir

### ✅ Sin migración automática
- No se copian datos de legacy a tenant
- Legacy se lee directamente si tenant no existe

### ✅ IDs inmutables
- `preset_id`: Hash del contenido (no incluye tenant)
- `export_id`: Generado normalmente (puede ser global)
- `hint_id`: Hash del contenido (no incluye tenant)

---

## Tests

Ejecutar tests:
```bash
python -m pytest tests/test_learning_store_tenant.py \
                 tests/test_decision_preset_store_tenant.py \
                 tests/test_export_tenant.py -v
```

**Resultado esperado:**
```
12 passed in 0.65s
```

**Tests incluidos:**
- `test_learning_store_tenant.py`: 4 tests
  - Escritura crea carpeta tenant
  - Lectura usa tenant si existe
  - Fallback legacy si tenant no existe
  - No mezcla datos entre tenants

- `test_decision_preset_store_tenant.py`: 5 tests
  - Presets aislados por tenant
  - Fallback legacy correcto
  - Hash estable no cambia

- `test_export_tenant.py`: 3 tests
  - Export crea ZIP en ruta tenant
  - No cruza exports entre tenants
  - Descarga solo accede a exports del tenant

---

## Archivos modificados

### Archivos nuevos
- `tests/test_learning_store_tenant.py`
- `tests/test_decision_preset_store_tenant.py`
- `tests/test_export_tenant.py`
- `docs/evidence/c2_22b/README.md`

### Archivos modificados
- `backend/shared/learning_store.py`
- `backend/shared/decision_preset_store.py`
- `backend/api/learning_routes.py`
- `backend/api/preset_routes.py`
- `backend/api/export_routes.py`
- `backend/shared/tenant_paths.py` (mejora en resolve_read_path)

---

## Notas importantes

1. **Lectura dinámica**: Los stores recalculan el path de lectura dinámicamente. Si el directorio tenant existe, se usa tenant; si no, se usa legacy.

2. **Escritura crea directorio**: Al escribir, se crea automáticamente el directorio tenant si no existe. A partir de ese momento, solo se lee de tenant (no legacy).

3. **Preset ID estable**: El `preset_id` es un hash del contenido del preset, no incluye tenant. Mismo contenido = mismo ID en cualquier tenant.

4. **Export ID**: Puede seguir siendo global, pero la ruta física y el acceso están aislados por tenant.

5. **Sin migración**: No se migran datos automáticamente de legacy a tenant. Legacy se lee directamente si el tenant no tiene carpeta creada.

---

## Próximos pasos (futuro)

- [ ] Pasar tenant_id en `learning_hints_generator.py`
- [ ] Pasar tenant_id en `document_matcher_v1.py`
- [ ] Migración opcional de datos legacy a tenants (script manual)
