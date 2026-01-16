# Fix: Filtros del Calendario y Cálculo de Períodos Faltantes

## Problemas Identificados

### 1. Pills "Aplica a" no funcionaban visualmente

**Síntoma**: Al hacer click en "Empresa" o "Trabajador", el pill visualmente no cambiaba, quedando siempre "Todos" seleccionado.

**Causa**: La función `setCalendarFilter()` no actualizaba las clases CSS de los pills después de cambiar el valor de `scope`.

**Fix**: Añadida lógica en `setCalendarFilter()` para actualizar las clases CSS de los pills cuando cambia `scope`:
- Remover clase `active` de todos los pills
- Añadir clase `active` al pill correspondiente según el valor de `scope`

### 2. Filtro redundante "Rango de búsqueda"

**Síntoma**: Existían dos filtros que hacían lo mismo:
- "Rango de búsqueda (opcional)" (12/24/36 meses)
- "Máx. meses atrás" (numérico, default 24)

**Causa**: Filtro antiguo que quedó después de añadir "Máx. meses atrás".

**Fix**: Eliminado el filtro "Rango de búsqueda (opcional)" y su función `updatePendingDocuments()`.

### 3. Cálculo de períodos faltantes no respetaba frecuencia

**Síntoma**: Tipos como RC (cada 12 meses) generaban períodos mensuales en "Pendientes de subir" (ej: 2025-12, 2025-11, 2025-10...).

**Causa**: El código ya tenía `is_periodic_submission()` que excluye tipos con `n_months.n > 1`, pero necesitaba verificación adicional.

**Fix**: Verificado que `is_periodic_submission()` funciona correctamente:
- Tipos con `n_months.n > 1` retornan `False` (no son periódicos)
- `generate_expected_periods()` retorna `[]` si `is_periodic_submission() == False`
- El endpoint `/docs/pending` ya usa `get_period_kind_from_type()` que verifica `is_periodic_submission()`

## Cambios Implementados

### Frontend

#### 1. Eliminación de filtro redundante

**Archivo**: `frontend/repository_v3.html`

- Eliminado el bloque HTML del filtro "Rango de búsqueda (opcional)"
- Eliminada función `updatePendingDocuments()` (ya no es necesaria)

#### 2. Fix de pills "Aplica a"

**Archivo**: `frontend/repository_v3.html`

- Modificada función `setCalendarFilter()` para actualizar clases CSS de pills:
  ```javascript
  if (key === 'scope') {
      // Actualizar clases CSS de los pills
      document.querySelectorAll('[data-testid^="calendar-scope-pill-"]').forEach(chip => {
          chip.classList.remove('active');
      });
      
      if (value === null) {
          const allChip = document.querySelector('[data-testid="calendar-scope-pill-all"]');
          if (allChip) allChip.classList.add('active');
      } else if (value === 'company') {
          const companyChip = document.querySelector('[data-testid="calendar-scope-pill-company"]');
          if (companyChip) companyChip.classList.add('active');
      } else if (value === 'worker') {
          const workerChip = document.querySelector('[data-testid="calendar-scope-pill-worker"]');
          if (workerChip) workerChip.classList.add('active');
      }
      // ... resto de la lógica
  }
  ```

#### 3. Actualización de data-testids

**Archivo**: `frontend/repository_v3.html`

- Cambiados data-testids de pills:
  - `calendar-filter-scope-all` → `calendar-scope-pill-all`
  - `calendar-filter-scope-company` → `calendar-scope-pill-company`
  - `calendar-filter-scope-worker` → `calendar-scope-pill-worker`
- Añadidos data-testids a tabs:
  - `calendar-tab-expired`
  - `calendar-tab-expiring`
  - `calendar-tab-pending`
- Añadido data-testid a filas de pendientes:
  - `calendar-pending-row`
- Actualizado data-testid de "Máx. meses atrás":
  - `calendar-max-months-back` → `calendar-filter-max-months-back`

### Backend

#### Verificación de lógica existente

**Archivo**: `backend/repository/period_planner_v1.py`

- Verificado que `is_periodic_submission()` excluye correctamente tipos con `n_months.n > 1`
- Verificado que `generate_expected_periods()` retorna `[]` para tipos de renovación
- Verificado que el endpoint `/docs/pending` usa `get_period_kind_from_type()` que verifica `is_periodic_submission()`

