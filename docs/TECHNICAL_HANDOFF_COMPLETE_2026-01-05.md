# Handoff Técnico Completo — CometLocal
**Fecha:** 2026-01-05  
**Versión:** v1.0  
**Estado:** Proyecto funcional, listo para desarrollo continuo

---

## 1. Visión General del Proyecto

**CometLocal** es una aplicación web para gestión documental empresarial con las siguientes capacidades principales:

### Funcionalidades Core

1. **Repositorio Documental**
   - CRUD de tipos de documento (configurables por UI)
   - Subida de documentos PDF con metadatos
   - Cálculo automático de validez basado en políticas declarativas
   - Gestión de períodos (mensual, trimestral, anual)
   - Calendario de documentos pendientes y próximos vencimientos
   - Búsqueda y edición de documentos

2. **Motor de Automatización (eGestiona)**
   - Integración con plataformas externas (eGestiona)
   - Automatización de subida de documentos
   - Flujos headful con Playwright
   - Matching inteligente de documentos pendientes

3. **Sistema de Agentes**
   - Agentes LLM para tareas complejas
   - Ejecución batch de tareas
   - Sistema de memoria y contexto

---

## 2. Stack Tecnológico

### Backend
- **Framework:** FastAPI (Python 3.x)
- **Servidor ASGI:** Uvicorn
- **Validación:** Pydantic v2
- **Navegador automatizado:** Playwright (Python)
- **LLM:** OpenAI API (configurable)
- **PDF:** PyPDF4

### Frontend
- **Tecnología:** HTML5 + JavaScript vanilla (sin frameworks)
- **UI:** Diseño dark theme, responsive
- **Comunicación:** Fetch API (REST)

### Testing
- **E2E:** Playwright (Node.js)
- **Unit Tests:** pytest (Python)

### Persistencia
- **Formato:** JSON (tipos, metadatos, configuración)
- **Archivos:** Filesystem (PDFs en `data/repository/docs/`)
- **Estructura:** Data-driven (sin base de datos relacional)

---

## 3. Arquitectura

### Arquitectura General

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                    │
│              frontend/repository_v3.html                 │
└────────────────────┬────────────────────────────────────┘
                     │ REST API
