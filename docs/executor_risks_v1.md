# CometLocal v1.0 — Executor Risks (CAE/PRL)

Este documento lista riesgos reales esperables en CAE/PRL y cómo los tratamos en v1.0 (o qué se pospone).

## 1) Login multi-step (SSO, redirects, flows por rol)

- **Riesgo**: flujos variables (company code → user → password → selección tenant → redirect).
- **Mitigación v1**:
  - `navigate` con `host_in_allowlist` y `url_matches`.
  - `click/fill` con `element_count_equals==1` obligatorio (U1).
  - `POLICY_HALT` por same-state revisit cuando el flujo no progresa.
  - Evidencia ampliada en fallos (`html_full` + screenshots) para diagnóstico.
- **Pospuesto**:
  - detección automática de “qué paso de login toca” sin señales explícitas (solo si se expresa como condiciones).

## 2) 2FA / Captcha

- **Riesgo**: ejecución bloqueada por OTP, app, captcha.
- **Mitigación v1**:
  - Tipificar como `AUTH_FAILED` (o `EXTERNAL_*` si se amplía el catálogo) y **detener**.
  - Capturar evidencia ampliada (html_full + screenshots) para auditoría.
- **Pospuesto**:
  - resolución automática de captcha/2FA.

## 3) Overlays/modales/banners (cookies, anuncios, interstitials)

- **Riesgo**: clicks interceptados o elementos no clicables.
- **Mitigación v1**:
  - Condición `no_blocking_overlay` en precondiciones.
  - Error canónico `OVERLAY_BLOCKING` cuando no se pueda interactuar.
  - Evidencia con screenshot en `OVERLAY_BLOCKING`.
- **Pospuesto**:
  - cierre heurístico de overlays sin target determinista.

## 4) SPAs (React/Vue) y estados asincrónicos

- **Riesgo**: DOM cambia sin navegación; condiciones de carga inestables.
- **Mitigación v1**:
  - `network_idle` y `wait_for` basado en condiciones (no sleeps).
  - postcondiciones fuertes (url_matches/toast_contains/element_text_contains critical).
  - same-state revisit detecta estancamiento.
- **Pospuesto**:
  - instrumentación profunda de SPA (route events, store hooks).

## 5) File uploads (inputs ocultos, multi-upload, validaciones)

- **Riesgo**: input file oculto, validación client-side, necesidad de “guardar” posterior.
- **Mitigación v1**:
  - `upload` es crítica por defecto: requiere postcondición fuerte (`upload_completed` o `toast_contains` critical).
  - Evidencia ampliada en upload (html_full + screenshots).
  - si `upload_completed` no es detectable: implementar como DOM/toast change (contrato).
- **Pospuesto**:
  - soporte genérico multi-upload y drag&drop sin input[type=file] estable.

## 6) Timeouts (red lenta, portales pesados)

- **Riesgo**: timeouts por carga o acciones.
- **Mitigación v1**:
  - timeouts por perfil (deterministas).
  - `NAVIGATION_TIMEOUT` tipado.
  - backoff determinista (0.3s/1s/2s) para reintentos permitidos.
- **Pospuesto**:
  - ajuste adaptativo de timeouts.

## 7) Iframes (contenidos embebidos)

- **Riesgo**: targets dentro de iframe; selector no funciona en main frame.
- **Mitigación v1**:
  - target `frame{selector}+inner_target` (máx 1 nivel).
  - fallback a xpath solo si css no sirve (contrato).
- **Pospuesto**:
  - resolución multi-frame profunda y cross-origin compleja.

## 8) Session drift / caducidad / logout silencioso

- **Riesgo**: expiración de sesión, redirección a login, tokens rotos.
- **Mitigación v1**:
  - `url_matches`/`title_contains` para detectar vuelta a login.
  - tipificar como `AUTH_FAILED`.
  - trace con `observation_captured` + evidencia ampliada en fallo.
- **Pospuesto**:
  - refresh automático de sesión sin señales explícitas.

## 9) Rate limits / bloqueos por automatización

- **Riesgo**: throttle, 429, bloqueo temporal.
- **Mitigación v1**:
  - backoff determinista en retries permitidos.
  - `POLICY_HALT` si no progresa y same-state revisits se disparan.
  - evidencia para auditoría.
- **Pospuesto**:
  - estrategias adaptativas por plataforma (jitter, pacing inteligente).





