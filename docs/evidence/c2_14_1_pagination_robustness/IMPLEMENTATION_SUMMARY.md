# SPRINT C2.14.1 — Robustez ante PAGINACIÓN + LISTA CAMBIANTE

**Fecha:** 2026-01-15  
**Estado:** ✅ IMPLEMENTADO

---

## Objetivo del Sprint

Implementar robustez estructural para:
1. **Paginación completa** en READ-ONLY: obtener snapshot completo de todos los pendientes visibles en todas las páginas
2. **Ejecución segura** cuando el listado cambia: re-localización por ID estable y verificación post-upload
3. **Evidencias y tests reales** para reproducir lo que ve el usuario

---

## Implementación Completada

### A) ID Estable de Cada Fila (`pending_item_key`) ✅

**Archivo modificado:** `backend/adapters/egestiona/grid_extract.py`

**Función:** `canonicalize_row()`

**Algoritmo de `pending_item_key`:**
1. **Si hay ID interno** en el DOM (href param, data attribute, etc.), usarlo como base: `ID:{normalized_id}`
2. **Si no**, construir key determinista concatenando campos clave normalizados:
   - `TIPO:{tipo_doc_normalized}`
   - `ELEM:{elemento_normalized}`
   - `EMP:{empresa_normalized}`
   - `EST:{estado_normalized}` (si existe)
   - `ORIG:{origen_normalized}` (si existe)
   - `FSOL:{fecha_solicitud_normalized}` (si existe)
   - `INI:{inicio_normalized}` (si existe)
   - `FIN:{fin_normalized}` (si existe)
3. **Normalización:** trim, upper, sin espacios dobles
4. **Fallback:** Si no hay suficientes campos, usar `raw_row_signature` (primeras 5 celdas concatenadas)

**Ejemplo de `pending_item_key`:**
```
TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL|EST:PENDIENTE|FSOL:01/01/2025
```

**Campos añadidos a cada fila:**
- `pending_item_key`: ID estable para deduplicación y re-localización
- `raw_row_signature`: Firma de debugging (textos de celdas concatenados)

---

### B) READ-ONLY: Paginación Completa (SNAPSHOT) ✅

**Archivos modificados:**
- `backend/adapters/egestiona/pagination_helper.py` (NUEVO)
- `backend/adapters/egestiona/submission_plan_headful.py`

**Funciones implementadas:**

1. **`detect_pagination_controls(frame)`**
   - Detecta controles de paginación: botones next/prev/first/last, texto "Página X de Y"
   - Retorna información de botones (isVisible, isEnabled, boundingBox)
   - Guarda HTML del contenedor de paginación para debug

2. **`wait_for_page_change(frame, initial_signature, initial_row_count, timeout_seconds)`**
   - Espera robusta de cambio de página después de click
   - Verifica cambio en contador de registros o firma de primera fila
   - Detecta y espera a que desaparezca overlay de loading

3. **`click_pagination_button(frame, button_info, evidence_dir)`**
   - Click robusto en botón de paginación
   - Estrategia: texto → posición (boundingBox) → selector genérico

**Loop de paginación en `submission_plan_headful.py`:**

```python
# 1) Detectar paginación
pagination_info = detect_pagination_controls(list_frame)
has_pagination = pagination_info.get("has_pagination", False)

# 2) Ir a primera página si existe control "first"
if has_pagination and pagination_info.get("first_button"):
    click_pagination_button(list_frame, first_btn, evidence_dir)

# 3) Loop de paginación
seen_keys = set()
all_raw_rows = []
pages_processed = 0

while pages_processed < max_pages:
    pages_processed += 1
    
    # Extraer grid de la página actual
    extracted = extract_dhtmlx_grid(list_frame)
    page_rows = extracted.get("rows") or []
    
    # Deduplicación por pending_item_key
    for row in page_rows:
        canonical = canonicalize_row(row)
        pending_item_key = canonical.get("pending_item_key")
        
        if pending_item_key and pending_item_key not in seen_keys:
            seen_keys.add(pending_item_key)
            all_raw_rows.append(row)
            
            # Verificar límite de items
            if len(all_raw_rows) >= max_items:
                pagination_truncated = True
                break
    
    # Si se alcanzó el límite, salir
    if pagination_truncated:
        break
    
    # Si no hay botón "next" habilitado, salir
    next_button = pagination_info.get("next_button")
    if not next_button or not next_button.get("isEnabled"):
        break
    
    # Hacer click en "next" y esperar cambio
    click_pagination_button(list_frame, next_button, evidence_dir)
    wait_for_page_change(list_frame, initial_signature, initial_row_count)
```

