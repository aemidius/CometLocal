# CometLocal v1.0 — Trace Contract v1.0 (trace.jsonl)

Este documento define el **contrato de trazas** del executor v1.0:
- `trace.jsonl` (append-only, 1 evento por línea)
- eventos tipados y comparables entre runs

La política de evidencia y su manifest se definen en `docs/evidence_manifest_v1.md`.

## Objetivos del trace

- **Determinismo y auditoría**: cada decisión del executor debe quedar registrada.
- **Reproducción**: dado un `trace.jsonl` y su evidence pack, se debe poder reconstruir el “por qué” de un fallo.
- **No bucles silenciosos**: loops y policies generan eventos explícitos.
- **Compatibilidad**: estos contratos se añaden sin romper el API actual; son “artefactos” y schemas internos v1.

## Reglas de formato (v1.0)

- Archivo: **`trace.jsonl`**
- **Append-only**: no se reescriben eventos; solo se anexan.
- **1 evento por línea**: cada línea es un JSON válido.
- Los eventos se ordenan por:
  - `seq` incremental (sin huecos), y
  - `ts_utc` (timestamp UTC)

## Artefactos por run (contexto)

Estructura recomendada (ruta configurable):

- `runs/<run_id>/run_manifest.json`
- `runs/<run_id>/trace.jsonl`
- `runs/<run_id>/evidence/`
  - `dom/step_<n>_before.json`
  - `dom/step_<n>_after.json`
  - `html/step_<n>_full.html` (solo fallo/crit)
  - `shots/step_<n>_before.png` (solo fallo/crit) + `shots/step_<n>_before.sha256`
  - `shots/step_<n>_after.png` (solo fallo/crit) + `shots/step_<n>_after.sha256`
  - `console/step_<n>.log` (opcional)
  - `network/step_<n>.har` (opcional)

**Nota**: por defecto guardamos el **hash** de screenshots. La imagen completa solo en fallo/acciones críticas.

## run_manifest.json (mínimo)

- `run_id`: string estable (UUID recomendado)
- `started_at`: ISO timestamp
- `execution_profile`: nombre + parámetros (timeouts, caps)
- `execution_mode`: `live|dry_run`
- `policy_defaults`: umbrales v1 (retries/recovery/same_state/steps/backoff)
- `app_version`: git sha / versión build
- `platform`: nombre simbólico (si aplica)
- `domain_allowlist`: lista de dominios permitidos
- `redaction_policy`: on/off + reglas

## Trace: formato JSONL (schema)

Cada línea es un `TraceEventV1`.

### Campos comunes (mínimo)

Requeridos para **todos** los eventos:

- `run_id`: string
- `seq`: int (incremental, sin huecos)
- `ts_utc`: ISO timestamp UTC
- `event_type`: string estable (ver tipos)
- `step_id`: string|null (obligatorio si el evento aplica a un step; si no, null)
- `state_signature_before`: `StateSignatureV1|null` (si aplica)
- `state_signature_after`: `StateSignatureV1|null` (si aplica)

Opcionales (según evento):
- `action_spec`: `ActionSpecV1|null`
- `result`: `ActionResultV1|null`
- `error`: `ExecutorErrorV1|null` (para `error_raised` y `policy_halt`)
- `evidence_refs`: `EvidenceRefV1[]` (para `evidence_captured` y cuando aplique)
- `metadata`: dict (extensible, pero determinista y serializable)

### Tipos de evento (v1 mínimo)

Obligatorios:

- `run_started`, `run_finished`
- `observation_captured`
- `proposal_received`, `proposal_accepted`, `proposal_rejected`
- `action_compiled`, `preconditions_checked`, `action_started`, `action_executed`
- `postconditions_checked`, `assert_checked`
- `retry_scheduled`, `backoff_applied`
- `recovery_started`, `recovery_finished`
- `policy_halt` (**con `error.error_code="POLICY_HALT"`**)
- `evidence_captured`
- `error_raised` (**con `error.error_code` canónico**)

## Extension events v1.0 (compatibles)

Estos eventos son **extensiones** del contrato v1.0. No sustituyen a los eventos mínimos; se añaden para soportar capacidades incrementales sin romper el esquema base.

### inspection_started

- **Semántica**: inicio de una inspección determinista de un documento (p.ej. antes de un `upload`).
- **Ámbito**: run-level o step-level.
  - `step_id`: **null** si es run-level, o `"step_<n>"` si se asocia a un step.
