# Fix Crítico: Cálculo de Expiración Usa Fecha Equivocada

## Problema Identificado

Para documentos RC (certificado) con:
- **Fecha de emisión**: 01/08/2025
- **Mes/Año**: 2025-08
- **Fecha inicio de vigencia**: 30/05/2026 (futura)
- **Periodicidad**: cada 12 meses
- **validity_start_mode**: "manual" (se introduce al subir)

El sistema mostraba incorrectamente:
- **Caduca**: 31/08/2025
- **Estado**: Expirado hace 126 días

**Causa**: El cálculo usaba `issue_date` o `period_key` en lugar de `validity_start_date` como base para calcular la caducidad.

## Causa Raíz

La función `calculate_document_status()` solo usaba `computed_validity.valid_to`, que a su vez se calculaba en `compute_validity()` usando `policy.basis` (issue_date, name_date, manual), pero **no consideraba `validity_start_mode` del tipo de documento**.

Para tipos con `validity_start_mode = "manual"`, la fecha base correcta debe ser `validity_start_date`, no `issue_date` ni `period_key`.

## Solución Implementada

### 1. Reescritura de `calculate_document_status()`

**Archivo**: `backend/repository/document_status_calculator_v1.py`

**Nueva lógica de selección de base_date**:

```python
# Regla 1: Si hay validity_start_date, usarla (prioridad máxima)
if doc.extracted.validity_start_date:
    base_date = doc.extracted.validity_start_date
    base_reason = "validity_start_date"

# Regla 2: Si validity_start_mode == "manual" pero falta validity_start_date, retornar UNKNOWN
elif doc_type.validity_start_mode == "manual":
    return UNKNOWN, None, None, None, "missing_validity_start_date_for_manual_mode"

# Regla 3: Fallback a issue_date si existe
elif doc.extracted.issue_date:
    base_date = doc.extracted.issue_date
    base_reason = "issue_date"

# Regla 4: Fallback a period_key solo si el tipo usa período como base
elif doc.period_key and policy.mode in ("monthly", "annual"):
    base_date = parse_period_key(doc.period_key)
    base_reason = "period_key"
```

**Cálculo de validity_end_date**:

- **Prioridad**: `n_months` override tiene prioridad sobre `mode`
- Si `policy.n_months.n = 12`: `validity_end_date = base_date + 12 meses`
- Si `policy.mode = "annual"`: `validity_end_date = base_date + annual.months`
- Si `policy.mode = "monthly"`: `validity_end_date = base_date + 1 mes` (último día del mes)

**Manejo de fechas futuras**:

- Si `validity_start_date > today`: Estado = VALID (aún no ha empezado la vigencia)
- Si `validity_end_date < today`: Estado = EXPIRED
- Si `0 <= days_until_expiry <= threshold`: Estado = EXPIRING_SOON
- Si `days_until_expiry > threshold`: Estado = VALID

### 2. Actualización de Endpoints

**Archivo**: `backend/repository/document_repository_routes.py`

- **`GET /api/repository/docs`**: Actualizado para pasar `doc_type` a `calculate_document_status()`
- **`GET /api/repository/docs/pending`**: Actualizado para pasar `doc_type` a `calculate_document_status()`

**Campos añadidos a la respuesta** (debug, opcionales):
- `validity_base_date`: Fecha base usada para el cálculo
- `validity_base_reason`: Razón de por qué se usó esa base_date

### 3. Funciones Auxiliares

- **`parse_period_key()`**: Parsea `YYYY-MM` a fecha (primer día del mes)
- **`add_months()`**: Añade N meses a una fecha, manejando correctamente los límites de mes

## Reglas de Prioridad

### Selección de base_date

1. **`validity_start_date`** (si existe) - PRIORIDAD MÁXIMA
2. **`validity_start_mode == "manual"` sin `validity_start_date`** → UNKNOWN
3. **`issue_date`** (si existe)
4. **`period_key`** (solo si el tipo usa período como base)

### Cálculo de validity_end_date

1. **`n_months.n`** (si existe) - PRIORIDAD MÁXIMA
2. **`mode = "annual"`** → `base_date + annual.months`
3. **`mode = "monthly"`** → `base_date + 1 mes` (último día del mes)
4. **`mode = "fixed_end_date"`** → Requiere override manual

