# Implementación: Estados de Validez y Documentos Pendientes

## Resumen

Se ha implementado un sistema completo de cálculo de estados de validez de documentos y una nueva vista de "Documentos pendientes y próximos vencimientos" que reemplaza la pantalla anterior de "Calendario de documentos".

## Archivos Modificados

### Backend

1. **`backend/repository/document_status_calculator_v1.py`** (NUEVO)
   - Implementa la función `calculate_document_status()` que calcula el estado de validez basado en `computed_validity.valid_to`
   - Estados: `VALID`, `EXPIRING_SOON`, `EXPIRED`, `UNKNOWN`
   - Retorna: `(status, validity_end_date, days_until_expiry)`

2. **`backend/shared/document_repository_v1.py`** (MODIFICADO)
   - Añadido enum `DocumentValidityStatusV1` (VALID, EXPIRING_SOON, EXPIRED, UNKNOWN)
   - Añadidos campos a `DocumentInstanceV1`:
     - `validity_status: DocumentValidityStatusV1`
     - `validity_end_date: Optional[date]`
     - `days_until_expiry: Optional[int]`

3. **`backend/repository/document_repository_routes.py`** (MODIFICADO)
   - Endpoint `/api/repository/docs` actualizado:
     - Calcula `validity_status` para cada documento usando `calculate_document_status()`
     - Añade `validity_status`, `validity_end_date`, `days_until_expiry` a la respuesta
     - Soporta filtro `?validity_status=EXPIRED|EXPIRING_SOON|VALID`
   - Endpoint `/api/repository/docs/pending` (NUEVO):
     - Retorna documentos expirados, próximos a expirar y períodos faltantes
     - Agrupa por tipo y sujeto
     - Usa `PeriodPlannerV1` para detectar períodos faltantes

4. **`backend/repository/period_planner_v1.py`** (MODIFICADO)
   - Añadida función `infer_period_key()` para inferir `period_key` desde `issue_date`, `name_date`, o `filename`

### Frontend