- **Campos mínimos**:
  - `run_id`, `seq`, `ts_utc`, `event_type="inspection_started"`
  - `step_id`: string|null
  - `metadata.file_ref`: string (file_ref)

### inspection_finished

- **Semántica**: fin de inspección, con resultado `ok|failed` y referencias al report.
- **Ámbito**: run-level o step-level (mismas reglas que `inspection_started`).
- **Campos mínimos**:
  - `run_id`, `seq`, `ts_utc`, `event_type="inspection_finished"`
  - `step_id`: string|null
  - `metadata.status`: `"ok"|"failed"`
  - `metadata.file_ref`: string
  - `metadata.doc_hash`: string|null
  - `metadata.criteria_profile`: string|null
  - `metadata.report_ref`: string|null (ruta relativa recomendada al report, p.ej. `data/documents/_inspections/<sha256>.json`)

## Anti-loop (registro y decisión)

### StateSignature y “same-state revisit”

- El executor calcula `state_signature_before` en `observation_captured`.
- Define `state_key = state_signature_before.key_elements_hash + ":" + state_signature_before.visible_text_hash + ":" + state_signature_before.screenshot_hash`.
- Mantiene contador por `state_key` dentro del run:
  - `same_state_revisit_count[state_key] = n`

### Registro obligatorio en trace

En cada `observation_captured`, el executor debe incluir en `metadata`:
- `policy.same_state_revisit_count`: int (contador actual para ese state)
- `policy.same_state_revisit_threshold`: int (por defecto 2)
- `policy.steps_taken`: int
- `policy.hard_cap_steps`: int (por defecto 60)

### Decisión de corte (policy_halt)

Si `same_state_revisit_count[state_key] > threshold`, el executor emite:
- `policy_halt` con:
  - `error.error_code="POLICY_HALT"`
  - `error.stage="policy"`
  - `metadata.policy.reason="same_state_revisit"`
  - `metadata.policy.state_key=...`
  - `metadata.policy.count=...`
  - `metadata.policy.threshold=...`

## Evidence policy (referencia)

La captura de evidencia se expresa mediante eventos `evidence_captured` y un **manifest** (ver `docs/evidence_manifest_v1.md`).

Requisito v1:
- Siempre: `dom_snapshot_partial` + `state_before` (incluye `screenshot_hash`)
- En fallo/postcondición o acción crítica: `html_full` + screenshots before/after

## Ejemplos (eventos JSONL)

Los ejemplos muestran *un evento por línea*.

### run_started

```json
{"run_id":"r_20251221_001","seq":1,"ts_utc":"2025-12-21T10:00:00.000000+00:00","event_type":"run_started","step_id":null,"state_signature_before":null,"state_signature_after":null,"metadata":{"execution_mode":"live","execution_profile":"balanced","policy":{"retries_per_action":2,"recovery_max":3,"same_state_revisits":2,"hard_cap_steps":60,"backoff_ms":[300,1000,2000]}}}
```

### observation_captured

```json
{"run_id":"r_20251221_001","seq":2,"ts_utc":"2025-12-21T10:00:00.200000+00:00","event_type":"observation_captured","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"metadata":{"policy":{"steps_taken":0,"hard_cap_steps":60,"same_state_revisit_count":1,"same_state_revisit_threshold":2}}}
```

### proposal_received

```json
{"run_id":"r_20251221_001","seq":3,"ts_utc":"2025-12-21T10:00:00.300000+00:00","event_type":"proposal_received","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"metadata":{"proposal_source":"llm","proposal_count":2}}
```

### proposal_rejected (con error canónico)

```json
{"run_id":"r_20251221_001","seq":4,"ts_utc":"2025-12-21T10:00:00.350000+00:00","event_type":"proposal_rejected","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"error":{"schema_version":"v1","error_code":"INVALID_ACTIONSPEC","stage":"proposal_validation","severity":"error","message":"missing strong postcondition for critical action","retryable":false,"details":{"violated_rules":["U5"]},"created_at":"2025-12-21T10:00:00.350000+00:00"},"metadata":{}}
```

### action_compiled

