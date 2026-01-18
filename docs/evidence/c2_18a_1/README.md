# SPRINT C2.18A.1 — Matching Debug: DATA_DIR_MISMATCH

## Resumen

Extensión de C2.18A que añade la detección de `DATA_DIR_MISMATCH` cuando el repositorio se "ve vacío" porque el `data_dir` resuelto difiere del esperado.

## Cambios realizados

### 1. Campos añadidos al meta del reporte:
- `data_dir_expected` - Ruta esperada del data_dir (desde settings/env/default)
- `data_dir_expected_source` - Origen de la ruta esperada:
  - `"settings.repository_root_dir"` - Desde settings.json
  - `"ENV:COMETLOCAL_DATA_DIR"` - Variable de entorno COMETLOCAL_DATA_DIR
  - `"ENV:REPOSITORY_DATA_DIR"` - Variable de entorno REPOSITORY_DATA_DIR
  - `"config.DATA_DIR (default)"` - Desde backend.config.DATA_DIR
  - `"default (calculated)"` - Calculado desde repo root
- `data_dir_exists` - Si el directorio existe (bool)
- `data_dir_contents_sample` - Lista de hasta 10 entradas del directorio (solo nombres)

### 2. Heurística de detección:
Se detecta `DATA_DIR_MISMATCH` cuando:
- `repo_docs_total == 0`
- `data_dir_expected` existe
- `normpath(data_dir_resolved) != normpath(data_dir_expected)`

### 3. Human hint mejorado:
El `human_hint` incluye:
- `data_dir_resolved` vs `data_dir_expected`
- `data_dir_expected_source` para indicar dónde revisar

## Ejemplo de debug.json con DATA_DIR_MISMATCH

Ver `example_data_dir_mismatch.json` en este directorio.

## Tests

```bash
python -m pytest tests/test_matching_debug_report.py::test_data_dir_mismatch_scenario -v
python -m pytest tests/test_matching_debug_report.py::test_data_dir_match_repo_empty_scenario -v
```

## Archivos modificados

- `backend/shared/matching_debug_report.py` - Añadidos campos al meta y lógica de detección de expected
- `backend/repository/document_matcher_v1.py` - Heurística DATA_DIR_MISMATCH en detección de causas
- `tests/test_matching_debug_report.py` - 2 nuevos tests

## Compatibilidad

- ✅ `DATA_DIR_MISMATCH` ya existía en `PrimaryReasonCode` (retrocompatible)
- ✅ No cambia semántica del matching ni `plan_id`
- ✅ Tests verdes (8/8 pasan)
