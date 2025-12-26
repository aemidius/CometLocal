# CometLocal v1.0 — Executor Contract (paquete contractual)

Este documento consolida el **contrato funcional** del Executor v1.0 para implementación incremental **sin romper el API**.

## 1) Definición ejecutiva

### Qué es

El **Executor CometLocal v1.0** es el componente determinista y auditable que:
- **decide** qué acciones ejecutar,
- **valida** precondiciones/postcondiciones,
- **ejecuta** side-effects web (vía Playwright; no se implementa aquí),
- **tipifica** fallos con `error_code` estable,
- y **traza** toda decisión en `trace.jsonl` + evidence pack.

### Qué no es

- No es un planner ni un LLM.
- No es un “best-effort bot” ni un scraper heurístico.
- No ejecuta texto libre ni código generado.
- No hace aprendizaje ni auto-tuning fuera de políticas explícitas.

## 2) Invariantes v1 (cerrados)

Referencia normativa: `docs/executor_invariants_v1.md`.

Resumen operativo:
- El executor decide; el LLM solo propone.
- Cada acción tiene precondición y postcondición verificable.
- No loops silenciosos (counters + límites + eventos).
- Todo fallo tipificado y reproducible.
- Auditabilidad fuerte (trace append-only + evidencia mínima).
- Acciones críticas con reglas reforzadas (dry-run/strong postconditions/evidencia ampliada).

## 3) DSL ActionSpec v1 (contrato funcional)

### 3.1 Acciones permitidas (v1)

- `navigate`
- `click`
- `fill`
- `select`
- `upload`
- `wait_for`
- `assert`
- `stop` (solo si policy lo acepta)

### 3.2 `ActionSpec` (schema mínimo)

Campos obligatorios:
- `id`: string único por run
- `kind`: uno de los anteriores
- `criticality`: `normal|critical`
- `target`: obligatorio salvo `assert`/`stop`
- `preconditions[]`: **no vacío**
- `postconditions[]`: **no vacío**
- `timeout_ms`: int > 0
- `tags[]`: opcional (pero estable)
- `metadata`: opcional (solo JSON serializable)

Reglas:
- Toda acción debe ser **compilable** a comandos Playwright sin ambigüedad.
- `assert` es acción de primera clase (sin side-effects).
- `wait_for` **no** admite sleeps libres: solo condiciones.

### 3.3 Condition.kind permitido (subset exacto v1)

**URL/Scope**
- `url_is`
- `url_matches`
- `host_in_allowlist`
- `title_contains`

**Elemento / DOM**
- `element_exists`
- `element_visible`
- `element_enabled`
- `element_clickable`
- `element_count_equals`
- `element_text_contains`
- `element_attr_equals`
- `element_value_equals`

**UI/estado**
- `network_idle`
- `no_blocking_overlay`
- `toast_contains`

**Descargas/Subidas**
- `download_started`
- `upload_completed` *(si no detectable, se implementa como DOM/toast change)*

### 3.4 Target v1 permitido

Targets base:
- `testid { id }`
- `role { role, name?, exact? }`
- `label { text, exact?, normalize_ws? }`
- `css { selector }`
- `xpath { selector }` *(solo si css no sirve)*
- `text { text, exact?, normalize_ws? }`

Composición:
- `frame { selector } + inner_target` *(máx 1 nivel)*
- `nth { base_target, index }` *(solo si base_target es estable)*

### 3.5 Reglas de unicidad determinista (obligatorias)

**U1)** `click`/`upload` (y cualquier “submit-like”) requieren `element_count_equals==1`:
- count == 0 → `TARGET_NOT_FOUND`
- count != 1 → `TARGET_NOT_UNIQUE`

**U2)** `text` y `label` solo con `exact`/normalización y siempre con `element_count_equals==1`.

**U3)** `nth` solo con `base_target` estable + rationale trazable:
- default conservador: el rationale debe existir en `ActionSpec.metadata.target_rationale`.

**U4)** Orden determinista de resolución:
- `testid > role > label > css > xpath > text`

**U5)** Acciones críticas requieren ≥1 **postcondición fuerte**; si falta → `INVALID_ACTIONSPEC`.

**Definición conservadora (v1) de “postcondición fuerte”**:
- `url_is`, `url_matches`, `download_started`, `upload_completed`
- o `toast_contains` con severidad `critical`
- o `element_text_contains` con severidad `critical`

## 4) Error codes canónicos v1

Norma: `docs/errors_contract_v1.md` y `docs/error_codes_v1.md`.

Canónicos obligatorios:
- `TARGET_NOT_FOUND`
- `TARGET_NOT_UNIQUE`
- `INVALID_ACTIONSPEC`
- `PRECONDITION_FAILED`
- `POSTCONDITION_FAILED`
- `POLICY_HALT`
- `DOMAIN_BLOCKED`
- `ACTION_CRITICAL_BLOCKED`
- `NAVIGATION_TIMEOUT`
- `UPLOAD_FAILED`
- `DOWNLOAD_FAILED`
- `OVERLAY_BLOCKING`
- `AUTH_FAILED`

## 5) Trace contract + Evidence policy

Norma:
- `docs/trace_contract_v1.md` (trace.jsonl, eventos tipados, anti-loop)
- `docs/evidence_manifest_v1.md` (manifest de evidencia + hashes + rutas)

Política v1 (resumen):
- Siempre: `dom_snapshot_partial` + `state_signature_before` (incluye `screenshot_hash`)
- En fallo/postcondición o acción crítica: `html_full` + screenshots before/after

## 6) Qué NO entra en v1.0 (explícito)

- Captcha/2FA bypass automático (se tipifica como `AUTH_FAILED`/`EXTERNAL_*` y se detiene o se deriva a intervención).
- Aprendizaje automático de selectores/estrategias (solo memoria/heurística permitida si está tipada y trazada; no se prioriza en v1).
- Multi-frame profundo (>1 nivel) y shadow DOM genérico.
- “Auto-heal” no determinista de selectores.
- Interpretación libre de lenguaje natural en ejecución (solo propuestas DSL).
- Ejecución de workflows de pago reales (solo detección y bloqueo por criticidad).

## 7) Checklist de implementación (orden recomendado)

1) **Validador DSL** (schema + U1–U5 + orden de resolución U4) → `INVALID_ACTIONSPEC`/target errors.
2) **Runner de trace**: `trace.jsonl` append-only con eventos mínimos obligatorios.
3) **Evidence capture**: dom snapshot parcial siempre + manifest; HTML/screenshot solo en fallo/crit.
4) **Policy anti-loop**: same-state revisit counters + `POLICY_HALT` determinista.
5) **Compilación DSL → comandos Playwright** (sin heurísticas; targets deterministas).
6) **Preconditions / Postconditions**: ejecución y fallo tipado (`PRECONDITION_FAILED` / `POSTCONDITION_FAILED`).
7) **Acciones críticas**: enforcement de strong postconditions + evidencia ampliada + dry-run.
8) **Compat API**: mapear `ExecutorError` tipado a `StepResult.error` solo como compat/debug (sin perder tipado interno).





