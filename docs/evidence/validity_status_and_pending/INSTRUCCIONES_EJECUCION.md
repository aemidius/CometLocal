# Instrucciones de Ejecución y Verificación

## Prerrequisitos

1. Servidor backend corriendo en `http://127.0.0.1:8000`
2. Playwright instalado: `npm install -g playwright` o `npx playwright install`

## Verificación de Endpoints Backend

### 1. Verificar endpoint `/api/repository/docs` con estados

```bash
# Listar todos los documentos con estados calculados
curl "http://127.0.0.1:8000/api/repository/docs" | jq '.[0] | {doc_id, type_id, validity_status, validity_end_date, days_until_expiry}'

# Filtrar por documentos expirados
curl "http://127.0.0.1:8000/api/repository/docs?validity_status=EXPIRED" | jq 'length'

# Filtrar por documentos que expiran pronto
curl "http://127.0.0.1:8000/api/repository/docs?validity_status=EXPIRING_SOON" | jq 'length'
```

**Resultado esperado:**
- Cada documento debe tener `validity_status`: `VALID`, `EXPIRING_SOON`, `EXPIRED`, o `UNKNOWN`
- `validity_end_date` debe ser una fecha ISO (YYYY-MM-DD) o `null`
- `days_until_expiry` debe ser un número entero (positivo si futuro, negativo si pasado)

### 2. Verificar endpoint `/api/repository/docs/pending`

```bash
# Obtener documentos pendientes
curl "http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3" | jq '{expired: (.expired | length), expiring_soon: (.expiring_soon | length), missing: (.missing | length)}'
```

**Resultado esperado:**
- JSON con 3 arrays: `expired`, `expiring_soon`, `missing`
- Cada array puede estar vacío `[]` si no hay documentos en esa categoría
- Los documentos en `expired` y `expiring_soon` deben tener `validity_status` correspondiente
- Los items en `missing` deben tener `type_id`, `scope`, `period_key`, etc.

## Ejecución de Tests E2E

### Ejecutar todos los tests

```bash
npx playwright test tests/e2e_calendar_pending_smoke.spec.js
```

### Ejecutar un test específico

```bash
# Test 1: Estados reales en Buscar documentos
npx playwright test tests/e2e_calendar_pending_smoke.spec.js -g "Test 1"

# Test 2: Tabs de Calendario
npx playwright test tests/e2e_calendar_pending_smoke.spec.js -g "Test 2"

# Test 3: Tab Pendientes
npx playwright test tests/e2e_calendar_pending_smoke.spec.js -g "Test 3"

# Test 4: Navegación a Upload
npx playwright test tests/e2e_calendar_pending_smoke.spec.js -g "Test 4"
```

### Ejecutar en modo headed (ver navegador)

```bash
npx playwright test tests/e2e_calendar_pending_smoke.spec.js --headed
```

### Generar reporte HTML

```bash
npx playwright test tests/e2e_calendar_pending_smoke.spec.js --reporter=html
```

## Verificación Manual en Frontend

### 1. Verificar "Buscar documentos"

1. Abrir `http://127.0.0.1:8000/repository_v3.html#buscar`
2. Verificar que la tabla muestra badges de estado:
   - Verde: "Válido"
   - Amarillo: "Expira pronto (X días)"
   - Rojo: "Expirado (hace X días)"
3. Verificar que NO aparece "Desconocido" (salvo casos reales de error)
4. Probar filtros por estado: "Válido", "Expira pronto", "Expirado"

### 2. Verificar "Calendario / Pendientes"

1. Abrir `http://127.0.0.1:8000/repository_v3.html#calendario`
2. Verificar que se muestran 3 tabs:
   - "Expirados" con badge de conteo
   - "Expiran pronto" con badge de conteo
   - "Pendientes de subir" con badge de conteo
3. Click en cada tab y verificar que se renderiza contenido (aunque sea mensaje "No hay...")
4. Verificar que los documentos están agrupados por sujeto (empresa/trabajador)
5. Verificar que se muestran nombres legibles (no IDs crudos)
6. Verificar que hay botones "Resubir" o "Subir documento"
7. Click en un botón y verificar que navega a `#subir` con query params:
   - `type_id=...`
   - `scope=...`
   - `company_key=...` o `person_key=...`
   - `period_key=...` (si aplica)

### 3. Verificar navegación con prefill

1. Desde Calendario, click en "Resubir" o "Subir documento"
2. Verificar que la pantalla Upload se carga con:
   - Tipo de documento preseleccionado
   - Sujeto (empresa/trabajador) preseleccionado
   - Período preseleccionado (si aplica)
3. Verificar que se puede subir el documento sin tener que rellenar campos manualmente

## Capturas de Pantalla Recomendadas

Para evidencia, capturar:

1. **Buscar documentos con estados reales**
   - URL: `#buscar`
   - Mostrar tabla con badges de colores
   - Mostrar filtros por estado funcionando

2. **Calendario - Tab Expirados**
   - URL: `#calendario` (tab "Expirados" activo)
   - Mostrar lista de documentos expirados agrupados por sujeto
   - Mostrar botones "Resubir"

3. **Calendario - Tab Pendientes**
   - URL: `#calendario` (tab "Pendientes de subir" activo)
   - Mostrar lista de períodos faltantes
   - Mostrar botones "Subir documento"

4. **Upload con prefill**
   - URL: `#subir?type_id=...&scope=...&company_key=...`
   - Mostrar campos preseleccionados

## Troubleshooting

### Endpoint `/docs/pending` devuelve `null`

- Verificar que el servidor backend está corriendo
- Verificar logs del servidor para errores
- Verificar que hay documentos en la base de datos
- Verificar que los documentos tienen `computed_validity.valid_to` calculado

### Tests E2E fallan

- Verificar que el servidor está corriendo en `http://127.0.0.1:8000`
- Verificar que Playwright está instalado: `npx playwright install`
- Ejecutar en modo headed para ver qué está pasando: `--headed`
- Verificar que hay datos en la base de datos (documentos, tipos, subjects)

### Frontend no muestra estados

- Abrir consola del navegador (F12)
- Verificar que no hay errores JavaScript
- Verificar que las requests a `/api/repository/docs` retornan `validity_status`
- Verificar que `renderSearchResults()` está siendo llamada

### Nombres de sujetos no aparecen

- Verificar que `/api/repository/subjects` retorna datos
- Verificar que `subjectsCache` se está cargando en `loadCalendario()`
- Verificar que `getSubjectName()` está usando el cache correctamente