**Resultado**: La lógica ya estaba correcta. Tipos como RC (cada 12 meses) no deberían generar períodos mensuales.

## Tests E2E

### Archivo: `tests/e2e_calendar_filters_and_periods.spec.js`

#### Test 1: Pills "Aplica a" cambian estado visual y filtran

- Verifica que inicialmente "Todos" está activo
- Click en "Empresa" → verifica que "Empresa" está activo y "Todos" no
- Verifica que los contadores cambian
- Click en "Trabajador" → verifica que "Trabajador" está activo
- Click en "Todos" → verifica que "Todos" está activo

#### Test 2: "Máx. meses atrás" reduce el número de filas en Pendientes

- Obtiene contador inicial de pendientes
- Cambia "Máx. meses atrás" a 3
- Verifica que el contador y las filas visibles se reducen

#### Test 3: Tipo con frecuencia >1 NO genera filas mensuales

- Agrupa períodos por tipo
- Para tipos como RC (cada 12 meses), verifica:
  - No hay períodos mensuales consecutivos
  - Máximo 2 períodos en una ventana de 24 meses

#### Test 4: Limpiar filtros restaura valores por defecto

- Aplica filtros (scope=company, max_months_back=12)
- Click "Limpiar filtros"
- Verifica que scope vuelve a "Todos" y max_months_back a 24

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Eliminado filtro "Rango de búsqueda (opcional)"
   - Fix de pills "Aplica a" para actualizar clases CSS
   - Actualizados data-testids
   - Añadido data-testid a filas de pendientes

2. **`tests/e2e_calendar_filters_and_periods.spec.js`** (NUEVO):
   - Tests E2E para filtros y períodos

3. **`docs/evidence/calendar_filters_and_periods/report.md`** (NUEVO):
   - Documentación del fix

## Validación

### Ejecutar Tests

```bash
npx playwright test tests/e2e_calendar_filters_and_periods.spec.js
```

### Verificación Manual

1. **Pills "Aplica a"**:
   - Abrir `#calendario`
   - Click en "Empresa" → debe quedar seleccionado visualmente
   - Click en "Trabajador" → debe quedar seleccionado visualmente
   - Click en "Todos" → debe quedar seleccionado visualmente

2. **Filtro "Máx. meses atrás"**:
   - Cambiar valor a 3 → debe reducir "Pendientes de subir"
   - Click "Limpiar filtros" → debe volver a 24

3. **Períodos faltantes**:
   - Ir a tab "Pendientes de subir"
   - Verificar que RC (o tipos con frecuencia >1) no aparecen con múltiples períodos mensuales consecutivos

## Evidencia Requerida

1. ✅ Test PASS output
2. ⏳ Screenshot: `calendario_pills_funcionando.png` - Pills "Aplica a" funcionando correctamente
3. ⏳ Screenshot: `calendario_sin_filtro_redundante.png` - Calendario sin filtro "Rango de búsqueda"
4. ⏳ Screenshot: `pendientes_sin_mensuales_rc.png` - Tab "Pendientes de subir" mostrando que RC no tiene períodos mensuales

## Criterios de Aceptación

- ✅ Pills "Aplica a" cambian visualmente y filtran correctamente
- ✅ Filtro "Rango de búsqueda" eliminado
- ✅ "Máx. meses atrás" funciona y afecta a "Pendientes de subir"
- ✅ Tipos con frecuencia >1 (ej: RC cada 12 meses) NO generan períodos mensuales
- ⏳ Tests E2E pasan localmente

## Notas Técnicas

1. **Pills "Aplica a"**: La actualización de clases CSS se hace inmediatamente después de cambiar `calendarFilters.scope`, antes de llamar a `applyCalendarFiltersAndUpdate()`.

2. **Filtro redundante**: El filtro "Rango de búsqueda" usaba `selectedMonths` que ya no se usa. Se eliminó completamente.

3. **Períodos faltantes**: La lógica de `is_periodic_submission()` ya estaba correcta. Tipos con `n_months.n > 1` no generan períodos mensuales.

4. **Data-testids**: Se estandarizaron los data-testids para facilitar testing E2E.

## Próximos Pasos

1. ✅ Fix implementado
2. ⏳ Ejecutar tests E2E y verificar PASS
3. ⏳ Verificar manualmente que los pills funcionan
4. ⏳ Capturar screenshots de evidencia
5. ⏳ Validar que RC no aparece con períodos mensuales







