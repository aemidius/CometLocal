# Regla de Selección de base_date para Cálculo de Validez

## Resumen

La fecha base (`base_date`) para calcular `validity_end_date` se selecciona según estas reglas de prioridad:

## Reglas de Prioridad

### 1. validity_start_date (PRIORIDAD MÁXIMA)

**Si existe `doc.extracted.validity_start_date`**:
- ✅ **Usar**: `base_date = validity_start_date`
- **Razón**: `"validity_start_date"`
- **Aplica a**: Todos los documentos que tengan esta fecha definida

**Ejemplo**:
- `issue_date` = 2025-08-01
- `validity_start_date` = 2026-05-30
- `base_date` = **2026-05-30** (no 2025-08-01)

### 2. validity_start_mode = "manual" sin validity_start_date

**Si `doc_type.validity_start_mode == "manual"` pero NO hay `validity_start_date`**:
- ❌ **Retornar**: `UNKNOWN`
- **Razón**: `"missing_validity_start_date_for_manual_mode"`
- **Aplica a**: Tipos configurados como "manual" pero sin fecha introducida

**Ejemplo**:
- Tipo RC tiene `validity_start_mode = "manual"`
- Documento NO tiene `validity_start_date`
- Resultado: `status = UNKNOWN` (no se puede calcular)

### 3. issue_date (Fallback)

**Si NO hay `validity_start_date` pero SÍ hay `issue_date`**:
- ✅ **Usar**: `base_date = issue_date` (o `issued_at`)
- **Razón**: `"issue_date"` o `"issued_at"`
- **Aplica a**: Documentos sin `validity_start_date` pero con fecha de emisión

**Ejemplo**:
- `issue_date` = 2025-08-01
- NO hay `validity_start_date`
- `base_date` = **2025-08-01**

### 4. period_key (Fallback condicional)

**Si NO hay `validity_start_date` ni `issue_date` pero SÍ hay `period_key`**:
- ✅ **Usar**: `base_date = parse_period_key(period_key)` (primer día del mes)
- **Razón**: `"period_key"`
- **Condición**: Solo si `policy.mode in ("monthly", "annual")` o `policy.n_months.n > 0`

**Ejemplo**:
- `period_key` = "2025-08"
- NO hay `validity_start_date` ni `issue_date`
- `base_date` = **2025-08-01** (primer día del mes)

## Flujo de Decisión

```
¿Existe validity_start_date?
├─ SÍ → base_date = validity_start_date ✅
└─ NO → ¿validity_start_mode == "manual"?
    ├─ SÍ → return UNKNOWN ❌
    └─ NO → ¿Existe issue_date?
        ├─ SÍ → base_date = issue_date ✅
        └─ NO → ¿Existe period_key Y tipo usa período?
            ├─ SÍ → base_date = parse_period_key(period_key) ✅
            └─ NO → return UNKNOWN ❌
```

## Cálculo de validity_end_date

Una vez determinada `base_date`, se calcula `validity_end_date` según la política:

### Prioridad de Cálculo

1. **`n_months.n`** (si existe):
   - `validity_end_date = base_date + n_months.n meses`
   - Ejemplo: `n_months.n = 12` → `base_date + 12 meses`

2. **`mode = "annual"`**:
   - `validity_end_date = base_date + annual.months meses`
   - Ejemplo: `annual.months = 12` → `base_date + 12 meses`

3. **`mode = "monthly"`**:
   - `validity_end_date = base_date + 1 mes` (ajustado al último día del mes)
   - Ejemplo: `base_date = 2025-08-15` → `validity_end_date = 2025-09-30`

4. **`mode = "fixed_end_date"`**:
   - Requiere `validity_override.valid_to` manual
   - Si no existe, retorna UNKNOWN

## Ejemplos Reales

### Ejemplo 1: RC Certificado (Caso del Bug)

**Configuración del tipo**:
- `validity_start_mode = "manual"`
- `validity_policy.mode = "monthly"`
- `validity_policy.n_months.n = 12` (cada 12 meses)

**Documento**:
- `issue_date` = 2025-08-01
- `period_key` = "2025-08"
- `validity_start_date` = 2026-05-30 ✅

**Cálculo**:
1. `base_date` = **2026-05-30** (validity_start_date, prioridad máxima)
2. `validity_end_date` = 2026-05-30 + 12 meses = **2027-05-30**
3. `status` = VALID (futuro)
4. `days_until_expiry` = positivo

**❌ ANTES (INCORRECTO)**:
- `base_date` = 2025-08-01 (issue_date)
- `validity_end_date` = 2025-08-31 (1 mes desde issue_date)
- `status` = EXPIRED ❌

### Ejemplo 2: Documento sin validity_start_date

**Configuración del tipo**:
- `validity_start_mode = "issue_date"`
- `validity_policy.mode = "annual"`
- `validity_policy.annual.months = 12`

**Documento**:
- `issue_date` = 2025-01-15
- NO hay `validity_start_date`

**Cálculo**:
1. `base_date` = **2025-01-15** (issue_date, fallback)
2. `validity_end_date` = 2025-01-15 + 12 meses = **2026-01-15**
3. `status` = según fecha actual

### Ejemplo 3: Tipo manual sin fecha

**Configuración del tipo**:
- `validity_start_mode = "manual"`

**Documento**:
- `issue_date` = 2025-08-01
- NO hay `validity_start_date` ❌

**Cálculo**:
1. `base_date` = None
2. `status` = **UNKNOWN**
3. `base_reason` = "missing_validity_start_date_for_manual_mode"

## Validación

Para verificar que se está usando la base_date correcta:

```bash
curl "http://127.0.0.1:8000/api/repository/docs?type_id=T8447_RC_CERTIFICADO" | \
  jq '.[0] | {
    validity_base_date,
    validity_base_reason,
    validity_end_date,
    validity_status
  }'
```

**Resultado esperado para RC con validity_start_date futura**:
```json
{
  "validity_base_date": "2026-05-30",
  "validity_base_reason": "validity_start_date",
  "validity_end_date": "2027-05-30",
  "validity_status": "VALID"
}
```

## Conclusión

La regla clave es: **Si existe `validity_start_date`, SIEMPRE usarla como base_date**, independientemente de `issue_date` o `period_key`. Esto asegura que documentos con fecha de inicio de vigencia manual se calculen correctamente.







