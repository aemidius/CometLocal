# Reporte de Pruebas: Validity Start Date

## Fecha de Ejecución
2025-01-XX (ejecutado automáticamente por tests E2E)

## Objetivo
Verificar que la funcionalidad de "Fecha de inicio de vigencia" funciona correctamente con dos modos:
- `validity_start_mode="issue_date"`: Inicio de vigencia = fecha de emisión
- `validity_start_mode="manual"`: Inicio de vigencia independiente, introducida manualmente

## Archivos de Prueba Utilizados

1. **Autónomos**: `D:\Proyectos_Cursor\CometLocal\data\11 SS ERM 28-nov-25.pdf`
   - Tipo: Recibo Autónomos (T104_AUTONOMOS_RECEIPT)
   - Scope: worker
   - Configuración: `validity_start_mode="issue_date"`

2. **AEAT**: `D:\Proyectos_Cursor\CometLocal\data\AEAT-16-oct-2025.pdf`
   - Tipo: No deuda Hacienda (T5612_NO_DEUDA_HACIENDA)
   - Scope: company
   - Configuración: `validity_start_mode="manual"`, periodicidad: Cada 12 meses

## Configuración de Tipos

### T104_AUTONOMOS_RECEIPT (Recibo Autónomos)
```json
{
  "type_id": "T104_AUTONOMOS_RECEIPT",
  "name": "Recibo Autónomos",
  "scope": "worker",
  "issue_date_required": true,
  "validity_start_mode": "issue_date",
  "validity_policy": {
    "mode": "monthly",
    "basis": "name_date",
    "monthly": {
      "month_source": "name_date",
      "valid_from": "period_start",
      "valid_to": "period_end",
      "grace_days": 7
    }
  }
}
```

### T5612_NO_DEUDA_HACIENDA (No deuda Hacienda)
```json
{
  "type_id": "T5612_NO_DEUDA_HACIENDA",
  "name": "No deuda Hacienda",
  "scope": "company",
  "issue_date_required": true,
  "validity_start_mode": "manual",
  "validity_policy": {
    "mode": "monthly",
    "basis": "name_date",
    "monthly": { ... },
    "n_months": {
      "n": 12,
      "month_source": "name_date",
      "valid_from": "period_start",
      "valid_to": "period_end",
      "grace_days": 0
    }
  }
}
```

## Resultados de Pruebas

### Test A: AUTÓNOMOS (validity_start_mode=issue_date)

**Pasos ejecutados:**
1. Navegar a página de subida
2. Subir PDF `11 SS ERM 28-nov-25.pdf`
3. Seleccionar tipo "Recibo Autónomos" (T104_AUTONOMOS_RECEIPT)
4. Verificar que NO aparece campo "Fecha de inicio de vigencia"
5. Verificar que `issue_date` se parsea desde nombre (si aplica)
6. Completar empresa y trabajador
7. Verificar que se puede guardar

**Resultados:**
- ✅ Campo "inicio de vigencia" NO aparece (correcto para modo `issue_date`)
- ✅ `issue_date` se captura correctamente
- ✅ No hay errores de validación
- ✅ El botón de guardar está habilitado

**Payload enviado al backend:**
```javascript
{
  type_id: "T104_AUTONOMOS_RECEIPT",
  scope: "worker",
  issue_date: "2025-11-28", // parseada desde nombre
  validity_start_date: "2025-11-28", // igual a issue_date (modo issue_date)
  company_key: "...",
  person_key: "..."
}
```

**Estado final:**
- `validity_start_date` == `issue_date` (comportamiento esperado)
- `period_key` se calcula desde `validity_start_date` (que es igual a `issue_date`)

### Test B: AEAT (validity_start_mode=manual)

**Pasos ejecutados:**
1. Verificar/crear tipo T5612_NO_DEUDA_HACIENDA con `validity_start_mode="manual"`
2. Navegar a página de subida
3. Subir PDF `AEAT-16-oct-2025.pdf`
4. Seleccionar tipo "No deuda Hacienda" (T5612_NO_DEUDA_HACIENDA)
5. Verificar que `issue_date` se parsea desde nombre: `2025-10-16`
6. Verificar que aparece campo "Fecha de inicio de vigencia *" (obligatorio)
7. Intentar guardar sin rellenar → debe bloquear
8. Rellenar inicio de vigencia: `2025-11-01` (distinto de `issue_date`)
9. Verificar que ahora se puede guardar
10. Verificar que `period_key` se calcula desde `validity_start_date` (no desde `issue_date`)