┌────────────────────▼────────────────────────────────────┐
│              Backend FastAPI (Python)                     │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Document Repository Routes                       │  │
│  │  - CRUD Tipos / Documentos                         │  │
│  │  - Upload / Download PDF                          │  │
│  │  - Cálculo de validez                              │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Document Repository Store                          │  │
│  │  - Persistencia JSON                               │  │
│  │  - Gestión de archivos                             │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  eGestiona Adapter                                 │  │
│  │  - Flujos automatizados                            │  │
│  │  - Playwright headful                               │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              Filesystem (data/)                          │
│  - repository/types/types.json                           │
│  - repository/docs/{doc_id}.pdf                          │
│  - repository/meta/{doc_id}.json                         │
│  - refs/ (configuración: org, people, platforms)        │
└──────────────────────────────────────────────────────────┘
```

### Principios de Diseño

1. **Data-Driven:** Configuración en JSON, sin hardcodeo
2. **Determinista:** Cálculos de validez sin LLM (políticas declarativas)
3. **Atomic Writes:** Integridad de datos con escrituras atómicas
4. **Separation of Concerns:** Backend (lógica) / Frontend (UI) / Store (persistencia)

---

## 4. Estructura del Proyecto

```
CometLocal/
├── backend/                    # Backend Python
│   ├── app.py                  # Aplicación FastAPI principal
│   ├── config.py               # Configuración (rutas, LLM)
│   ├── repository/             # Módulo Repositorio Documental
│   │   ├── document_repository_routes.py    # Endpoints REST
│   │   ├── document_repository_store_v1.py  # Persistencia
│   │   ├── validity_calculator_v1.py        # Cálculo validez
│   │   ├── date_parser_v1.py                # Parser fechas
│   │   ├── period_planner_v1.py             # Planificación períodos
│   │   ├── document_status_calculator_v1.py # Cálculo estado
│   │   ├── config_routes.py                 # Config endpoints
│   │   ├── settings_routes.py               # Settings endpoints
│   │   └── ...
│   ├── adapters/               # Adaptadores externos
│   │   └── egestiona/         # Integración eGestiona
│   ├── agents/                 # Sistema de agentes
│   ├── executor/               # Ejecutor de tareas
│   ├── shared/                 # Modelos compartidos
│   │   ├── document_repository_v1.py  # Modelos Pydantic
│   │   └── ...
│   └── tests/                  # Tests unitarios Python
│
├── frontend/                   # Frontend HTML/JS
│   ├── repository_v3.html      # UI principal (ACTUAL)
│   ├── repository.html         # UI legacy
│   └── ...
│
├── data/                       # Datos persistentes
│   ├── repository/
│   │   ├── types/types.json    # Tipos de documento
│   │   ├── docs/               # PDFs (ruta configurable)
│   │   ├── meta/               # Metadatos JSON
│   │   ├── settings.json       # Configuración repositorio
│   │   └── ...
│   └── refs/                   # Referencias
│       ├── org.json            # Organizaciones
│       ├── people.json          # Personas/trabajadores
│       ├── platforms.json       # Plataformas
│       └── secrets.json         # Secretos (no commitear)
│
├── tests/                      # Tests E2E (Playwright)
│   ├── e2e_calendar_filters.spec.js
│   ├── e2e_edit_document.spec.js
│   ├── e2e_resubmit_pdf.spec.js
│   └── ...
│
├── docs/                       # Documentación
│   ├── evidence/               # Evidencias de bugs/fixes
│   │   ├── calendar_max_months_back_fix/
│   │   ├── edit_doc_500/
│   │   ├── upload_doc_500/
│   │   └── ...
│   └── ...
│
├── requirements.txt            # Dependencias Python
├── package.json               # Dependencias Node.js
├── playwright.config.js       # Config Playwright
└── README.md
```

---

## 5. Componentes Principales

### 5.1 Backend - Aplicación Principal (`backend/app.py`)

**Responsabilidades:**
- Inicialización FastAPI
- Registro de routers
- Gestión de navegador compartido (Playwright)
- Endpoints principales de agentes
- Configuración LLM persistente

**Endpoints principales:**
- `GET /repository` → Sirve `frontend/repository_v3.html`
- `POST /agent/answer` → Ejecución de agente LLM
- `POST /agent/batch` → Ejecución batch
- `GET /api/config/llm` → Configuración LLM
- `POST /api/config/llm` → Actualizar configuración LLM

**Arranque:**
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

---

### 5.2 Repositorio Documental (`backend/repository/`)

#### 5.2.1 Document Repository Store (`document_repository_store_v1.py`)

**Responsabilidades:**
- Gestión de tipos de documento (`types.json`)
- Gestión de instancias de documentos (CRUD)
- Persistencia de PDFs en filesystem
- Cálculo automático de validez
- Atomic writes para integridad

**Métodos principales:**
- `list_types()` → Lista tipos con filtros
- `get_type(type_id)` → Obtiene tipo
- `save_type(type)` → Guarda/actualiza tipo
- `get_document(doc_id)` → Obtiene documento
- `save_document(doc)` → Guarda/actualiza documento
- `store_pdf(pdf_path, doc_id)` → Almacena PDF
- `compute_file_hash(pdf_path)` → Calcula SHA256

#### 5.2.2 Document Repository Routes (`document_repository_routes.py`)

**Endpoints REST:**

**Tipos de Documento:**
- `GET /api/repository/types` → Lista tipos (con filtros y paginación)
- `GET /api/repository/types/{type_id}` → Obtiene tipo
- `POST /api/repository/types` → Crea tipo
- `PUT /api/repository/types/{type_id}` → Actualiza tipo
- `DELETE /api/repository/types/{type_id}` → Elimina tipo
- `PUT /api/repository/types/{type_id}/toggle_active` → Toggle activo
- `POST /api/repository/types/{type_id}/duplicate` → Duplica tipo

**Documentos:**
- `GET /api/repository/docs` → Lista documentos (con filtros)
- `GET /api/repository/docs/{doc_id}` → Obtiene documento
- `GET /api/repository/docs/{doc_id}/pdf` → Descarga PDF
- `POST /api/repository/docs/upload` → Sube documento (multipart/form-data)
- `PUT /api/repository/docs/{doc_id}` → Actualiza metadatos
- `PUT /api/repository/docs/{doc_id}/pdf` → Reemplaza PDF (multipart/form-data)
- `DELETE /api/repository/docs/{doc_id}` → Elimina documento
- `GET /api/repository/docs/pending` → Documentos pendientes (para calendario)

**Configuración:**
- `GET /api/repository/settings` → Obtiene configuración
- `PUT /api/repository/settings` → Actualiza configuración

#### 5.2.3 Validity Calculator (`validity_calculator_v1.py`)

**Responsabilidades:**
- Cálculo determinista de validez basado en políticas
- Soporte para modos: `monthly`, `annual`, `fixed_end_date`
- Cálculo de `valid_from` y `valid_to`

**Función principal:**
```python
def compute_validity(
    policy: ValidityPolicyV1,
    extracted: ExtractedMetadataV1
) -> ComputedValidityV1
```

#### 5.2.4 Date Parser (`date_parser_v1.py`)

**Responsabilidades:**
- Extracción de fechas desde nombres de archivo
- Formatos soportados: `DD-MM-YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD`, etc.
- Detección de fechas en español (ej: "31-dic-25")

#### 5.2.5 Period Planner (`period_planner_v1.py`)

**Responsabilidades:**
- Generación de períodos esperados (mensual, trimestral, anual)
- Cálculo de períodos faltantes
- Planificación de períodos futuros

---

### 5.3 Frontend (`frontend/repository_v3.html`)

**Arquitectura:**
- **Single Page Application** (SPA) con hash routing (`#calendario`, `#subir`, `#buscar`, etc.)
- **Sin frameworks:** JavaScript vanilla
- **Estado global:** Variables en `window` (ej: `uploadFiles`, `uploadTypes`)