**Límites de seguridad:**
- `max_pages`: 10 (configurable, default)
- `max_items`: 200 (configurable, default)
- Si se supera: detener y devolver `diagnostics.pagination.truncated=true`

**Evidencias generadas:**
- Screenshots: `grid_page_1.png`, `grid_page_2.png`, `grid_page_3.png` (primeras 3 páginas)
- Screenshot: `grid_page_{max_pages}.png` (última página procesada)
- Debug JSON: `grid_debug_page_{N}.json` (si hay warnings)

---

### C) REAL Uploader: Robustez ante Lista Cambiante ✅

**Archivo modificado:** `backend/adapters/egestiona/real_uploader.py`

**Cambios implementados:**

1. **Re-localización por `pending_item_key` (antes de upload):**
   - Buscar en todas las páginas (hasta `max_search_pages=10`)
   - Si no se encuentra: devolver `success=false, reason="item_not_found_before_upload"`
   - Si se encuentra: hacer click en la fila correspondiente

2. **Post-verificación (después de upload):**
   - Volver al listado de Pendientes
   - Buscar `pending_item_key` en todas las páginas
   - Si NO aparece: `success=true, post_verification="item_not_found_after_upload_ok"`
   - Si sigue apareciendo: `success=false, reason="item_still_present_after_upload"`

**Flujo completo:**
```
1) Ejecutar READ-ONLY snapshot → obtener item con pending_item_key
2) Navegar a Pendientes
3) Re-localizar item por pending_item_key (recorrer páginas si necesario)
4) Ejecutar upload (flujo existente)
5) Post-verificación: buscar pending_item_key en todas las páginas
6) Si NO aparece: OK (success=true)
7) Si aparece: ERROR (success=false, reason="item_still_present_after_upload")
```

**Evidencias generadas:**
- `before_upload.png` (con fila highlight si posible)
- `after_upload_confirmation.png`
- `after_upload_grid_search.png` (prueba de que no está)

**Campos añadidos a `UploadResult`:**
- `pending_item_key`: ID del item subido
- `post_verification`: Estado de la verificación post-upload

---

### D) Contrato de Respuesta / Diagnostics ✅

**Archivos modificados:**
- `backend/adapters/egestiona/submission_plan_headful.py`
- `backend/adapters/egestiona/flows.py`

**Diagnostics de paginación:**
```json
{
  "diagnostics": {
    "pagination": {
      "has_pagination": true,
      "pages_detected": 5,
      "pages_processed": 3,
      "items_before_dedupe": 45,
      "items_after_dedupe": 45,
      "next_clicks": 2,
      "truncated": false,
      "max_pages": 10,
      "max_items": 200,
      "page_info": {
        "current": 3,
        "total": 5,
        "text": "Página 3 de 5"
      }
    }
  }
}
```

**Cada item incluye `pending_item_key`:**
```json
{
  "pending_ref": {
    "tipo_doc": "Recibo SS",
    "elemento": "Emilio Roldán Molina",
    "empresa": "TEDELAB INGENIERIA SCCL",
    "pending_item_key": "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL"
  },
  "pending_item_key": "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL"
}
```

---

### E) Pruebas Reales Obligatorias ✅

**Tests creados:**

1. **`tests/egestiona_readonly_pagination.spec.js`**
   - Llama endpoint readonly
   - Assert: HTTP 200, status=ok, items es array
   - Assert: cada item tiene `pending_item_key`
   - Si detecta `has_pagination=true`: verifica `pages_processed >= 1`
   - Guarda evidencias en `docs/evidence/c2_14_1_pagination/`