5. **`frontend/repository_v3.html`** (MODIFICADO)
   - **Función `loadBuscar()`**:
     - Actualizada para consumir `validity_status` del backend
     - Filtro por `validity_status` añadido a `performSearch()`
   - **Función `renderSearchResults()`**:
     - Muestra badges de estado con colores:
       - Verde: `VALID`
       - Amarillo: `EXPIRING_SOON`
       - Rojo: `EXPIRED`
     - Muestra `validity_end_date` y `days_until_expiry`
   - **Función `loadCalendario()`** (REDISEÑADA):
     - Nueva estructura HTML: "Documentos pendientes y próximos vencimientos"
     - Eliminados campos obligatorios "¿Qué documento?" y "¿De quién?"
     - **Filtros ampliados añadidos** (paridad con #buscar):
       - Buscar (texto libre): filtra por filename, type_name, type_code, subject_name
       - Tipo de documento (select): filtra por type_id
       - Aplica a (pills): Todos | Empresa | Trabajador
       - Sujeto (select): dinámico según "Aplica a"
       - Botón "Limpiar filtros"
     - Filtrado client-side sobre datos de `/api/repository/docs/pending`
     - Contadores de tabs reflejan resultados filtrados
     - Mensajes diferenciados: "No hay documentos con estos filtros" vs "No hay documentos"
   - **Nuevas funciones de filtrado**:
     - `applyCalendarFilters()`: función única para filtrar las 3 listas (expired, expiringSoon, missing)
     - `normalizeString()`: normaliza strings (sin tildes, case-insensitive)
     - `debounceCalendarFilter()`: debounce para búsqueda de texto
     - `setCalendarFilter()`: establece filtro y actualiza UI
     - `clearCalendarFilters()`: limpia todos los filtros
   - **Variables globales añadidas**:
     - `calendarFilters`: objeto con estado de filtros
     - `calendarSubjects`: cache de subjects (empresas y trabajadores)
     - `window.pendingDocumentsDataRaw`: datos sin filtrar
     - `window.pendingDocumentsData`: datos filtrados actuales
     - Tabs para: Expirados, Expiran pronto, Pendientes de subir
     - Carga datos desde `/api/repository/docs/pending`
     - Carga subjects desde `/api/repository/subjects` para nombres legibles
   - **Función `renderPendingDocuments()`** (NUEVA):
     - Renderiza las 3 secciones (expired, expiring_soon, missing)
     - Agrupa por sujeto (empresa/trabajador)
     - Muestra: Tipo, Archivo/Período, Estado, Fecha caducidad, Acciones
     - Botones "Resubir" y "Subir documento" con navegación a Upload con prefill
   - **Funciones auxiliares** (NUEVAS):
     - `showPendingSection()`: Cambia entre tabs
     - `updatePendingDocuments()`: Recarga con nuevo rango
     - `navigateToUploadForDocument()`: Navega a Upload con prefill para reemplazar
     - `navigateToUploadForPeriod()`: Navega a Upload con prefill para período faltante
   - **Función `formatDate()`**: Helper para formatear fechas (ya existía, reutilizada)

### Tests

6. **`tests/e2e_calendar_pending_smoke.spec.js`** (NUEVO)
   - Test 1: Verificar que "Buscar documentos" muestra estados reales (no "Desconocido")
   - Test 2: Verificar que Calendario muestra tabs y renderiza correctamente
   - Test 3: Verificar que click en tab "Pendientes" renderiza lista
   - Test 4: Verificar navegación a Upload desde botón de acción

## Cálculo de Estado de Validez

### Lógica

El cálculo se realiza en `calculate_document_status()`:

1. **Obtener fecha de caducidad**:
   - Primero desde `doc.computed_validity.valid_to`
   - Si no existe, desde `doc.validity_override.valid_to` (override manual)
   - Si no existe, retorna `UNKNOWN`

2. **Calcular días hasta caducidad**:
   ```python
   days_until_expiry = (validity_end_date - today).days
   ```

3. **Determinar estado**:
   - `EXPIRED`: `days_until_expiry < 0` (ya expirado)
   - `EXPIRING_SOON`: `0 <= days_until_expiry <= threshold` (default: 30 días)
   - `VALID`: `days_until_expiry > threshold` (válido)

### Threshold

El threshold por defecto es **30 días**, pero puede configurarse:
- En `calculate_document_status()`: parámetro `expiring_soon_threshold_days`
- En endpoint `/docs/pending`: `months_ahead` (se convierte a días: `months_ahead * 30`)

### Ejemplo

```python
# Documento con valid_to = 2025-12-31
# Hoy = 2026-01-15
# days_until_expiry = -15
# status = EXPIRED

# Documento con valid_to = 2026-02-10
# Hoy = 2026-01-15
# days_until_expiry = 26
# threshold = 30
# status = EXPIRING_SOON

# Documento con valid_to = 2026-03-15
# Hoy = 2026-01-15
# days_until_expiry = 59
# threshold = 30
# status = VALID
```

## Endpoints del Backend

### GET `/api/repository/docs`

Lista documentos con estados calculados.

**Query params:**
- `validity_status`: Filtrar por estado (VALID, EXPIRING_SOON, EXPIRED)
- `type_id`, `scope`, `status`: Filtros existentes

**Response:**
```json
[
  {
    "doc_id": "...",
    "type_id": "...",
    "validity_status": "EXPIRED",
    "validity_end_date": "2025-08-31",
    "days_until_expiry": -126,
    ...
  }
]
```

### GET `/api/repository/docs/pending`

Obtiene documentos pendientes, expirados y próximos a expirar.

**Query params:**
- `months_ahead`: Meses hacia adelante para considerar "expira pronto" (default: 3)

**Response:**
```json
{
  "expired": [
    {
      "doc_id": "...",
      "type_id": "...",
      "scope": "company",
      "company_key": "...",
      "validity_status": "EXPIRED",
      "validity_end_date": "2025-08-31",
      "days_until_expiry": -126,
      ...
    }
  ],
  "expiring_soon": [...],
  "missing": [
    {
      "type_id": "...",
      "type_name": "...",
      "scope": "worker",
      "company_key": "...",
      "person_key": "...",
      "period_key": "2025-12",
      "period_start": "2025-12-01",
      "period_end": "2025-12-31",
      "status": "MISSING",
      "days_late": null
    }
  ]
}
```

## Navegación con Prefill

### Desde "Resubir" (documento existente)

```javascript
navigateTo('subir', {
  type_id: '...',
  scope: 'company|worker',
  company_key: '...',  // si scope === 'company'
  person_key: '...',   // si scope === 'worker'
  replace_doc_id: '...' // ID del documento a reemplazar
});
```

### Desde "Subir documento" (período faltante)

```javascript
navigateTo('subir', {
  type_id: '...',
  scope: 'company|worker',
  company_key: '...',  // si scope === 'company'
  person_key: '...',   // si scope === 'worker'
  period_key: '2025-12' // Período a subir
});
```

La pantalla Upload detecta estos parámetros y preselecciona tipo y sujeto automáticamente.

## Cambios en UX

### Antes
- Calendario requería seleccionar documento y sujeto obligatoriamente
- No mostraba documentos expirados automáticamente
- No mostraba períodos faltantes
- Estados siempre "Desconocido"

### Después
- Vista automática de documentos que requieren atención
- Tabs claros: Expirados, Expiran pronto, Pendientes
- Agrupación por sujeto (empresa/trabajador)
- Nombres legibles (no IDs crudos)
- Acciones directas: "Resubir" / "Subir documento"
- Estados reales calculados dinámicamente

## Testing

### Ejecutar Tests E2E

```bash
npx playwright test tests/e2e_calendar_pending_smoke.spec.js
```

### Verificar Endpoints

```bash
# Listar documentos expirados
curl "http://127.0.0.1:8000/api/repository/docs?validity_status=EXPIRED"

# Obtener documentos pendientes
curl "http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3"
```

## Fix de Inconsistencia (CRÍTICO)

### Problema
En `#buscar` se mostraban documentos expirados, pero en `#calendario` el tab Expirados mostraba 0.

### Causa Raíz
**BUG DE ROUTING EN FASTAPI**: La ruta `/docs/{doc_id}` capturaba `/docs/pending` porque FastAPI interpretaba "pending" como un `doc_id`. El orden de rutas importa: las rutas específicas deben ir ANTES que las rutas con parámetros.

### Fix Aplicado
1. **Reordenar rutas**: Movida `/docs/pending` ANTES de `/docs/{doc_id}` (línea 444 → antes de línea 547)
2. **Consistencia garantizada**: Ambos endpoints usan:
   - Misma fuente: `store.list_documents()`
   - Misma función: `calculate_document_status()`
   - Mismo enum: `DocumentValidityStatus`
3. **Manejo de errores**: Añadido try/except en `/docs/pending`

### Validación
- Test de consistencia creado: `tests/test_consistency_docs_pending.py`
- Documentación: `docs/evidence/validity_status_and_pending/CONSISTENCY_DEBUG.md`

**IMPORTANTE**: El servidor backend debe reiniciarse para que el fix surta efecto.

## Filtros Ampliados del Calendario

### Implementación

Se han añadido filtros ampliados al calendario con paridad visual y funcional con la vista de "Buscar documentos":

1. **Buscar (texto libre)**:
   - Placeholder: "Buscar por tipo, sujeto o archivo…"
   - Filtra por: `filename`, `type_name`, `type_code`, `subject_name`
   - Normalización: sin tildes, case-insensitive (reutiliza `normalizeString()`)

2. **Tipo de documento (select)**:
   - Default: "Todos los tipos"
   - Opciones: cargadas del mismo origen que #buscar (tipos existentes)

3. **Aplica a (pills)**:
   - "Todos | Empresa | Trabajador"
   - Mismo componente visual que Upload/Buscar (filter-chip)

4. **Sujeto (select)**:
   - Default: "Todos"
   - Opciones dinámicas según "Aplica a":
     - Si "Aplica a" = Empresa: solo empresas
     - Si "Aplica a" = Trabajador: solo trabajadores
     - Si "Aplica a" = Todos: ambas listas
   - Fuente: `/api/repository/subjects` (cache en `calendarSubjects`)

5. **Botón "Limpiar filtros"**:
   - Resetea todos los filtros a valores por defecto
   - Reconstruye opciones del select de sujeto según scope actual

### Funcionalidad Técnica

- **Filtrado client-side**: Los filtros actúan sobre el payload ya recibido de `/api/repository/docs/pending` (no requiere cambios en backend)
- **Función única**: `applyCalendarFilters(pendingData, filters)` aplica filtros a las 3 listas (expired, expiringSoon, missing)
- **Contadores actualizados**: Los contadores de tabs reflejan resultados filtrados, no totales brutos
- **Mensajes diferenciados**: 
   - Si hay filtros activos y 0 resultados: "No hay documentos con estos filtros"
   - Si no hay filtros y 0 resultados: "No hay documentos expirados" (genérico)
- **Persistencia suave**: Los filtros se mantienen al cambiar de tab
- **Data-testids**: Todos los filtros tienen `data-testid` para E2E testing

### Tests E2E

**Archivo**: `tests/e2e_calendar_filters.spec.js`

Tests implementados:
1. Smoke: Verificar que existen todos los filtros (data-testids)
2. Filtrado por "Aplica a" = Trabajador reduce resultados
3. Filtrado por texto reduce resultados
4. Limpiar filtros restaura resultados originales
5. Cambiar de tab mantiene filtros

## Notas de Implementación

1. **Cache de Subjects**: Se carga una vez al entrar a Calendario desde `/api/repository/subjects` para evitar múltiples requests.

2. **Fallback de Nombres**: Si no se encuentra el nombre de un sujeto, se muestra "(sin nombre)" en lugar de romper la UI.

3. **Agrupación por Sujeto**: Los documentos se agrupan por `scope + company_key + person_key` para mostrar todos los documentos de un mismo sujeto juntos.

4. **Ordenamiento**:
   - Expirados: Más antiguos primero (por `validity_end_date`)
   - Expiran pronto: Más próximos primero (por `validity_end_date`)

5. **Períodos Faltantes**: Solo se generan para tipos periódicos (no `NONE`) y para sujetos que ya tienen al menos un documento del tipo.

## Próximos Pasos (Opcionales)

1. Expandir períodos faltantes para incluir todos los sujetos del sistema (no solo los que ya tienen documentos)
2. Añadir filtros adicionales en la vista de Calendario (por tipo, por empresa, etc.)
3. Añadir notificaciones/push cuando hay documentos próximos a expirar
4. Exportar reporte de documentos pendientes a PDF/Excel

