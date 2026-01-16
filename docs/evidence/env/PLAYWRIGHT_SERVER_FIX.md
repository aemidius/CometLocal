# Fix ERR_CONNECTION_REFUSED en Playwright Tests

**Fecha:** 2026-01-06  
**Objetivo:** Reducir drásticamente los 48 fallos Playwright (ERR_CONNECTION_REFUSED) arreglando la causa raíz del server.

## Problema Identificado

Muchos tests estaban usando `localhost:8000` en lugar de `127.0.0.1:8000`, lo que causaba problemas de conexión en Windows. Además, la configuración de Playwright no tenía un health check URL configurado.

## Cambios Realizados

### 1. playwright.config.js

**Antes:**
```javascript
module.exports = {
  testDir: './tests',
  timeout: 30000,
  use: {
    headless: false,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: getPythonCommand(),
    port: 8000,
    timeout: 120000,
    reuseExistingServer: false,
    cwd: __dirname,
    env: { ... },
  },
};
```

**Después:**
```javascript
module.exports = {
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:8000',  // ✅ Agregado baseURL
    headless: false,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: getPythonCommand(),
    url: 'http://127.0.0.1:8000/api/health',  // ✅ Health check URL
    timeout: 120000,
    reuseExistingServer: false,
    cwd: __dirname,
    env: { ... },
    stdout: 'pipe',  // ✅ Logging del servidor
    stderr: 'pipe',
  },
};
```

### 2. Tests Actualizados

Reemplazado `localhost:8000` por `127.0.0.1:8000` en los siguientes archivos:

- `tests/e2e_calendar_filters_and_periods.spec.js`
- `tests/e2e_calendar_periodicity.spec.js`
- `tests/e2e_fix_pdf_viewing.spec.js`
- `tests/e2e_upload_scope_filter.spec.js`
- `tests/e2e_validity_start.spec.js`
- `tests/e2e_repository_settings.spec.js`
- `tests/e2e_search_docs_actions.spec.js`
- `tests/e2e_upload_validity_persistence.spec.js`
- `tests/e2e_upload_validity_start_date.spec.js`
- `tests/e2e_upload_preview.spec.js`
- `tests/e2e_upload_clear_all.spec.js`

## Resultados

### Antes del Fix
- **48 tests fallidos** con ERR_CONNECTION_REFUSED
- Servidor no siempre arrancaba antes de los tests
- Health check no configurado

### Después del Fix
- **0 errores ERR_CONNECTION_REFUSED** relacionados con configuración del servidor
- Servidor arranca correctamente antes de cada test
- Health check funciona correctamente (`/api/health` responde 200 OK)
- Tests restantes que fallan son por lógica de negocio, no por tooling

## Verificación

### Health Check
```bash
curl http://127.0.0.1:8000/api/health
# Respuesta: {"status":"ok","build_id":"...","cae_plan_patch":"v1.2.0"}
```

### Logs del Servidor
El servidor muestra correctamente:
```
[WebServer] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
[WebServer] INFO:     127.0.0.1:XXXXX - "GET /api/health HTTP/1.1" 200 OK
```

## Archivos Modificados

1. `playwright.config.js` - Agregado baseURL y health check URL
2. `tests/e2e_*.spec.js` (11 archivos) - Reemplazado localhost por 127.0.0.1

## Próximos Pasos

Los tests que aún fallan son por problemas de lógica de negocio (elementos no encontrados, timeouts de UI, etc.), no por problemas de tooling o configuración del servidor.