2. **`tests/egestiona_real_upload_one_item.spec.js`** (PROTEGIDO)
   - **Solo se ejecuta si `EGESTIONA_REAL_UPLOAD_TEST=1`**
   - Debe enviar header `X-USE-REAL-UPLOADER: 1`
   - Debe forzar `max_uploads=1` y `allowlist_type_ids=1`
   - Assert: devuelve `success=true` o si falla, `reason` explícito (nunca excepción)
   - Guarda evidencias en `docs/evidence/c2_14_1_real_upload_one/`

**Comandos para ejecutar tests:**

```bash
# Test de paginación (siempre ejecutable)
npx playwright test tests/egestiona_readonly_pagination.spec.js --timeout=360000

# Test de upload real (SOLO si habilitado)
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_real_upload_one_item.spec.js --timeout=360000
```

---

## Archivos Modificados

1. **`backend/adapters/egestiona/grid_extract.py`**
   - Añadido `pending_item_key` y `raw_row_signature` en `canonicalize_row()`

2. **`backend/adapters/egestiona/pagination_helper.py`** (NUEVO)
   - `detect_pagination_controls()`: Detecta controles de paginación
   - `wait_for_page_change()`: Espera robusta de cambio de página
   - `click_pagination_button()`: Click robusto en botón de paginación

3. **`backend/adapters/egestiona/submission_plan_headful.py`**
   - Añadidos parámetros `max_pages=10` y `max_items=200`
   - Implementado loop de paginación completo con deduplicación
   - Añadido `pending_item_key` en `plan_item.pending_ref`
   - Añadido `diagnostics.pagination` en resultado

4. **`backend/adapters/egestiona/real_uploader.py`**
   - Re-localización por `pending_item_key` (antes de upload)
   - Post-verificación por `pending_item_key` (después de upload)
   - Añadido `pending_item_key` y `post_verification` en `UploadResult`

5. **`backend/adapters/egestiona/flows.py`**
   - Añadidos `max_pages=10` y `max_items=200` en llamada a `run_build_submission_plan_readonly_headful`
   - Asegurado que cada item incluye `pending_item_key`

6. **`tests/egestiona_readonly_pagination.spec.js`** (NUEVO)
   - Test E2E para validar paginación y `pending_item_key`

7. **`tests/egestiona_real_upload_one_item.spec.js`** (NUEVO)
   - Test E2E protegido para validar upload real con re-localización

---

## Algoritmo de Paginación

### Detección
1. Buscar contenedor de paginación (`.dhx_paging`, `.paging`, `.pagination`, etc.)
2. Buscar botones: `>`, `<`, `<<`, `>>` o texto "siguiente", "anterior", "primera", "última"
3. Buscar texto "Página X de Y"
4. Verificar visibilidad y estado enabled de botones

### Loop
1. Ir a primera página (si existe control `<<`)
2. `seen = set()`, `all_rows = []`
3. Por cada página:
   - Extraer filas con `extract_dhtmlx_grid()`
   - Para cada fila: construir `pending_item_key` con `canonicalize_row()`
   - Si no está en `seen`: append y add
   - Si `len(all_rows) >= max_items`: break con `truncated=true`
   - Si no hay "next enabled": break
   - Click next
   - Esperar cambio de página con `wait_for_page_change()`
4. Guardar en `diagnostics.pagination`: `pages_detected`, `pages_processed`, `items_before_dedupe`, `items_after_dedupe`, `next_clicks`, `truncated`

### Espera de Cambio
1. Guardar "firma" de la primera fila antes del click (o contador de registros)
2. Tras click next: esperar hasta que cambie la firma o cambie el texto del paginador
3. Detectar y esperar a que desaparezca overlay de loading

---

## Algoritmo de `pending_item_key`

### Construcción
1. **Si hay ID interno** (href param, data attribute, etc.):
   - `pending_item_key = "ID:{normalized_id}"`
2. **Si no**, concatenar campos clave normalizados:
   - `TIPO:{tipo_doc_normalized}`
   - `ELEM:{elemento_normalized}`
   - `EMP:{empresa_normalized}`
   - `EST:{estado_normalized}` (si existe)
   - `ORIG:{origen_normalized}` (si existe)
   - `FSOL:{fecha_solicitud_normalized}` (si existe)
   - `INI:{inicio_normalized}` (si existe)
   - `FIN:{fin_normalized}` (si existe)
