# CometLocal v1.0 — Error Codes v1 (catálogo inicial)

Este catálogo define `error_code` estables para el executor v1.0.
Los códigos están pensados para ser:

- **deterministas** (misma causa → mismo código),
- **accionables** (orientan fix/retry/policy),
- **auditables** (se correlacionan con evidencia y state signatures).

## Convenciones

- Prefijos:
  - `PROPOSAL_*`: validación/rechazo de propuestas (LLM)
  - `PRE_*`: fallos de precondición
  - `EXEC_*`: fallos durante ejecución Playwright
  - `POST_*`: fallos de postcondición
  - `POLICY_*`: cortes por políticas (anti-loop / caps)
  - `EVIDENCE_*`: fallos al generar/persistir evidencia
  - `SECURITY_*`: acciones bloqueadas por seguridad/scope
  - `EXTERNAL_*`: interferencias externas (captcha/SSO/2FA/popups)

- Todo error debe incluir:
  - `stage`: proposal_validation|precondition|execution|postcondition|policy|evidence
  - `retryable`: boolean (solo true si está explícitamente permitido)

## Catálogo v1.0

### PROPOSAL_*

- `PROPOSAL_SCHEMA_INVALID`: la propuesta no cumple el schema mínimo.
- `PROPOSAL_UNSUPPORTED_ACTION`: acción propuesta fuera del vocabulario permitido.
- `PROPOSAL_OUT_OF_SCOPE`: target fuera de dominio permitido / contexto inválido.
- `PROPOSAL_UNSAFE`: acción propuesta es crítica sin garantías o viola guardrails.

### PRE_*

- `PRE_STATE_MISMATCH`: el estado observado no coincide con la firma esperada (precondición de contexto).
- `PRE_URL_NOT_ALLOWED`: URL fuera de allowlist.
- `PRE_TARGET_NOT_FOUND`: no existe el target (selector/rol/texto).
- `PRE_TARGET_NOT_VISIBLE`: target existe pero no está visible.
- `PRE_TARGET_NOT_ENABLED`: target deshabilitado / no interactuable.
- `PRE_AMBIGUOUS_TARGET`: múltiples targets plausibles; no se puede decidir determinísticamente.

### EXEC_*

- `EXEC_TIMEOUT`: timeout ejecutando acción (con operación y umbral).
- `EXEC_NAVIGATION_FAILED`: navegación fallida (error de carga/redirección inesperada).
- `EXEC_CLICK_FAILED`: click fallido (intercepted/overlay/etc).
- `EXEC_FILL_FAILED`: rellenado fallido.
- `EXEC_SELECT_FAILED`: selección en `<select>` fallida.
- `EXEC_UPLOAD_FAILED`: upload fallido (input file / set_input_files).
- `EXEC_DOWNLOAD_TRIGGERED`: se disparó descarga (si no estaba permitido/esperado).
- `EXEC_JS_EVALUATION_FAILED`: fallo en evaluate/JS helpers.
- `EXEC_BROWSER_DISCONNECTED`: el browser/context/page se desconectó.

### POST_*

- `POST_NO_EFFECT`: la acción no produjo cambio verificable esperado.
- `POST_CONTRACT_MISMATCH`: contrato visual no cumple (mismatch).
- `POST_CONTRACT_VIOLATION`: contrato visual indica error/violación.
- `POST_ASSERT_FAILED`: una aserción explícita (`assert`) falló.

### POLICY_*

- `POLICY_MAX_STEPS_REACHED`: hard cap steps por run alcanzado.
- `POLICY_RETRY_LIMIT_REACHED`: retries por acción agotados.
- `POLICY_RECOVERY_LIMIT_REACHED`: recovery strategies agotadas.
- `POLICY_SAME_STATE_REVISIT`: demasiadas revisitas a la misma StateSignature.
- `POLICY_STOP_REQUESTED`: stop solicitado y aceptado por policy.

### EVIDENCE_*

- `EVIDENCE_DOM_SNAPSHOT_FAILED`: no se pudo generar snapshot parcial.
- `EVIDENCE_HTML_CAPTURE_FAILED`: fallo capturando HTML completo.
- `EVIDENCE_SCREENSHOT_FAILED`: fallo al capturar screenshot.
- `EVIDENCE_PERSIST_FAILED`: fallo persistiendo evidencia en disco.

### SECURITY_*

- `SECURITY_BLOCKED_CRITICAL_ACTION`: acción crítica bloqueada por falta de confirmación/contrato.
- `SECURITY_BLOCKED_DOMAIN_ESCAPE`: navegación fuera de dominio bloqueada.

### EXTERNAL_*

- `EXTERNAL_CAPTCHA_DETECTED`: captcha detectado.
- `EXTERNAL_SSO_INTERSTITIAL`: pantalla intermedia SSO.
- `EXTERNAL_2FA_REQUIRED`: 2FA requerido.
- `EXTERNAL_MODAL_BLOCKING`: modal/popup bloquea interacción.


