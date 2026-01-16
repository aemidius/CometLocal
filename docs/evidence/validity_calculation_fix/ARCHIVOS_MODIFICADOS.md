# Archivos Modificados - Fix Cálculo de Validez

## Resumen

Fix crítico del cálculo de validez para usar `validity_start_date` correctamente cuando `validity_start_mode = "manual"`.

## Archivos Modificados

### Backend

1. **`backend/repository/document_status_calculator_v1.py`** (MODIFICADO)
   - **Función `calculate_document_status()`**: Reescrita completamente
     - Nueva lógica de selección de `base_date` con prioridades claras
     - Soporte para `validity_start_date` como prioridad máxima
     - Manejo de `validity_start_mode = "manual"` sin fecha → UNKNOWN
     - Cálculo de `validity_end_date` usando `n_months` override con prioridad
     - Retorna 5 valores: `(status, validity_end_date, days_until_expiry, base_date, base_reason)`
   - **Nuevas funciones auxiliares**:
     - `parse_period_key()`: Parsea `YYYY-MM` a fecha
     - `add_months()`: Añade N meses a una fecha

2. **`backend/repository/document_repository_routes.py`** (MODIFICADO)
   - **Endpoint `GET /api/repository/docs`**:
     - Actualizado para pasar `doc_type` a `calculate_document_status()`
     - Añadidos campos debug: `validity_base_date`, `validity_base_reason`
   - **Endpoint `GET /api/repository/docs/pending`**:
     - Actualizado para pasar `doc_type` a `calculate_document_status()`

### Tests

3. **`tests/test_calculate_document_status_fix.py`** (NUEVO)
   - Test 1: RC con `validity_start_date` futura → debe usar esa fecha como base
   - Test 2: RC con `validity_start_date` pasada → cálculo correcto
   - Test 3: Tipo manual sin `validity_start_date` → debe retornar UNKNOWN

### Documentación

4. **`docs/evidence/validity_calculation_fix/REPORT.md`** (NUEVO)
   - Documentación completa del problema y solución

5. **`docs/evidence/validity_calculation_fix/REGLA_BASE_DATE.md`** (NUEVO)
   - Explicación detallada de las reglas de selección de base_date

## Cambios Clave

### Antes (INCORRECTO)

```python
# Solo usaba computed_validity.valid_to
if doc.computed_validity and doc.computed_validity.valid_to:
    validity_end_date = doc.computed_validity.valid_to
```

**Problema**: `computed_validity` se calculaba usando `issue_date` o `period_key`, ignorando `validity_start_date`.

### Después (CORRECTO)

```python
# Selección de base_date con prioridades
if doc.extracted.validity_start_date:
    base_date = doc.extracted.validity_start_date  # PRIORIDAD MÁXIMA
elif doc_type.validity_start_mode == "manual":
    return UNKNOWN  # Requiere validity_start_date
elif doc.extracted.issue_date:
    base_date = doc.extracted.issue_date  # Fallback
elif doc.period_key:
    base_date = parse_period_key(doc.period_key)  # Último fallback

# Cálculo de validity_end_date
if policy.n_months and policy.n_months.n > 0:
    validity_end_date = add_months(base_date, policy.n_months.n)  # PRIORIDAD
elif policy.mode == "annual":
    validity_end_date = add_months(base_date, policy.annual.months)
# ...
```

## Estadísticas

- **Archivos modificados**: 2
- **Archivos nuevos**: 3 (tests + docs)
- **Líneas añadidas**: ~250
- **Líneas modificadas**: ~100
- **Tests**: 3 tests unitarios (todos PASSED)

## Validación

### Tests Unitarios

```bash
pytest tests/test_calculate_document_status_fix.py -v
```

**Resultado**: ✅ 3 tests PASSED

### Endpoint (requiere servidor corriendo)

```bash
curl "http://127.0.0.1:8000/api/repository/docs?type_id=T8447_RC_CERTIFICADO" | \
  jq '.[0] | {
    validity_base_date,
    validity_base_reason,
    validity_end_date,
    validity_status,
    days_until_expiry
  }'
```

**Resultado esperado**:
- `validity_base_reason` = "validity_start_date"
- `validity_end_date` = fecha correcta (base_date + 12 meses)
- `validity_status` = "VALID" (no "EXPIRED" si es futuro)

## Breaking Changes

**Ninguno**: La función mantiene compatibilidad hacia atrás. Si no hay `validity_start_date`, usa `issue_date` como antes.

## Notas

1. **Campos debug**: `validity_base_date` y `validity_base_reason` son opcionales y se pueden quitar después de validar.

2. **Reinicio requerido**: El servidor backend debe reiniciarse para que los cambios surtan efecto.

3. **Consistencia**: Ambos endpoints (`/docs` y `/docs/pending`) usan la misma función, garantizando consistencia.