**Secciones principales:**

1. **Calendario de Documentos** (`#calendario`)
   - Tabs: Expirados, Expiran pronto, Pendientes de subir
   - Filtros: Tipo, Aplica a, Sujeto, Máx. meses atrás
   - Renderizado de tablas con documentos agrupados

2. **Subir Documentos** (`#subir`)
   - Drag & drop de PDFs
   - Wizard guiado por archivo
   - Autocompletado de tipos
   - Validación de campos requeridos
   - Detección automática de fechas

3. **Buscar Documentos** (`#buscar`)
   - Búsqueda por filtros
   - Tabla de resultados
   - Acciones: Ver, Editar, Resubir, Eliminar

4. **Catálogo de Documentos** (`#catalogo`)
   - CRUD de tipos de documento
   - Gestión de políticas de validez
   - Configuración de campos requeridos

**Funciones JavaScript principales:**
- `loadCalendario()` → Carga datos del calendario
- `applyCalendarFilters()` → Aplica filtros al calendario
- `setCalendarMaxMonthsBack(value)` → Actualiza filtro de meses
- `saveAllUploadFiles()` → Guarda todos los archivos subidos
- `performSearch()` → Ejecuta búsqueda de documentos
- `editDocumentFromSearch(docId)` → Abre modal de edición
- `saveDocumentEdit()` → Guarda cambios de edición

---

## 6. Cómo Arrancar el Proyecto

### 6.1 Prerrequisitos

**Python:**
- Python 3.9+ (recomendado 3.11+)
- Virtual environment (`.venv`)

**Node.js:**
- Node.js 18+ (para Playwright E2E)

