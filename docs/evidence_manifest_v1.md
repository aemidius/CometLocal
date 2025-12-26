# CometLocal v1.0 — Evidence Manifest v1.0 (evidence_manifest.json)

Este documento define el **manifest de evidencia** de un run. Su objetivo es:
- asegurar **integridad** (hashes),
- permitir **comparación** entre runs,
- y hacer **auditable** el evidence pack sin leer el HTML/screenshot completo salvo necesidad.

## 1) Artefacto

- Archivo: `evidence_manifest.json`
- Ubicación recomendada: `runs/<run_id>/evidence_manifest.json`
- Rutas en el manifest: **relativas al directorio del run**.

## 2) Reglas v1

- El manifest es **inmutable** una vez escrito (append-only del trace; el manifest puede generarse al final o incremental, pero debe ser consistente).
- Cada item del manifest tiene:
  - `kind` tipado,
  - `relative_path`,
  - `sha256`,
  - `size_bytes`.
- Si `redaction.enabled=true`, debe declararse en el manifest.

## 3) Policy de evidencia (v1)

### Siempre (cada step)

- `dom_snapshot_partial` before/after (si existe after)
- `state_signature_before` (en trace; incluye `screenshot_hash`)

### Solo en fallo/postcondición o acción crítica

- `html_full` (redactado si aplica)
- `screenshot` before/after (PNG)
- opcional: `console_log`, `network_har`

## 4) Estructura: `EvidenceManifestV1`

Campos obligatorios:

- `schema_version`: `"v1"`
- `run_id`: string
- `created_at_utc`: ISO timestamp UTC
- `policy`:
  - `always`: lista de `kind` (mínimo: `dom_snapshot_partial`)
  - `on_failure_or_critical`: lista de `kind` (mínimo: `html_full`, `screenshot`)
- `redaction`:
  - `enabled`: bool
  - `rules`: lista (puede estar vacía si disabled)
- `items`: lista no vacía de `EvidenceItemV1`

Campos opcionales:
- `metadata`: dict

### `EvidenceItemV1`

Campos obligatorios:
- `kind`: `"dom_snapshot_partial" | "html_full" | "screenshot" | "screenshot_hash" | "console_log" | "network_har"`
- `relative_path`: string (posix o windows-safe; recomendado posix)
- `sha256`: string hex
- `size_bytes`: int

Campos opcionales:
- `step_id`: string (si aplica)
- `ts_utc`: ISO timestamp UTC
- `redacted`: bool
- `mime_type`: string
- `state_signature_ref`: `{ before: "...", after: "..." }` (hash refs si aplica)
- `metadata`: dict

## 5) Ejemplo

```json
{
  "schema_version": "v1",
  "run_id": "r_20251221_001",
  "created_at_utc": "2025-12-21T10:00:03.250000+00:00",
  "policy": {
    "always": ["dom_snapshot_partial"],
    "on_failure_or_critical": ["html_full", "screenshot"]
  },
  "redaction": {
    "enabled": true,
    "rules": ["emails", "dni", "passwords", "tokens"]
  },
  "items": [
    {
      "kind": "dom_snapshot_partial",
      "step_id": "step_000",
      "relative_path": "evidence/dom/step_000_before.json",
      "sha256": "a3f4...c9",
      "size_bytes": 12450,
      "mime_type": "application/json",
      "redacted": true
    },
    {
      "kind": "screenshot",
      "step_id": "step_002",
      "relative_path": "evidence/shots/step_002_after.png",
      "sha256": "b1d2...ee",
      "size_bytes": 845221,
      "mime_type": "image/png",
      "redacted": false
    }
  ],
  "metadata": {
    "notes": "screenshots only on critical/failure"
  }
}
```





