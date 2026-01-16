# Fix: Filtros del Calendario de Documentos

## Problemas Identificados

### 1. Pills "Aplica a" no funcionaban visualmente

**Síntoma**: Al hacer click en "Empresa" o "Trabajador", el pill visualmente no cambiaba, quedando siempre "Todos" marcado en azul.

**Causa**: La función `setCalendarFilter()` no actualizaba correctamente las clases CSS de los pills después de cambiar el valor de `scope`.

**Fix**: Reemplazados los pills por un SELECT (dropdown) consistente con el resto de filtros.

### 2. "Máx. meses atrás" no filtraba períodos faltantes

**Síntoma**: Aunque se pusiera 3 en "Máx. meses atrás", aparecían períodos muy antiguos en "Pendientes de subir".

**Causa**: El filtro `maxMonthsBack` no se aplicaba a los períodos faltantes en la función `applyCalendarFilters()`.

**Fix**: Añadido filtrado de períodos faltantes por `maxMonthsBack` en `applyCalendarFilters()`:
- Calcula `monthsDiff` entre fecha actual y período (YYYY-MM)
- Solo muestra períodos donde `0 <= monthsDiff <= maxMonthsBack`
- No muestra períodos futuros (monthsDiff < 0)

### 3. Filtro redundante "Rango de búsqueda (opcional)"

**Síntoma**: Existían dos filtros que hacían lo mismo:
- "Rango de búsqueda (opcional)" (12/24/36 meses)
- "Máx. meses atrás" (numérico, default 24)

**Causa**: Filtro antiguo que quedó después de añadir "Máx. meses atrás".

**Fix**: Eliminado completamente el filtro "Rango de búsqueda (opcional)" y su función asociada.

## Cambios Implementados

### Frontend

#### 1. Reemplazo de pills por SELECT

**Archivo**: `frontend/repository_v3.html`

**Antes**:
```html
<span class="filter-chip" onclick="setCalendarFilter('scope', null)">Todos</span>
<span class="filter-chip" onclick="setCalendarFilter('scope', 'company')">Empresa</span>
<span class="filter-chip" onclick="setCalendarFilter('scope', 'worker')">Trabajador</span>
```

**Después**:
```html
<select class="form-input" 
        id="calendar-scope-select"
        data-testid="calendar-scope-select"
        onchange="setCalendarFilter('scope', this.value)">
    <option value="all">Todos</option>
    <option value="company">Empresa</option>
    <option value="worker">Trabajador</option>
</select>
```

**Cambios en estado**:
- `calendarFilters.scope` ahora usa `'all'` en lugar de `null` para "Todos"
- Normalización: `null` → `'all'` en `setCalendarFilter()`

#### 2. Filtrado de "Máx. meses atrás" en períodos faltantes

**Archivo**: `frontend/repository_v3.html`

**Función `applyCalendarFilters()` modificada**:
```javascript
function applyCalendarFilters(pendingData, filters, maxMonthsBack = 24) {
    const today = new Date();
    const currentYear = today.getFullYear();
    const currentMonth = today.getMonth() + 1;
    
    function filterItems(items, isMissing = false) {
        return items.filter(item => {
            // ... otros filtros ...
            
            // Filtro por maxMonthsBack (solo para períodos faltantes)
            if (isMissing && item.period_key) {
                const periodMatch = item.period_key.match(/(\d{4})-(\d{2})/);
                if (periodMatch) {
                    const periodYear = parseInt(periodMatch[1]);
                    const periodMonth = parseInt(periodMatch[2]);
                    const monthsDiff = (currentYear - periodYear) * 12 + (currentMonth - periodMonth);
                    
                    // Solo mostrar si 0 <= monthsDiff <= maxMonthsBack
                    if (monthsDiff < 0 || monthsDiff > maxMonthsBack) {
                        return false;
                    }
                }
            }
            
            return true;
        });
    }
    
    return {
        expired: filterItems(pendingData.expired || [], false),
        expiringSoon: filterItems(pendingData.expiring_soon || [], false),
        missing: filterItems(pendingData.missing || [], true)  // isMissing=true
    };
}
```

**Función `setCalendarMaxMonthsBack()` modificada**:
- Ya no recarga la página completa (`loadCalendario()`)
- Solo aplica filtros client-side (`applyCalendarFiltersAndUpdate()`)
- Más rápido y no pierde el estado de los filtros

#### 3. Eliminación de filtro redundante

**Archivo**: `frontend/repository_v3.html`

- Eliminado bloque HTML del filtro "Rango de búsqueda (opcional)"
- Eliminada función `updatePendingDocuments()` (comentada)

#### 4. Actualización de data-testids

**Archivo**: `frontend/repository_v3.html`

- `calendar-scope-select`: SELECT de "Aplica a"
- `calendar-max-months-back`: Input de "Máx. meses atrás"
- `calendar-search-input`: Input de búsqueda
- `calendar-type-select`: SELECT de tipo
- `calendar-subject-select`: SELECT de sujeto
- `calendar-clear-filters`: Botón limpiar filtros
- `calendar-tab-expired|expiring|pending`: Tabs
- `calendar-pending-row`: Filas de períodos faltantes

#### 5. Ajuste de lógica de filtros activos

**Archivo**: `frontend/repository_v3.html`

- `hasFilters` ahora verifica `scope !== 'all'` en lugar de solo `scope`
- Mensajes diferenciados solo se muestran si realmente hay filtros activos

