# CometLocal v1.0 — Contrato de errores tipificados (Block 4)

Este documento define el **contrato formal** de errores del executor v1.0 adaptado al DSL de acciones (Block 3).

## 1) Principios

- Todo fallo del executor se expresa como **`ExecutorError` tipado** (`error_code` estable), nunca como string libre.
- Todo error debe ser **reproducible**: debe incluir `action_spec`, `state_before`, y evidencia mínima.
- El executor decide: si una acción no puede validarse determinísticamente, se rechaza con `INVALID_ACTIONSPEC` o errores de target.

## 2) Estructura: `ExecutorError` (campos obligatorios)

Campos obligatorios (v1.0):

- **`schema_version`**: `"v1"`
- **`error_code`**: string estable (ver catálogo)
- **`stage`**: `"proposal_validation" | "precondition" | "execution" | "postcondition" | "policy" | "evidence"`
- **`severity`**: `"warning" | "error" | "critical"`
- **`message`**: string corto, técnico, sin prosa
- **`retryable`**: boolean (solo true si policy lo permite explícitamente)
- **`run_id`**: string
- **`seq`**: int (secuencia de evento/step, sin huecos)
- **`step_index`**: int (0-based)
- **`action_id`**: string (ActionSpec.id)
- **`action_kind`**: string (ActionSpec.kind)
- **`criticality`**: `"normal" | "critical"`
- **`state_before`**: `StateSignature v1`
- **`evidence_refs`**: lista no vacía de `EvidenceRef`
- **`created_at`**: ISO timestamp

Campos opcionales:
- `state_after`: `StateSignature v1` (si aplica)
- `cause`: string (repr de excepción original, si hay)
- `details`: dict (estructurado; nunca texto libre sin clave)
- `debug_message`: string (solo debug; no se usa para lógica)
- `failed_conditions`: lista de `{ kind, args, phase: "pre|post|assert" }`

## 3) Evidencia mínima obligatoria (por cualquier error)

Para cualquier `ExecutorError`, el executor debe adjuntar al menos:

- **`dom_snapshot_partial`** (siempre):
  - url, title
  - targets + ancestros + siblings (según ActionSpec.target)
  - visible anchors + visible inputs
- **`state_signature`**:
  - `state_before` con `screenshot_hash` (solo hash por defecto)

Además, **si el error ocurre en acción crítica o en cualquier fallo de ejecución/postcondición**, se adjunta:
- **`html_full`** (redactado si aplica)
- **`screenshot`** real before/after (no solo hash)

## 4) Relación con el DSL (Block 3)

Reglas relevantes que el executor debe traducir a errores:

- **U1**: click/submit/upload requieren `element_count_equals==1`
  - si count == 0 → `TARGET_NOT_FOUND`
  - si count != 1 → `TARGET_NOT_UNIQUE`
- **U2**: `text` y `label` solo con exact/normalización + `count_equals==1`
  - si no cumple → `INVALID_ACTIONSPEC`
- **U3**: `nth` solo con base_target estable + rationale trazable
  - si no cumple → `INVALID_ACTIONSPEC`
- **U4**: orden determinista de resolución de targets:
  - `testid > role > label > css > xpath > text`
- **U5**: acciones críticas requieren al menos 1 postcondición fuerte
  - si falta → `INVALID_ACTIONSPEC`

## 5) Catálogo de `error_code` (subset obligatorio v1.0)

Estos códigos son **obligatorios** y estables en v1.0:

- **`TARGET_NOT_FOUND`**
- **`TARGET_NOT_UNIQUE`**
- **`INVALID_ACTIONSPEC`**
- **`PRECONDITION_FAILED`**
- **`POSTCONDITION_FAILED`**
- **`POLICY_HALT`**
- **`DOMAIN_BLOCKED`**
- **`ACTION_CRITICAL_BLOCKED`**
- **`NAVIGATION_TIMEOUT`**
- **`UPLOAD_FAILED`**
- **`DOWNLOAD_FAILED`**
- **`OVERLAY_BLOCKING`**
- **`AUTH_FAILED`**

