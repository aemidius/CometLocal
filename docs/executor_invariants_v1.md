# CometLocal v1.0 — Invariantes del Executor (Contrato)

Este documento define los **invariantes obligatorios** del executor de CometLocal v1.0.
Su objetivo es garantizar que el sistema sea **robusto, determinista y auditable** para tareas web reales (CAE/PRL/portales corporativos),
usando LLMs **solo como apoyo cognitivo** (propuesta), nunca como motor de ejecución.

## Principios (no negociables)

- **El executor decide; el LLM solo propone.**
- **Cada acción tiene precondición y postcondición verificable.**
- **No se permiten bucles silenciosos ni heurísticas opacas.**
- **Todo fallo debe ser tipificado y reproducible.**
- **Debe funcionar en escenarios CAE reales, no ideales.**

## Definiciones

- **Propuesta (LLM)**: salida no ejecutable; puede sugerir targets/acciones.
- **Especificación (Executor)**: acción ejecutable (`ActionSpec`) creada/aceptada por el executor tras validación determinista.
- **Evidencia**: artefactos persistidos (snapshots, hashes, logs) que permiten auditoría y reproducción del fallo.
- **StateSignature**: firma estable del estado observado que alimenta políticas anti-loop y trazabilidad.
- **Acción crítica**: acción con potencial de cambio persistente o irreversible, o que sale del dominio permitido.

## Invariantes v1.0

### I1) Separación estricta: proponer ≠ ejecutar

- El LLM puede generar `ActionProposal[]`.
- El executor **nunca** ejecuta propuestas directamente.
- Toda ejecución en Playwright se hace exclusivamente a partir de un `ActionSpec` validado.

**Criterio de verificación**
- En trace debe quedar registrado `proposal_received` → `proposal_accepted|proposal_rejected`.
- Si se ejecuta una acción, debe existir `action_started` con `action_spec` validado.

### I2) Precondición y postcondición verificables por acción

Para cada `ActionSpec`:
- Debe existir al menos **una precondición** verificable (ej. selector visible/enabled, URL en scope, frame esperado).
- Debe existir al menos **una postcondición** verificable o contrato visual aplicable.

**Nota**: `assert` es una acción de primera clase (ver Decisión D1).

### I3) Determinismo operativo

Dado el mismo:
- `Observation` (o su equivalente en evidencia),
- `ActionSpec`,
- `ExecutionProfile`,
- `PolicyState`,

el executor debe producir el mismo tipo de resultado (éxito/fallo tipado) sin comportamientos ocultos.

Permitido:
- timeouts configurables por perfil,
- backoff determinista (ver D4),
- normalizaciones declaradas y registradas en trace.

Prohibido:
- sleeps arbitrarios no declarados,
- heurísticas no trazadas (“parece que…” sin evidencia),
- reintentos infinitos.

### I4) No bucles silenciosos (liveness)

Todo loop debe tener:
- contador,
- límite,
- y razón registrada en trace.

Se aplican umbrales por defecto (ver D4) y el corte debe tipificarse como `POLICY_HALT_*`.

### I5) Fallos tipificados y reproducibles

No se permiten fallos expresados solo como string libre.
Todo fallo expuesto por el executor se codifica como:

- `error_code` estable (catálogo v1),
- `stage` (proposal_validation / precondition / execution / postcondition / policy / evidence),
- `state_before` (StateSignature),
- `action_spec`,
- `evidence_refs` (mínimo dom snapshot parcial, y hashes pertinentes).

### I6) Auditoría fuerte (trace + evidence)

Cada decisión relevante genera un evento estructurado en `trace.jsonl`:
- recepción/rechazo/aceptación de propuestas,
- inicio/fin de acción,
- reintentos/backoff,
- recovery visual,
- cortes por policy,
- fallos tipificados.

La política de evidencia v1.0 se define en `docs/trace_contract_v1.md`.

### I7) Modo seguro (dry-run) para acciones críticas

Acciones críticas deben soportar `execution_mode=dry_run`:
- no modifican el portal real,
- simulan ejecución y producen evidencia consistente (dom snapshot parcial + state signature).

### I8) Acciones críticas v1.0 (cerrado)

Se consideran críticas:
- `submit`, `upload`, `confirm`, `payment`, `delete`, `send`, `sign`, `finalize`
- `navigate` fuera del dominio permitido
- cualquier interacción que dispare **descarga/subida** o cambie **estado persistente**

## Decisiones cerradas (v1.0)

### D1) `assert` como acción de primera clase

`ActionSpec.kind = "assert"` existe y se puede ejecutar sin side-effects.
Debe tener precondición/postcondición (normalmente la propia aserción).

### D2) Evidencia / HTML snapshot

- Siempre guardar **DOM snapshot parcial** acotado:
  - URL, title
  - subárboles relevantes (targets + ancestros + siblings)
  - lista de anchors/inputs visibles
- HTML completo solo en:
  - fallo, o
  - acción crítica
  - (con redaction si aplica)

### D3) StateSignature v1

StateSignature incluye:
- hash(url + title + elementos clave + texto visible acotado)
- hash de screenshot

Por defecto:
- guardar **solo el hash** del screenshot (no la imagen).
- guardar la imagen completa solo en fallo/acciones críticas.

### D4) Umbrales policy por perfil (default)

- retries por acción: 2
- recovery strategies max: 3
- same-state revisits: 2
- hard cap steps por run: 60
- backoff determinista: 0.3s, 1s, 2s

### D5) Definición de acción crítica v1

Ver I8.

## Referencias

- `docs/trace_contract_v1.md`: estructura del trace + evidence policy + state signatures
- `docs/error_codes_v1.md`: catálogo inicial de error_code