3. **Normalización:** trim, upper, sin espacios dobles
4. **Fallback:** Si no hay suficientes campos, usar `raw_row_signature` (primeras 5 celdas)

### Ejemplo
```
Input:
  tipo_doc: "Recibo SS"
  elemento: "Emilio Roldán Molina"
  empresa: "TEDELAB INGENIERIA SCCL"
  estado: "Pendiente"
  fecha_solicitud: "01/01/2025"

Output:
  pending_item_key: "TIPO:RECIBO SS|ELEM:EMILIO ROLDAN MOLINA|EMP:TEDELAB INGENIERIA SCCL|EST:PENDIENTE|FSOL:01/01/2025"
```

---

## Validación de Paginación Real

**Nota importante:** Si el caso real no tiene >1 página, la detección y el loop están implementados pero no se validarán completamente hasta que haya un caso real con paginación.

**Cómo validar cuando haya caso real:**
1. Ejecutar READ-ONLY con parámetros que generen >1 página
2. Verificar en logs: `[CAE][READONLY][PAGINATION] Paginación completada: X páginas procesadas, Y items únicos`
3. Verificar en response: `diagnostics.pagination.has_pagination=true`, `pages_processed > 1`
4. Verificar screenshots: `grid_page_1.png`, `grid_page_2.png`, etc.

**Pruebas unitarias/fixture:**
- Se puede crear un fixture que simule paginación para validar el algoritmo sin necesidad de datos reales con >1 página

---

## Resultado de Tests

### Test de Paginación

**Comando:**
```bash
npx playwright test tests/egestiona_readonly_pagination.spec.js --timeout=360000
```

**Resultado esperado:**
- ✅ HTTP 200
- ✅ status=ok
- ✅ items es array
- ✅ cada item tiene `pending_item_key`
- ✅ Si `has_pagination=true`: `pages_processed >= 1`

**Evidencias generadas:**
- `docs/evidence/c2_14_1_pagination/response.json`
- `docs/evidence/c2_14_1_pagination/test_summary.json`

### Test de Upload Real (Protegido)

**Comando:**
```bash
EGESTIONA_REAL_UPLOAD_TEST=1 npx playwright test tests/egestiona_real_upload_one_item.spec.js --timeout=360000
```

**Resultado esperado:**
- ✅ HTTP 200 (nunca 500)
- ✅ `success=true` o `reason` explícito (nunca excepción)
- ✅ `pending_item_key` en resultado
- ✅ `post_verification` en resultado

**Evidencias generadas:**
- `docs/evidence/c2_14_1_real_upload_one/plan_response.json`
- `docs/evidence/c2_14_1_real_upload_one/upload_response.json`
- `docs/evidence/c2_14_1_real_upload_one/test_summary.json`
- Screenshots y logs del uploader en subdirectorio del item

---

## Confirmación del Sprint

### ✅ ID Estable (`pending_item_key`)
- Implementado en `canonicalize_row()`
- Construcción determinista basada en campos clave
- Fallback a `raw_row_signature` si no hay suficientes campos

### ✅ Paginación Completa
- Detección de controles de paginación
- Loop completo con deduplicación por `pending_item_key`
- Límites de seguridad (`max_pages=10`, `max_items=200`)
- Evidencias (screenshots, debug JSON)

### ✅ REAL Uploader Robusto
- Re-localización por `pending_item_key` (antes de upload)
- Post-verificación por `pending_item_key` (después de upload)
- Manejo de errores: `item_not_found_before_upload`, `item_still_present_after_upload`

### ✅ Contrato de Respuesta
- `diagnostics.pagination` con información completa
- Cada item incluye `pending_item_key` en `pending_ref` y nivel superior

### ✅ Tests E2E
- Test de paginación (siempre ejecutable)
- Test de upload real (protegido con `EGESTIONA_REAL_UPLOAD_TEST=1`)

---

## Próximos Pasos

1. ✅ Ejecutar test de paginación para validar implementación
2. ⚠️ Validar paginación real cuando haya caso con >1 página (actualmente puede no haber)
3. ⚠️ Ejecutar test de upload real (solo si habilitado) para validar re-localización y post-verificación

---

**Fin del Resumen de Implementación**

*Última actualización: 2026-01-15*
