# Dashboard - Revisar Pendientes CAE

## Descripción

Funcionalidad avanzada en el Dashboard HOME (`/`) que permite revisar pendientes CAE con filtros configurables en modo READ-ONLY.

## Ubicación

- **UI**: Botón "📋 Revisar Pendientes CAE" en el Dashboard HOME
- **Endpoint**: `POST /runs/egestiona/build_submission_plan_readonly`

## Filtros Disponibles

### 1. Empresa propia (quién entrega documentación)
- **Fuente**: `/api/config/org`
- **UI**: Dropdown con buscador incremental
- **Opciones**: "Todas" + empresa propia (tax_id)
- **Value**: `company_key` (tax_id de la organización)

### 2. Cliente / Empresa a coordinar
- **Fuente**: `/api/config/platforms` (coordinaciones)
- **UI**: Dropdown con buscador incremental
- **Opciones**: "Todas" + lista de coordinaciones de todas las plataformas
- **Value**: `coord` (label de la coordinación)

### 3. Plataforma CAE (dónde se sube)
- **Fuente**: `/api/config/platforms`
- **UI**: Dropdown con buscador incremental
- **Opciones**: "Todas" + lista de plataformas (egestiona, cetaima, ecoordina...)
- **Value**: `platform_key` (string)
- **Requerido**: Sí (no se puede ejecutar con "Todas")

### 4. Ámbito del documento
- **UI**: Radio buttons
- **Opciones**:
  - Documentos de trabajador
  - Documentos de empresa
  - Ambos (default)
- **Behavior**:
  - Si "empresa": desactiva selector de trabajador
  - Si "trabajador" o "ambos": habilita selector de trabajador

### 5. Trabajador (solo si aplica)
- **Fuente**: `/api/config/people`
- **UI**: Dropdown con buscador incremental
- **Opciones**: "Todos" + lista de personas
- **Value**: `person_key` (worker_id)
- **Filtro**: Por nombre/apellidos/DNI
- **Matching robusto**: El sistema realiza matching inteligente contra la columna "Elemento" del grid:
  - **Preferente por DNI**: Si el elemento contiene "(DNI)", se compara directamente el DNI
  - **Matching por nombre**: Soporta formatos como "Apellidos, Nombre (DNI)" y "Nombre Apellidos"
  - **Normalización**: Elimina acentos, normaliza espacios y puntuación para matching robusto
  - **Ejemplo**: Si en eGestiona aparece "Verdés Ochoa, Oriol (38133024J)" y en people.json está "Oriol Verdés Ochoa" con DNI "38133024J", el matching funciona correctamente

### 6. Tipo de documento (filtro UI-side)
- **Fuente**: `/api/repository/types`
- **UI**: Dropdown con buscador incremental
- **Opciones**: "Todos" + tipos activos
- **Value**: `type_id`
- **Nota**: Este filtro es solo para la visualización de resultados, no afecta la ejecución del endpoint

## Ejecución

### Validaciones
1. **Plataforma requerida**: Debe seleccionarse una plataforma específica (no "Todas")
2. **Solo eGestiona soportado**: Actualmente solo funciona con `platform_key="egestiona"`

### Parámetros del Endpoint
- `coord`: Coordinación seleccionada (si no es "Todas")
- `company_key`: Empresa propia (si no es "Todas")
- `person_key`: Trabajador (si no es "Todos")
- `limit`: 50 (default)
- `only_target`: `true` si company_key y person_key están seleccionados, `false` en caso contrario

### Resultados

El modal muestra:
1. **Run ID y link**: Link directo a `/runs/<run_id>` para ver evidence completo
2. **Tabla de resultados**:
   - Columnas: Pendiente, Empresa, Trabajador, Documento, Vigencia, Decisión, Razones, Acciones
   - Badges de decisión:
     - `AUTO_SUBMIT_OK`: Verde (badge-success)
     - `REVIEW_REQUIRED`: Amarillo (badge-warning)
     - `NO_MATCH` / `SKIP_*`: Rojo (badge-error)
   - Botón "Ver detalle" por fila:
     - Expande razones completas
     - Muestra doc_id
     - Link a repositorio documental

## Persistencia

Los filtros se guardan en `localStorage` con la clave `pendingReviewFilters`:
- Se cargan automáticamente al abrir el modal
- Se guardan al cerrar el modal o cambiar filtros

## Limitaciones Actuales

1. **Solo eGestiona**: El sistema actual solo soporta la plataforma "egestiona"
2. **Futuro**: Cuando haya adaptadores para otras plataformas (cetaima, ecoordina), se ampliará el soporte

## Endpoints Relacionados

- `GET /api/config/org`: Organización propia
- `GET /api/config/people`: Lista de personas
- `GET /api/config/platforms`: Lista de plataformas y coordinaciones
- `GET /api/repository/types`: Tipos de documento
- `POST /runs/egestiona/build_submission_plan_readonly`: Ejecutar revisión
- `GET /runs/{run_id}/file/evidence/submission_plan.json`: Leer resultados

## Visualización del Plan

Tras ejecutar correctamente la revisión, la UI muestra:

1. **Run ID y Link**: Información del run generado con link a `/runs/<run_id>`

2. **Tabla de Resultados**: Tabla renderizada dentro del modal con las filas del plan:
   - **Pendiente**: tipo_doc + elemento
   - **Empresa**: de pending_ref
   - **Trabajador**: de pending_ref
   - **Documento propuesto**: file_name y/o doc_id si hay match
   - **Vigencia propuesta**: inicio/fin de proposed_fields
   - **Decisión**: decision.action con badge de color
   - **Razones**: resumen corto (primera razón + "(+N)" si hay más)
   - **Acciones**: botón "Ver detalle"

3. **Botón "Ver detalle"**: Expande/colapsa una fila detalle inline que muestra:
   - Razones completas
   - Blocking issues si existen
   - Matched doc completo (doc_id, status, validity, confidence)
   - Matched rule (si existe)
   - Link al run `/runs/<run_id>`

4. **Filtro UI por Tipo de Documento**:
   - Filtra filas renderizadas (no toca backend)
   - Si type_id == "Todos" => no filtrar
   - Si hay matched_doc.type_id => comparar
   - Si NO hay match => ocultar cuando se filtra por tipo concreto

5. **Estados de Carga**:
   - Mientras descarga JSON: muestra "⏳ Cargando plan..."
   - Si falla la descarga pero el run se creó: muestra run_id + link + error legible
   - Si el plan está vacío: muestra "0 pendientes" (no es error)

6. **Persistencia**:
   - Guarda en localStorage: company_key, coord, platform_key, scope, person_key, type_filter
   - Al abrir modal, restaura estado guardado

## Notas Técnicas

- **Modo READ-ONLY**: No ejecuta envíos, solo genera plan y evidence
- **Determinismo**: Los resultados son deterministas basados en los filtros
- **Trazabilidad**: Cada ejecución genera un run_id único con evidence completo
- **Visualización**: La tabla se renderiza directamente en el modal, no requiere navegar al run viewer