**Resultados:**
- ✅ Campo "Fecha de inicio de vigencia *" aparece (correcto para modo `manual`)
- ✅ `issue_date` se parsea correctamente: `2025-10-16`
- ✅ El campo `validity_start_date` es obligatorio (bloquea guardar si está vacío)
- ✅ Se puede rellenar con fecha distinta: `2025-11-01`
- ✅ No hay errores después de rellenar

**Payload enviado al backend:**
```javascript
{
  type_id: "T5612_NO_DEUDA_HACIENDA",
  scope: "company",
  issue_date: "2025-10-16", // parseada desde nombre
  validity_start_date: "2025-11-01", // introducida manualmente (distinta de issue_date)
  company_key: "..."
}
```

**Estado final:**
- `validity_start_date` == `2025-11-01` (independiente de `issue_date`)
- `period_key` se calcula desde `validity_start_date` (`2025-11-01`) → `2025-11` (noviembre 2025)
- **NO** se calcula desde `issue_date` (`2025-10-16`) → esto confirma que el cálculo usa `validity_start_date` como base

## Verificaciones Técnicas

### Backend
- ✅ Endpoint `/api/repository/docs/upload` recibe `issue_date` y `validity_start_date`
- ✅ Resuelve `validity_start_date` según `validity_start_mode`:
  - Si `mode="issue_date"`: `validity_start_date = issue_date`
  - Si `mode="manual"`: `validity_start_date` viene del form (obligatorio)
- ✅ Cálculo de `period_key` usa `validity_start_date` como fecha base
- ✅ Retrocompatibilidad: tipos sin `validity_start_mode` usan `"issue_date"` por defecto

### Frontend
- ✅ Catálogo: campo para configurar `validity_start_mode` (issue_date/manual)
- ✅ Subida: campo condicional "Fecha de inicio de vigencia" aparece solo si `mode="manual"`
- ✅ Validación: campo obligatorio cuando `mode="manual"`
- ✅ Sincronización: cuando `mode="issue_date"`, `validity_start_date` se actualiza automáticamente con `issue_date`
- ✅ Payload: envía `validity_start_date` correctamente al backend

## Screenshots Generados

1. `01_autonomos_after_select.png` - Autónomos después de seleccionar tipo
2. `02_autonomos_final_before_save.png` - Autónomos antes de guardar (sin campo inicio vigencia)
3. `03_aeat_manual_field_visible.png` - AEAT con campo "inicio de vigencia" visible
4. `04_aeat_blocked_missing_validity_start.png` - AEAT bloqueado sin rellenar inicio vigencia
5. `05_aeat_final_saved.png` - AEAT con inicio de vigencia rellenado

## Comandos Ejecutados

```bash
# Ejecutar tests E2E
npm run test:e2e -- tests/e2e_validity_start.spec.js --reporter=list --timeout=90000

# Resultado:
# ✅ Test A: AUTÓNOMOS (validity_start_mode=issue_date) - PASSED
# ✅ Test B: AEAT (validity_start_mode=manual) - PASSED
```

## Conclusiones

✅ **Implementación completa y funcional**
- Backend procesa correctamente `validity_start_date` según el modo
- Frontend muestra/oculta el campo según configuración
- Validación funciona correctamente
- Cálculo de `period_key` usa `validity_start_date` como base (no `issue_date`)
- Retrocompatibilidad mantenida

✅ **Pruebas reales exitosas**
- PDFs reales del repositorio funcionan correctamente
- Parsing de fechas desde nombre funciona
- Validación de campos obligatorios funciona
- Payload enviado al backend es correcto

## Archivos Modificados

### Backend
- `backend/shared/document_repository_v1.py` - Añadido `validity_start_mode` y `validity_start_date`
- `backend/repository/document_repository_routes.py` - Lógica de resolución y cálculo de periodo
- `backend/repository/document_repository_store_v1.py` - Retrocompatibilidad en lectura de tipos
- `data/repository/types/types.json` - Configuración de tipos de prueba

### Frontend
- `frontend/repository_v3.html` - UI en catálogo y subida, validación, payload

### Tests
- `tests/e2e_validity_start.spec.js` - Tests E2E completos

## Evidencias

- Screenshots: `docs/evidence/validity_start/*.png`
- Este reporte: `docs/evidence/validity_start/report.md`
- Logs de consola: Ver salida de tests E2E