**Sistema:**
- Windows 10+ / Linux / macOS
- Playwright browsers instalados

### 6.2 Instalación

**1. Clonar repositorio:**
```bash
git clone <repo-url>
cd CometLocal
```

**2. Configurar Python:**
```bash
# Crear virtual environment
python -m venv .venv

# Activar (Windows)
.venv\Scripts\activate

# Activar (Linux/macOS)
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

**3. Configurar Node.js (para tests E2E):**
```bash
npm install
npx playwright install
```

**4. Configurar datos iniciales:**
```bash
# El backend crea automáticamente la estructura en data/
# Asegúrate de que data/refs/ existe con:
# - org.json
# - people.json
# - platforms.json
# - secrets.json (con credenciales si aplica)
```

### 6.3 Arrancar Backend

```bash
# Activar venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Arrancar servidor
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

**Verificar:**
- Backend: `http://127.0.0.1:8000/docs` (Swagger UI)
- Frontend: `http://127.0.0.1:8000/repository`

### 6.4 Ejecutar Tests E2E

```bash
# Todos los tests
npx playwright test

# Test específico
npx playwright test tests/e2e_calendar_filters.spec.js

# Con UI visible
npx playwright test --headed
```

---

## 7. Flujos Principales

### 7.1 Flujo: Subir Documento

1. Usuario navega a `#subir`
2. Arrastra PDF o selecciona archivo
3. Frontend detecta archivo y crea entrada en `uploadFiles[]`
4. Frontend extrae fecha del nombre (si aplica)
5. Usuario completa wizard:
   - Aplica a (Todos/Empresa/Trabajador)
   - Tipo de documento (autocompletado)
   - Sujeto (empresa/trabajador)
   - Período (si aplica)
   - Fecha de emisión
   - Fecha inicio de vigencia (si `validity_start_mode=manual`)
6. Usuario hace click en "Guardar todo"
7. Frontend valida todos los campos requeridos
8. Frontend envía `POST /api/repository/docs/upload` (multipart/form-data)
9. Backend:
   - Valida tipo de documento
   - Calcula `sha256` del PDF
   - Extrae metadatos (fechas, períodos)
   - Calcula validez (`compute_validity`)
   - Guarda PDF en `data/repository/docs/{doc_id}.pdf`
   - Guarda metadatos en `data/repository/meta/{doc_id}.json`
10. Backend responde con `DocumentInstanceV1`
11. Frontend muestra mensaje de éxito y limpia formulario

### 7.2 Flujo: Calendario de Documentos

1. Usuario navega a `#calendario`
2. Frontend llama `GET /api/repository/docs/pending?months_ahead=3&max_months_back=24`
3. Backend calcula:
   - `expired`: Documentos con `valid_to < today`
   - `expiring_soon`: Documentos con `valid_to` en próximos N meses
   - `missing`: Períodos faltantes (agrupados por tipo/sujeto)
4. Frontend recibe datos y aplica filtros UI:
   - `applyCalendarFilters()` filtra por tipo, scope, sujeto, meses atrás
5. Frontend renderiza tablas con `renderPendingDocuments()`
6. Usuario puede cambiar filtros (sin recargar página)
7. Usuario puede hacer click en "Subir" para un período faltante

### 7.3 Flujo: Editar Documento

1. Usuario navega a `#buscar`
2. Usuario busca documento y hace click en "Editar"
3. Frontend abre modal con datos del documento
4. Usuario modifica campos editables (status, fechas, etc.)
5. Usuario hace click en "Guardar"
6. Frontend envía `PUT /api/repository/docs/{doc_id}` con `DocumentUpdateRequest`
7. Backend:
   - Valida request
   - Actualiza documento
   - Recalcula validez si cambió fecha relevante
   - Guarda cambios
8. Backend responde con `DocumentInstanceV1` actualizado
9. Frontend cierra modal y refresca lista

### 7.4 Flujo: Resubir PDF

