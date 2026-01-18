# SPRINT C2.19A.1 — UI de administración de Learning Hints + integración en Plan Review

## Resumen

Extensión de la UI de plan_review para visualizar y administrar hints de aprendizaje:
- Visualización de hints aplicados en el modal de debug
- Columna "Hints" en la tabla de items
- Panel completo de administración de hints con filtros y desactivación

## Archivos modificados/creados

### Archivos modificados:
- `backend/api/learning_routes.py` - Completado con platform, limit, reason en disable
- `backend/shared/learning_store.py` - Añadido soporte para reason en disable_hint
- `frontend/repository_v3.html` - Extendido con:
  - Visualización de applied_hints en debug modal
  - Columna "Hints" en tabla de items
  - Panel completo de Learning con filtros y tabla
  - Botón "Learning" en cabecera

### Nuevos archivos:
- `docs/evidence/c2_19a_1/README.md` - Esta documentación

## Funcionalidades implementadas

### 1. Visualización de hints aplicados en Debug Modal
- Sección "Learning Hints Aplicados" en el modal de debug
- Muestra: hint_id (clicable), strength (EXACT/SOFT), effect (resolved/boosted/ignored), reason
- Badges visuales para cada estado
- Clic en hint_id abre el panel Learning enfocado en ese hint

### 2. Columna "Hints" en tabla de items
- Muestra número de hints aplicados si el debug ya se ha consultado
- Badge con tooltip mostrando efectos
- No fuerza llamadas extra (solo muestra si ya está en cache)

### 3. Panel "Learning (Hints)"
- Botón "🧠 Learning (Hints)" en cabecera de plan_review
- Filtros:
  - Type ID
  - Subject Key
  - Period Key
- Tabla de resultados con:
  - Hint ID (con botón copiar)
  - Strength (EXACT/SOFT)
  - Type ID esperado
  - Subject Key
  - Period Key
  - Local Doc ID
  - Estado (Active/Disabled)
  - Acción: Disable (si está activo)
- Persistencia de filtros en localStorage

### 4. API completada
- `GET /api/learning/hints` - Añadidos parámetros: platform, limit
- `POST /api/learning/hints/{hint_id}/disable` - Añadido body opcional con reason

## Pasos para reproducir manualmente

### 1. Abrir Plan Review

```bash
# 1. Iniciar servidor (si no está corriendo)
# 2. Abrir navegador en http://localhost:8000
# 3. Navegar a "Revisión Plan (CAE)" desde el menú lateral
# 4. Cargar un plan_id existente
```

### 2. Ver hints aplicados en Debug

1. En la tabla de items, hacer clic en "Ver debug" de un item que tenga hints aplicados
2. En el modal de debug, buscar la sección "Learning Hints Aplicados"
3. Verificar que muestra:
   - Número de hints aplicados
   - Tabla con hint_id, strength, effect, reason
   - Badges visuales (resolved/boosted/ignored, EXACT/SOFT)
4. Hacer clic en un hint_id para abrir el panel Learning enfocado en ese hint

### 3. Ver columna Hints en tabla

1. En la tabla de items, verificar que existe la columna "Hints"
2. Si un item tiene debug cargado con hints aplicados, debería mostrar un badge con el número
3. Si no se ha abierto el debug, mostrará "—" con tooltip

### 4. Abrir panel Learning y filtrar

1. Hacer clic en el botón "🧠 Learning (Hints)" en la cabecera
2. En el modal, verificar que aparecen los filtros:
   - Type ID
   - Subject Key
   - Period Key
3. Rellenar filtros (ejemplo: type_id="T104_AUTONOMOS_RECEIPT")
4. Hacer clic en "Buscar"
5. Verificar que la tabla muestra los hints filtrados

### 5. Desactivar un hint

1. En el panel Learning, encontrar un hint activo
2. Hacer clic en "Disable"
3. Confirmar en el diálogo
4. Opcionalmente, proporcionar una razón
5. Verificar que:
   - El hint aparece como "Disabled" en la tabla
   - El botón "Disable" desaparece
   - La lista se recarga automáticamente

### 6. Verificar que hint desactivado no se aplica

1. Desactivar un hint que estaba siendo aplicado
2. Regenerar un plan con items similares
3. Abrir el debug de un item que debería haber usado ese hint
4. Verificar que:
   - `applied_hints` está vacío o
   - El hint aparece como "ignored" con razón "Hint disabled"

## Ejemplos de uso

### Ejemplo 1: Ver hints aplicados en debug

```javascript
// Al abrir debug de un item con hints:
{
  "outcome": {
    "applied_hints": [
      {
        "hint_id": "hint_a1b2c3d4e5f6g7h8",
        "strength": "EXACT",
        "effect": "resolved",
        "reason": "EXACT hint matched, doc verified"
      }
    ]
  }
}
```

En la UI se muestra:
- Sección "Learning Hints Aplicados" con 1 hint
- Tabla con hint_id clicable, badge "EXACT", badge "resolved", reason

### Ejemplo 2: Filtrar hints en panel Learning

```bash
# Filtros aplicados:
type_id: "T104_AUTONOMOS_RECEIPT"
subject_key: "COMPANY123"
period_key: "2025-01"

# Resultado: Solo hints que coincidan con todos los filtros
```

### Ejemplo 3: Desactivar hint

```javascript
// POST /api/learning/hints/hint_abc123/disable
{
  "reason": "Hint ya no es válido, documento fue eliminado"
}

// Response:
{
  "hint_id": "hint_abc123",
  "disabled": true
}
```

## Data test IDs añadidos

Para testing E2E:

- `debug-hints-section` - Sección de hints en debug modal
- `debug-hint-row-{hint_id}` - Fila de hint en debug
- `learning-open` - Botón para abrir panel Learning
- `learning-filter-type` - Input filtro Type ID
- `learning-filter-subject` - Input filtro Subject Key
- `learning-filter-period` - Input filtro Period Key
- `learning-search` - Botón buscar
- `learning-table` - Contenedor de tabla de resultados
- `learning-disable-{hint_id}` - Botón desactivar hint

## Comandos útiles

```bash
# Listar hints con filtros
curl "http://127.0.0.1:8000/api/learning/hints?type_id=T104_AUTONOMOS_RECEIPT&limit=50"

# Desactivar hint con razón
curl -X POST "http://127.0.0.1:8000/api/learning/hints/hint_abc123/disable" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Hint inválido"}'
```

## Notas importantes

1. **Cache de debug**: Los hints aplicados solo se muestran en la columna "Hints" si el debug ya se ha consultado (está en cache). Esto evita llamadas extra por performance.

2. **Persistencia de filtros**: Los filtros del panel Learning se guardan en localStorage con la clave `learning_last_filters`.

3. **Reversibilidad**: Los hints desactivados se pueden ver si se incluye `include_disabled=true` en la búsqueda, pero no se aplican durante el matching.

4. **Navegación**: Clic en hint_id en el debug modal abre el panel Learning y hace scroll al hint específico.

5. **Confirmación**: La desactivación de hints requiere confirmación para evitar errores accidentales.

## Ubicación de archivos

- **UI**: `frontend/repository_v3.html` (funciones de plan_review y learning panel)
- **API**: `backend/api/learning_routes.py`
- **Store**: `backend/shared/learning_store.py`
- **Evidencias**: `docs/evidence/c2_19a_1/README.md`
