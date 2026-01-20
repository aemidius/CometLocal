# Handoff Técnico y Funcional Completo — CometLocal

**Fecha:** 2026-01-20  
**Versión:** v4.1 (Handoff Completo para Traspaso)  
**Estado:** Proyecto funcional, listo para desarrollo continuo

---

## 📋 Tabla de Contenidos

1. [Visión General del Proyecto](#1-visión-general-del-proyecto)
2. [Funcionalidades Principales](#2-funcionalidades-principales)
3. [Stack Tecnológico](#3-stack-tecnológico)
4. [Arquitectura del Sistema](#4-arquitectura-del-sistema)
5. [Estructura del Proyecto](#5-estructura-del-proyecto)
6. [Componentes Principales](#6-componentes-principales)
7. [APIs y Endpoints](#7-apis-y-endpoints)
8. [Modelos de Datos](#8-modelos-de-datos)
9. [Flujos Principales](#9-flujos-principales)
10. [UI y Frontend](#10-ui-y-frontend)
11. [Configuración y Variables de Entorno](#11-configuración-y-variables-de-entorno)
12. [Testing](#12-testing)
13. [Instalación y Ejecución](#13-instalación-y-ejecución)
14. [Estado Actual](#14-estado-actual)
15. [Próximos Pasos Conocidos](#15-próximos-pasos-conocidos)
16. [Issues Conocidos y Limitaciones](#16-issues-conocidos-y-limitaciones)
17. [Guías de Referencia Rápida](#17-guías-de-referencia-rápida)
18. [Decisiones de Diseño Importantes](#18-decisiones-de-diseño-importantes)

---

## 1. Visión General del Proyecto

**CometLocal** es una plataforma de automatización para la gestión documental en portales CAE (Coordinación de Actividades Empresariales). El sistema combina:

- **Repositorio Documental Inteligente**: Gestión centralizada de documentos con cálculo automático de validez, series temporales y matching inteligente
- **Automatización CAE**: Subida automática de documentos a portales CAE reales (eGestiona) usando Playwright
- **Agentes LLM**: Sistema de agentes autónomos para navegación y ejecución de tareas complejas
- **UI Humanizada**: Interfaz de usuario orientada a tareas con lenguaje natural
- **Training Guiado**: Sistema de onboarding obligatorio para usuarios nuevos (C2.35)
- **Acciones Asistidas**: Sistema de acciones humanas asistidas para gestionar NO_MATCH (C2.35)
- **Observabilidad de Matching**: Sistema de debug reports determinista para explicar NO_MATCH (C2.34)

### Propósito del Sistema

Automatizar tareas repetitivas de gestión documental CAE/PRL en portales empresariales reales, con:
- **Determinismo**: Ejecución reproducible y predecible
- **Evidencia**: Trazabilidad completa con screenshots y logs
- **Seguridad**: Guardrails de contexto humano para operaciones WRITE
- **Auditabilidad**: Runs audit-ready con summary.md y evidencias
- **Multi-tenant**: Soporte para múltiples empresas y plataformas

---

## 2. Funcionalidades Principales

### 2.1. Repositorio Documental (v1)

**Ubicación:** `backend/repository/`, `frontend/repository_v3.html`

**Características:**
- ✅ CRUD completo de tipos de documento configurables por UI
- ✅ Subida de documentos PDF con metadatos (fecha, sujeto, período)
- ✅ Cálculo automático de validez basado en políticas declarativas
- ✅ Gestión de períodos (mensual, trimestral, anual, ninguno)
- ✅ Series temporales: documentos periódicos con gestión por períodos
- ✅ Calendario de documentos pendientes y próximos vencimientos
- ✅ Búsqueda avanzada y edición de documentos
- ✅ Matching inteligente de documentos pendientes con repositorio
- ✅ Reglas de envío configurables (GLOBAL/COORD) con herencia
- ✅ Historial de envíos completo con trazabilidad
- ✅ Aliases de tipos de documento para matching flexible
- ✅ Overrides de validez manuales
- ✅ Exportación de documentos (ZIP, individual)

**Modelos clave:**
- `DocumentTypeV1`: Tipo de documento (id, name, validity_policy, period_kind)
- `DocumentInstanceV1`: Instancia de documento (type_id, date, subject_key, period_key, file_path)
- `DocumentStatusV1`: Estado calculado (valid, expired, pending, missing)
- `PeriodKindV1`: Tipo de período (NONE, MONTHLY, QUARTERLY, ANNUAL)

### 2.2. Motor de Automatización CAE

**Ubicación:** `backend/adapters/egestiona/`, `backend/cae/`, `backend/connectors/`

**Características:**
- ✅ **eGestiona Adapter**: Integración completa con plataforma eGestiona real
- ✅ **Connector SDK**: Framework para crear conectores de plataformas CAE
- ✅ Flujos headful/headless con Playwright
- ✅ Matching de documentos pendientes con repositorio
- ✅ Ejecución determinista con evidencias (screenshots, logs)
- ✅ Modo dry-run para simulación sin cambios reales
- ✅ Job queue para ejecuciones asíncronas
- ✅ Headful runs con navegación asistida
- ✅ Auto-upload para subidas automáticas

**Flujos principales:**
1. **Plan CAE**: Obtener plan de documentos pendientes desde portal
2. **Matching**: Asociar documentos pendientes con documentos del repositorio
3. **Ejecución**: Subir documentos al portal usando Playwright
4. **Evidencia**: Generar screenshots y logs de cada paso

### 2.3. Sistema de Agentes LLM

**Ubicación:** `backend/agents/`

**Características:**
- ✅ Agentes LLM para tareas complejas de navegación
- ✅ Ejecución batch de tareas
- ✅ Sistema de memoria y contexto persistente
- ✅ Visual memory para reconocimiento de elementos UI
- ✅ OCR service para extracción de texto de imágenes
- ✅ Document analyzer para análisis profundo de documentos
- ✅ Form filler para llenado automático de formularios

**Tipos de agentes:**
- `SimpleAgent`: Agente básico para tareas simples
- `LLMAgent`: Agente con capacidades LLM para tareas complejas
- `BatchAgent`: Agente para ejecución batch de múltiples tareas

### 2.4. Training Guiado (C2.35)

**Ubicación:** `backend/training/`, `frontend/repository_v3.html`

**Características:**
- ✅ Training obligatorio para usuarios nuevos
- ✅ Wizard de 5 pasos con explicaciones sobre NO_MATCH
- ✅ Banner persistente hasta completar training
- ✅ Estado persistente en `data/training/state.json`
- ✅ Bloqueo de acciones asistidas hasta completar training
- ✅ Prevención de solape con training legacy

**Flujo:**
1. Usuario nuevo ve banner de training
2. Click en "Iniciar Training" abre wizard modal
3. 5 pasos explicando qué es NO_MATCH y cómo gestionarlo
4. Confirmación final con checkbox
5. Al completar, se desbloquean acciones asistidas

#### 2.4.1. TrainingGate y Prevención de Solape (C2.35.2)

**Problema histórico:**
Antes de C2.35.2, existía un training legacy (modal con pasos tipo "Ejecuta una simulación") que se auto-disparaba en `DOMContentLoaded` después de 2 segundos. Esto causaba solape visual cuando el training C2.35 estaba activo, mostrando ambos trainings simultáneamente.

**Solución implementada:**
- **TrainingGate Central**: Helpers `isC235TrainingCompleted()` e `isC235TrainingActive()` para controlar el estado
- **Regla estricta**: Si `isC235TrainingActive() === true` → BLOQUEAR cualquier trigger del legacy
- **Desactivación de Auto-Start**: `initTrainingWizard()` (legacy) verifica `isC235TrainingActive()` antes de mostrar
- **Hard-Guard Visual**: Función `dismissLegacyTutorialIfPresent()` que cierra/oculta legacy si está presente
- **Bloqueo de Demo Banner**: `demo-onboarding-banner` también bloqueado si C2.35 está activo

**Resultado:**
- Con training C2.35 incompleto: Solo se ve banner/wizard C2.35, NO legacy
- Con training C2.35 completado: Legacy NO auto-dispara; solo manual
- Tests E2E: `tests/training_no_overlap.spec.js` verifica ausencia de solape

### 2.5. Acciones Asistidas (C2.35)

**Ubicación:** `backend/training/`, `frontend/repository_v3.html`

**Características:**
- ✅ Acciones asistidas para gestionar NO_MATCH
- ✅ "Asignar a tipo existente": Añadir alias a tipo existente
- ✅ "Crear nuevo tipo": Crear nuevo tipo de documento
- ✅ Solo visible si training completado
- ✅ Logging de todas las acciones en `data/training/actions.log.jsonl`
- ✅ Endpoint `/api/repository/types/{type_id}/add_alias` para añadir alias

### 2.6. Sistema de Runs y Schedules

**Ubicación:** `backend/api/runs_routes.py`, `backend/api/schedules_routes.py`

**Características:**
- ✅ Runs audit-ready con summary.md y evidencias
- ✅ Contexto humano guardado en cada run
- ✅ Schedules para ejecución automática (daily/weekly)
- ✅ Historial completo de runs con estado y contadores
- ✅ Exportación de runs (ZIP con evidencias)

**Modelos:**
- `RunSummaryV1`: Resumen de run con contexto, estado, contadores
- `ScheduleV1`: Schedule con cadencia, hora, contexto humano

### 2.7. Sistema de Coordinación Humana

**Ubicación:** `backend/shared/context_guardrails.py`, `backend/api/coordination_context_routes.py`

**Características:**
- ✅ Contexto de coordinación humano (empresa propia, plataforma, empresa coordinada)
- ✅ Guardrails para operaciones WRITE (requieren contexto válido)
- ✅ Headers `X-Coordination-*` para identificar contexto
- ✅ Validación automática en middleware
- ✅ Multi-tenant basado en contexto

### 2.8. Observabilidad de Matching (C2.34)

**Ubicación:** `backend/repository/document_matcher_v1.py`, `backend/repository/matching_debug_codes_v1.py`, `frontend/repository_v3.html`

**Características:**
- ✅ Matching Debug Report determinista cuando NO se sube nada (NO_MATCH/REVIEW_REQUIRED)
- ✅ Panel UI "¿Por qué no se ha subido?" con lenguaje humano
- ✅ Taxonomía cerrada de 9 códigos de razón
- ✅ Reporte determinista: mismo input → mismo output
- ✅ Razones ordenadas por prioridad
- ✅ Contadores por etapa del pipeline de matching

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

**Flujo:**
1. Backend genera plan CAE con documentos pendientes
2. Para cada item con decisión NO_MATCH o REVIEW_REQUIRED:
   - `DocumentMatcherV1.build_matching_debug_report()` genera reporte
   - Reporte incluye: `pending_id`, `decision`, `filters_applied`, `reasons`, `counters`
3. Frontend muestra panel "¿Por qué no se ha subido?" con razones en lenguaje humano
4. Panel solo visible si hay items con `debug_report` y no son AUTO_UPLOAD

**Componentes:**
- `matching_debug_codes_v1.py`: Taxonomía de códigos
- `document_matcher_v1.py`: Función `build_matching_debug_report()`
- `frontend/repository_v3.html`: Función `renderMatchingDebugPanel()` con `data-testid="matching-debug-panel"`

---

## 3. Stack Tecnológico

### Backend

- **Framework:** FastAPI (Python 3.10+)
- **Servidor ASGI:** Uvicorn
- **Validación:** Pydantic v2
- **Navegador automatizado:** Playwright (Python)
- **LLM:** OpenAI API / LM Studio (configurable)
- **PDF:** PyPDF4 / pypdf
- **Testing:** pytest, pytest-asyncio

### Frontend

- **Tecnología:** HTML5 + JavaScript vanilla (sin frameworks)
- **UI:** Diseño dark theme, responsive
- **Comunicación:** Fetch API (REST)
- **Routing:** Hash-based routing (`#inicio`, `#subir`, etc.)

### Testing

- **E2E:** Playwright (Node.js) con `@playwright/test`
- **Unit Tests:** pytest (Python)
- **Configuración:** `playwright.config.js`, `pytest.ini` (implícito)

### Persistencia

- **Formato:** JSON (tipos, metadatos, configuración)
- **Archivos:** Filesystem (PDFs en `data/repository/docs/`)
- **Estructura:** Data-driven (sin base de datos relacional)
- **Multi-tenant:** Directorios por tenant (`data/<tenant_id>/`)

### Dependencias Principales

**Backend (`requirements.txt`):**
```
fastapi
uvicorn[standard]
pydantic
playwright
openai>=1.0.0
pypdf>=4.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
requests>=2.31.0
```

**Frontend (sin package manager, solo Playwright para tests):**
```json
{
  "devDependencies": {
    "@playwright/test": "^1.57.0"
  }
}
```

---

## 4. Arquitectura del Sistema

### Arquitectura General

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                    │
│              frontend/repository_v3.html                │
│  - Routing hash-based                                    │
│  - Fetch API para comunicación                           │
│  - UI components (sidebar, modals, forms)                │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP REST
┌──────────────────────▼──────────────────────────────────┐
│              Backend FastAPI (Python)                    │
│                   backend/app.py                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Routers:                                        │  │
│  │  - /api/repository/* (documentos)               │  │
│  │  - /api/runs/* (ejecuciones)                    │  │
│  │  - /api/training/* (training)                   │  │
│  │  - /api/coordination/* (contexto)               │  │
│  │  - /api/connectors/* (conectores)               │  │
│  │  - /api/runs/*/matching_debug (debug reports)   │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Stores (JSON filesystem):                      │  │
│  │  - DocumentRepositoryStoreV1                     │  │
│  │  - ConfigStoreV1                                 │  │
│  │  - TrainingStateStoreV1                          │  │
│  │  - LearningStore                                  │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Adapters:                                        │  │
│  │  - eGestionaAdapter                              │  │
│  │  - Connector SDK                                  │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Agents:                                         │  │
│  │  - LLMAgent                                       │  │
│  │  - SimpleAgent                                   │  │
│  │  - BatchAgent                                     │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Persistencia (Filesystem)                    │
│                   data/                                   │
│  - repository/ (documentos, tipos, reglas)              │
│  - training/ (estado, acciones)                         │
│  - runs/ (ejecuciones, evidencias)                      │
│  - refs/ (configuración: org, platforms, people)        │
└──────────────────────────────────────────────────────────┘
```

### Flujo de Datos

1. **Frontend → Backend**: Requests HTTP REST con contexto en headers
2. **Backend → Store**: Lectura/escritura de JSON filesystem
3. **Backend → Adapter**: Ejecución de flujos CAE con Playwright
4. **Backend → Agent**: Ejecución de tareas complejas con LLM
5. **Backend → Filesystem**: Persistencia de documentos, evidencias, logs

### Middleware y Guardrails

**Context Guardrail (`backend/shared/context_guardrails.py`):**
- Valida contexto humano para operaciones WRITE
- Requiere headers `X-Coordination-Own-Company`, `X-Coordination-Platform`, `X-Coordination-Coordinated-Company`
- Bloquea requests sin contexto válido

**CORS Middleware:**
- Configurado para desarrollo (allow_origins=["*"])
- Debe restringirse en producción

---

## 5. Estructura del Proyecto

```
CometLocal/
├── backend/                    # Backend FastAPI
│   ├── app.py                  # Aplicación principal FastAPI
│   ├── config.py               # Configuración global
│   ├── adapters/               # Adaptadores de plataformas CAE
│   │   └── egestiona/         # Adapter eGestiona
│   ├── agents/                 # Sistema de agentes LLM
│   ├── api/                    # Endpoints API REST
│   │   ├── runs_routes.py
│   │   ├── schedules_routes.py
│   │   ├── coordination_context_routes.py
│   │   ├── export_routes.py
│   │   └── ...
│   ├── cae/                    # Lógica CAE (submission, coordination, job_queue)
│   ├── connectors/             # Connector SDK
│   ├── repository/             # Repositorio documental
│   │   ├── document_repository_store_v1.py
│   │   ├── document_repository_routes.py
│   │   ├── config_store_v1.py
│   │   └── ...
│   ├── shared/                 # Modelos y utilidades compartidas
│   │   ├── document_repository_v1.py  # Modelos Pydantic
│   │   ├── context_guardrails.py
│   │   ├── tenant_context.py
│   │   └── ...
│   ├── training/               # Sistema de training (C2.35)
│   │   ├── routes.py
│   │   ├── training_state_store_v1.py
│   │   └── training_action_logger.py
│   ├── tests/                  # Unit tests
│   └── ...
├── frontend/                    # Frontend HTML/JS
│   └── repository_v3.html      # UI principal (SPA)
├── tests/                       # Tests E2E Playwright
│   ├── training_and_assisted_actions.spec.js
│   ├── training_no_overlap.spec.js
│   ├── e2e_*.spec.js
│   └── ...
├── data/                        # Datos persistentes
│   ├── repository/             # Documentos y tipos
│   │   ├── docs/               # PDFs
│   │   ├── meta/                # Metadatos JSON
│   │   ├── types/              # Tipos de documento
│   │   └── rules/              # Reglas de envío
│   ├── training/                # Estado de training
│   │   ├── state.json
│   │   └── actions.log.jsonl
│   ├── runs/                    # Ejecuciones (runs)
│   ├── refs/                    # Configuración
│   │   ├── org.json            # Empresas
│   │   ├── platforms.json      # Plataformas CAE
│   │   ├── people.json         # Trabajadores
│   │   └── ...
│   └── ...
├── docs/                        # Documentación
│   ├── ONBOARDING.md
│   ├── HANDOFF_TECNICO_FUNCIONAL_COMPLETO.md  # Este documento
│   └── ...
├── scripts/                     # Scripts de utilidad
├── tools/                       # Herramientas
├── requirements.txt             # Dependencias Python
├── package.json                # Dependencias Node.js (tests)
├── playwright.config.js        # Configuración Playwright
└── README.md
```

---

## 6. Componentes Principales

### 6.1. DocumentRepositoryStoreV1

**Ubicación:** `backend/repository/document_repository_store_v1.py`

**Responsabilidad:** Gestión persistente de tipos de documento e instancias.

**Métodos principales:**
- `list_types()`: Lista tipos de documento
- `get_type(type_id)`: Obtiene un tipo por ID
- `create_type(type_data)`: Crea un nuevo tipo
- `update_type(type_id, updates)`: Actualiza un tipo
- `delete_type(type_id)`: Elimina un tipo
- `list_documents(filters)`: Lista documentos con filtros
- `get_document(doc_id)`: Obtiene un documento por ID
- `upload_document(type_id, file, metadata)`: Sube un documento
- `delete_document(doc_id)`: Elimina un documento

**Persistencia:** `data/repository/types/types.json`, `data/repository/meta/*.json`

### 6.2. ConfigStoreV1

**Ubicación:** `backend/repository/config_store_v1.py`

**Responsabilidad:** Gestión de configuración (empresas, plataformas, trabajadores).

**Métodos principales:**
- `get_org()`: Obtiene empresas
- `get_platforms()`: Obtiene plataformas CAE
- `get_people()`: Obtiene trabajadores
- `get_secrets()`: Obtiene secretos (credenciales)

**Persistencia:** `data/refs/org.json`, `data/refs/platforms.json`, `data/refs/people.json`, `data/refs/secrets.json`

### 6.3. TrainingStateStoreV1

**Ubicación:** `backend/training/training_state_store_v1.py`

**Responsabilidad:** Gestión del estado de training.

**Métodos principales:**
- `get_state()`: Obtiene estado actual
- `mark_completed(confirm=True)`: Marca training como completado

**Persistencia:** `data/training/state.json`

### 6.4. eGestionaAdapter

**Ubicación:** `backend/adapters/egestiona/`

**Responsabilidad:** Integración con plataforma eGestiona.

**Flujos principales:**
- `get_plan()`: Obtiene plan de documentos pendientes
- `execute_plan()`: Ejecuta plan (sube documentos)
- `headful_run()`: Ejecución headful con navegación asistida

### 6.5. Connector SDK

**Ubicación:** `backend/connectors/`

**Responsabilidad:** Framework para crear conectores de plataformas CAE.

**Componentes:**
- `base.py`: Clase base `Connector`
- `registry.py`: Registro de conectores
- `routes.py`: Endpoints para conectores
- `runner.py`: Ejecutor de conectores

### 6.6. LearningStore

**Ubicación:** `backend/shared/learning_store.py`

**Responsabilidad:** Almacenamiento de hints de aprendizaje.

**Métodos principales:**
- `add_hint(hint)`: Añade un hint
- `list_hints(filters)`: Lista hints con filtros
- `disable_hint(hint_id)`: Desactiva un hint

**Persistencia:** `data/<tenant_id>/learning/hints.jsonl`

### 6.7. DocumentMatcherV1 (Matching Debug Report)

**Ubicación:** `backend/repository/document_matcher_v1.py`

**Responsabilidad:** Matching de documentos y generación de debug reports (C2.34).

**Métodos principales:**
- `match_document(pending, context)`: Hace matching de un documento pendiente
- `build_matching_debug_report(pending, context, repo_docs, match_result, stage_counts)`: Genera reporte de debug determinista

**Características del debug report:**
- Solo se genera cuando `decision` es "NO_MATCH" o "REVIEW_REQUIRED"
- Función pura y determinista: mismo input → mismo output
- Incluye: `pending_id`, `decision`, `filters_applied`, `reasons` (ordenados por prioridad), `counters`
- No modifica la lógica de matching, solo añade explicación

**Persistencia:** Reportes guardados en `data/runs/<run_id>/matching_debug/` o incluidos en `plan_item.debug_report`

---

## 7. APIs y Endpoints

### 7.1. Repositorio Documental

**Base:** `/api/repository`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/types` | Lista tipos de documento |
| POST | `/types` | Crea un tipo |
| GET | `/types/{type_id}` | Obtiene un tipo |
| PUT | `/types/{type_id}` | Actualiza un tipo |
| DELETE | `/types/{type_id}` | Elimina un tipo |
| POST | `/types/{type_id}/add_alias` | Añade alias a tipo (C2.35) |
| GET | `/docs` | Lista documentos |
| POST | `/docs` | Sube un documento |
| GET | `/docs/{doc_id}` | Obtiene un documento |
| PUT | `/docs/{doc_id}` | Actualiza un documento |
| DELETE | `/docs/{doc_id}` | Elimina un documento |
| GET | `/docs/pending` | Lista documentos pendientes |
| GET | `/rules` | Obtiene reglas de envío |
| POST | `/rules` | Crea/actualiza regla |
| GET | `/subjects` | Lista sujetos (trabajadores) |

### 7.2. Training (C2.35)

**Base:** `/api/training`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/state` | Obtiene estado de training |
| POST | `/complete` | Marca training como completado |
| POST | `/log-action` | Registra acción asistida |

### 7.3. Runs y Schedules

**Base:** `/api/runs`, `/api/schedules`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/runs/start` | Inicia un run |
| GET | `/runs/latest` | Obtiene último run |
| GET | `/runs/{run_id}` | Obtiene un run |
| GET | `/schedules/list` | Lista schedules |
| POST | `/schedules` | Crea un schedule |
| PUT | `/schedules/{schedule_id}` | Actualiza schedule |
| DELETE | `/schedules/{schedule_id}` | Elimina schedule |

### 7.4. Coordinación Humana

**Base:** `/api/coordination`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/context/options` | Obtiene opciones de contexto |
| GET | `/context/current` | Obtiene contexto actual |

### 7.5. Configuración

**Base:** `/api/config`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/org` | Obtiene empresas |
| GET | `/platforms` | Obtiene plataformas |
| GET | `/people` | Obtiene trabajadores |

### 7.6. Exportación

**Base:** `/api/export`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/docs/zip` | Exporta documentos en ZIP |
| GET | `/docs/{doc_id}/file` | Descarga un documento |

### 7.7. Conectores

**Base:** `/api/connectors`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/list` | Lista conectores disponibles |
| POST | `/execute` | Ejecuta un conector |

### 7.8. Matching Debug (C2.34)

**Base:** `/api/runs`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/{run_id}/matching_debug` | Obtiene índice y resumen de matching debug reports para un run |
| GET | `/{run_id}/matching_debug/{item_id}` | Obtiene reporte completo de debug para un item específico |

**Nota:** Los reportes también están disponibles directamente en `plan_item.debug_report` cuando se obtiene un plan CAE.

---

## 8. Modelos de Datos

### 8.1. DocumentTypeV1

```python
class DocumentTypeV1(BaseModel):
    type_id: str
    name: str
    description: Optional[str] = None
    validity_policy: ValidityPolicyV1
    period_kind: PeriodKindV1  # NONE, MONTHLY, QUARTERLY, ANNUAL
    aliases: List[str] = []  # Aliases para matching
    created_at: datetime
    updated_at: datetime
```

### 8.2. DocumentInstanceV1

```python
class DocumentInstanceV1(BaseModel):
    doc_id: str
    type_id: str
    file_path: str  # Ruta relativa desde data/repository/docs/
    date: date  # Fecha del documento
    subject_key: Optional[str] = None  # Clave del sujeto (trabajador)
    period_key: Optional[str] = None  # Clave del período (YYYY-MM, YYYY-Q1, etc.)
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
```

### 8.3. DocumentStatusV1

```python
class DocumentStatusV1(BaseModel):
    status: Literal["valid", "expired", "pending", "missing"]
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    computed_at: datetime
```

### 8.4. RunSummaryV1

```python
class RunSummaryV1(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: Literal["success", "error", "blocked", "partial_success", "canceled"]
    context: RunContextV1
    plan_id: Optional[str] = None
    preset_id: Optional[str] = None
    decision_pack_id: Optional[str] = None
    dry_run: bool = False
    steps_executed: List[str] = []
    counters: Dict[str, int] = {}
    artifacts: Dict[str, str] = {}
    error: Optional[str] = None
    run_dir_rel: str
```

### 8.5. ScheduleV1

```python
class ScheduleV1(BaseModel):
    schedule_id: str
    enabled: bool
    plan_id: str
    dry_run: bool = False
    cadence: Literal["daily", "weekly"]
    at_time: str  # "HH:MM"
    weekday: Optional[int] = None  # 0-6 (solo si weekly)
    own_company_key: str
    platform_key: str
    coordinated_company_key: str
    created_at: datetime
    updated_at: datetime
    last_run_id: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
```

### 8.6. PersonV1

```python
class PersonV1(BaseModel):
    worker_id: str
    full_name: str = ""
    tax_id: str = ""  # DNI/NIE/NIF
    role: str = ""
    relation_type: str = ""
    own_company_key: Optional[str] = None
```

---

## 9. Flujos Principales

### 9.1. Flujo de Subida de Documento

1. Usuario navega a `#subir`
2. Selecciona tipo de documento
3. Selecciona archivo PDF
4. Frontend llama `POST /api/repository/docs` con `multipart/form-data`
5. Backend:
   - Guarda PDF en `data/repository/docs/{doc_id}.pdf`
   - Crea metadatos en `data/repository/meta/{doc_id}.json`
   - Calcula validez usando `ValidityCalculatorV1`
   - Calcula período si aplica usando `PeriodPlannerV1`
6. Frontend muestra documento en lista

### 9.2. Flujo de Training (C2.35)

1. Usuario nuevo abre aplicación
2. Frontend llama `GET /api/training/state`
3. Si `training_completed === false`:
   - Muestra banner de training
   - Usuario click en "Iniciar Training"
   - Abre wizard modal con 5 pasos
   - Usuario completa wizard y marca checkbox
   - Frontend llama `POST /api/training/complete` con `confirm: true`
   - Backend guarda `training_completed: true` en `data/training/state.json`
   - Banner desaparece
   - Acciones asistidas se desbloquean

### 9.3. Flujo de Acción Asistida (C2.35)

1. Usuario ve NO_MATCH en CAE Plan
2. Si training completado, aparecen botones de acción asistida
3. Usuario click en "Asignar a tipo existente":
   - Frontend muestra modal con lista de tipos
   - Usuario selecciona tipo
   - Frontend llama `POST /api/repository/types/{type_id}/add_alias` con alias
   - Backend añade alias al tipo
   - Frontend llama `POST /api/training/log-action` para registrar acción
4. O usuario click en "Crear nuevo tipo":
   - Frontend abre wizard de creación de tipo
   - Usuario completa wizard
   - Frontend llama `POST /api/repository/types` para crear tipo
   - Frontend llama `POST /api/training/log-action` para registrar acción

### 9.4. Flujo de Run CAE

1. Usuario navega a `#ejecuciones`
2. Usuario click en "Ejecutar Run"
3. Frontend llama `POST /api/runs/start` con contexto humano
4. Backend:
   - Crea directorio de run: `data/<tenant_id>/runs/<run_id>/`
   - Obtiene plan CAE usando adapter
   - Hace matching con repositorio
   - Ejecuta subidas usando Playwright
   - Genera evidencias (screenshots, logs)
   - Guarda `summary.json` y `summary.md`
5. Frontend muestra resultado en UI

### 9.5. Flujo de Matching

1. Backend obtiene plan CAE (documentos pendientes)
2. Para cada documento pendiente:
   - Extrae tipo, fecha, sujeto
   - Busca en repositorio usando `DocumentMatcherV1`:
     - Match por tipo exacto
     - Match por alias
     - Match por fecha y sujeto
   - Si encuentra match, asocia documento
   - Si no encuentra (NO_MATCH), marca para acción asistida

### 9.6. Flujo de Matching Debug Report (C2.34)

1. Backend genera plan CAE con documentos pendientes
2. Para cada item pendiente:
   - `DocumentMatcherV1.match_document()` hace matching
   - Si decisión es NO_MATCH o REVIEW_REQUIRED:
     - `DocumentMatcherV1.build_matching_debug_report()` genera reporte
     - Reporte incluye: `pending_id`, `decision`, `filters_applied`, `reasons`, `counters`
     - Reporte se añade a `plan_item.debug_report`
3. Frontend recibe plan con `debug_report` en items NO_MATCH/REVIEW_REQUIRED
4. Frontend llama `renderMatchingDebugPanel()`:
   - Filtra items con `debug_report` y que no sean AUTO_UPLOAD
   - Muestra panel "¿Por qué no se ha subido?" con razones en lenguaje humano
   - Panel incluye motivo principal y acciones sugeridas
5. Usuario puede ver explicación detallada de por qué no se subió el documento

---

## 10. UI y Frontend

### 10.1. Estructura de `repository_v3.html`

**Routing hash-based:**
- `#inicio`: Vista principal
- `#subir`: Subida de documentos
- `#calendario`: Calendario de documentos
- `#configuracion`: Configuración (tipos, empresas, etc.)
- `#ejecuciones`: Ejecuciones CAE
- `#programacion`: Schedules

**Componentes principales:**
- Sidebar: Navegación
- Content area: Contenido dinámico según ruta
- Modals: Wizards, confirmaciones, formularios
- Training banner: Banner persistente (C2.35)
- Training wizard: Modal de 5 pasos (C2.35)
- Matching debug panel: Panel "¿Por qué no se ha subido?" (C2.34)

### 10.2. Comunicación con Backend

**Función `fetchWithContext()`:**
```javascript
async function fetchWithContext(url, options = {}) {
    const context = getCoordinationContext();
    const headers = {
        ...options.headers,
        'X-Coordination-Own-Company': context.own_company_key || '',
        'X-Coordination-Platform': context.platform_key || '',
        'X-Coordination-Coordinated-Company': context.coordinated_company_key || '',
    };
    return fetch(url, { ...options, headers });
}
```

**Uso:**
- Todas las operaciones WRITE usan `fetchWithContext()`
- Operaciones READ pueden usar `fetch()` normal

### 10.3. TrainingGate (C2.35.2)

**Helpers centrales:**
```javascript
function isC235TrainingCompleted() {
    return trainingState.completed === true;
}

function isC235TrainingActive() {
    return !trainingState.completed;
}

function dismissLegacyTutorialIfPresent() {
    // Cierra training legacy si está abierto
    const legacyWizard = document.getElementById('training-wizard');
    if (legacyWizard && legacyWizard.style.display !== 'none') {
        legacyWizard.style.display = 'none';
    }
}
```

**Uso:**
- Bloquea training legacy si C2.35 está activo
- Cierra legacy automáticamente al abrir C2.35 wizard

---

## 11. Configuración y Variables de Entorno

### 11.1. Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Entorno (demo/dev/prod) | - |
| `LLM_API_BASE` | URL base del LLM | `http://127.0.0.1:1234/v1` |
| `LLM_API_KEY` | API key del LLM | `lm-studio` |
| `LLM_MODEL` | Model ID del LLM | `local-model` |
| `COMETLOCAL_DATA_DIR` | Directorio de datos | `<repo_root>/data` |
| `CAE_COORDINATION_MODE` | Modo coordinación (FAKE/REAL) | - |
| `CAE_EXECUTOR_MODE` | Modo ejecutor (FAKE/REAL) | - |
| `REPOSITORY_DATA_DIR` | Directorio de repositorio (tests) | `data/repository_e2e` |

### 11.2. Configuración en `backend/config.py`

**LLM Config:**
- Persistido en `data/refs/llm_config.json`
- Configurable desde UI (futuro)

**Data Dir:**
- `DATA_DIR`: Directorio absoluto de datos
- `BATCH_RUNS_DIR`: Directorio de runs
- `VISUAL_MEMORY_BASE_DIR`: Directorio de memoria visual

### 11.3. Configuración de Datos

**Archivos en `data/refs/`:**
- `org.json`: Empresas
- `platforms.json`: Plataformas CAE
- `people.json`: Trabajadores
- `secrets.json`: Credenciales (no versionado)
- `llm_config.json`: Configuración LLM

**Formato ejemplo (`org.json`):**
```json
{
  "schema_version": "v1",
  "companies": [
    {
      "company_key": "F63161988",
      "name": "Empresa Demo SL",
      "tax_id": "F63161988"
    }
  ]
}
```

---

## 12. Testing

### 12.1. Tests E2E (Playwright)

**Ubicación:** `tests/`

**Ejecución:**
```bash
# Todos los tests
npx playwright test

# Test específico
npx playwright test tests/training_and_assisted_actions.spec.js

# Con UI
npx playwright test --headed

# Con debug
npx playwright test --debug
```

**Tests principales:**
- `training_and_assisted_actions.spec.js`: Training y acciones asistidas (C2.35)
- `training_no_overlap.spec.js`: Prevención de solape legacy (C2.35.2)
- `matching_debug_report_ui.spec.js`: UI de matching debug report (C2.34)
- `e2e_*.spec.js`: Tests E2E de funcionalidades core
- `cae_plan_e2e.spec.js`: Tests de plan CAE

**Configuración:** `playwright.config.js`
- Base URL: `http://127.0.0.1:8000`
- Web server: Auto-inicia backend con `uvicorn`
- Timeout: 30s
- Screenshots: Solo en fallo
- Video: Solo en fallo

### 12.2. Tests Unitarios (pytest)

**Ubicación:** `backend/tests/`

**Ejecución:**
```bash
# Todos los tests
pytest backend/tests/

# Test específico
pytest backend/tests/test_training_state_store.py

# Con verbose
pytest backend/tests/ -v

# Con coverage
pytest backend/tests/ --cov=backend
```

**Tests principales:**
- `test_training_state_store.py`: Training state store
- `test_add_alias_endpoint.py`: Endpoint de alias
- `test_document_repository_store.py`: Document repository store
- `test_config_store.py`: Config store
- `test_matching_debug_report_no_local_docs.py`: Matching debug report (NO_LOCAL_DOCS)
- `test_matching_debug_report_period_mismatch.py`: Matching debug report (PERIOD_MISMATCH)

### 12.3. Aislamiento de Tests

**E2E:**
- Usa `data/repository_e2e/` (separado de datos reales)
- Resetea estado antes de cada test
- Usa modo FAKE para coordinación CAE

**Unit:**
- Usa `tmp_path` para directorios temporales
- Mock de stores cuando aplica
- Aislamiento por test usando UUIDs únicos

---

## 13. Instalación y Ejecución

### 13.1. Requisitos

- Python 3.10+
- Node.js 18+ (para tests E2E)
- Playwright browsers (instalado automáticamente)

### 13.2. Instalación

```bash
# Clonar repositorio
git clone <repo_url>
cd CometLocal

# Instalar dependencias Python
pip install -r requirements.txt

# Instalar dependencias Node.js (tests)
npm install

# Instalar browsers Playwright
npx playwright install
```

### 13.3. Ejecución en Modo Demo

```bash
# Windows
set ENVIRONMENT=demo
python -m uvicorn backend.app:app --reload

# Linux/Mac
export ENVIRONMENT=demo
python -m uvicorn backend.app:app --reload
```

Abrir: `http://127.0.0.1:8000/repository_v3.html`

### 13.4. Ejecución en Modo Desarrollo

```bash
# Sin variable ENVIRONMENT (o ENVIRONMENT=dev)
python -m uvicorn backend.app:app --reload
```

### 13.5. Ejecución de Tests

```bash
# Tests E2E
npx playwright test

# Tests unitarios
pytest backend/tests/
```

---

## 14. Estado Actual

### 14.1. Funcionalidades Completadas

✅ **Repositorio Documental v1:**
- CRUD completo de tipos y documentos
- Cálculo automático de validez
- Gestión de períodos y series temporales
- Calendario de documentos pendientes
- Matching inteligente
- Reglas de envío con herencia
- Historial de envíos
- Exportación

✅ **Training Guiado (C2.35):**
- Wizard de 5 pasos
- Banner persistente
- Estado persistente
- Bloqueo de acciones hasta completar

✅ **Acciones Asistidas (C2.35):**
- Asignar a tipo existente (añadir alias)
- Crear nuevo tipo
- Logging de acciones

✅ **Sistema de Runs:**
- Runs audit-ready
- Contexto humano guardado
- Evidencias completas
- Summary.md y summary.json

✅ **Sistema de Schedules:**
- Schedules daily/weekly
- Contexto humano guardado
- Ejecución automática

✅ **eGestiona Adapter:**
- Integración completa
- Flujos headful/headless
- Evidencias

✅ **Connector SDK:**
- Framework para conectores
- Registro de conectores
- Ejecución de conectores

✅ **Sistema de Coordinación:**
- Contexto humano
- Guardrails para WRITE
- Multi-tenant

✅ **Observabilidad de Matching (C2.34):**
- Matching Debug Report determinista
- Panel UI "¿Por qué no se ha subido?"
- 9 códigos de razón implementados
- Tests E2E y unitarios

✅ **TrainingGate (C2.35.2):**
- Prevención de solape legacy + C2.35
- Hard-guard visual
- Tests E2E anti-solape

### 14.2. Funcionalidades en Desarrollo

🔄 **Mejoras de UI:**
- Refinamiento de componentes
- Mejoras de UX

🔄 **Optimizaciones:**
- Performance de matching
- Caché de cálculos de validez

### 14.3. Versión Actual

**Último commit:** `4600b16` - "C2.35.2 unify training: prevent legacy overlap and disable autostart"

**Sprint actual:** C2.35.2 (completado)

---

## 15. Próximos Pasos Conocidos

### 15.1. Mejoras de Training

- [ ] Refinamiento de contenido del wizard
- [ ] Analytics de completación
- [ ] Re-training opcional

### 15.2. Mejoras de Matching

- [ ] Matching más inteligente con ML
- [ ] Sugerencias de matching
- [ ] Aprendizaje de patrones

### 15.3. Nuevos Conectores

- [ ] Conector para otras plataformas CAE
- [ ] SDK mejorado para desarrolladores

### 15.4. Mejoras de UI

- [ ] Dashboard mejorado
- [ ] Notificaciones
- [ ] Mejoras de accesibilidad

---

## 16. Issues Conocidos y Limitaciones

### 16.1. Issues Conocidos

1. **Training Legacy:**
   - Legacy training desactivado pero código aún presente
   - Puede reactivarse manualmente (no recomendado)

2. **Performance:**
   - Cálculo de validez puede ser lento con muchos documentos
   - Matching puede ser lento con muchos documentos pendientes

3. **Multi-tenant:**
   - Aislamiento por directorio, no por base de datos
   - Posibles conflictos si mismo tenant_id usado en múltiples instancias

### 16.2. Limitaciones

1. **Persistencia:**
   - Solo filesystem JSON, no base de datos relacional
   - Escalabilidad limitada para grandes volúmenes

2. **Concurrencia:**
   - No hay locks de archivos (posibles race conditions)
   - Runs no pueden ejecutarse en paralelo para mismo tenant

3. **Seguridad:**
   - CORS abierto en desarrollo (debe restringirse en producción)
   - Secretos en JSON (debe usar variables de entorno o vault)

---

## 17. Guías de Referencia Rápida

### 17.1. Añadir Nuevo Tipo de Documento

1. Navegar a `#configuracion` → "Tipos de Documento"
2. Click en "Crear Tipo"
3. Completar formulario:
   - ID único
   - Nombre
   - Política de validez
   - Tipo de período
4. Guardar

### 17.2. Subir Documento

1. Navegar a `#subir`
2. Seleccionar tipo
3. Seleccionar archivo PDF
4. Completar metadatos (fecha, sujeto)
5. Click en "Subir"

### 17.3. Ejecutar Run CAE

1. Navegar a `#ejecuciones`
2. Seleccionar contexto humano (empresa, plataforma, cliente)
3. Click en "Ejecutar Run"
4. Esperar a que complete
5. Ver resultado y evidencias

### 17.4. Crear Schedule

1. Navegar a `#programacion`
2. Click en "Crear Schedule"
3. Completar formulario:
   - Plan ID
   - Cadencia (daily/weekly)
   - Hora
   - Contexto humano
4. Guardar

### 17.5. Añadir Alias a Tipo

1. Navegar a `#configuracion` → "Tipos de Documento"
2. Seleccionar tipo
3. Click en "Añadir Alias"
4. Introducir alias
5. Guardar

---

## 18. Decisiones de Diseño Importantes

### 18.1. Arquitectura

**Decisión:** Filesystem JSON en lugar de base de datos relacional

**Razón:** Simplicidad, portabilidad, fácil debugging

**Trade-off:** Escalabilidad limitada, posibles race conditions

### 18.2. Multi-tenant

**Decisión:** Aislamiento por directorio (`data/<tenant_id>/`)

**Razón:** Simplicidad, fácil backup/restore

**Trade-off:** No hay validación de tenant_id único

### 18.3. Contexto Humano

**Decisión:** Headers HTTP para contexto humano en lugar de sesión

**Razón:** Stateless, fácil debugging, compatible con API REST

**Trade-off:** Requiere enviar contexto en cada request WRITE

### 18.4. Training Obligatorio

**Decisión:** Training obligatorio antes de desbloquear acciones

**Razón:** Seguridad, evitar errores de usuario

**Trade-off:** Puede ser molesto para usuarios avanzados

### 18.5. Evidencias

**Decisión:** Screenshots y logs en cada run

**Razón:** Auditabilidad, debugging, trazabilidad

**Trade-off:** Almacenamiento, puede ser lento

### 18.6. Frontend Vanilla

**Decisión:** HTML/JS vanilla sin frameworks

**Razón:** Simplicidad, sin dependencias, fácil debugging

**Trade-off:** Más código manual, menos reutilización

---

## Apéndices

### A. Comandos Útiles

```bash
# Arrancar backend
python -m uvicorn backend.app:app --reload

# Tests E2E
npx playwright test

# Tests unitarios
pytest backend/tests/ -v

# Limpiar datos E2E
python tools/purge_e2e_data.py

# Ver logs
tail -f logs/app.log  # Si existe
```

### B. Estructura de Datos

```
data/
├── repository/
│   ├── docs/              # PDFs
│   ├── meta/              # Metadatos JSON
│   ├── types/             # Tipos de documento
│   └── rules/             # Reglas de envío
├── training/
│   ├── state.json         # Estado de training
│   └── actions.log.jsonl  # Log de acciones
├── runs/                  # Runs (por tenant)
│   └── <tenant_id>/
│       └── <run_id>/
│           ├── input.json
│           ├── result.json
│           ├── summary.md
│           ├── summary.json
│           └── evidence/
└── refs/                  # Configuración
    ├── org.json
    ├── platforms.json
    ├── people.json
    └── secrets.json
```

### C. Referencias

- **Onboarding:** `docs/ONBOARDING.md`
- **Arquitectura:** `docs/architecture.md`
- **Repositorio Documental:** `docs/document_repository_v1.md`
- **Evidencias C2.34:** `docs/evidence/c2_34/README.md`
- **Evidencias C2.35:** `docs/evidence/c2_35/README.md`

---

**Fin del Handoff Técnico y Funcional Completo**

*Última actualización: 2026-01-20*
