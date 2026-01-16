# Repositorio Documental: Soporte de Series Temporales (Period-Based Documents)

## Objetivo

Rediseñar el Repositorio Documental para soportar documentos periódicos (mensuales/anuales/etc.) como series temporales, permitiendo que el agente seleccione determinísticamente el documento del período exacto sin heurísticas.

## Problema Original

La falta de estructura temporal causaba `NO_MATCH` en eGestiona para documentos como "cuota autónomos" porque el agente no podía seleccionar determinísticamente el documento del período exacto (ej: "Mayo 2023").

## Cambios Implementados

### 1. Extensión del Modelo de Documento

Se añadieron los siguientes campos a `DocumentInstanceV1`:

- `period_kind: PeriodKindV1`: Tipo de período (`NONE`, `MONTH`, `YEAR`, `QUARTER`)
  - Se deriva automáticamente del `validity_policy.mode` del tipo de documento
- `period_key: Optional[str]`: Clave del período
  - `MONTH` => `YYYY-MM` (ej: "2023-05")
  - `YEAR` => `YYYY` (ej: "2023")
  - `QUARTER` => `YYYY-Qn` (ej: "2023-Q2")
- `issued_at: Optional[date]`: Fecha de emisión del documento
- `needs_period: bool`: Si el documento necesita que se le asigne un `period_key` (migración pendiente)

### 2. Servicio de Planificación de Períodos

Se creó `PeriodPlannerV1` (`backend/repository/period_planner_v1.py`) que:

- **Genera períodos esperados**: Dado un tipo de documento y un sujeto (persona/empresa), genera una lista de períodos esperados (ej: últimos 24 meses)
- **Calcula estado**: Para cada período, determina si está `AVAILABLE`, `MISSING`, o `LATE` (con días de gracia)
- **Infiere period_key**: A partir de metadatos disponibles (`issue_date`, `name_date`, `filename`)

### 3. Endpoints Nuevos

- `GET /api/repository/types/{type_id}/expected?company_key=...&person_key=...&months=24`
  - Devuelve lista de períodos esperados con estado (AVAILABLE/MISSING/LATE)
  
- `GET /api/repository/docs/best?type_id=...&company_key=...&person_key=...&period=YYYY-MM`
  - Devuelve 1 documento exacto para el período especificado o 404 (no "best guess")

### 4. Migración/Backfill

Se creó `PeriodMigrationV1` (`backend/repository/period_migration_v1.py`) para:

- Migrar documentos existentes: Infiere y asigna `period_key` basándose en metadatos disponibles
- Marcar documentos que no se pueden migrar: Si no se puede inferir, marca `needs_period=True`

**Script de migración**: `scripts/migrate_period_keys.py`

```bash
python scripts/migrate_period_keys.py [--dry-run]
```

### 5. Integración con eGestiona Matching

El matching ahora:

1. **Detecta período del pending**: Si el texto del pending contiene mes/año (ej: "Mayo 2023"), lo convierte a `period_key` (`2023-05`)

2. **Busca por período exacto**: Si hay `period_key`, busca documentos con ese período exacto

3. **Error explícito**: Si no encuentra documento para el período, devuelve `"Missing document for period {period_key}"` en lugar de `NO_MATCH` genérico

4. **Fallback sin empresa**: Para documentos `scope=worker`, si no encuentra con `company_key`, intenta sin `company_key` (útil para recibos de autónomos)

### 6. Upload Automático

Al subir un documento:

- Si el tipo es periódico, se infiere automáticamente el `period_key` a partir de:
  - `issue_date` (si está disponible)
  - `name_date` (fecha extraída del nombre del archivo)
  - `filename` (patrones como "recibo_2023-05.pdf")
- Si no se puede inferir, se marca `needs_period=True` y el usuario debe asignarlo manualmente

## Estructura de Datos

### PeriodKindV1 (Enum)

```python
class PeriodKindV1(str, Enum):
    NONE = "NONE"      # No es periódico
    MONTH = "MONTH"    # Mensual
    YEAR = "YEAR"      # Anual
    QUARTER = "QUARTER" # Trimestral
```