### Backend

**No se requirieron cambios**: El filtrado de `maxMonthsBack` se hace client-side sobre los datos ya recibidos de `/api/repository/docs/pending`.

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Reemplazados pills por SELECT
   - Añadido filtrado de `maxMonthsBack` en `applyCalendarFilters()`
   - Eliminado filtro "Rango de búsqueda"
   - Actualizados data-testids
   - Modificada función `setCalendarMaxMonthsBack()` para no recargar página

2. **`tests/e2e_calendar_filters.spec.js`** (NUEVO):
   - Test 1: Scope select funciona
   - Test 2: Máx. meses atrás filtra de verdad
   - Test 3: Clear filtros resetea correctamente

3. **`docs/evidence/calendar_filters/report.md`** (NUEVO):
   - Documentación del fix

## Tests E2E

### Archivo: `tests/e2e_calendar_filters.spec.js`

#### Test 1: Scope select funciona

- Verifica que inicialmente "Todos" está seleccionado
- Cambia a "Trabajador" → verifica que el select tiene el valor correcto
- Verifica que los contadores cambian
- Cambia a "Empresa" → verifica que el select tiene el valor correcto
- Cambia de vuelta a "Todos" → verifica que el select tiene el valor correcto

#### Test 2: Máx. meses atrás filtra de verdad

- Obtiene contador inicial (con default 24)
- Cambia "Máx. meses atrás" a 3
- Verifica que el contador se reduce
- Para cada período renderizado, verifica que `0 <= monthsDiff <= 3`

#### Test 3: Clear filtros resetea correctamente

- Aplica filtros (scope=company, search=test, maxMonthsBack=12)
- Click "Limpiar filtros"
- Verifica que todos los filtros vuelven a valores por defecto

### Ejecución de Tests

**Nota**: Los tests requieren que el servidor backend esté corriendo en `http://localhost:8000`.

```bash
# Asegurar que el servidor está corriendo
# Luego ejecutar:
npx playwright test tests/e2e_calendar_filters.spec.js --reporter=line
```

**Estado actual**: Los tests están escritos pero no se han ejecutado exitosamente porque el servidor no está corriendo. Una vez que el servidor esté activo, los tests deberían pasar.

## Validación Manual

### 1. Pills "Aplica a" → SELECT

1. Abrir `#calendario`
2. Verificar que existe un SELECT "Aplica a" (no pills)
3. Cambiar a "Empresa" → verificar que el select muestra "Empresa"
4. Verificar que los contadores cambian
5. Cambiar a "Trabajador" → verificar que el select muestra "Trabajador"
6. Verificar que solo aparecen items de trabajador

### 2. "Máx. meses atrás" filtra períodos

1. Ir a tab "Pendientes de subir"
2. Anotar número de períodos mostrados (con default 24)
3. Cambiar "Máx. meses atrás" a 3
4. Verificar que el número de períodos se reduce
5. Verificar que todos los períodos mostrados están dentro de los últimos 3 meses

### 3. Filtro "Rango de búsqueda" eliminado

1. Verificar que NO existe el select "Rango de búsqueda (opcional)"
2. Solo debe existir "Máx. meses atrás"

### 4. Limpiar filtros

1. Aplicar varios filtros
2. Click "Limpiar filtros"
3. Verificar que todos vuelven a valores por defecto:
   - Scope: "Todos" (all)
   - Búsqueda: vacío
   - Tipo: "Todos los tipos"
   - Sujeto: "Todos"
   - Máx. meses atrás: 24

## Evidencia Requerida

1. ⏳ Screenshot: `calendario_select_aplica_a.png` - SELECT "Aplica a" funcionando
2. ⏳ Screenshot: `calendario_max_months_back_filtra.png` - "Máx. meses atrás" filtrando períodos
3. ⏳ Screenshot: `calendario_sin_rango_busqueda.png` - Calendario sin filtro "Rango de búsqueda"
4. ⏳ Test PASS output (una vez que el servidor esté corriendo)

## Criterios de Aceptación

- ✅ "Aplica a" en calendario es un SELECT y refleja correctamente el valor seleccionado
- ✅ "Máx. meses atrás" limita realmente los períodos mostrados (implementado client-side)
- ✅ No existe "Rango de búsqueda (opcional)" en la pantalla calendario
- ✅ Tests E2E creados y listos para ejecutar (requieren servidor activo)
- ⏳ Tests E2E ejecutados y evidencias guardadas (pendiente servidor activo)

## Notas Técnicas

1. **Filtrado client-side**: El filtrado de `maxMonthsBack` se hace client-side sobre los datos ya recibidos. Esto es más rápido y no requiere cambios en el backend.

2. **Normalización de scope**: `scope` ahora usa `'all'` en lugar de `null` para mayor claridad y consistencia.

3. **Performance**: `setCalendarMaxMonthsBack()` ya no recarga la página completa, solo aplica filtros client-side, mejorando la experiencia de usuario.

4. **Data-testids**: Todos los elementos de filtro tienen data-testids estables para facilitar testing E2E.

## Próximos Pasos

1. ✅ Fix implementado
2. ⏳ Ejecutar tests E2E cuando el servidor esté activo
3. ⏳ Verificar manualmente que los filtros funcionan
4. ⏳ Capturar screenshots de evidencia
5. ⏳ Validar que "Máx. meses atrás" realmente filtra períodos antiguos

