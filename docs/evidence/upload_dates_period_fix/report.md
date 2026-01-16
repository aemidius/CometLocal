# Reporte: Fix de Campo Mes/Año y Parser de Fecha

## Fecha
2025-01-27T12:00:00.000Z

## Problemas Reportados

### A) Campo "Mes/Año" aparece cuando no aplica
**Problema**: Para tipos RC (cada 12 meses, Empresa, periodo NONE/NO mensual) se mostraba el campo "3. ¿De qué mes/año?" y lo marcaba como obligatorio, pero NO aplica.

**Causa**: La lógica de `needsPeriod` estaba basada en `validity_policy.mode` directamente, sin derivar correctamente `period_kind`. Para tipos "n_months", el periodo se calcula desde fechas, no requiere entrada manual.

### B) No extrae fecha desde filename en formato español/catalán
**Problema**: No extraía fecha desde filename "Tedelab Certificat RC 2025_1-ago-25.pdf", pese a que el tipo está configurado "Cómo se calcula el periodo: Desde nombre" y "Fecha de emisión obligatoria".

**Causa**: El parser de fecha no soportaba el formato `YYYY_DD-MMM-YY` (año al inicio seguido de día-mes-año).

## Fix Aplicado

### A) Corrección de lógica de mostrar/ocultar campo Mes/Año

**Ubicación**: `frontend/repository_v3.html` líneas ~2064-2073

**Cambio**:
1. **Derivación correcta de `period_kind`**:
   ```javascript
   // Derivar period_kind desde periodMode (igual que backend)
   let periodKind = 'none';
   if (periodMode === 'monthly') {
       periodKind = 'month';
   } else if (periodMode === 'annual') {
       periodKind = 'year';
   } else if (periodMode === 'quarter') {
       periodKind = 'quarter';
   } else {
       // n_months, none, o cualquier otro => NONE (no requiere periodo manual)
       periodKind = 'none';
   }
   ```

2. **Condición de `needsPeriod`**:
   ```javascript
   // Mostrar campo Mes/Año SOLO si period_kind es MONTH, QUARTER o YEAR (no NONE)
   const needsPeriod = (periodKind === 'month' || periodKind === 'year' || periodKind === 'quarter') && !shouldHidePeriodForNMonths;
   ```

3. **Template actualizado**:
   - Usa `periodKind === 'month'` en lugar de `periodKind === 'monthly'`
   - Soporta `quarter` con input de texto para formato `YYYY-Qn`
   - Oculta el campo si `periodKind === 'none'`

4. **Validación corregida**:
   ```javascript
   if (needsPeriod && !file.period_key) {
       errors.push(`El ${periodKind === 'month' ? 'mes' : periodKind === 'quarter' ? 'trimestre' : 'año'} es obligatorio`);
   }
   ```

**Resultado**: Para tipos RC (n_months, period_kind=NONE), el campo Mes/Año NO aparece y NO bloquea el guardado.

### B) Mejora del parser de fecha

**Ubicación**: `frontend/repository_v3.html` líneas ~2588-2650

**Cambios**:

1. **Normalización de filename**:
   ```javascript
   // Normalizar: reemplazar _ por -, colapsar espacios múltiples, lower
   const normalized = filename.replace(/_/g, '-').replace(/\s+/g, '-').toLowerCase();
   ```

2. **Nuevo patrón 0 para formato YYYY_DD-MMM-YY**:
   ```javascript
   // Patrón 0: YYYY_DD-MMM-YY o YYYY-DD-MMM-YY (ej: "2025_1-ago-25", "2025-1-ago-25")
   const pattern0 = /(\d{4})[-_](\d{1,2})[-/](ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)[-/](\d{2,4})/i;
   ```
   - Extrae año del inicio (preferido)
   - Extrae día, mes (español/catalán) y año del final
   - Si hay año de 4 dígitos al inicio, lo usa (más confiable)

3. **Soporte para catalán**:
   ```javascript
   'ago': 8, 'agosto': 8, 'agost': 8, // catalán
   'sep': 9, 'septiembre': 9, 'set': 9, 'setembre': 9, // catalán
   ```

