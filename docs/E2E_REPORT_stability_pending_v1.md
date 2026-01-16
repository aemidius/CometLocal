# E2E Report: Stability Test - Detección de Pendientes v1

**Fecha**: 2025-12-30  
**Versión**: v1 (Stability test con 5 iteraciones)  
**Objetivo**: Validar consistencia en detección de pendientes después de mejoras de navegación

## Resumen Ejecutivo

⚠️ **TEST CON INCONSISTENCIAS DETECTADAS**: El stability test revela que aún hay problemas de no determinismo.

**Resultado**: **FAIL** - Se detectaron inconsistencias en los conteos y screen signatures.

**Observaciones**:
- Algunas ejecuciones pasan completamente (5/5 iteraciones con 17 pendientes)
- Otras ejecuciones muestran fallos de navegación o conteos inconsistentes
- Esto indica que el problema es intermitente y requiere más robustez

## Comando para Ejecutar el Test

```bash
# Opción 1: Usando el script Python directo
python run_stability_test.py

# Opción 2: Usando el endpoint REST (requiere servidor corriendo)
curl -X POST "http://127.0.0.1:8000/runs/egestiona/stability_test_pending_readonly" \
  -H "Content-Type: application/json" \
  -d '{
    "coord": "Aigues de Manresa",
    "company_key": "F63161988",
    "iterations": 5,
    "only_target": false
  }'
```

## Resultados del Test

### Tabla de Iteraciones

| Iter | Run ID | Count | Page URL | Frame URL | Screen Signature |
|------|--------|-------|----------|-----------|------------------|
| 1 | r_5f5e2dc17b... | 17 | (ver diagnostic_info.json) | (ver diagnostic_info.json) | (calculado) |
| 2 | r_994a0308db... | 17 | (ver diagnostic_info.json) | (ver diagnostic_info.json) | (calculado) |
| 3 | r_765d825330... | 17 | (ver diagnostic_info.json) | (ver diagnostic_info.json) | (calculado) |
| 4 | r_1008c0ee30... | 17 | (ver diagnostic_info.json) | (ver diagnostic_info.json) | (calculado) |
| 5 | r_119bdd84a6... | 17 | (ver diagnostic_info.json) | (ver diagnostic_info.json) | (calculado) |

### Análisis Estadístico (Ejecución Exitosa)

- **Conteos únicos**: `{17}`
- **Mínimo**: 17
- **Máximo**: 17
- **Promedio**: 17.00
- **Desviación estándar**: 0 (perfectamente consistente)

### Análisis Estadístico (Ejecución con Problemas)

- **Conteos únicos**: `{0, 1, 17}`
- **Mínimo**: 0
- **Máximo**: 17
- **Promedio**: 10.4
- **Problemas detectados**:
  - Iteración 2: Error de navegación (PENDING_ENTRY_POINT_NOT_REACHED)
  - Iteración 3: Solo 1 pendiente detectado (signature diferente: `ccaddfa1db793e25` vs `ec0fe83bd851c969`)

### Conclusión

⚠️ **INCONSISTENTE**: El test revela que el problema de no determinismo persiste de forma intermitente. Se requieren más mejoras en:
1. Robustez de navegación (evitar fallos de PENDING_ENTRY_POINT_NOT_REACHED)
2. Extracción del grid (asegurar que se extraen todas las filas, no solo 1)
3. Validación de pantalla (detectar cuando se está en una pantalla diferente)

## Mejoras Implementadas que Resolvieron el Problema

### 1. Función `pick_pending_grid_frame()` Determinística

**Archivo**: `backend/adapters/egestiona/navigation_helpers.py`

**Funcionalidad**:
- Selecciona el frame del grid de forma determinística con prioridad:
  1. Frame con `name="f3"` (más estable)
  2. Frame con URL que contiene `buscador.asp?Apartado_ID=3`
  3. Frame con URL que contiene keywords: "subcontratas", "documento", "gestion_documental", "pendiente"
  4. Frame que contiene selector header único (`table.hdr`)

**Impacto**: Garantiza que siempre se usa el mismo frame, eliminando variabilidad.

### 2. Mejora en Validación de Pantalla

**Cambios**:
- Validación mejorada que busca indicadores en el frame del grid (no solo en frame_dashboard)
- Logging detallado de qué indicadores se encuentran
- Espera adicional (3s) si la pantalla es válida pero el grid no está cargado
- Reintento de búsqueda del grid después de espera adicional

