# E2E Report: Repositorio UI v2 - Fase 1

## Fecha
2025-12-30

## Objetivo
Implementar y probar la Fase 1 de la nueva UI del Repositorio Documental:
1. Upload Wizard (MVP usable)
2. Cobertura por períodos (time-series operable)
3. Reglas (UI mínima para herencia + autogeneración)

## Estado
**IMPLEMENTACIÓN COMPLETA** - Pendiente pruebas reales en navegador

## Cambios Implementados

### 1. Upload Wizard
- ✅ Drag&drop + multiarchivo
- ✅ Autodetección de tipo/persona/período desde filename
- ✅ Form por archivo con validaciones inline
- ✅ Month picker para tipos mensuales
- ✅ Detección de duplicados con modal de confirmación
- ✅ Guardado batch con feedback por archivo

### 2. Vista Cobertura
- ✅ Selector de tipo/sujeto/rango
- ✅ Tabla de períodos con estados (AVAILABLE/MISSING/LATE)
- ✅ Acción "Subir para este período" que pre-llena upload
- ✅ Integración con API `/api/repository/types/{type_id}/expected`

### 3. Vista Reglas
- ✅ Tabla con scope GLOBAL/COORD
- ✅ Detección de coords sin reglas
- ✅ Autogeneración de reglas GLOBAL
- ✅ Visualización de herencia

### 4. Backend
- ✅ Endpoint `/api/repository/types/{type_id}/expected` añadido
- ✅ Endpoint upload acepta `period_key` como parámetro
- ✅ Modelo de reglas extendido con `RuleScopeV1` (GLOBAL/COORD)
- ✅ Matcher actualizado para herencia (COORD → GLOBAL)

## Archivos Modificados
- `frontend/repository_v2.html` - Nueva UI completa
- `backend/repository/document_repository_routes.py` - Endpoint `/expected` y `period_key` en upload
- `backend/shared/document_repository_v1.py` - `RuleScopeV1` enum
- `backend/repository/rule_based_matcher_v1.py` - Herencia de reglas
- `backend/app.py` - Ruta actualizada a `repository_v2.html`

## Pruebas Pendientes

### Upload Wizard
1. Subir 2 PDFs (multiarchivo):
   - Uno con filename parseable que infiera período
   - Otro sin inferencia → obliga a elegir período con month picker
2. Guardar todo, comprobar que aparecen en /repository/documents
3. Probar duplicado para mismo período → aparece modal y reemplaza o cancela correctamente

### Cobertura
1. Seleccionar T104_AUTONOMOS_RECEIPT + trabajador Emilio + 12 meses
2. Ver AVAILABLE en el mes que se subió y MISSING en otros
3. Click "Subir para este período" abre upload precargado

### Reglas
1. Crear regla GLOBAL egestiona + T104_AUTONOMOS_RECEIPT con tokens desde aliases
2. Confirmar que Aigues de Manresa queda "cubierto" por herencia (en UI debe verse)
3. Probar autogeneración de reglas

## Notas
- El backend está configurado para servir `repository_v2.html`
- Se requiere reiniciar el backend o hacer hard refresh (Ctrl+F5) para ver la nueva UI
- Backend corriendo en http://127.0.0.1:8000

## Próximos Pasos
1. Reiniciar backend
2. Abrir http://127.0.0.1:8000/repository con Ctrl+F5
3. Ejecutar pruebas reales según especificaciones
4. Guardar capturas en `docs/evidence/repo_ui_v2_phase1/`
5. Actualizar este reporte con resultados























