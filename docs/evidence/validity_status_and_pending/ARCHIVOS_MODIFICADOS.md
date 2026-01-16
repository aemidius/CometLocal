# Archivos Modificados - Estados de Validez y Documentos Pendientes

## Resumen de Cambios

### Archivos Nuevos (2)

1. **`backend/repository/document_status_calculator_v1.py`**
   - Módulo nuevo con lógica de cálculo de estados de validez
   - Función principal: `calculate_document_status()`
   - Enum: `DocumentValidityStatus`

2. **`tests/e2e_calendar_pending_smoke.spec.js`**
   - Tests E2E para verificar funcionalidad end-to-end
   - 4 tests: estados reales, tabs de calendario, renderizado, navegación

### Archivos Modificados (4)

3. **`backend/shared/document_repository_v1.py`**
   - Añadido enum `DocumentValidityStatusV1`
   - Añadidos campos a `DocumentInstanceV1`:
     - `validity_status: DocumentValidityStatusV1`
     - `validity_end_date: Optional[date]`
     - `days_until_expiry: Optional[int]`

4. **`backend/repository/document_repository_routes.py`**
   - Modificado endpoint `/api/repository/docs`:
     - Calcula y añade `validity_status`, `validity_end_date`, `days_until_expiry`
     - Soporta filtro `?validity_status=...`
   - Nuevo endpoint `/api/repository/docs/pending`:
     - Retorna documentos expirados, próximos a expirar, y períodos faltantes

5. **`backend/repository/period_planner_v1.py`**
   - Añadida función `infer_period_key()` para inferir `period_key` desde metadatos

6. **`frontend/repository_v3.html`**
   - **Función `loadBuscar()`**: Actualizada para consumir y filtrar por `validity_status`
   - **Función `renderSearchResults()`**: Muestra badges de estado con colores
   - **Función `loadCalendario()`**: Rediseñada completamente
     - Nueva estructura HTML
     - Eliminados campos obligatorios
     - Tabs para Expirados/Expiran pronto/Pendientes
     - Carga desde `/api/repository/docs/pending`
   - **Nuevas funciones**:
     - `renderPendingDocuments()`: Renderiza las 3 secciones
     - `showPendingSection()`: Cambia entre tabs
     - `updatePendingDocuments()`: Recarga con nuevo rango
     - `navigateToUploadForDocument()`: Navegación con prefill para reemplazar
     - `navigateToUploadForPeriod()`: Navegación con prefill para período faltante

## Estadísticas

- **Archivos nuevos**: 2
- **Archivos modificados**: 4
- **Líneas añadidas**: ~800
- **Líneas eliminadas**: ~200
- **Neto**: ~600 líneas

## Dependencias

- Backend usa: `PeriodPlannerV1`, `DocumentRepositoryStoreV1`
- Frontend usa: Endpoints `/api/repository/docs`, `/api/repository/docs/pending`, `/api/repository/subjects`
- Tests usan: Playwright