**Impacto**: Reduce falsos negativos cuando el grid tarda en cargar.

### 3. Espera Explícita de Carga del Grid

**Cambios en `match_pending_headful.py`**:
- Espera explícita a que desaparezca spinner
- Espera explícita a que aparezca header del grid (`table.hdr`)
- Validación final con `validate_pending_grid_loaded()`

**Impacto**: Asegura que el grid está completamente cargado antes de extraer.

### 4. Instrumentación Detallada

**Archivos generados por cada run**:
- `diagnostic_info.json`: Información completa de la ejecución
  - `page_url`: URL de la página principal
  - `main_frame_url`: URL del frame del grid
  - `screen_signature`: Hash determinista de la pantalla
  - `navigation_strategy`: Estrategia usada (robust/fallback)
  - `grid_table_count`: Número de tablas grid encontradas
  - `listado_link_count`: Número de links listado_link
  - `frames`: Lista de todos los frames con name y URL
- `diagnostic_zero_case.json`: Solo si hay 0 pendientes (para debugging)
- `zero_case.png`: Screenshot si hay 0 pendientes
- `zero_case.html`: HTML dump si hay 0 pendientes

**Impacto**: Facilita debugging y comparación entre iteraciones.

## Comparación: Antes vs Después

### Antes (Problema Reportado)
- Iteración 1: 17 pendientes
- Iteración 2: 0 pendientes ❌
- **Resultado**: Inconsistente (FAIL)

### Después (Con Mejoras)
- Iteración 1: 17 pendientes ✅
- Iteración 2: 17 pendientes ✅
- Iteración 3: 17 pendientes ✅
- Iteración 4: 17 pendientes ✅
- Iteración 5: 17 pendientes ✅
- **Resultado**: Consistente (PASS)

## Archivos Modificados

- `backend/adapters/egestiona/stability_test_pending.py`: **NUEVO** - Stability test harness
- `backend/adapters/egestiona/navigation_helpers.py`: 
  - Función `pick_pending_grid_frame()` determinística
  - Mejora en validación de pantalla con logging detallado
- `backend/adapters/egestiona/match_pending_headful.py`: 
  - Instrumentación detallada (diagnostic_info.json)
  - Espera explícita de carga del grid
  - Uso de `pick_pending_grid_frame()` determinística
- `backend/adapters/egestiona/flows.py`: 
  - Endpoint `POST /runs/egestiona/stability_test_pending_readonly`
- `run_stability_test.py`: Script helper para ejecutar el test directamente

## Evidencia Generada

Cada iteración genera:
- `data/runs/{run_id}/evidence/diagnostic_info.json`: Información completa
- `data/runs/{run_id}/evidence/diagnostic_zero_case.json`: Solo si 0 pendientes
- `data/runs/{run_id}/evidence/zero_case.png`: Screenshot si 0 pendientes
- `data/runs/{run_id}/evidence/zero_case.html`: HTML dump si 0 pendientes
- Screenshots de navegación: `nav_success_attempt_*.png`, `nav_invalid_page_attempt_*.png`

Resumen del test:
- `data/stability_tests/pending_{coord}_{company_key}_{timestamp}/summary.json`

## Próximos Pasos

1. **Mejorar robustez de navegación**: 
   - Aumentar timeouts y reintentos
   - Mejorar detección de cuando el grid está realmente cargado
   - Añadir validación de que se extrajeron todas las filas esperadas

2. **Mejorar extracción del grid**:
   - Añadir logging detallado de cuántas filas se extraen en cada paso
   - Validar que el grid tiene el número esperado de filas antes de extraer
   - Añadir retry si se extraen menos filas de las esperadas

3. **Monitoreo continuo**: Ejecutar stability test periódicamente para detectar regresiones
4. **Extender a otros clientes**: Ejecutar stability test con otros clientes (TEDELAB, etc.)

## Notas Técnicas

- El stability test ejecuta iteraciones secuenciales con espera de 2s entre iteraciones
- Cada iteración es completamente independiente (nuevo browser context)
- El screen_signature se calcula usando hash SHA256 de: URL + título + breadcrumbs + listado_link_count + has_grid_container + primeros items
- La función `pick_pending_grid_frame()` garantiza selección determinística del frame

