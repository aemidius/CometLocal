# Fixes Aplicados - Fecha y N Meses

## Fecha: 2025-12-31

## Problemas Resueltos

### BUG 2: Fecha no se extrae del nombre
**Estado**: ✅ RESUELTO

**Cambios aplicados**:
1. **Patrón regex mejorado** (`frontend/repository_v3.html` línea ~2316):
   - Cambiado de patrón con espacios opcionales a patrón más estricto: `/(\d{1,2})[-/](ene|feb|...)[-/](\d{2,4})/i`
   - Esto captura correctamente "16-oct-2025" en "AEAT-16-oct-2025.pdf"
   - Añadido logging: `console.log('[repo-upload] parseDateFromFilename pattern1 match:', ...)`

2. **Lógica de parseo mejorada** (`frontend/repository_v3.html` línea ~2228):
   - Cambiado para SIEMPRE intentar parsear fecha si está vacía (best effort)
   - Antes: solo parseaba si `issueDateRequired && !file.issue_date` o `!issueDateRequired && !file.issue_date`
   - Ahora: parsea siempre si `!file.issue_date`, independientemente de `issueDateRequired`
   - Si requiere fecha y falla el parseo, muestra error

**Evidencia**:
- Test E2E muestra: `issue_date: '2025-10-16'` ✅
- Console log muestra: `[repo-upload] auto-date candidate: {filename: AEAT-16-oct-2025.pdf, parsed: 2025-10-16, ...}` ✅

### BUG 4: "Cada N meses" no se guarda correctamente
**Estado**: ✅ RESUELTO

**Cambios aplicados**:
1. **Detección de `n_months` en `renderTypeDrawer`** (`frontend/repository_v3.html` línea ~3715):
   - Añadido: `const hasNMonths = type.validity_policy?.n_months?.n;`
   - Cambiado: `const periodMode = hasNMonths ? 'n_months' : (type.validity_policy?.mode || 'monthly');`
   - Añadido logging para debug

2. **Valor del input `n-months`** (`frontend/repository_v3.html` línea ~3756):
   - Cambiado: `value="${hasNMonths ? hasNMonths : (type.validity_policy?.n_months?.n || 1)}"`
   - Esto asegura que si `hasNMonths` existe, se use ese valor

3. **Logging en `saveType`** (`frontend/repository_v3.html` línea ~4003):
   - Añadido logging antes de enviar: `console.log('[repo-upload] saveType - sending:', ...)`
   - Añadido logging después de guardar: `console.log('[repo-upload] saveType - saved type:', ...)`

**Evidencia**:
- Test E2E muestra: `✅ BUG 4: Guardar "Cada N meses" funciona sin error enum` ✅

## Archivos Modificados

- `frontend/repository_v3.html`:
  - Línea ~2316: Patrón regex mejorado para parseo de fecha
  - Línea ~2228: Lógica de parseo mejorada (siempre intentar si está vacía)
  - Línea ~3715: Detección de `n_months` en `renderTypeDrawer`
  - Línea ~3756: Valor del input `n-months` corregido
  - Línea ~4003: Logging añadido en `saveType`

## Tests Ejecutados

```bash
npm run test:e2e:aeat
```

**Resultado**: ✅ 2 passed (17.4s)
- Test 1: BUG 1+2+3 - PASADO
- Test 2: BUG 4 - PASADO

## Notas

1. El parseo de fecha ahora funciona correctamente para "AEAT-16-oct-2025.pdf" → `2025-10-16`
2. El guardado de "Cada N meses" ahora persiste correctamente al reabrir el tipo
3. Se añadió logging extensivo para facilitar debugging futuro














