# CometLocal v1.0 — Trace Contract v1 (Trace + Evidence + StateSignatures)

Este documento define el **contrato de trazas** (trace) y la **política de evidencia** del executor.
El objetivo es asegurar **auditabilidad** y **reproducibilidad** sin introducir heurísticas opacas.

## Objetivos del trace

- **Determinismo y auditoría**: cada decisión del executor debe quedar registrada.
- **Reproducción**: dado un `trace.jsonl` y su evidence pack, se debe poder reconstruir el “por qué” de un fallo.
- **No bucles silenciosos**: loops y policies generan eventos explícitos.
- **Compatibilidad**: estos contratos se añaden sin romper el API actual; son “artefactos” y schemas internos v1.

## Artefactos por run

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

## Trace: formato JSONL

Un archivo `trace.jsonl` con **un evento por línea** (JSON).
Cada evento es un `TraceEventV1` (ver schema en backend).

### Campos comunes (mínimo)

- `run_id`: string
- `seq`: int (incremental, sin huecos)
- `ts`: ISO timestamp
- `event_type`: string estable (ver tipos)
- `step_index`: int (0-based)
- `sub_goal_index`: int|null
- `state_before`: `StateSignatureV1`|null
- `state_after`: `StateSignatureV1`|null
- `action_spec`: `ActionSpecV1`|null
- `result`: `ActionResultV1`|null
- `error`: `ExecutorErrorV1`|null
- `evidence_refs`: `EvidenceRefV1[]`
- `metadata`: dict (extensible)

### Tipos de evento (v1 mínimo)

- `run_started`
- `proposal_received`
- `proposal_rejected`
- `proposal_accepted`
- `action_started`
- `preconditions_checked`
- `action_executed`
- `postconditions_checked`
- `action_finished`
- `retry_scheduled`
- `backoff_applied`
- `recovery_started`
- `recovery_finished`
- `policy_halt`
- `run_finished`

## Evidence policy v1.0 (cerrado)

### Siempre (cada step)

- **DOM snapshot parcial acotado**:
  - `url`, `title`
  - `targets[]` (subárbol relevante: target + ancestros + siblings)
  - `visible_anchors[]` (href/text/attrs whitelist)
  - `visible_inputs[]` (selector/name/type/label/value_redacted)
- **StateSignature** con hash de screenshot:
  - solo guardar `screenshot_hash` por defecto (no imagen).

### Solo en fallo o acción crítica

- HTML completo (`html_full`) con redaction si aplica.
- screenshot real antes/después.
- opcional: console log y network HAR.

## StateSignature v1.0

`StateSignatureV1` incluye (mínimo):

- `algorithm_version`: `"v1"`
- `url`: string (opcional) y/o `url_hash`
- `title_hash`
- `key_elements_hash` (anchors/inputs/targets normalizados)
- `visible_text_hash` (texto visible acotado y normalizado)
- `screenshot_hash` (sha256 del PNG)

### Normalización

Para evitar diferencias no deterministas:
- normalizar espacios,
- normalizar unicode (NFKC),
- truncar texto visible a un máximo definido por perfil (ej. 3000 chars).

## Redaction (cuando aplique)

Si `redaction_policy.enabled=True`, el evidence pack debe:
- sustituir valores sensibles (passwords, tokens, DNIs, emails) por `***`,
- registrar en `run_manifest` qué reglas se aplicaron.