Notas:
- `PRECONDITION_FAILED` y `POSTCONDITION_FAILED` deben incluir `failed_conditions[]`.
- `POLICY_HALT` debe incluir `details.policy_reason` estable (ej. `max_steps`, `same_state_revisit`, `retry_limit`, `recovery_limit`).

## 6) Evidencia adicional requerida (por error_code)

### `TARGET_NOT_FOUND`
- **Mínimo**: dom_snapshot_partial + state_before (con screenshot_hash)
- **Debe incluir**:
  - `details.target_resolution_order` (U4)
  - `details.target` (target serializado)
  - `details.count_observed=0`

### `TARGET_NOT_UNIQUE`
- **Mínimo**: dom_snapshot_partial + state_before
- **Debe incluir**:
  - `details.count_observed` (!=1)
  - `details.matches_sample` (hasta N identificadores/attrs safe)

### `INVALID_ACTIONSPEC`
- **Mínimo**: dom_snapshot_partial + state_before
- **Debe incluir**:
  - `details.validation_errors` (lista estructurada)
  - `details.violated_rules` (ej. `U2`, `U3`, `U5`)

### `PRECONDITION_FAILED`
- **Mínimo**: dom_snapshot_partial + state_before
- **Debe incluir**:
  - `failed_conditions[]` con phase `"pre"`

### `POSTCONDITION_FAILED`
- **Mínimo**: dom_snapshot_partial + state_before + state_after
- **Además**: html_full + screenshot before/after si acción crítica o si el fallo es en ejecución/postcondición (regla global)
- **Debe incluir**:
  - `failed_conditions[]` con phase `"post"|"assert"`

### `POLICY_HALT`
- **Mínimo**: dom_snapshot_partial + state_before
- **Debe incluir**:
  - `details.policy_reason`
  - `details.policy_thresholds` (retries/recovery/revisits/steps/backoff)

### `DOMAIN_BLOCKED`
- **Mínimo**: dom_snapshot_partial + state_before
- **Debe incluir**:
  - `details.host`
  - `details.allowlist`

### `ACTION_CRITICAL_BLOCKED`
- **Mínimo**: dom_snapshot_partial + state_before
- **Además**: html_full + screenshot (porque es crítica)
- **Debe incluir**:
  - `details.critical_reason` (ej. missing_strong_postcondition, unsafe_domain_escape)

### `NAVIGATION_TIMEOUT`
- **Mínimo**: dom_snapshot_partial + state_before + state_after (si existe)
- **Además**: screenshot (fallo de ejecución)
- **Debe incluir**:
  - `details.timeout_ms`
  - `details.wait_condition` (si aplica)

### `UPLOAD_FAILED`
- **Mínimo**: dom_snapshot_partial + state_before + state_after (si existe)
- **Además**: html_full + screenshot before/after (crítica)
- **Debe incluir**:
  - `details.file_ref`
  - `details.upload_signal` (toast/dom change)

### `DOWNLOAD_FAILED`
- **Mínimo**: dom_snapshot_partial + state_before
- **Además**: screenshot (fallo de ejecución)
- **Debe incluir**:
  - `details.expected_download` boolean

### `OVERLAY_BLOCKING`
- **Mínimo**: dom_snapshot_partial + state_before
- **Además**: screenshot (para ver overlay)
- **Debe incluir**:
  - `details.overlay_selector|overlay_text` (si detectable)

### `AUTH_FAILED`
- **Mínimo**: dom_snapshot_partial + state_before
- **Además**: screenshot + html_full (si detectable y redaction on)
- **Debe incluir**:
  - `details.auth_signal` (ej. texto “credenciales incorrectas”, redirect login, 401 detectado)