## Tests Implementados

**Archivo**: `tests/test_calculate_document_status_fix.py`

1. **`test_rc_certificate_with_validity_start_date_future`**:
   - Verifica que con `validity_start_date` futura (2026-05-30) y `n_months=12`
   - `base_date` = 2026-05-30
   - `validity_end_date` = 2027-05-30
   - `status` = VALID (no EXPIRED)
   - `days_until_expiry` > 0

2. **`test_rc_certificate_with_validity_start_date_past`**:
   - Verifica cálculo correcto con fecha pasada

3. **`test_manual_mode_missing_validity_start_date`**:
   - Verifica que retorna UNKNOWN si `validity_start_mode="manual"` pero falta `validity_start_date`

**Resultado**: ✅ 3 tests PASSED

## Archivos Modificados

1. **`backend/repository/document_status_calculator_v1.py`**:
   - Reescrita función `calculate_document_status()`
   - Añadidas funciones auxiliares `parse_period_key()`, `add_months()`
   - Nueva lógica de selección de base_date
   - Soporte para `n_months` override

2. **`backend/repository/document_repository_routes.py`**:
   - Actualizado `list_documents()` para pasar `doc_type`
   - Actualizado `get_pending_documents()` para pasar `doc_type`
   - Añadidos campos debug `validity_base_date`, `validity_base_reason`

3. **`tests/test_calculate_document_status_fix.py`** (NUEVO):
   - Tests unitarios para verificar el fix

## Validación

### Ejecutar Tests

```bash
pytest tests/test_calculate_document_status_fix.py -v
```

**Resultado esperado**: 3 tests PASSED

### Verificar Endpoint

```bash
# Obtener documento RC
curl "http://127.0.0.1:8000/api/repository/docs?type_id=T8447_RC_CERTIFICADO" | jq '.[0] | {
  doc_id,
  issue_date: .issued_at,
  validity_start_date: .extracted.validity_start_date,
  period_key,
  validity_status,
  validity_end_date,
  days_until_expiry,
  validity_base_date,
  validity_base_reason
}'
```

**Resultado esperado**:
- `validity_base_reason` = "validity_start_date"
- `validity_base_date` = "2026-05-30" (o la fecha de inicio de vigencia del documento)
- `validity_end_date` = "2027-05-30" (base_date + 12 meses)
- `validity_status` = "VALID" (no "EXPIRED")
- `days_until_expiry` > 0 (futuro)

### Verificar en Frontend

1. Abrir `#buscar` y buscar documentos RC
2. Verificar que el estado de validez es correcto (no "Expirado" si `validity_start_date` es futura)
3. Abrir modal "Editar documento" de un RC
4. Verificar que "Estado de validez" muestra:
   - Badge correcto (VALID, no EXPIRED)
   - Fecha de caducidad correcta (2027-05-30, no 2025-08-31)
   - Días restantes positivos

## Evidencia Requerida

1. ✅ Test PASS output
2. ⏳ Screenshot de Buscar mostrando RC con estado correcto
3. ⏳ Screenshot de modal Editar mostrando caducidad correcta
4. ⏳ JSON de `/api/repository/docs` para RC mostrando campos correctos

## Notas Técnicas

1. **Compatibilidad hacia atrás**: Si un documento no tiene `validity_start_date` y `validity_start_mode != "manual"`, se usa `issue_date` como antes.

2. **Debug fields**: Los campos `validity_base_date` y `validity_base_reason` son opcionales y se pueden quitar después de validar el fix.

3. **Fechas futuras**: Si `validity_start_date > today`, el documento se considera VALID aunque aún no haya empezado la vigencia.

4. **n_months override**: Tiene prioridad sobre `mode`, permitiendo tipos con `mode="monthly"` pero `n_months.n=12` para "cada 12 meses".

## Próximos Pasos

1. ✅ Fix implementado
2. ⏳ Validar con documento real RC
3. ⏳ Verificar en frontend que se muestra correctamente
4. ⏳ Remover campos debug si no se necesitan
5. ⏳ Actualizar `compute_validity()` para usar la misma lógica (opcional, para consistencia)