### PeriodInfoV1

Información de un período esperado:

```python
{
    "period_key": "2023-05",
    "period_kind": "MONTH",
    "period_start": "2023-05-01",
    "period_end": "2023-05-31",
    "status": "AVAILABLE",  # o "MISSING" o "LATE"
    "doc_id": "doc_123...",
    "doc_file_name": "recibo_2023-05.pdf",
    "days_late": null  # Solo si status="LATE"
}
```

## Decisiones de Diseño

### 1. Period Key como String

Se eligió `period_key` como string en lugar de objetos Date porque:
- Es más fácil de comparar y filtrar
- Permite búsquedas exactas sin parsing
- Es legible en logs y debug

### 2. Inferencia Automática

El sistema intenta inferir `period_key` automáticamente, pero si no puede, marca `needs_period=True` en lugar de fallar. Esto permite:
- Migración gradual de documentos existentes
- Documentos nuevos que requieren asignación manual

### 3. Fallback Sin Empresa

Para documentos `scope=worker`, si no se encuentra con `company_key`, se intenta sin `company_key`. Esto es útil para:
- Recibos de autónomos que pueden no estar asociados a una empresa específica
- Documentos personales que no requieren empresa

### 4. Error Explícito vs NO_MATCH

Cuando se busca un período específico y no se encuentra, se devuelve un error explícito `"Missing document for period {period_key}"` en lugar de `NO_MATCH` genérico. Esto permite:
- Identificar claramente qué período falta
- Mejor diagnóstico y debugging

## Migración de Documentos Existentes

Los documentos existentes se pueden migrar ejecutando:

```bash
python scripts/migrate_period_keys.py
```

El script:
1. Lee todos los documentos del repositorio
2. Para cada documento, determina si es periódico según su tipo
3. Intenta inferir `period_key` a partir de metadatos
4. Si puede inferir, asigna `period_key` y `period_kind`
5. Si no puede inferir, marca `needs_period=True`

## Ejemplo de Uso

### Crear Documento con Period Key

Al subir un PDF con nombre "recibo_autonomos_2023-05.pdf" para el tipo `T104_AUTONOMOS_RECEIPT`:

1. El sistema detecta que el tipo es `mode=monthly`
2. Extrae `name_date=2023-05-01` del nombre
3. Infiere `period_key="2023-05"`
4. Crea el documento con `period_kind=MONTH` y `period_key="2023-05"`

### Buscar Documento por Período

```python
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1

store = DocumentRepositoryStoreV1()
docs = store.list_documents(
    type_id="T104_AUTONOMOS_RECEIPT",
    person_key="Emilio",
    period_key="2023-05"
)
# Devuelve solo documentos del período 2023-05
```

### Matching en eGestiona

Cuando el pending es "T205.0 Último Recibo bancario pago cuota autónomos … (Mayo 2023)":

1. Se detecta `pending_period_key="2023-05"`
2. Se busca documento con `type_id="T104_AUTONOMOS_RECEIPT"`, `person_key="Emilio"`, `period_key="2023-05"`
3. Si existe, se devuelve ese documento (MATCH determinista)
4. Si no existe, se devuelve `"Missing document for period 2023-05"`

## Próximos Pasos (UI)

1. **Vista de Cobertura por Períodos**: Mostrar qué períodos están cubiertos y cuáles faltan
2. **Selector de Período en Upload**: Si el tipo es periódico y no se puede inferir, mostrar dropdown para seleccionar período
3. **Indicadores Visuales**: Mostrar estado (AVAILABLE/MISSING/LATE) en la UI

## Referencias

- `backend/shared/document_repository_v1.py`: Modelos de datos
- `backend/repository/period_planner_v1.py`: Servicio de planificación
- `backend/repository/period_migration_v1.py`: Migración de documentos
- `backend/repository/document_matcher_v1.py`: Matching con period_key
- `backend/repository/document_repository_routes.py`: Endpoints API