```json
{"run_id":"r_20251221_001","seq":5,"ts_utc":"2025-12-21T10:00:00.500000+00:00","event_type":"action_compiled","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"action_spec":{"schema_version":"v1","action_id":"a_login_submit","kind":"click","target":{"type":"role","role":"button","name":"Acceder","exact":true},"preconditions":[{"kind":"element_visible","args":{"target":{"type":"role","role":"button","name":"Acceder","exact":true}},"severity":"error"}],"postconditions":[{"kind":"url_matches","args":{"pattern":"/dashboard"},"severity":"critical"}],"timeout_ms":8000,"criticality":"critical","tags":["auth"],"assertions":[],"metadata":{}},"metadata":{}}
```

### preconditions_checked / action_started / action_executed

```json
{"run_id":"r_20251221_001","seq":6,"ts_utc":"2025-12-21T10:00:00.650000+00:00","event_type":"preconditions_checked","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"metadata":{"ok":true}}
```

```json
{"run_id":"r_20251221_001","seq":7,"ts_utc":"2025-12-21T10:00:00.700000+00:00","event_type":"action_started","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"metadata":{}}
```

```json
{"run_id":"r_20251221_001","seq":8,"ts_utc":"2025-12-21T10:00:00.900000+00:00","event_type":"action_executed","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":null,"metadata":{"duration_ms":180}}
```

### postconditions_checked / assert_checked / evidence_captured

```json
{"run_id":"r_20251221_001","seq":9,"ts_utc":"2025-12-21T10:00:01.200000+00:00","event_type":"postconditions_checked","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/dashboard","created_at":"2025-12-21T10:00:01.150000+00:00","metadata":{}},"metadata":{"ok":true}}
```

```json
{"run_id":"r_20251221_001","seq":10,"ts_utc":"2025-12-21T10:00:01.250000+00:00","event_type":"evidence_captured","step_id":"step_000","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/login","created_at":"2025-12-21T10:00:00.200000+00:00","metadata":{}},"state_signature_after":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/dashboard","created_at":"2025-12-21T10:00:01.150000+00:00","metadata":{}},"evidence_refs":[{"kind":"dom_snapshot_partial","uri":"evidence/dom/step_000_before.json","sha256":"...","metadata":{}},{"kind":"dom_snapshot_partial","uri":"evidence/dom/step_000_after.json","sha256":"...","metadata":{}}],"metadata":{"manifest_uri":"evidence_manifest.json"}}
```

### error_raised (error_code canónico)

```json
{"run_id":"r_20251221_001","seq":11,"ts_utc":"2025-12-21T10:00:02.000000+00:00","event_type":"error_raised","step_id":"step_001","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/upload","created_at":"2025-12-21T10:00:01.900000+00:00","metadata":{}},"state_signature_after":null,"error":{"schema_version":"v1","error_code":"TARGET_NOT_UNIQUE","stage":"precondition","severity":"error","message":"target resolution returned 3 matches; requires exactly 1","retryable":false,"details":{"count_observed":3,"resolution_order":["testid","role","label","css","xpath","text"]},"created_at":"2025-12-21T10:00:02.000000+00:00"},"metadata":{}}
```

### policy_halt (POLICY_HALT)

```json
{"run_id":"r_20251221_001","seq":12,"ts_utc":"2025-12-21T10:00:03.000000+00:00","event_type":"policy_halt","step_id":"step_010","state_signature_before":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/upload","created_at":"2025-12-21T10:00:02.900000+00:00","metadata":{}},"state_signature_after":null,"error":{"schema_version":"v1","error_code":"POLICY_HALT","stage":"policy","severity":"critical","message":"policy halt: same_state_revisit","retryable":false,"details":{"policy_reason":"same_state_revisit","state_key":"...","count":3,"threshold":2},"created_at":"2025-12-21T10:00:03.000000+00:00"},"metadata":{"policy":{"same_state_revisit_count":3,"same_state_revisit_threshold":2}}}
```

### run_finished

```json
{"run_id":"r_20251221_001","seq":13,"ts_utc":"2025-12-21T10:00:03.200000+00:00","event_type":"run_finished","step_id":null,"state_signature_before":null,"state_signature_after":{"schema_version":"v1","algorithm_version":"v1","url_hash":"...","title_hash":"...","key_elements_hash":"...","visible_text_hash":"...","screenshot_hash":"sha256:...","url":"https://portal.example.com/upload","created_at":"2025-12-21T10:00:03.150000+00:00","metadata":{}},"metadata":{"status":"halted"}}
```


