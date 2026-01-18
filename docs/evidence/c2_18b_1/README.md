# SPRINT C2.18B.1 — UI "Revisión del plan" (Decision Packs) + ejecución guiada

## Resumen

Implementación de una UI completa (vanilla HTML/JS) para revisar planes congelados, crear Decision Packs y ejecutar auto_upload con overrides manuales.

## Archivos modificados/creados

### Nuevos archivos:
- `docs/evidence/c2_18b_1/README.md` - Esta documentación

### Archivos modificados:
- `backend/api/auto_upload_routes.py` - Añadido endpoint `GET /api/plans/{plan_id}` optimizado para UI
- `frontend/repository_v3.html` - Añadida página "Revisión Plan (CAE)" con funcionalidad completa

## Funcionalidades implementadas

### 1. Carga de Plan
- Input para ingresar `plan_id`
- Botón "Cargar" que llama a `GET /api/plans/{plan_id}`
- Persistencia del último `plan_id` en localStorage

### 2. Tabla de Items
- Muestra todos los items del plan con:
  - Item ID
  - Tipo
  - Sujeto (empresa/trabajador)
  - Periodo
  - Estado (decision actual)
  - Reason (primary_reason_code)
  - Acciones: "Ver debug" / "Decidir"

### 3. Ver Debug
- Modal que carga `GET /api/runs/{plan_id}/matching_debug/{item_id}`
- Muestra:
  - Outcome (decision, reason_code, human_hint)
  - Pipeline steps (input/output counts)
  - Top candidates (si hay)

### 4. Editor de Decisiones
- Modal con selector de acción:
  - **MARK_AS_MATCH**: Lista candidates del debug + input manual para doc_id
  - **FORCE_UPLOAD**: Input para ruta de archivo
  - **SKIP**: Textarea para motivo (requerido)
- Campo "Razón / Notas" para todas las acciones
- Guarda decisiones en memoria (draft) y localStorage

### 5. Decision Pack
- Muestra contador de items decididos
- Botón "Guardar Pack" que llama a `POST /api/plans/{plan_id}/decision_packs`
- Muestra `decision_pack_id` una vez guardado
- Link a endpoint para ver pack completo

### 6. Ejecución
- Botón "Ejecutar con Pack" que llama a `POST /api/runs/auto_upload/execute`
- Muestra resultado con:
  - Status
  - Run ID (si existe)
  - Resumen (total, success, failed, skipped)
  - Link a run summary

## Data-testid añadidos

- `plan-review-load` - Contenedor de carga
- `plan-review-load-btn` - Botón cargar
- `plan-review-table` - Tabla de items
- `plan-item-row-{item_id}` - Fila de item
- `plan-item-debug-{item_id}` - Botón ver debug
- `plan-item-decide-{item_id}` - Botón decidir
- `decision-action-select` - Selector de acción
- `decision-docid-input` - Input doc_id
- `decision-filepath-input` - Input file path
- `decision-reason-input` - Textarea razón
- `decision-save-item` - Botón guardar decisión
- `decision-pack-save` - Botón guardar pack
- `decision-pack-execute` - Botón ejecutar
- `decision-pack-id` - ID del pack guardado

## Cómo probar manualmente

### 1. Cargar un plan existente

1. Abrir `http://127.0.0.1:8000/repository_v3.html#plan_review`
2. En el input "Plan ID", pegar un `plan_id` existente (ej: de `data/runs/plan_*/plan_response.json`)
3. Clic en "Cargar"
4. Verificar que se muestra la tabla con items

### 2. Ver debug de un item NO_MATCH

1. En la tabla, buscar un item con estado "NO_MATCH"
2. Clic en "Ver debug"
3. Verificar que se muestra el modal con:
   - Outcome (primary_reason_code, human_hint)
   - Pipeline steps
   - Top candidates (si hay)

### 3. Crear Decision Pack con SKIP

1. Clic en "Decidir" en un item
2. Seleccionar acción "SKIP"
3. Ingresar motivo (ej: "Documento ya subido manualmente")
4. Clic en "Guardar Decisión"
5. Verificar que el contador de "Items decididos" aumenta
6. Clic en "Guardar Pack"
7. Verificar que aparece el `decision_pack_id`

### 4. Ejecutar con Decision Pack

1. Con un pack guardado, clic en "Ejecutar con Pack"
2. Confirmar ejecución
3. Verificar que se muestra el resultado con:
   - Status
   - Run ID
   - Resumen
   - Link a run summary

## Persistencia

- **localStorage**: 
  - `plan_review_last_plan_id` - Último plan_id cargado
  - `plan_review_draft_{plan_id}` - Draft de decisiones por plan_id

## Evidencias

Las evidencias se pueden generar:
1. Capturando screenshots de la UI en cada paso
2. Guardando el `decision_pack_id` generado
3. Verificando que el pack se guardó en `data/runs/{plan_id}/decision_packs/`
4. Verificando que la ejecución usó el pack correctamente

## Notas técnicas

- La UI usa el mismo estilo que `repository_v3.html` (dark theme, cards, badges)
- Los modales usan `modal-overlay` y `modal` classes existentes
- La persistencia en localStorage permite no perder trabajo al recargar
- Los data-testid están listos para tests E2E con Playwright

## Compatibilidad

- ✅ No rompe pantallas existentes del repositorio
- ✅ Mantiene estilo del frontend existente
- ✅ Maneja estados: loading / ready / error
- ✅ Data-testid añadidos para E2E futuro
