# E2E Report: Repositorio Documental - Series Temporales (Period-Based Documents) - v1

## Objetivo

Validar que el sistema de series temporales funciona correctamente:
- Los documentos periódicos tienen `period_key` asignado
- El matching en eGestiona usa `period_key` para selección determinista
- Los errores son explícitos cuando falta un documento para un período

## Cambios Implementados

### 1. Modelo de Datos Extendido

- `DocumentInstanceV1` ahora incluye:
  - `period_kind: PeriodKindV1` (NONE, MONTH, YEAR, QUARTER)
  - `period_key: Optional[str]` (YYYY-MM, YYYY, YYYY-Qn)
  - `issued_at: Optional[date]`
  - `needs_period: bool`

### 2. Servicio de Planificación

- `PeriodPlannerV1`: Genera períodos esperados y calcula estado (AVAILABLE/MISSING/LATE)
- `PeriodMigrationV1`: Migra documentos existentes añadiendo `period_key`

### 3. Endpoints Nuevos

- `GET /api/repository/types/{type_id}/expected`: Lista períodos esperados
- `GET /api/repository/docs/best?period=YYYY-MM`: Busca documento por período exacto

### 4. Matching Mejorado

- Detecta período del pending (ej: "Mayo 2023" → `2023-05`)
- Busca documento con `period_key` exacto
- Error explícito: `"Missing document for period {period_key}"` en lugar de `NO_MATCH` genérico

## Pruebas Ejecutadas

### A) Migración de Documentos Existentes

**Comando**:
```bash
python scripts/migrate_period_keys.py
```

**Resultado**:
- Total documentos: 2
- Migrados: 2 (ya tenían period_key asignado)
- Errores: 0

**Conclusión**: ✅ La migración funciona correctamente. Los documentos existentes ya tienen `period_key` asignado automáticamente al subirlos.

### B) Verificación de Tipo T104_AUTONOMOS_RECEIPT

**Comando**:
```python
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.period_planner_v1 import PeriodPlannerV1

store = DocumentRepositoryStoreV1()
planner = PeriodPlannerV1(store)
doc_type = store.get_type('T104_AUTONOMOS_RECEIPT')
period_kind = planner.get_period_kind_from_type(doc_type)
```

**Resultado**:
- Tipo encontrado: `T104_AUTONOMOS_RECEIPT`
- Period kind: `MONTH`

**Conclusión**: ✅ El tipo está correctamente configurado como mensual.

### C) Pruebas de Matching con eGestiona

**Estado**: Pendiente de ejecución real con Aigues de Manresa

**Próximos pasos**:
1. Ejecutar flujo READ-ONLY con cliente "Aigues de Manresa"
2. Verificar que el pending "T205.0 Último Recibo bancario pago cuota autónomos … (Mayo 2023)":
   - Detecta `pending_period_key="2023-05"`
   - Busca documento con `type_id="T104_AUTONOMOS_RECEIPT"`, `person_key="Emilio"`, `period_key="2023-05"`
   - Si existe: devuelve MATCH determinista
   - Si no existe: devuelve `"Missing document for period 2023-05"` (no `NO_MATCH` genérico)

## Archivos Modificados

1. `backend/shared/document_repository_v1.py`: Modelo extendido con `period_kind`, `period_key`, etc.
2. `backend/repository/period_planner_v1.py`: Servicio de planificación de períodos
3. `backend/repository/period_migration_v1.py`: Migración de documentos existentes
4. `backend/repository/document_repository_routes.py`: Endpoints nuevos + inferencia automática en upload
5. `backend/repository/document_repository_store_v1.py`: Soporte para filtrar por `period_key`
6. `backend/repository/document_matcher_v1.py`: Matching mejorado con `period_key`
7. `scripts/migrate_period_keys.py`: Script de migración

## Documentación

- `docs/REPO_TIME_SERIES_DESIGN.md`: Diseño completo del sistema de series temporales

## Próximos Pasos

1. **Pruebas E2E con eGestiona**: Ejecutar flujo READ-ONLY y verificar matching determinista
2. **UI de Cobertura**: Implementar vista para mostrar períodos cubiertos/faltantes
3. **Selector de Período**: Añadir dropdown en upload cuando no se puede inferir `period_key`

## Commit

```
repo: add period-based document instances and deterministic matching
```























