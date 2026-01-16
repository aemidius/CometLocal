# Submission History V1

## Formato de Registro

Cada registro (`SubmissionRecordV1`) contiene:

- `record_id`: ID único del registro
- `platform_key`: Plataforma (ej: "egestiona")
- `coord_label`: Coordinación (ej: "Kern")
- `company_key`: Clave de empresa
- `person_key`: Clave de persona/trabajador
- `pending_fingerprint`: SHA256 hex del fingerprint determinista
- `pending_snapshot`: Snapshot del pending item al momento del registro
- `doc_id`: ID del documento del repositorio
- `type_id`: ID del tipo de documento
- `file_sha256`: SHA256 del archivo PDF (opcional)
- `action`: Acción realizada:
  - `"planned"`: Planificado (aún no ejecutado)
  - `"submitted"`: Enviado exitosamente
  - `"skipped"`: Omitido (self-test, dry-run, dedupe)
  - `"failed"`: Fallido
- `decision`: Decisión del guardrail (ej: "AUTO_SUBMIT_OK", "SKIP_ALREADY_SUBMITTED")
- `run_id`: ID del run que generó este registro
- `evidence_path`: Ruta al directorio de evidence
- `created_at`: Fecha de creación (ISO 8601)
- `updated_at`: Fecha de última actualización (ISO 8601)
- `submitted_at`: Fecha de envío real (ISO 8601, solo si action=submitted)
- `error_message`: Mensaje de error si action=failed

## Fingerprint

El fingerprint se calcula usando `compute_pending_fingerprint()`:

1. Normaliza campos estables del pending item:
   - `tipo_doc`
   - `elemento`
   - `empresa`
   - `centro_trabajo` (si existe)
   - `trabajador` (si existe)

2. Normaliza texto: lowercase, trim, collapse whitespace

3. Construye string canónico: `platform_key|coord_label|tipo_doc|elemento|empresa|centro_trabajo|trabajador`

4. Calcula SHA256 y retorna hex

## Comportamiento de Dedupe

### En Submission Plan

Al construir el plan, se verifica el historial:

1. Si existe registro con `action="submitted"` y mismo `fingerprint`:
   - `decision.action = "SKIP_ALREADY_SUBMITTED"`
   - `confidence = 1.0`
   - `reasons` incluye `record_id` y `run_id` del registro anterior
   - NO se ejecuta en `execute`

2. Si existe registro con `action="planned"` y mismo `fingerprint` (pero no "submitted"):
   - `decision.action = "SKIP_ALREADY_PLANNED"`
   - `confidence = 1.0`
   - `reasons` incluye `record_id` y `run_id` del registro anterior
   - NO se ejecuta en `execute`

### En Execute

1. Antes de ejecutar cada item:
   - Se crea registro con `action="planned"`

2. Tras confirmación OK:
   - Se actualiza registro a `action="submitted"`
   - Se establece `submitted_at`

3. Si falla:
   - Se actualiza registro a `action="failed"`
   - Se guarda `error_message`

### En Self-Test

1. Se genera fingerprint estable para el pending sintético
2. Se verifica dedupe (igual que en plan normal)
3. Se registra con `action="skipped"` y `error_message="SELF_TEST: No actual execution performed"`

## Storage

- Archivo: `data/repository/history/submissions.json`
- Formato: `{"schema_version": "v1", "submissions": [...]}`
- Atomic writes: temp file -> rename (igual que el resto del sistema)

## Endpoints

- `GET /api/repository/history`: Lista registros con filtros opcionales
  - Query params: `platform_key`, `coord_label`, `company_key`, `person_key`, `doc_id`, `action`, `limit`
- `GET /api/repository/history/{record_id}`: Obtiene un registro por ID




