# SPRINT C2.36 — Evidencias de Preview de Impacto + Sugerencias Inteligentes

## Objetivo
Antes de que el humano confirme una acción asistida (asignar alias / crear tipo), el sistema explica el impacto esperado, sugiere opciones y evita errores — sin automatizar nada y sin aprendizaje silencioso.

## Archivos de Evidencia

### impact_preview_example.json
Ejemplo de respuesta del endpoint `/api/preview/assign-alias` o `/api/preview/create-type`.

**Estructura:**
```json
{
  "will_affect": {
    "pending_count": 1,
    "examples": ["P-2025-12-A"],
    "platforms": ["egestiona"]
  },
  "will_add": {
    "aliases": ["T205.0"]
  },
  "will_not_change": [
    "Documentos existentes",
    "Reglas de validez del tipo",
    "Overrides de validez",
    "Aliases existentes",
    "Otros tipos de documento"
  ],
  "confidence_notes": [
    "Scope coincide (company)",
    "Periodo compatible con validez del tipo"
  ]
}
```

### suggestions_example.json
Ejemplo de respuesta del endpoint `/api/suggestions/types`.

**Estructura:**
```json
{
  "suggestions": [
    {
      "type_id": "T104_AUTONOMOS_RECEIPT",
      "type_name": "Recibo Autónomos",
      "score": 0.9,
      "reasons": [
        "Alias coincide: 'T205.0'",
        "Scope coincide (worker)",
        "Plataforma compatible (egestiona)",
        "Validez periódica compatible"
      ]
    },
    {
      "type_id": "OTHER_TYPE",
      "type_name": "Otro Tipo",
      "score": 0.4,
      "reasons": [
        "Nombre coincide: 'Otro Tipo'"
      ]
    }
  ]
}
```

### 01_impact_preview_panel.png
Screenshot del panel de preview de impacto antes de confirmar.

**Ubicación:** Se generará al ejecutar el flujo E2E o manualmente desde la UI.

### 02_suggestions_panel.png
Screenshot del panel de sugerencias con tipos recomendados.

**Ubicación:** Se generará al ejecutar el flujo E2E o manualmente desde la UI.

## Implementación

### Backend

**Módulos nuevos:**
- `backend/repository/impact_preview_v1.py`: Engine de preview de impacto (read-only)
  - `preview_assign_alias()`: Preview de añadir alias
  - `preview_create_type()`: Preview de crear tipo
  - `ImpactPreviewV1`: Modelo de preview

- `backend/repository/type_suggestions_v1.py`: Engine de sugerencias (read-only)
  - `suggest_types()`: Sugiere tipos con scoring determinista
  - `TypeSuggestionV1`: Modelo de sugerencia

**Endpoints API:**
- `backend/api/preview_routes.py`:
  - `POST /api/preview/assign-alias`: Preview de asignar alias
  - `POST /api/preview/create-type`: Preview de crear tipo

- `backend/api/suggestions_routes.py`:
  - `POST /api/suggestions/types`: Obtener sugerencias de tipos

### Frontend

**Modificaciones en `frontend/repository_v3.html`:**
- Función `loadSuggestionsForItem()`: Carga sugerencias para un item
- Función `useSuggestedType()`: Usa un tipo sugerido
- Función `showImpactPreview()`: Obtiene preview de impacto
- Función `showPreviewAndConfirmAssignAlias()`: Muestra preview antes de confirmar alias
- Función `showPreviewAndConfirmCreateType()`: Muestra preview antes de confirmar crear tipo
- Panel de sugerencias en `renderMatchingDebugPanel()` con `id="suggestions-container-{itemId}"`
- Panel de preview con `data-testid="impact-preview-panel"` y `data-testid="impact-preview-confirm"`

### Tests

**Unit tests:**
- `backend/tests/test_impact_preview.py`: Tests para impact preview
  - `test_preview_assign_alias_no_write`: Verifica que preview no escribe
  - `test_preview_assign_alias_already_exists`: Verifica detección de alias existente
  - `test_preview_create_type_no_write`: Verifica que preview no escribe
  - `test_preview_deterministic`: Verifica determinismo

- `backend/tests/test_type_suggestions.py`: Tests para suggestions
  - `test_suggest_types_scoring`: Verifica scoring determinista
  - `test_suggestions_deterministic`: Verifica determinismo
  - `test_suggestions_limit`: Verifica límite de sugerencias

**E2E tests:**
- `tests/impact_preview_e2e.spec.js`: Tests E2E para preview y sugerencias
  - `should show preview before confirming assign alias`
  - `should show suggestions with explanations`
  - `should not apply changes when canceling preview`

## Verificación

Para verificar la implementación:

1. **Unit tests:**
   ```bash
   pytest backend/tests/test_impact_preview.py -v
   pytest backend/tests/test_type_suggestions.py -v
   ```

2. **E2E test:**
   ```bash
   npx playwright test tests/impact_preview_e2e.spec.js
   ```

3. **Manual - Cómo reproducir:**
   - Abrir `http://127.0.0.1:8000/repository_v3.html#cae-plan`
   - Generar un plan con items NO_MATCH
   - Verificar que aparecen sugerencias de tipos (si hay tipos similares)
   - Click en "Asignar a un tipo existente"
   - Seleccionar un tipo
   - Click en "Ver Preview"
   - Verificar que aparece panel de impacto con:
     - Qué afectará
     - Qué añadirá
     - Qué NO cambiará
     - Notas de confianza
   - Marcar checkbox de confirmación
   - Verificar que botón "Aplicar" se habilita
   - Click en "Aplicar" para confirmar
   - O click en "Cancelar" para cancelar (no debe cambiar nada)

## Guardrails Implementados

- ✅ Preview es read-only (no escribe nada)
- ✅ Determinismo: mismo input → mismo preview
- ✅ Confirmación reforzada requerida (checkbox)
- ✅ Scoring explicable (sin ML opaco)
- ✅ Sugerencias limitadas (máximo 3 por defecto)
- ✅ Cancelar preview no cambia nada
- ✅ Guardrails de contexto intactos

## Notas

- El preview solo calcula impacto, no aplica cambios
- Las sugerencias usan scoring determinista con pesos explícitos:
  - +0.4 si nombre/alias coincide
  - +0.3 si scope coincide
  - +0.2 si plataforma coincide
  - +0.1 si período/validez compatible
- El preview se genera antes de confirmar, no durante la acción
- Las sugerencias se cargan automáticamente cuando hay items con debug_report
