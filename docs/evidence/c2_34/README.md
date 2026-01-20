# SPRINT C2.34 — Evidencias de Observabilidad de Matching

## Objetivo
Implementar observabilidad determinista cuando NO se sube nada (AUTO_UPLOAD=0 / NO_MATCH / REVIEW_REQUIRED), generando un informe determinista y mostrándolo en la UI con lenguaje humano.

## Archivos de Evidencia

### matching_debug_report.json
Ejemplo de respuesta del backend con `debug_report` (expuesto como `matching_debug_report_c234` en match_result, pero como `debug_report` en plan_item) cuando un item tiene decisión NO_MATCH o REVIEW_REQUIRED.

**Ubicación:** `docs/evidence/c2_34/matching_debug_report.json`

**Estructura:**
- `pending_id`: Identificador del item pendiente
- `decision`: "NO_MATCH" | "REVIEW_REQUIRED"
- `filters_applied`: Filtros aplicados durante el matching
- `reasons`: Lista de razones ordenadas por prioridad (cada una con code, message, hint opcional, meta opcional)
- `counters`: Contadores por etapa del pipeline de matching

**Códigos de razón implementados:**
- `NO_LOCAL_DOCS`: No hay documentos en el repositorio
- `TYPE_NOT_FOUND`: El tipo de documento no existe
- `TYPE_INACTIVE`: El tipo de documento está inactivo
- `ALIAS_NOT_MATCHING`: No se reconoce el alias en la plataforma
- `SCOPE_MISMATCH`: Mismatch entre scope del tipo y del requisito
- `PERIOD_MISMATCH`: No hay documentos para el periodo solicitado
- `COMPANY_MISMATCH`: Documentos asignados a otra empresa
- `PERSON_MISMATCH`: Documentos asignados a otro trabajador
- `VALIDITY_MISMATCH`: Documentos no válidos para la fecha actual

### 01_matching_debug_panel.png
Screenshot de la UI mostrando el panel "¿Por qué no se ha subido?" cuando hay items con debug_report.

**Ubicación:** Se generará al ejecutar el flujo E2E o manualmente desde la UI.

## Implementación

### Backend
- `backend/repository/matching_debug_codes_v1.py`: Taxonomía de códigos
- `backend/repository/document_matcher_v1.py`: Función `build_matching_debug_report()`
- `backend/adapters/egestiona/submission_plan_headful.py`: Integración en plan items

### Frontend
- `frontend/repository_v3.html`: Función `renderMatchingDebugPanel()` con data-testid:
  - `matching-debug-panel`
  - `matching-debug-primary`
  - `matching-debug-reasons`
  - `matching-debug-actions`

### Tests
- `backend/tests/test_matching_debug_report_no_local_docs.py`: Unit tests para NO_LOCAL_DOCS
- `backend/tests/test_matching_debug_report_period_mismatch.py`: Unit tests para PERIOD_MISMATCH
- `tests/matching_debug_report_ui.spec.js`: E2E test para UI

## Verificación

Para verificar la implementación:

1. **Unit tests:**
   ```bash
   pytest backend/tests/test_matching_debug_report_no_local_docs.py
   pytest backend/tests/test_matching_debug_report_period_mismatch.py
   ```

2. **E2E test:**
   ```bash
   npx playwright test tests/matching_debug_report_ui.spec.js
   ```

3. **Manual - Cómo reproducir caso NO_MATCH:**
   - Abrir `http://127.0.0.1:8000/repository_v3.html#cae-plan`
   - Configurar contexto (empresa propia, plataforma, empresa coordinada)
   - Generar un plan con un tipo de documento que NO existe en el repositorio
   - O generar un plan con un periodo que NO tiene documentos
   - Verificar que aparece el panel "¿Por qué no se ha subido?" (data-testid="matching-debug-panel")
   - Verificar que el texto es humano (no JSON crudo)
   - Verificar que hay acciones sugeridas (data-testid="matching-debug-actions")
   - Verificar que el motivo principal está visible (data-testid="matching-debug-primary")

## Notas

- El reporte solo se genera cuando `decision` es "NO_MATCH" o "REVIEW_REQUIRED"
- El reporte es determinista: mismo input -> mismo output
- Los reasons están ordenados por prioridad (orden determinista por code)
- La UI solo muestra el panel cuando hay items con `debug_report` y no son AUTO_UPLOAD