1. Usuario navega a `#buscar`
2. Usuario hace click en "Resubir" en un documento
3. Frontend navega a `#subir` con `replace_doc_id` en params
4. Frontend establece `window.replaceDocId = doc_id`
5. Usuario selecciona nuevo PDF
6. Usuario completa wizard (campos pre-rellenados)
7. Usuario hace click en "Guardar todo"
8. Frontend detecta `window.replaceDocId` y envía `PUT /api/repository/docs/{doc_id}/pdf`
9. Backend:
   - Valida PDF
   - Calcula nuevo `sha256`
   - Reemplaza PDF en filesystem
   - Actualiza `sha256` y `file_name_original` en documento
   - Guarda cambios
10. Backend responde con `DocumentInstanceV1` actualizado
11. Frontend muestra mensaje de éxito

---

## 8. Bugs Recientes y Fixes

### 8.1 Bug: "Máx. meses atrás" ignorado en Calendario

**Síntoma:** El filtro "Máx. meses atrás" no filtraba períodos antiguos en "Pendientes de subir".

**Causa raíz:** La función `setCalendarMaxMonthsBack()` no existía, causando `ReferenceError` y dejando el valor en default (24).

**Fix:** Implementada función `setCalendarMaxMonthsBack()` que actualiza `calendarMaxMonthsBack` y re-renderiza con datos filtrados.

**Evidencia:** `docs/evidence/calendar_max_months_back_fix/report.md`

**Archivos modificados:**
- `frontend/repository_v3.html`
- `tests/e2e_calendar_filters.spec.js`

---

### 8.2 Bug: Internal Server Error al editar documento

**Síntoma:** Al guardar cambios en modal "Editar documento", el backend devolvía 500.

**Causa raíz:** Llamada incorrecta a `compute_validity()`:
- **Incorrecto:** `compute_validity(doc, doc_type)`
- **Correcto:** `compute_validity(doc_type.validity_policy, doc.extracted)`

**Fix:** Corregida llamada en `update_document()` endpoint.

**Evidencia:** `docs/evidence/edit_doc_500/report.md`

**Archivos modificados:**
- `backend/repository/document_repository_routes.py`
- `tests/e2e_edit_document.spec.js`

---

### 8.3 Bug: Internal Server Error al resubir PDF

**Síntoma:** Al resubir PDF desde "Buscar documentos → Resubir", el backend devolvía 500.

**Causa raíz:** Intentaba escribir campos inexistentes en `DocumentInstanceV1`:
- `doc.file_hash` → debe ser `doc.sha256`
- `doc.doc_file_name` → debe ser `doc.file_name_original`

**Fix:** Corregidos nombres de campos en `replace_document_pdf()`.

**Evidencia:** `docs/evidence/upload_doc_500/report.md`

**Archivos modificados:**
- `backend/repository/document_repository_routes.py`
- `tests/e2e_resubmit_pdf.spec.js`

---

## 9. Tests E2E

### 9.1 Tests Disponibles

**Calendario:**
- `tests/e2e_calendar_filters.spec.js` → Filtros del calendario
- `tests/e2e_calendar_pending_smoke.spec.js` → Smoke test pendientes

**Documentos:**
- `tests/e2e_edit_document.spec.js` → Edición de documentos
- `tests/e2e_resubmit_pdf.spec.js` → Resubida de PDF

**Upload:**
- `tests/e2e_upload_type_select.spec.js` → Selección de tipo
- `tests/e2e_upload_subjects.spec.js` → Selección de sujetos
- `tests/e2e_upload_scope_filter.spec.js` → Filtro de scope

**Otros:**
- `tests/e2e_repository_settings.spec.js` → Configuración
- `tests/e2e_validity_start.spec.js` → Fecha inicio de vigencia

### 9.2 Ejecutar Tests

```bash
# Todos
npx playwright test

# Específico
npx playwright test tests/e2e_calendar_filters.spec.js

# Con UI
npx playwright test --headed

# Con reporter
npx playwright test --reporter=line
```

