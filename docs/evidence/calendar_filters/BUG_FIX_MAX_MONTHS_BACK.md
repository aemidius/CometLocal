# Fix: Bug Crítico - "Máx. meses atrás" no filtraba períodos antiguos

## Diagnóstico

**Problema**: Con "Máx. meses atrás = 3", se seguían mostrando períodos muy antiguos (ej: 2025-04, 2025-05) en el tab "Pendientes de subir".

**Causa raíz identificada**:
1. **`showPendingSection()` usaba datos desactualizados**: La función `showPendingSection()` leía `window.pendingDocumentsData` que podía estar desactualizado si el usuario cambiaba `maxMonthsBack` y luego cambiaba de tab.
2. **Falta de re-aplicación de filtros**: Al cambiar de tab, no se re-aplicaban los filtros con el valor actual de `calendarMaxMonthsBack`.
3. **Parsing de períodos no robusto**: El regex no validaba estrictamente el formato YYYY-MM.

## Fix Implementado

### 1. Re-aplicación de filtros en `showPendingSection()`

**Antes**:
```javascript
function showPendingSection(section) {
    // ...
    const data = window.pendingDocumentsData || { expired: [], expiringSoon: [], missing: [] };
    container.innerHTML = renderPendingDocuments(data.expired, data.expiringSoon, data.missing, section);
}
```

**Después**:
```javascript
function showPendingSection(section) {
    // ...
    // IMPORTANTE: Re-aplicar filtros antes de renderizar para asegurar datos actualizados
    const rawData = window.pendingDocumentsDataRaw || { expired: [], expiringSoon: [], missing: [] };
    const filtered = applyCalendarFilters(rawData, calendarFilters, calendarMaxMonthsBack);
    window.pendingDocumentsData = filtered;
    container.innerHTML = renderPendingDocuments(filtered.expired, filtered.expiringSoon, filtered.missing, section);
}
```

### 2. Parsing robusto de períodos

**Antes**:
```javascript
const periodMatch = item.period_key.match(/(\d{4})-(\d{2})/);
```

**Después**:
```javascript
const periodMatch = item.period_key.match(/^(\d{4})-(\d{2})$/);
if (periodMatch) {
    const periodYear = parseInt(periodMatch[1], 10);
    const periodMonth = parseInt(periodMatch[2], 10);
    
    // Validar mes (1-12)
    if (periodMonth < 1 || periodMonth > 12) {
        return false;
    }
    // ...
}
```

### 3. Añadido `oninput` al input de maxMonthsBack

**Antes**:
```html
onchange="setCalendarMaxMonthsBack(parseInt(this.value) || 24)"
```

**Después**:
```html
onchange="setCalendarMaxMonthsBack(parseInt(this.value) || 24)"
oninput="setCalendarMaxMonthsBack(parseInt(this.value) || 24)"
```

### 4. Logs de debug (con flag `DEBUG_CALENDAR_FILTERS`)

Añadidos logs temporales para diagnosticar:
- Valor leído de `calendar-max-months-back` (raw + parseInt)
- Número de items antes/después de aplicar filtro
- Ejemplos de períodos incluidos/excluidos con `monthsDiff`

**Flag**: `const DEBUG_CALENDAR_FILTERS = true;` (cambiar a `false` en producción)

### 5. Data-testid para períodos

Añadido `data-testid="calendar-period"` al elemento que muestra el período en cada fila:
```html
<td>
    <span data-testid="calendar-period">${escapeHtml(periodKey)}</span>
</td>
```

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Función `showPendingSection()`: Re-aplica filtros antes de renderizar
   - Función `applyCalendarFilters()`: Parsing robusto de períodos + validación de mes
   - Función `setCalendarMaxMonthsBack()`: Logs de debug
   - Input `calendar-max-months-back`: Añadido `oninput`
   - Render de períodos: Añadido `data-testid="calendar-period"`
   - Logs de debug con flag `DEBUG_CALENDAR_FILTERS`

2. **`tests/e2e_calendar_filters.spec.js`**:
   - Test TEST 2: Mejorado para usar `data-testid="calendar-period"`
   - Test TEST 4 (NUEVO): Test específico para este bug que verifica que NO aparecen períodos con `monthsDiff > maxMonthsBack`

## Validación

### Manual
1. Ir a `#calendario`
2. Tab "Pendientes de subir"
3. Cambiar "Máx. meses atrás" a 3
4. **Verificar**: NO debe verse ningún período con `monthsDiff > 3`

### E2E
- Test TEST 4: Verifica que todos los períodos mostrados tienen `monthsDiff <= 3`

## Notas Técnicas

1. **Filtrado client-side**: El filtrado se hace client-side sobre los datos ya recibidos de `/api/repository/docs/pending`.
2. **Cálculo de `monthsDiff`**: `(currentYear - periodYear) * 12 + (currentMonth - periodMonth)`
3. **Validación**: Períodos futuros (`monthsDiff < 0`) también se excluyen.

## Próximos Pasos

1. ⏳ Ejecutar tests E2E y verificar que pasan
2. ⏳ Capturar screenshots antes/después del fix
3. ⏳ Desactivar logs de debug (`DEBUG_CALENDAR_FILTERS = false`) antes de producción







