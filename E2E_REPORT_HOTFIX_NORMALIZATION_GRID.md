# Reporte E2E - HOTFIX Normalización Global + Grid Extraction

## IMPLEMENTACIÓN COMPLETADA

### PARTE 1 — NORMALIZACIÓN GLOBAL (BACKEND)

**Archivo mejorado**: `backend/shared/text_normalizer.py`

Funciones implementadas:

1. **`normalize_text(text: Optional[str]) -> str`**:
   - Unicode NFKD normalization
   - Elimina diacríticos (acentos, tildes, diéresis, etc.)
   - Convierte "ñ" a "n" explícitamente
   - lower()
   - Elimina puntuación común (.,;:()[]{}"') convirtiéndola en espacios
   - Colapsa espacios múltiples
   - strip()

2. **`normalize_for_match(text: Optional[str]) -> str`**:
   - Alias de `normalize_text()` por claridad semántica

3. **`contains_all_tokens(haystack: str, tokens: list[str]) -> bool`**:
   - Verifica si un texto normalizado contiene todos los tokens normalizados

4. **`safe_join(*parts: Optional[str]) -> str`**:
   - Une partes no vacías con espacio

**Archivos refactorizados**:

1. **`backend/shared/person_matcher.py`**:
   - ✅ Usa `normalize_text()` centralizada
   - ✅ Eliminada función duplicada `normalize_text_robust()`

2. **`backend/repository/document_matcher_v1.py`**:
   - ✅ Usa `normalize_text()` de `text_normalizer`
   - ✅ Mejora mensajes cuando `base_text` está vacío
   - ✅ Mantiene compatibilidad con código existente

3. **`backend/repository/rule_based_matcher_v1.py`**:
   - ✅ Usa `normalize_text()` de `text_normalizer`
   - ✅ Normaliza `base_text`, `empresa_text`, y tokens de reglas

4. **`backend/adapters/egestiona/submission_plan_headful.py`**:
   - ✅ Usa `normalize_text()` para matching de empresa y persona
   - ✅ Normaliza campos antes de comparación

5. **`backend/adapters/egestiona/execute_plan_headful.py`**:
   - ✅ Usa normalización robusta en `_row_matches_target()`

6. **`backend/adapters/egestiona/match_pending_headful.py`**:
   - ✅ Usa normalización robusta en `_row_matches_target()`

### PARTE 2 — FIX REAL: EXTRACCIÓN DEL GRID (DHTMLX)

**Archivo creado**: `backend/adapters/egestiona/grid_extract.py`

Funciones implementadas:

1. **`extract_dhtmlx_grid(frame: Any) -> Dict[str, Any]`**:
   - Extrae headers de `table.hdr` (mejor header por score)
   - Extrae filas de `table.obj.row20px` (mejor tabla por número de filas)
   - Filtra filas completamente vacías
   - Retorna: headers, rows, raw_rows_preview, mapping_debug, warnings

2. **`canonicalize_row(row: Dict[str, Any]) -> Dict[str, Any]`**:
   - Canonicaliza keys a campos estándar:
     - `tipo_doc`: "Tipo Documento" / "tipo_doc" / "Tipo" / "TipoDoc"
     - `elemento`: "Elemento" / "elemento"
     - `empresa`: "Empresa" / "empresa"
     - `estado`, `origen`, `fecha_solicitud`, `inicio`, `fin`
   - Convierte strings vacíos a `None` (no "N/A")
   - Mantiene `_raw_row` para debug

**Archivo refactorizado**: `backend/adapters/egestiona/submission_plan_headful.py`

1. **Uso de `extract_dhtmlx_grid()`**:
   - Reemplaza código JavaScript inline duplicado
   - Guarda `grid_debug.json` si hay warnings
   - Filtra filas que no tienen `tipo_doc` o `elemento`

2. **Canonicalización de filas**:
   - Usa `canonicalize_row()` antes de filtrar
   - Solo incluye filas con contenido real

3. **Matching mejorado**:
   - Usa campos canonicalizados (`r.get("empresa")` en lugar de `r.get("Empresa")`)
   - Normalización robusta aplicada

### PARTE 3 — UI: QUE NO PONGA "-" SI HAY DATOS

**Archivo actualizado**: `frontend/home.html`

1. **Renderizado de campos**:
   - ✅ No muestra "-" cuando hay datos reales
   - ✅ Muestra string vacío si no hay datos (no "-" fijo)
   - ✅ `pendienteText`, `empresa`, `trabajador`, `docInfo`, `vigencia` usan valores reales o vacío

2. **Mensajes de razones mejorados**:
   - ✅ Si reason menciona `text: ""`, lo reemplaza con mensaje claro:
     "Pending item missing text fields (tipo_doc/elemento). Check grid extraction."

### PARTE 4 — PRUEBAS E2E OBLIGATORIAS

#### Prueba 1: person_key=ovo

**Comando**:
```bash
POST /runs/egestiona/build_submission_plan_readonly?coord=Kern&company_key=F63161988&person_key=ovo&limit=50&only_target=true
```

**Resultado**:
- ✅ Run ID generado: `r_836f3458b0b844c4aa19fff55434bd48`
- ✅ Plan items: 2
- ✅ Datos extraídos correctamente:
  - `tipo_doc`: 'T104.0 Último recibo bancario pago cuota autónomos'
  - `elemento`: 'Verdés Ochoa, Oriol (38133024J)'
  - `empresa`: 'TEDELAB INGENIRIA SCCL (F63161988)'

**Análisis**:
- ✅ El extractor de grid funciona correctamente
- ✅ Los campos se extraen con datos reales (no vacíos)
- ✅ El matching de persona funciona (encuentra 2 items para Oriol)

#### Prueba 2: only_target=false (scope empresa)

**Comando**:
```bash
POST /runs/egestiona/build_submission_plan_readonly?coord=Kern&company_key=F63161988&limit=50&only_target=false
```

**Resultado**:
- ✅ Run ID generado: `r_0d64cebd36884cc1b0593d702f1cdec0`
- ✅ Plan items: 7
- ✅ Datos extraídos correctamente:
  - `tipo_doc`: 'T104.0 Último recibo bancario pago cuota autónomos'
  - `elemento`: 'Moran Villalobos, Joan (44023445L)'
  - `empresa`: 'TEDELAB INGENIRIA SCCL (F63161988)'

**Análisis**:
- ✅ El extractor funciona para scope empresa (only_target=false)
- ✅ Los campos se extraen con datos reales (no vacíos)
- ✅ No hay filas vacías con "-" en los resultados

## ESTADO FINAL

✅ **Normalización global**: Implementada y aplicada en todo el sistema
✅ **Extractor de grid**: Funcionando correctamente, extrae datos reales
✅ **UI mejorada**: No muestra "-" cuando hay datos, mensajes claros
✅ **Pruebas E2E**: Ejecutadas, resultados positivos

## ARCHIVOS MODIFICADOS/CREADOS

1. `backend/shared/text_normalizer.py` - Mejorado con nuevas funciones
2. `backend/adapters/egestiona/grid_extract.py` - Nuevo extractor robusto
3. `backend/adapters/egestiona/submission_plan_headful.py` - Refactorizado
4. `backend/shared/person_matcher.py` - Usa normalización centralizada
5. `backend/repository/document_matcher_v1.py` - Usa normalización centralizada, mensajes mejorados
6. `backend/repository/rule_based_matcher_v1.py` - Usa normalización centralizada
7. `backend/adapters/egestiona/execute_plan_headful.py` - Usa normalización robusta
8. `backend/adapters/egestiona/match_pending_headful.py` - Usa normalización robusta
9. `frontend/home.html` - UI mejorada, no muestra "-" cuando hay datos

## COMMITS SUGERIDOS

```
fix(norm): global accent-insensitive normalization for matching
fix(egestiona): robust dhtmlx grid extraction with evidence
fix(ui): render pending fields and clearer reasons when missing
```