### 9.3 Configuración

Ver `playwright.config.js`:
- Timeout: 30s
- Headless: false (por defecto)
- WebServer: Arranca backend automáticamente

---

## 10. Modelos de Datos

### 10.1 DocumentTypeV1

```python
class DocumentTypeV1(BaseModel):
    type_id: str                    # ID único (ej: "T104_AUTONOMOS_RECEIPT")
    name: str                       # Nombre legible
    description: Optional[str]      # Descripción
    scope: DocumentScopeV1          # "company" | "worker"
    validity_policy: ValidityPolicyV1  # Política de validez
    required_fields: List[str]      # Campos requeridos
    platform_aliases: List[str]      # Aliases para matching
    active: bool                     # Si está activo
    validity_start_mode: str         # "issue_date" | "manual"
    allow_late_submission: bool       # Permitir envío tardío
    late_submission_max_days: Optional[int]  # Máx días tarde
```

### 10.2 DocumentInstanceV1

```python
class DocumentInstanceV1(BaseModel):
    doc_id: str                      # UUID
    file_name_original: str          # Nombre original del archivo
    stored_path: str                 # Ruta relativa al PDF
    sha256: str                      # Hash SHA256 del PDF
    type_id: str                     # ID del tipo
    scope: DocumentScopeV1           # "company" | "worker"
    company_key: Optional[str]        # ID empresa
    person_key: Optional[str]         # ID trabajador
    extracted: ExtractedMetadataV1    # Metadatos extraídos
    computed_validity: ComputedValidityV1  # Validez calculada
    validity_override: Optional[ValidityOverrideV1]  # Override manual
    status: DocumentStatusV1          # "draft" | "reviewed" | "submitted"
    period_kind: PeriodKindV1         # "MONTH" | "QUARTER" | "YEAR" | "NONE"
    period_key: Optional[str]         # "YYYY-MM" | "YYYY-Qn" | "YYYY"
    issued_at: Optional[date]         # Fecha de emisión
    needs_period: bool                # Si requiere período
    created_at: datetime
    updated_at: datetime
```

### 10.3 ValidityPolicyV1

```python
class ValidityPolicyV1(BaseModel):
    mode: ValidityModeV1              # "monthly" | "annual" | "fixed_end_date"
    months: Optional[int]             # Duración en meses (monthly)
    years: Optional[int]               # Duración en años (annual)
    end_date: Optional[date]           # Fecha fija (fixed_end_date)
    grace_days: int                    # Días de gracia
```

---

## 11. Estructura de Datos en Disco

```
data/
├── repository/
│   ├── types/
│   │   └── types.json              # Array de DocumentTypeV1
│   ├── docs/
│   │   └── {doc_id}.pdf            # PDFs (ruta configurable en settings.json)
│   ├── meta/
│   │   └── {doc_id}.json           # DocumentInstanceV1 (sin PDF)
│   ├── settings.json                # Configuración repositorio
│   │   {
│   │     "docs_path": "data/repository/docs",
│   │     "meta_path": "data/repository/meta"
│   │   }
│   └── ...
├── refs/
│   ├── org.json                     # Organizaciones
│   ├── people.json                  # Personas/trabajadores
│   ├── platforms.json               # Plataformas
│   ├── secrets.json                 # Secretos (NO commitear)
│   └── llm_config.json              # Configuración LLM
└── ...
```

---

## 12. Configuración

### 12.1 Configuración LLM

**Archivo:** `data/refs/llm_config.json`

```json
{
  "provider": "openai",
  "model": "gpt-4",
  "api_key": "...",
  "temperature": 0.7
}
```

**Endpoints:**
- `GET /api/config/llm` → Obtiene configuración
- `POST /api/config/llm` → Actualiza configuración

### 12.2 Configuración Repositorio

**Archivo:** `data/repository/settings.json`

```json
{
  "docs_path": "data/repository/docs",
  "meta_path": "data/repository/meta"
}
```

