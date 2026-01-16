# CAE Runs Evidence

Este directorio contiene la evidencia de ejecución de planes CAE (CometLocal Automated Execution).

## Estructura

Cada ejecución genera una carpeta con el siguiente formato:
```
CAERUN-YYYYMMDD-HHMMSS-<shortid>/
├── manifest.json          # Metadatos del run (plan_id, item, timestamps, mode)
├── run_finished.json      # Estado final del run (status, summary, error si aplica)
└── screenshots/           # Screenshots capturados durante la ejecución
    └── ...
```

## Modos de Ejecución

### FAKE Mode (Simulación)

Para ejecutar en modo FAKE (sin abrir navegador, solo genera evidencia simulada):

```bash
export CAE_EXECUTOR_MODE=FAKE
# O en Windows:
set CAE_EXECUTOR_MODE=FAKE
```

En modo FAKE:
- No se abre navegador
- No se conecta a eGestiona
- Genera evidencia simulada (manifest, run_finished.json, screenshot fake)
- Retorna status SUCCESS (simulado)
- Útil para tests y desarrollo

### REAL Mode (Ejecución Real)

Para ejecutar en modo REAL (usa Playwright y eGestiona):

```bash
export CAE_EXECUTOR_MODE=REAL
# O en Windows:
set CAE_EXECUTOR_MODE=REAL
# O simplemente no definir la variable (REAL es el default)
```

En modo REAL:
- Abre navegador con Playwright (headless=False por defecto)
- Se conecta a eGestiona
- Ejecuta acciones reales (login, navegación, upload)
- Genera evidencia real (screenshots numerados 01_, 02_, etc., manifest, run_finished.json)
- Requiere credenciales configuradas en `data/refs/secrets.json`

**IMPORTANTE**: El modo REAL solo está disponible para uso manual. Los tests E2E usan `dry_run=true` que siempre ejecuta en modo FAKE.

#### Requisitos para Modo REAL

1. **Credenciales en `data/refs/secrets.json`**:
   - Debe existir una coordination en `data/refs/platforms.json` con:
     - `client_code`: Código de cliente
     - `username`: Usuario
     - `password_ref`: Referencia al secreto (ej: "pw:egestiona:kern")
   - El secreto debe estar en `data/refs/secrets.json` con la clave `password_ref`

2. **Documento en el repositorio**:
   - El item del plan debe tener `suggested_doc_id` o debe existir un documento que coincida con type_id, sujeto y período
   - El PDF del documento debe existir en `data/repository/docs/<doc_id>.pdf`

3. **Playwright instalado**:
   ```bash
   pip install playwright
   playwright install chromium
   ```

#### Ejemplo de Configuración

`data/refs/platforms.json`:
```json
{
  "schema_version": "v1",
  "platforms": [
    {
      "key": "egestiona",
      "base_url": "https://coordinate.egestiona.es/login?origen=subcontrata",
      "coordinations": [
        {
          "label": "Kern",
          "client_code": "GRUPO_INDUKERN",
          "username": "F63161988",
          "password_ref": "pw:egestiona:kern"
        }
      ]
    }
  ]
}
```

`data/refs/secrets.json`:
```json
{
  "schema_version": "v1",
  "secrets": {
    "pw:egestiona:kern": "TU_PASSWORD_AQUI"
  }
}
```

**NOTA**: No commitees `secrets.json` con valores reales. Usa variables de entorno o un sistema de gestión de secretos.

## Dry Run

El parámetro `dry_run=true` en el endpoint de ejecución:
- Siempre ejecuta en modo FAKE (independientemente de `CAE_EXECUTOR_MODE`)
- No modifica datos reales
- Útil para validar el flujo sin riesgo

## Allowlist (Hard Scope)

Por seguridad, la ejecución WRITE está limitada a un allowlist hardcoded:

- `company_key`: "TEDELAB" (o la clave real del repositorio)
- `person_key`: "EMILIO" (o None si scope es company)

Si el plan tiene `company_key` o `person_key` fuera del allowlist, la ejecución será BLOCKED.

## Ejemplo de Uso

### 1. Generar un Plan

```bash
curl -X POST http://127.0.0.1:8000/api/cae/plan \
  -H "Content-Type: application/json" \
  -d '{
    "scope": {
      "platform_key": "egestiona",
      "type_ids": ["T104_AUTONOMOS_RECEIPT"],
      "company_key": "TEDELAB",
      "person_key": "EMILIO",
      "mode": "PREPARE_WRITE"
    }
  }'
```

**Nota**: El request debe incluir el campo `scope` que contiene `CAEScopeContextV1`.

### 2. Obtener Challenge

```bash
curl -X POST http://127.0.0.1:8000/api/cae/execute/CAEPLAN-XXXXX/challenge \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3. Ejecutar (Dry Run)

```bash
curl -X POST http://127.0.0.1:8000/api/cae/execute/CAEPLAN-XXXXX \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_token": "...",
    "challenge_response": "EJECUTAR CAEPLAN-XXXXX",
    "dry_run": true
  }'
```

### 4. Ejecutar (REAL - Requiere credenciales)

**ADVERTENCIA**: Esto ejecuta acciones reales en eGestiona. Solo usar con precaución.

```bash
# Asegurar que CAE_EXECUTOR_MODE=REAL (o no definir, es el default)
export CAE_EXECUTOR_MODE=REAL

curl -X POST http://127.0.0.1:8000/api/cae/execute/CAEPLAN-XXXXX \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_token": "...",
    "challenge_response": "EJECUTAR CAEPLAN-XXXXX",
    "dry_run": false
  }'
```

**Respuesta exitosa**:
```json
{
  "run_id": "CAERUN-20260106-123456-abc123",
  "status": "SUCCESS",
  "evidence_path": "data/docs/evidence/cae_runs/CAERUN-20260106-123456-abc123",
  "summary": {
    "items_processed": 1,
    "items_success": 1,
    "items_failed": 0
  },
  "started_at": "2026-01-06T12:34:56",
  "finished_at": "2026-01-06T12:35:30"
}
```

**Evidencia generada**:
- `manifest.json`: Metadatos del run
- `run_finished.json`: Estado final
- `screenshots/01_login.png`: Screenshot después del login
- `screenshots/02_dashboard.png`: Dashboard principal
- `screenshots/03_listado.png`: Grid de pendientes
- `screenshots/04_detail.png`: Detalle del pendiente
- `screenshots/05_uploaded.png`: Después de subir PDF
- `screenshots/06_confirmation.png`: Confirmación final

## Validaciones

La ejecución valida:
- Plan existe (404 si no)
- Plan.decision == READY (409 si no)
- Plan.scope.platform_key == "egestiona" (400 si no)
- Plan.scope.mode in ["PREPARE_WRITE", "WRITE"] (409 si no)
- Challenge token válido y no expirado (403 si no)
- Challenge response exacto (403 si no)
- Allowlist (BLOCKED si no)
- Todos los items tienen status == PLANNED (BLOCKED si no)
- MVP: solo 1 item (BLOCKED si más)

## Estados del Run

- `SUCCESS`: Ejecución completada exitosamente
- `FAILED`: Ejecución falló (error durante la ejecución)
- `BLOCKED`: Ejecución bloqueada (validaciones fallaron)

## Notas de Seguridad

- Los challenges tienen TTL de 5 minutos
- Los challenges se guardan en `data/refs/cae_challenges/` (sin secretos)
- Las credenciales nunca se guardan en la evidencia
- El allowlist es hardcoded y no se puede cambiar sin modificar código