4. **Detección automática en `detectUploadMetadata`**:
   ```javascript
   // Detect date from filename (name_date)
   const parsedDate = parseDateFromFilename(fileData.name, null);
   if (parsedDate) {
       fileData.detected.name_date = parsedDate;
       // Si issue_date está vacío, prefill con name_date
       if (!fileData.issue_date) {
           fileData.issue_date = parsedDate;
       }
   }
   ```

**Resultado**: Con filename "Tedelab Certificat RC 2025_1-ago-25.pdf", la UI pre-rellena `issue_date` a `2025-08-01`.

### C) Data-testids añadidos

- `data-testid="period-monthyear"` - Contenedor del campo Mes/Año
- `data-testid="issue-date-input"` - Input de fecha de emisión
- `data-testid="validity-start-input"` - Input de fecha de inicio de vigencia

## Tests E2E Añadidos

### Test E: Mes/Año oculto cuando no aplica
- Crea tipo RC con `n_months=12` (period_kind=NONE)
- Sube PDF y selecciona tipo
- **Assert**: Campo `period-monthyear` NO es visible

### Test F: Parse fecha desde nombre
- Sube PDF con filename `Tedelab Certificat RC 2025_1-ago-25.pdf`
- Selecciona tipo que requiere `issue_date`
- **Assert**: Input `issue-date-input` tiene valor `2025-08-01`

## Archivos Modificados

1. **`frontend/repository_v3.html`**:
   - Derivación correcta de `period_kind` (líneas ~2064-2073)
   - Condición `needsPeriod` actualizada (línea ~2073)
   - Template del campo Mes/Año actualizado (líneas ~2307-2329)
   - Validación de errores corregida (línea ~2138)
   - Parser de fecha mejorado con patrón 0 (líneas ~2588-2650)
   - Detección automática de fecha en `detectUploadMetadata` (líneas ~2014-2022)
   - Data-testids añadidos

2. **`tests/e2e_upload_scope_filter.spec.js`**:
   - Test E añadido (líneas ~393-430)
   - Test F añadido (líneas ~432-480)

## Criterios de Aceptación Verificados

✅ **A) Campo Mes/Año**:
- Para RC (Cada N meses=12, Empresa), el campo Mes/Año NO aparece
- Para RC, NO bloquea guardado por "mes obligatorio"
- Para tipos Mensual/Trimestral/Anual, el campo aparece y valida

✅ **B) Parser de fecha**:
- Con filename "Tedelab Certificat RC 2025_1-ago-25.pdf", la UI pre-rellena `issue_date` a `2025-08-01`
- Ya no aparece `issue_date=NULL` en el debug para ese caso
- Soporta formatos español y catalán

## Cómo Verificar

### 1. Verificar campo Mes/Año oculto
1. Abrir `http://127.0.0.1:8000/repository#subir`
2. Subir un PDF
3. Seleccionar tipo RC (o cualquier tipo con `n_months` y `period_kind=NONE`)
4. **Verificar**: Campo "3. ¿De qué mes/año?" NO aparece

### 2. Verificar parser de fecha
1. Abrir `http://127.0.0.1:8000/repository#subir`
2. Subir PDF con nombre "Tedelab Certificat RC 2025_1-ago-25.pdf"
3. Seleccionar tipo que requiere `issue_date`
4. **Verificar**: Input de "Fecha de emisión" tiene valor `01/08/2025` (o `2025-08-01` según formato del navegador)

### 3. Ejecutar tests E2E
```bash
npm run test:e2e -- tests/e2e_upload_scope_filter.spec.js
```

## Screenshots

- `docs/evidence/upload_scope_filter/11_rc_no_period_field.png` - Campo Mes/Año oculto para RC
- `docs/evidence/upload_scope_filter/12_date_parsed_from_filename.png` - Fecha parseada desde filename

## Notas

- El fix respeta la lógica del backend: `period_kind` se deriva de `validity_policy.mode`
- Para tipos "n_months", el periodo se calcula desde fechas (issue_date/name_date), no requiere entrada manual
- El parser de fecha es "best effort": intenta parsear siempre, no requiere configuración específica del tipo
- Se mantiene compatibilidad con formatos anteriores (DD-MMM-YY, DD/MM/YYYY, etc.)








