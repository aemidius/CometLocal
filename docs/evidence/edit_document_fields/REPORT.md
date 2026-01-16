# Mejora: Modal Editar Documento - Campos Editables Completos

## Resumen

Se ha mejorado el modal "Editar documento" en la pantalla "Buscar documentos" para permitir editar todos los metadatos clave del documento, separando claramente el "Estado de tramitación" (workflow) del "Estado de validez" (calculado, readonly).

## Problema Original

1. El modal solo mostraba: Tipo, Archivo, Empresa/Persona y "Estado" (workflow)
2. **NO permitía editar**:
   - Mes/Año (period_key)
   - Fecha de emisión (issue_date)
   - Fecha inicio de vigencia (validity_start_date)
3. El campo "Estado" se confundía con "Estado de validez" (Válido/Expira pronto/Expirado)

## Solución Implementada

### Backend

1. **Extendido `DocumentUpdateRequest`** (`backend/repository/document_repository_routes.py`):
   - Añadidos campos: `issue_date`, `validity_start_date`, `period_key`

2. **Actualizado endpoint `PUT /api/repository/docs/{doc_id}`**:
   - Maneja actualización de `issue_date` (actualiza `doc.issued_at` y `doc.extracted.issue_date`)
   - Maneja actualización de `validity_start_date` (actualiza `doc.extracted.validity_start_date`)
   - Maneja actualización de `period_key`
   - Recalcula `computed_validity` si se modificaron fechas relevantes

### Frontend

1. **Modal rediseñado** (`frontend/repository_v3.html`):
   - **Estado de validez (readonly)**: Muestra badge con color, fecha de caducidad, días restantes/expirados
   - **Estado de tramitación (editable)**: Renombrado de "Estado", con ayuda explicativa
   - **Campos condicionales**:
     - **Mes/Año** (`period_key`): Solo si el tipo requiere período (period_kind !== 'NONE')
     - **Fecha de emisión** (`issue_date`): Si `type.issue_date_required` o si ya existe
     - **Fecha inicio de vigencia** (`validity_start_date`): Si `type.validity_start_mode === 'manual'` o si ya existe

2. **Función `saveDocumentEdit()` actualizada**:
   - Recopila todos los campos editables (fechas, período, workflow status)
   - Envía al backend en el formato correcto

## Separación: Estado de Tramitación vs Estado de Validez

### Estado de Tramitación (Workflow) - EDITABLE

**Label**: "Estado de tramitación"

**Opciones**:
- **Borrador**: Datos en preparación
- **Revisado**: Verificado internamente
- **Listo para enviar**: Preparado para plataforma CAE
- **Enviado**: Ya subido/enviado a plataforma

**Nota**: Este estado NO afecta a la caducidad. La caducidad depende de las fechas.

### Estado de Validez (Calculado) - READONLY

**Label**: "Estado de validez (calculado)"

**Valores posibles**:
- 🟢 **Válido**: Documento vigente
- 🟡 **Expira pronto**: Expira dentro del threshold (default: 30 días)
- 🔴 **Expirado**: Ya expirado
- ⚪ **Desconocido**: No se puede calcular

**Información mostrada**:
- Badge con estado
- Fecha de caducidad
- Días restantes o días expirados

**Nota**: Este estado se calcula automáticamente según las fechas del documento. No es editable.

## Campos Editables

### 1. Empresa / Trabajador
- **Editable**: Sí
- **Obligatorio**: Sí
- **Validación**: Según scope del tipo

### 2. Mes/Año (period_key)
- **Editable**: Sí
- **Obligatorio**: Si el tipo requiere período mensual
- **Formato**: YYYY-MM (ej: 2025-01)
- **Condición**: Solo se muestra si `period_kind !== 'NONE'`

### 3. Fecha de emisión (issue_date)
- **Editable**: Sí
- **Obligatorio**: Si `type.issue_date_required === true`
- **Formato**: Date input (YYYY-MM-DD)
- **Condición**: Se muestra si `type.issue_date_required` o si ya existe

### 4. Fecha inicio de vigencia (validity_start_date)
- **Editable**: Sí
- **Obligatorio**: Si `type.validity_start_mode === 'manual'`
- **Formato**: Date input (YYYY-MM-DD)
- **Condición**: Se muestra si `type.validity_start_mode === 'manual'` o si ya existe

### 5. Estado de tramitación (status)
- **Editable**: Sí
- **Obligatorio**: No (tiene valor por defecto)
- **Opciones**: draft, reviewed, ready_to_submit, submitted

## Archivos Modificados

### Backend
1. **`backend/repository/document_repository_routes.py`**:
   - Extendido `DocumentUpdateRequest` con nuevos campos
   - Actualizado `update_document()` para manejar nuevos campos
   - Añadida recalculación de `computed_validity` tras cambios

### Frontend
2. **`frontend/repository_v3.html`**:
   - Rediseñado `showEditDocumentModal()` con todos los campos
   - Actualizado `saveDocumentEdit()` para recopilar nuevos campos
   - Añadida lógica condicional para mostrar campos según tipo

### Tests
3. **`tests/e2e_edit_document_fields.spec.js`** (NUEVO):
   - Test 1: Verificar que modal muestra campos editables
   - Test 2: Verificar que muestra Estado de validez (readonly)
   - Test 3: Verificar campos condicionales (fechas, período)
   - Test 4: Verificar que guardar cambios funciona

## Validación

### Ejecutar Tests E2E

```bash
npx playwright test tests/e2e_edit_document_fields.spec.js -v
```

### Verificar Manualmente

1. Abrir `http://127.0.0.1:8000/repository_v3.html#buscar`
2. Click en "Editar" en cualquier documento
3. Verificar que aparecen:
   - Estado de validez (readonly) con badge
   - Estado de tramitación (editable) con ayuda
   - Campos condicionales según el tipo de documento
4. Modificar un campo y guardar
5. Verificar que se refleja el cambio

## Evidencia Requerida

1. ✅ Screenshot del modal mostrando:
   - Estado de validez (readonly)
   - Estado de tramitación (editable + ayuda)
   - Campos de fechas (si aplican)
2. ✅ Output PASS del test E2E
3. ✅ Comparación antes/después de editar un campo

## Notas Técnicas

1. **Recalculación automática**: Al cambiar fechas o período, el backend recalcula `computed_validity` automáticamente
2. **Validación condicional**: Los campos se muestran según las reglas del tipo de documento
3. **Consistencia con Upload**: Reutiliza la misma lógica de validación que la pantalla de Upload
4. **Sin breaking changes**: Los campos existentes siguen funcionando igual

## Próximos Pasos (Opcionales)

1. Añadir validación en frontend antes de guardar (reusar lógica de Upload)
2. Mostrar preview del efecto de cambios (ej: "Si cambias la fecha, caducará el...")
3. Añadir campo "Notas" si existe en el modelo
4. Permitir editar `type_id` con validación estricta (si se requiere)