**Endpoints:**
- `GET /api/repository/settings` → Obtiene configuración
- `PUT /api/repository/settings` → Actualiza configuración

---

## 13. Debugging

### 13.1 Logs del Backend

El backend usa `logging` estándar de Python. Para ver logs:
- Consola donde se ejecuta `uvicorn`
- Logs de errores aparecen en stderr

### 13.2 Debug en Frontend

**Flags de debug:**
- `window.__DEBUG_CALENDAR__ = true` → Logs de calendario
- `window.__REPO_DEBUG__ = true` → Logs generales
- `?debug_calendar=1` en URL → Activa debug de calendario

**Console logs:**
- `[CAL]` → Calendario
- `[repo-upload]` → Upload
- `[DEBUG_CALENDAR_FILTERS]` → Filtros de calendario

### 13.3 Network Tab

Para debugging de requests:
1. Abrir DevTools (F12)
2. Tab "Network"
3. Filtrar por `/api/repository/`
4. Inspeccionar request/response

---

## 14. Próximos Pasos Recomendados

### 14.1 Mejoras de Código

1. **Refactorizar estado global del frontend:**
   - Migrar de variables `window` a un sistema de estado más estructurado
   - Considerar un patrón de eventos para comunicación entre componentes

2. **Mejorar manejo de errores:**
   - Errores más descriptivos en backend
   - UI de errores más amigable en frontend

3. **Optimizar rendimiento:**
   - Paginación en listados grandes
   - Lazy loading de datos

### 14.2 Features Pendientes

1. **Historial de cambios:**
   - Auditoría de modificaciones en documentos
   - Versionado de PDFs

2. **Notificaciones:**
   - Alertas de documentos próximos a expirar
   - Recordatorios de períodos faltantes

3. **Exportación:**
   - Exportar calendario a CSV/Excel
   - Generar reportes de documentos

### 14.3 Testing

1. **Aumentar cobertura E2E:**
   - Tests de edge cases
   - Tests de regresión

2. **Tests unitarios:**
   - Aumentar cobertura en `backend/tests/`
   - Tests de `validity_calculator_v1.py`
   - Tests de `date_parser_v1.py`

---

## 15. Referencias y Documentación

### 15.1 Documentación Existente

- `docs/document_repository_v1.md` → Especificación del repositorio
- `docs/REPO_TIME_SERIES_DESIGN.md` → Diseño de series temporales
- `docs/evidence/` → Evidencias de bugs y fixes

### 15.2 Handoffs Anteriores

- `docs/TECHNICAL_HANDOFF_COMPLETE_2025-12-30.md`
- `docs/TECHNICAL_HANDOFF_COMPLETE_2026-01-02.md`

### 15.3 Commits Recientes

- `6d44641` → Fix: Corregir Internal Server Error al resubir/reemplazar PDF

---

## 16. Contacto y Soporte

**Para dudas técnicas:**
- Revisar documentación en `docs/`
- Revisar evidencias en `docs/evidence/`
- Revisar código con comentarios inline

**Para bugs:**
- Revisar `docs/evidence/` para ver cómo se documentan bugs
- Seguir el patrón: screenshot BEFORE/AFTER, traceback, network logs, test E2E

---

## 17. Checklist de Onboarding

Para un nuevo desarrollador:

- [ ] Leer este documento completo
- [ ] Configurar entorno local (Python, Node.js, venv)
- [ ] Arrancar backend y verificar `http://127.0.0.1:8000/docs`
- [ ] Arrancar frontend y verificar `http://127.0.0.1:8000/repository`
- [ ] Ejecutar tests E2E: `npx playwright test`
- [ ] Revisar estructura de datos en `data/repository/`
- [ ] Revisar código de un flujo completo (ej: subir documento)
- [ ] Revisar evidencias de bugs recientes en `docs/evidence/`
- [ ] Hacer un cambio pequeño y verificar que funciona

---

**Fin del Handoff Técnico**

*Última actualización: 2026-01-05*





