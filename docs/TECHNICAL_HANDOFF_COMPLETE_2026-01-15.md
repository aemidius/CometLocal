# Handoff Técnico y Funcional Completo — CometLocal
**Fecha:** 2026-01-15  
**Versión:** v3.0 (Handoff Completo para Traspaso)  
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

---

## 1. Visión General del Proyecto

**CometLocal** es una plataforma de automatización para la gestión documental en portales CAE (Coordinación de Actividades Empresariales). El sistema combina:

- **Repositorio Documental Inteligente**: Gestión centralizada de documentos con cálculo automático de validez, series temporales y matching inteligente
- **Automatización CAE**: Subida automática de documentos a portales CAE reales (eGestiona) usando Playwright
- **Agentes LLM**: Sistema de agentes autónomos para navegación y ejecución de tareas complejas
- **UI Humanizada**: Interfaz orientada a tareas con lenguaje natural

### Propósito del Sistema

Automatizar tareas repetitivas de gestión documental CAE/PRL en portales empresariales reales, con:
- **Determinismo**: Ejecución reproducible y predecible
- **Evidencia**: Trazabilidad completa con screenshots y logs
- **Seguridad**: Guardrails estrictos para operaciones WRITE
- **Extensibilidad**: SDK para crear conectores de nuevas plataformas

---

## 2. Funcionalidades Principales

### 2.1 Repositorio Documental (v1)

#### Gestión de Tipos de Documento
- ✅ CRUD completo de tipos configurables
- ✅ Políticas de validez (monthly, annual, fixed_end_date, none)
- ✅ Aliases de plataforma para matching
- ✅ Configuración de scope (company/worker/both)
- ✅ Filtrado avanzado y paginación
- ✅ Toggle activo/inactivo
- ✅ Duplicación de tipos

#### Gestión de Documentos
- ✅ Subida de PDFs con drag & drop multiarchivo
- ✅ Extracción automática de metadatos (fechas desde filename)
- ✅ Cálculo automático de validez según políticas
- ✅ Overrides manuales de validez
- ✅ Soporte para series temporales (period_key)
- ✅ Inferencia automática de period_key
- ✅ Estados: valid, expired, expiring_soon

#### Series Temporales
- ✅ Generación de períodos esperados
- ✅ Cálculo de estado por período (AVAILABLE/MISSING/LATE)
- ✅ Calendario de documentos pendientes
- ✅ Vista de cobertura por tipo/sujeto

#### Matching Inteligente
- ✅ Matching de documentos pendientes con repositorio
- ✅ Normalización robusta de texto
- ✅ Cálculo de confianza
- ✅ Matching por tipo, empresa, trabajador, período
- ✅ Aplicación de reglas de envío

### 2.2 Sistema CAE

#### Planificación de Envíos
- ✅ Generación de planes de ejecución
- ✅ Filtrado por empresa, trabajador, tipo
- ✅ Priorización de documentos
- ✅ Modo READ-ONLY y WRITE

#### Ejecución
- ✅ Ejecución headful/headless con Playwright
- ✅ Login real en portales CAE
- ✅ Navegación y subida automatizada
- ✅ Evidencias completas (screenshots, logs)
- ✅ Cola de trabajos asíncrona

#### Coordinación
- ✅ Gestión de coordinaciones entre empresas
- ✅ Tracking de estado de envíos
- ✅ Historial completo

### 2.3 Adapter eGestiona

- ✅ Login real en coordinate.egestiona.es
- ✅ Extracción de pendientes (READ-ONLY)
- ✅ Subida de documentos (WRITE scoped)
- ✅ Matching con repositorio
- ✅ Evidencias por ejecución
- ✅ Headful runs persistentes (timeline y observabilidad)

### 2.4 Sistema de Agentes LLM

- ✅ Agentes autónomos para navegación web
- ✅ Reasoning Spotlight (análisis previo)
- ✅ Execution Planning (planificación)
- ✅ Outcome Judge (evaluación post-ejecución)
- ✅ Memoria persistente
- ✅ Ejecución batch

### 2.5 Connector SDK

- ✅ Framework para crear conectores de plataformas
- ✅ Interfaz base (BaseConnector)
- ✅ Registry de conectores
- ✅ Runner de ejecución
- ✅ eGestiona connector (stub funcional)

### 2.6 UI y Frontend

- ✅ Dashboard HOME con navegación centralizada
- ✅ Repositorio UI v3 (humanizada, orientada a tareas)
- ✅ Calendario de documentos pendientes
- ✅ Wizard de subida guiado
- ✅ Búsqueda avanzada
- ✅ Vista de plataformas y reglas
- ✅ Configuración LLM persistente
- ✅ Monitor de estado LLM

---

## 3. Stack Tecnológico

### Backend
- **Framework**: FastAPI (Python 3.13+)
- **Servidor ASGI**: Uvicorn
- **Validación**: Pydantic v2
- **Navegador automatizado**: Playwright (Python async)
- **LLM**: OpenAI API compatible (LM Studio, OpenAI, Anthropic, etc.)
- **PDF**: PyPDF4 / pypdf
- **Testing**: pytest, pytest-asyncio
- **HTTP Client**: requests

### Frontend
- **Tecnología**: HTML5 + JavaScript vanilla (sin frameworks)
- **UI**: Diseño dark theme, responsive
- **Comunicación**: Fetch API (REST)
- **Routing**: Hash-based routing

### Testing E2E
- **Framework**: Playwright (Node.js)
- **Configuración**: `playwright.config.js`
- **Tests**: Archivos `.spec.js` en `tests/`

### Persistencia
- **Formato**: JSON (tipos, metadatos, configuración)
- **Archivos**: Filesystem (PDFs en `data/repository/docs/`)
- **Estructura**: Data-driven (sin base de datos relacional)
- **Atomic writes**: Para integridad de datos

---

## 4. Arquitectura del Sistema

### 4.1 Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                         │
│  - repository_v3.html (UI principal)                        │
│  - home.html (Dashboard)                                     │
│  - index.html (Chat UI)                                       │
│  - training.html (Training UI)                               │
└────────────────────┬────────────────────────────────────────┘
                     │ REST API
┌────────────────────▼────────────────────────────────────────┐
│              Backend FastAPI (Python)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Routes                                           │  │
│  │  - /api/repository/* (Repositorio)                   │  │
│  │  - /api/cae/* (Sistema CAE)                          │  │
│  │  - /api/connectors/* (Conectores SDK)                │  │
│  │  - /agent/* (Agentes LLM)                            │  │
│  │  - /api/config/* (Configuración)                     │  │
│  │  - /api/egestiona/* (Adapter eGestiona)              │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Core Services                                        │  │
│  │  - DocumentRepositoryStoreV1                        │  │
│  │  - PeriodPlannerV1                                   │  │
│  │  - ValidityCalculatorV1                              │  │
│  │  - DocumentMatcherV1                                 │  │
│  │  - CAEExecutionRunnerV1                              │  │
│  │  - Connector SDK (BaseConnector)                     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Agents & Automation                                  │  │
│  │  - AgentRunner (LLM-based)                            │  │
│  │  - BatchRunner                                        │  │
│  │  - BrowserController (Playwright)                     │  │
│  │  - VisualFlow, VisualContracts                        │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│              Persistencia (JSON + Filesystem)               │
│  - data/repository/types/types.json                         │
│  - data/repository/docs/{doc_id}.pdf                        │
│  - data/repository/meta/{doc_id}.json                       │
│  - data/refs/ (org, people, platforms, secrets)            │
│  - data/cae/ (planes, jobs, historial)                      │
│  - memory/ (memoria persistente de agentes)                 │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Principios de Diseño

1. **Separación de Responsabilidades**
   - Repositorio documental independiente del motor CAE
   - Agentes LLM separados de la lógica de negocio
   - Adapters específicos por plataforma

2. **Determinismo**
   - Cálculos de validez deterministas
   - Matching con reglas claras
   - Ejecución reproducible

3. **Evidencia y Trazabilidad**
   - Screenshots por paso crítico
   - Logs estructurados
   - Manifiestos de ejecución

4. **Atomicidad**
   - Writes atómicos para integridad
   - Transacciones de archivo + metadata

5. **Extensibilidad**
   - SDK de conectores para nuevas plataformas
   - Sistema de plugins por tenant/empresa

---

## 5. Estructura del Proyecto

```
CometLocal/
├── backend/                          # Backend Python
│   ├── __init__.py
│   ├── app.py                        # Aplicación FastAPI principal
│   ├── config.py                     # Configuración global
│   │
│   ├── adapters/                     # Adapters de plataformas
│   │   └── egestiona/
│   │       ├── flows.py              # Flujos principales
│   │       ├── execute_plan_headful.py
│   │       ├── match_pending_headful.py
│   │       ├── submission_plan_headful.py
│   │       ├── headful_run_routes.py # Headful runs persistentes
│   │       ├── real_uploader.py      # Uploader real
│   │       ├── fake_uploader.py      # Uploader fake (testing)
│   │       └── ...
│   │
│   ├── agents/                       # Sistema de agentes LLM
│   │   ├── agent_runner.py           # Runner principal
│   │   ├── batch_runner.py           # Ejecución batch
│   │   ├── document_repository.py    # Integración con repo
│   │   ├── execution_plan.py         # Planificación
│   │   ├── visual_flow.py            # Flujo visual
│   │   ├── visual_contracts.py      # Contratos visuales
│   │   ├── reasoning_spotlight.py   # Reasoning Spotlight
│   │   ├── llm_planner_hints.py     # Planner Hints
│   │   ├── outcome_judge.py          # Outcome Judge
│   │   └── ...
│   │
│   ├── browser/                       # Control de navegador
│   │   └── browser.py                # BrowserController async
│   │
│   ├── cae/                          # Sistema CAE
│   │   ├── submission_planner_v1.py  # Planificación de envíos
│   │   ├── execution_runner_v1.py    # Ejecutor CAE
│   │   ├── coordination_models_v1.py  # Modelos de coordinación
│   │   ├── job_queue_v1.py          # Cola de trabajos
│   │   ├── submission_routes.py      # API routes
│   │   ├── coordination_routes.py
│   │   └── job_queue_routes.py
│   │
│   ├── connectors/                   # SDK de Conectores
│   │   ├── __init__.py
│   │   ├── models.py                 # PendingRequirement, UploadResult, RunContext
│   │   ├── base.py                   # BaseConnector (ABC)
│   │   ├── registry.py               # Registry de conectores
│   │   ├── runner.py                 # Runner de conectores
│   │   ├── routes.py                 # API routes
│   │   └── egestiona/
│   │       ├── connector.py          # Conector e-gestiona
│   │       ├── tenants.py            # Configuración por tenant
│   │       ├── selectors.py         # Selectores CSS/XPath
│   │       └── README.md
│   │
│   ├── documents/                    # Helpers de documentos
│   │   ├── repository.py
│   │   └── helpers.py
│   │
│   ├── executor/                     # Ejecutor determinista
│   │   ├── browser_controller.py    # BrowserController sync
│   │   ├── runtime_skeleton.py      # Runtime skeleton
│   │   ├── runs_viewer.py           # Viewer de runs
│   │   └── config_viewer.py        # Viewer de config
│   │
│   ├── inspector/                    # Inspector de documentos
│   │   ├── document_inspector_v1.py  # Inspector principal
│   │   └── criteria_profiles_v1.py  # Perfiles de criterios
│   │
│   ├── memory/                       # Memoria persistente
│   │   ├── __init__.py
│   │   └── memory_store.py          # MemoryStore
│   │
│   ├── planner/                      # Planificadores
│   │   ├── planner.py
│   │   ├── llm_planner.py
│   │   └── simple_planner.py
│   │
│   ├── repository/                   # Repositorio Documental
│   │   ├── document_repository_store_v1.py  # Store principal
│   │   ├── document_repository_routes.py   # API routes
│   │   ├── document_matcher_v1.py           # Matching
│   │   ├── validity_calculator_v1.py       # Cálculo de validez
│   │   ├── period_planner_v1.py            # Planificación de períodos
│   │   ├── submission_rules_store_v1.py    # Reglas de envío
│   │   ├── submission_history_store_v1.py # Historial
│   │   ├── document_status_calculator_v1.py # Estado de documentos
│   │   ├── config_routes.py                # Config API
│   │   ├── settings_routes.py               # Settings API
│   │   └── ...
│   │
│   ├── runs/                         # Gestión de runs
│   │   ├── headful_run_manager.py    # Manager de runs headful
│   │   └── run_timeline.py           # Timeline de eventos
│   │
│   ├── shared/                       # Modelos compartidos
│   │   ├── models.py                 # Modelos principales
│   │   ├── document_repository_v1.py # Modelos del repo
│   │   ├── executor_contracts_v1.py # Contratos del ejecutor
│   │   ├── file_ref_v1.py           # Referencias de archivos
│   │   ├── org_v1.py                # Organizaciones
│   │   ├── people_v1.py             # Personas
│   │   ├── platforms_v1.py          # Plataformas
│   │   ├── person_matcher.py        # Matching de personas
│   │   └── text_normalizer.py       # Normalización de texto
│   │
│   ├── simulation/                   # Simulación de portales
│   │   ├── routes.py
│   │   ├── simulator.py
│   │   └── scenarios/
│   │       └── portal_a/
│   │
│   ├── tests/                        # Tests unitarios
│   │   ├── test_*.py
│   │   └── e2e/
│   │
│   ├── training/                     # Training UI
│   │   └── routes.py
│   │
│   ├── vision/                       # Visión y OCR
│   │   ├── ocr_service.py
│   │   ├── visual_memory.py
│   │   └── visual_targets.py
│   │
│   └── tests_seed_routes.py         # Routes de seeding (DEV)
│
├── frontend/                         # Frontend HTML/JS
│   ├── repository_v3.html           # UI principal del repo
│   ├── home.html                     # Dashboard
│   ├── index.html                    # Chat UI
│   ├── training.html                 # Training UI
│   └── simulation/                   # Portales simulados
│       ├── portal_a/
│       └── portal_a_v2/
│
├── tests/                            # Tests E2E (Playwright)
│   ├── *.spec.js
│   ├── cae_plan_e2e.spec.js
│   ├── egestiona_manual_review_readonly.spec.js
│   └── ...
│
├── data/                             # Datos persistentes
│   ├── repository/                   # Repositorio documental
│   │   ├── types/types.json
│   │   ├── docs/                     # PDFs
│   │   ├── meta/                      # Metadatos JSON
│   │   └── settings.json
│   ├── refs/                         # Referencias
│   │   ├── org.json
│   │   ├── people.json
│   │   ├── platforms.json
│   │   ├── secrets.json
│   │   └── llm_config.json
│   ├── cae/                          # Datos CAE
│   │   ├── plans/
│   │   ├── jobs/
│   │   └── history/
│   ├── connectors/                    # Evidencias de conectores
│   │   └── evidence/
│   └── runs/                         # Runs de ejecución
│
├── memory/                           # Memoria persistente
│   └── platforms/                     # Memoria por plataforma
│
├── docs/                            # Documentación
│   ├── TECHNICAL_HANDOFF_*.md
│   ├── evidence/
│   └── ...
│
├── requirements.txt                 # Dependencias Python
├── package.json                     # Dependencias Node.js
├── playwright.config.js            # Config Playwright
└── README.md
```

---

## 6. Componentes Principales

### 6.1 Backend - Aplicación Principal (`backend/app.py`)

**Responsabilidades:**
- Inicialización de FastAPI
- Registro de todos los routers
- Gestión de navegador compartido (BrowserController)
- Endpoints principales de agentes
- Configuración LLM persistente
- Manejo de credenciales en memoria
- Event handlers (startup/shutdown)

**Routers Registrados:**
1. `simulation_router` - Portales simulados
2. `training_router` - Training UI
3. `runs_viewer_router` - Viewer de runs
4. `config_viewer_router` - Viewer de configuración
5. `egestiona_router` - Flujos eGestiona
6. `egestiona_execute_router` - Ejecución de planes
7. `egestiona_execute_headful_router` - Ejecución headful
8. `egestiona_headful_run_router` - Headful runs persistentes
9. `document_repository_router` - API del repositorio
10. `config_routes_router` - Config API
11. `submission_rules_router` - Reglas de envío
12. `submission_history_router` - Historial
13. `repository_settings_router` - Settings del repo
14. `cae_submission_router` - Planificación CAE
15. `cae_coordination_router` - Coordinación CAE
16. `cae_job_queue_router` - Cola de trabajos CAE
17. `test_seed_router` - Seeding para tests (DEV)
18. `connectors_router` - SDK de conectores (DEV)

**Endpoints Principales (en app.py):**
- `GET /` - HOME Dashboard
- `GET /home` - Alias para HOME
- `GET /index.html` - Chat UI
- `GET /repository` - UI del repositorio (v3)
- `POST /agent/answer` - Ejecución de agente LLM
- `POST /agent/batch` - Ejecución batch
- `POST /chat` - Chat simple
- `GET /api/config/llm` - Configuración LLM
- `POST /api/config/llm` - Actualizar configuración LLM
- `GET /api/health/llm` - Health check LLM
- `GET /health` - Health check general
- `GET /api/health` - Health check API

**Startup Event:**
- Asegura layout de `data/`
- Inicia worker de cola de jobs CAE
- Inicializa cliente LLM compartido
- Carga configuración LLM persistente
- Registra conectores automáticamente
- Opcionalmente abre navegador si `OPEN_UI_ON_START=1`

**Shutdown Event:**
- Detiene worker de cola CAE
- Cierra navegador si está iniciado

### 6.2 Repositorio Documental (`backend/repository/`)

#### Document Repository Store (`document_repository_store_v1.py`)

**Responsabilidades:**
- Gestión de tipos de documento (`types.json`)
- Gestión de instancias de documentos (CRUD)
- Persistencia de PDFs en filesystem
- Cálculo automático de validez
- Atomic writes para integridad
- Filtrado por `period_key`

**Estructura de Datos:**
- **Tipos:** `data/repository/types/types.json` (array de `DocumentTypeV1`)
- **Documentos:** 
  - PDFs: `data/repository/docs/{doc_id}.pdf`
  - Metadatos: `data/repository/meta/{doc_id}.json`

**Métodos Principales:**
- `list_types()` - Lista tipos con filtros
- `get_type(type_id)` - Obtiene un tipo
- `create_type()` - Crea un tipo
- `update_type()` - Actualiza un tipo
- `delete_type()` - Elimina un tipo
- `list_documents()` - Lista documentos con filtros
- `get_document(doc_id)` - Obtiene un documento
- `save_document()` - Guarda documento (PDF + metadata)
- `delete_document()` - Elimina documento

#### Document Repository Routes (`document_repository_routes.py`)

**Endpoints:**
- `GET /api/repository/types` - Listar tipos (con filtros, paginación)
- `GET /api/repository/types/{type_id}` - Obtener tipo
- `POST /api/repository/types` - Crear tipo
- `PUT /api/repository/types/{type_id}` - Actualizar tipo
- `DELETE /api/repository/types/{type_id}` - Eliminar tipo
- `PUT /api/repository/types/{type_id}/toggle_active` - Toggle activo
- `POST /api/repository/types/{type_id}/duplicate` - Duplicar tipo
- `GET /api/repository/types/{type_id}/expected` - Períodos esperados
- `GET /api/repository/docs` - Listar documentos (con filtros)
- `GET /api/repository/docs/{doc_id}` - Obtener documento
- `POST /api/repository/docs/upload` - Subir documento
- `PUT /api/repository/docs/{doc_id}` - Actualizar documento
- `DELETE /api/repository/docs/{doc_id}` - Eliminar documento
- `POST /api/repository/docs/{doc_id}/override` - Override de validez
- `GET /api/repository/docs/pending` - Documentos pendientes
- `GET /api/repository/subjects` - Sujetos (empresas/trabajadores)
- `GET /api/repository/debug/data_dir` - Debug: directorio de datos

#### Document Matcher (`document_matcher_v1.py`)

**Responsabilidades:**
- Matching de documentos pendientes con repositorio
- Normalización de texto robusta
- Cálculo de confianza
- Matching por tipo, empresa, trabajador, fechas

**Algoritmo:**
1. Normaliza texto del requisito pendiente
2. Busca tipos de documento por aliases (`platform_aliases`)
3. Calcula confidence score
4. Filtra documentos por tipo, empresa, trabajador, período
5. Retorna matches ordenados por confidence

#### Validity Calculator (`validity_calculator_v1.py`)

**Responsabilidades:**
- Cálculo determinista de validez
- Soporte para modos: `monthly`, `annual`, `fixed_end_date`, `none`
- Bases: `issue_date`, `name_date`, `manual`
- Grace days configurables

**Lógica:**
- Calcula fecha de inicio según base
- Calcula fecha de fin según modo y período
- Aplica grace days
- Determina estado: `valid`, `expired`, `expiring_soon`

#### Period Planner (`period_planner_v1.py`)

**Responsabilidades:**
- Planificación de períodos esperados
- Generación de períodos faltantes
- Cálculo de períodos basado en política de validez

#### Document Status Calculator (`document_status_calculator_v1.py`)

**Responsabilidades:**
- Cálculo de estado de documentos
- Agregación de estados por tipo/empresa/trabajador
- Cálculo de pendientes

### 6.3 Sistema CAE (`backend/cae/`)

#### Submission Planner (`submission_planner_v1.py`)

**Responsabilidades:**
- Planificación de envíos CAE
- Generación de planes de ejecución
- Filtrado por empresa, trabajador, tipo de documento

#### Execution Runner (`execution_runner_v1.py`)

**Responsabilidades:**
- Ejecución de planes CAE
- Coordinación con adapters de plataformas
- Gestión de estado de ejecución

#### Job Queue (`job_queue_v1.py`)

**Responsabilidades:**
- Cola de trabajos asíncrona
- Worker background para procesar jobs
- Persistencia de jobs en disco

**Endpoints (`job_queue_routes.py`):**
- `GET /api/cae/jobs` - Listar jobs
- `POST /api/cae/jobs` - Crear job
- `GET /api/cae/jobs/{job_id}` - Obtener job
- `PUT /api/cae/jobs/{job_id}/cancel` - Cancelar job

### 6.4 Adapters eGestiona (`backend/adapters/egestiona/`)

#### Flows (`flows.py`)

**Endpoints:**
- `POST /api/egestiona/match-pending` - Matching de pendientes
- `POST /api/egestiona/submission-plan` - Plan de envío
- `POST /api/egestiona/execute-plan` - Ejecutar plan

#### Headful Run Routes (`headful_run_routes.py`)

**Endpoints:**
- `POST /runs/egestiona/start_headful_run` - Inicia run headful persistente
- `POST /runs/egestiona/execute_action_headful` - Ejecuta acción dentro de un run activo
- `POST /runs/egestiona/close_headful_run` - Cierra run headful persistente
- `GET /runs/egestiona/headful_run_status` - Obtiene estado y timeline de un run activo

**Características:**
- Runs persistentes con timeline de eventos
- Observabilidad en tiempo real
- Niveles de riesgo automáticos
- Storage state persistente

#### Execute Plan Headful (`execute_plan_headful.py`)

**Responsabilidades:**
- Ejecución headful de planes
- Login real en eGestiona
- Navegación y subida
- Evidencias completas

#### Match Pending (`match_pending_headful.py`)

**Responsabilidades:**
- Extracción de pendientes de eGestiona
- Matching con repositorio
- Generación de reporte

### 6.5 Sistema de Agentes (`backend/agents/`)

#### Agent Runner (`agent_runner.py`)

**Responsabilidades:**
- Ejecución de agentes LLM
- Integración con navegador
- Gestión de steps y contexto
- ActionPlanner (generación de acciones desde DOM)
- ExecutionPolicyState (corte temprano por éxito)

**Flujo:**
1. Generar Reasoning Spotlight
2. Construir Execution Plan
3. Ejecutar steps con Playwright
4. Generar acciones desde DOM si es necesario
5. Ejecutar múltiples fases (Phase 1, 2, 3)
6. Evaluar resultado con Outcome Judge

### 6.6 Browser Controller

**Dos implementaciones:**
1. **Async** (`browser/browser.py`) - Para agentes LLM
2. **Sync** (`executor/browser_controller.py`) - Para ejecutor determinista

**Funcionalidades:**
- Lanzar Playwright
- Navegar a URLs
- Interactuar con elementos (click, fill, select)
- Screenshots
- Manejo de frames
- Manejo de cookies

---

## 7. APIs y Endpoints

### 7.1 Repositorio Documental (`/api/repository/*`)

Ver sección 6.2.2 para lista completa.

### 7.2 Sistema CAE (`/api/cae/*`)

**Submission:**
- `POST /api/cae/submission/plan` - Generar plan
- `POST /api/cae/submission/execute` - Ejecutar plan

**Coordination:**
- `POST /api/cae/coordination/request` - Solicitar coordinación
- `GET /api/cae/coordination/{request_id}` - Obtener coordinación

**Job Queue:**
- `GET /api/cae/jobs` - Listar jobs
- `POST /api/cae/jobs` - Crear job
- `GET /api/cae/jobs/{job_id}` - Obtener job
- `PUT /api/cae/jobs/{job_id}/cancel` - Cancelar job

### 7.3 eGestiona (`/api/egestiona/*` y `/runs/egestiona/*`)

**Flujos básicos:**
- `POST /api/egestiona/match-pending` - Matching de pendientes
- `POST /api/egestiona/submission-plan` - Plan de envío
- `POST /api/egestiona/execute-plan` - Ejecutar plan

**Headful runs persistentes:**
- `POST /runs/egestiona/start_headful_run` - Inicia run persistente
- `POST /runs/egestiona/execute_action_headful` - Ejecuta acción
- `POST /runs/egestiona/close_headful_run` - Cierra run
- `GET /runs/egestiona/headful_run_status` - Estado y timeline

**Build submission plan readonly:**
- `POST /runs/egestiona/build_submission_plan_readonly` - Genera plan READ-ONLY

### 7.4 Conectores (`/api/connectors/*`)

- `POST /api/connectors/run` - Ejecutar conector (DEV-ONLY)

### 7.5 Agentes (`/agent/*`)

- `POST /agent/answer` - Ejecutar agente LLM
- `POST /agent/batch` - Ejecución batch
- `POST /agent/run` - Ejecutar agente simple
- `POST /agent/run_llm` - Ejecutar agente LLM

### 7.6 Configuración (`/api/config/*`)

- `GET /api/config/llm` - Configuración LLM
- `POST /api/config/llm` - Actualizar configuración LLM
- `GET /api/config/platforms` - Listar plataformas
- `GET /api/config/people` - Listar personas
- `GET /api/config/org` - Organización

---

## 8. Modelos de Datos

### 8.1 Document Repository Models

#### DocumentTypeV1
```python
class DocumentTypeV1(BaseModel):
    type_id: str
    name: str
    description: Optional[str]
    scope: DocumentScopeV1  # "company" | "worker" | "both"
    validity_policy: ValidityPolicyV1
    platform_aliases: List[str]
    active: bool
    created_at: str
    updated_at: str
```

#### DocumentInstanceV1
```python
class DocumentInstanceV1(BaseModel):
    doc_id: str
    type_id: str
    company_key: Optional[str]
    person_key: Optional[str]
    period_key: Optional[str]  # "YYYY-MM"
    file_path: str
    status: DocumentStatusV1  # "valid" | "expired" | "expiring_soon"
    validity_start: Optional[str]  # "YYYY-MM-DD"
    validity_end: Optional[str]  # "YYYY-MM-DD"
    extracted_metadata: Optional[ExtractedMetadataV1]
    validity_override: Optional[ValidityOverrideV1]
    created_at: str
    updated_at: str
```

#### ValidityPolicyV1
```python
class ValidityPolicyV1(BaseModel):
    mode: PeriodKindV1  # "monthly" | "annual" | "fixed_end_date" | "none"
    base: str  # "issue_date" | "name_date" | "manual"
    grace_days: int
    n_months: Optional[int]  # Para monthly
    fixed_end_date: Optional[str]  # Para fixed_end_date
```

### 8.2 CAE Models

Ver `backend/cae/coordination_models_v1.py` y `backend/cae/submission_models_v1.py` para modelos completos.

### 8.3 Agent Models

Ver `backend/shared/models.py` para modelos completos de agentes.

---

## 9. Flujos Principales

### 9.1 Flujo de Subida de Documento

1. Usuario selecciona archivo PDF en UI
2. Frontend llama `POST /api/repository/docs/upload`
3. Backend:
   - Valida archivo
   - Extrae metadatos (DocumentInspector)
   - Valida criterios (si aplica)
   - Calcula validez (ValidityCalculator)
   - Guarda PDF + metadata (atomic write)
4. Retorna documento creado
5. Frontend actualiza UI

### 9.2 Flujo de Matching de Pendientes (eGestiona)

1. Usuario ejecuta `POST /api/egestiona/match-pending`
2. Backend:
   - Lanza Playwright headful
   - Login en eGestiona
   - Navega a pendientes
   - Extrae requisitos pendientes
   - Matching con repositorio (DocumentMatcher)
   - Genera reporte
3. Retorna matches con confidence scores

### 9.3 Flujo de Ejecución de Plan CAE

1. Usuario genera plan: `POST /api/cae/submission/plan`
2. Backend genera plan filtrado
3. Usuario ejecuta plan: `POST /api/cae/submission/execute`
4. Backend:
   - Crea job en cola
   - Worker procesa job
   - Ejecuta adapter eGestiona
   - Sube documentos
   - Guarda evidencias
5. Retorna resultados

### 9.4 Flujo de Headful Run Persistente

1. Usuario inicia run: `POST /runs/egestiona/start_headful_run`
2. Backend:
   - Crea run persistente
   - Inicia navegador
   - Carga storage state (si existe)
   - Retorna run_id
3. Usuario ejecuta acciones: `POST /runs/egestiona/execute_action_headful`
4. Backend:
   - Ejecuta acción en navegador activo
   - Registra eventos en timeline
   - Retorna resultado
5. Usuario consulta estado: `GET /runs/egestiona/headful_run_status`
6. Usuario cierra run: `POST /runs/egestiona/close_headful_run`

### 9.5 Flujo de Agente LLM

1. Usuario envía goal: `POST /agent/answer`
2. Backend:
   - Genera Reasoning Spotlight
   - Genera Execution Plan
   - Si `plan_only=True`, retorna plan
   - Si `execution_confirmed=False`, cancela
   - Ejecuta steps con Playwright
   - Genera acciones desde DOM si es necesario
   - Ejecuta múltiples fases
   - Genera Outcome Judge
3. Retorna respuesta con steps y resultado

---

## 10. UI y Frontend

### 10.1 HOME Dashboard (`frontend/home.html`)

**Funcionalidades:**
- Navegación centralizada a todas las pantallas
- Configuración LLM persistente
- Monitor de estado LLM en tiempo real
- Quick links a funcionalidades principales

### 10.2 Repositorio UI v3 (`frontend/repository_v3.html`)

**Funcionalidades:**
- **Inicio**: KPIs y acciones rápidas
- **Calendario**: Vista mensual de documentos pendientes
- **Subir documentos**: Wizard guiado con drag & drop
- **Buscar documentos**: Búsqueda avanzada con filtros
- **Plataformas**: Vista de estado y configuración
- **Catálogo**: Gestión de tipos de documento
- **Actividad**: Historial de acciones

**Características:**
- Lenguaje humano (no técnico)
- Orientado a tareas
- Autocompletado inteligente
- Validaciones claras
- Feedback visual

### 10.3 Chat UI (`frontend/index.html`)

- Interfaz de chat para agentes LLM
- Ejecución de tareas complejas
- Visualización de steps

---

## 11. Configuración y Variables de Entorno

### 11.1 Variables de Entorno

**LLM:**
- `LLM_API_BASE` - URL del servidor LLM (default: `http://127.0.0.1:1234/v1`)
- `LLM_API_KEY` - API key (default: `lm-studio`)
- `LLM_MODEL` - Modelo a usar
- `LLM_TIMEOUT` - Timeout en segundos (default: 30)

**Data:**
- `COMETLOCAL_DATA_DIR` - Directorio de datos (default: `<repo>/data`)
- `BATCH_RUNS_DIR` - Directorio de runs (default: `data/runs`)

**Memoria:**
- `MEMORY_BASE_DIR` - Directorio de memoria (default: `memory`)
- `VISUAL_MEMORY_BASE_DIR` - Directorio de memoria visual (default: `memory/visual`)
- `VISUAL_MEMORY_ENABLED` - Habilitar memoria visual (default: 1)

**Testing:**
- `E2E_SEED_ENABLED` - Habilitar endpoints de seeding (default: 0)
- `ENVIRONMENT` - Entorno (dev/development/local para habilitar endpoints DEV)

**Otros:**
- `OPEN_UI_ON_START` - Abrir navegador al iniciar (default: 0)
- `VISION_OCR_ENABLED` - Habilitar OCR (default: true)
- `VISION_OCR_PROVIDER` - Proveedor OCR (default: lmstudio)

### 11.2 Archivos de Configuración

**`data/refs/llm_config.json`:**
```json
{
  "base_url": "http://127.0.0.1:1234/v1",
  "api_key": "lm-studio",
  "provider": "lm-studio",
  "model": "model-name",
  "timeout_seconds": 30
}
```

**`data/refs/org.json`:** Organizaciones/empresas

**`data/refs/people.json`:** Personas/trabajadores

**`data/refs/platforms.json`:** Plataformas CAE

**`data/refs/secrets.json`:** Secretos (NO commitear)

**`data/repository/settings.json`:** Configuración del repositorio

---

## 12. Testing

### 12.1 Tests Unitarios (pytest)

**Ubicación:** `backend/tests/`

**Ejecutar:**
```bash
pytest backend/tests/ -v
pytest backend/tests/test_document_repository_h7_5.py -v
```

**Cobertura:**
- Tests de modelos
- Tests de stores
- Tests de calculadores
- Tests de matchers
- Tests de agentes
- Tests de conectores

### 12.2 Tests E2E (Playwright)

**Ubicación:** `tests/*.spec.js`

**Ejecutar:**
```bash
npx playwright test
npx playwright test tests/cae_plan_e2e.spec.js
npx playwright test tests/egestiona_manual_review_readonly.spec.js --headed --timeout=360000
```

**Tests principales:**
- `cae_plan_e2e.spec.js` - Tests de planificación CAE
- `egestiona_manual_review_readonly.spec.js` - Test manual de revisión READ-ONLY
- `e2e_*.spec.js` - Tests E2E del repositorio
- `isolation_repository_data_dir.spec.js` - Aislamiento de datos

**Configuración:** `playwright.config.js`

---

## 13. Instalación y Ejecución

### 13.1 Requisitos

- Python 3.13+
- Node.js 18+
- Playwright browsers instalados

### 13.2 Instalación

```bash
# Instalar dependencias Python
pip install -r requirements.txt

# Instalar dependencias Node.js
npm install

# Instalar browsers de Playwright
npx playwright install chromium
```

### 13.3 Ejecución

**Backend:**
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

**Con variables de entorno:**
```bash
ENVIRONMENT=dev python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

**Abrir UI automáticamente:**
```bash
OPEN_UI_ON_START=1 python -m uvicorn backend.app:app
```

### 13.4 Estructura de Datos Inicial

El sistema crea automáticamente la estructura en `data/` al iniciar si no existe.

**Layout:**
```
data/
├── repository/
│   ├── types/
│   ├── docs/
│   ├── meta/
│   └── settings.json
├── refs/
│   ├── org.json
│   ├── people.json
│   ├── platforms.json
│   ├── secrets.json
│   └── llm_config.json
├── cae/
│   ├── plans/
│   ├── jobs/
│   └── history/
└── runs/
```

---

## 14. Estado Actual

### 14.1 Funcionalidades Completadas

✅ **Repositorio Documental**
- CRUD completo de tipos y documentos
- Cálculo automático de validez
- Series temporales
- Matching inteligente
- UI v3 completa

✅ **Sistema CAE**
- Planificación de envíos
- Ejecución con evidencias
- Cola de trabajos
- Coordinación

✅ **Adapter eGestiona**
- Login real
- Extracción de pendientes (READ-ONLY)
- Subida de documentos (WRITE scoped)
- Headful runs persistentes

✅ **Sistema de Agentes**
- Agentes LLM funcionales
- Reasoning Spotlight
- Execution Planning
- Outcome Judge

✅ **Testing**
- Tests unitarios (pytest)
- Tests E2E (Playwright)
- Evidencias automáticas

### 14.2 Funcionalidades en Desarrollo

🔄 **Connector SDK**
- eGestiona connector end-to-end
- Mejoras en selectores
- Perfiles por tenant

🔄 **Mejoras**
- Optimizaciones de performance
- Más tests E2E
- Mejoras en UI/UX

---

## 15. Próximos Pasos Conocidos

### 15.1 Corto Plazo

- Completar eGestiona connector end-to-end
- Mejorar matching de documentos
- Optimizar performance de queries
- Añadir más tests E2E

### 15.2 Medio Plazo

- Soporte para más plataformas CAE
- Mejoras en UI/UX
- Sistema de notificaciones
- Dashboard de analytics

### 15.3 Largo Plazo

- Multi-tenant
- API pública
- Integraciones con sistemas externos
- Machine learning para matching

---

## 16. Issues Conocidos y Limitaciones

### 16.1 Issues Técnicos

- Algunos tests async pueden fallar (requieren configuración de pytest-asyncio)
- Endpoints DEV requieren `E2E_SEED_ENABLED=1` o `ENVIRONMENT=dev`
- Playwright requiere browsers instalados
- Error `updateWorkerField is not defined` en algunos casos (no crítico)

### 16.2 Limitaciones

- Solo soporta eGestiona actualmente (otros conectores en desarrollo)
- Requiere LLM local o API key para agentes
- No hay autenticación de usuarios (desarrollo)
- CORS abierto (solo desarrollo)

---

## 17. Guías de Referencia Rápida

### 17.1 Comandos Útiles

```bash
# Iniciar backend
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

# Ejecutar tests unitarios
pytest backend/tests/ -v

# Ejecutar tests E2E
npx playwright test

# Ejecutar test específico
npx playwright test tests/egestiona_manual_review_readonly.spec.js --headed

# Verificar salud del sistema
curl http://127.0.0.1:8000/api/health
```

### 17.2 Archivos Clave para Modificar

**Backend:**
- `backend/app.py` - Punto de entrada principal
- `backend/config.py` - Configuración global
- `backend/repository/document_repository_store_v1.py` - Store del repositorio
- `backend/cae/execution_runner_v1.py` - Ejecutor CAE
- `backend/adapters/egestiona/flows.py` - Flujos eGestiona

**Frontend:**
- `frontend/home.html` - Dashboard principal
- `frontend/repository_v3.html` - UI del repositorio

**Tests:**
- `tests/egestiona_manual_review_readonly.spec.js` - Test manual completo
- `backend/tests/test_document_repository_h7_5.py` - Tests del repositorio

### 17.3 Debugging

**Ver logs del backend:**
- Los logs se muestran en consola
- Errores se capturan en `page_errors.txt` (tests E2E)

**Ver evidencias:**
- Screenshots: `docs/evidence/`
- Network responses: `docs/evidence/*/last_network_response.json`
- Console logs: `docs/evidence/*/console_log.txt`

**Debugging de Playwright:**
- Usar `--headed` para ver el navegador
- Usar `--debug` para modo debug
- Screenshots automáticos en fallos

### 17.4 Documentación Adicional

- `docs/TECHNICAL_HANDOFF_COMPLETE_2026-01-14.md` - Handoff anterior
- `docs/home_ui.md` - Documentación de HOME UI
- `docs/evidence/` - Evidencias de ejecuciones
- `00_README.md` - Visión general del proyecto
- `01_PRODUCT_VISION.md` - Visión de producto
- `02_ARCHITECTURE.md` - Arquitectura
- `03_CURRENT_STATUS.md` - Estado actual
- `05_TESTING_PLAYBOOK.md` - Guía de testing
- `06_DEBUGGING_GUIDE.md` - Guía de debugging

---

## 18. Contacto y Soporte

Para preguntas o dudas sobre la implementación:

1. **Revisar este documento** - Handoff completo
2. **Revisar código fuente** - Comentarios en el código
3. **Revisar tests** - Ejemplos de uso en tests
4. **Revisar documentación** - Archivos en `docs/`
5. **Revisar evidencias** - Ejemplos en `docs/evidence/`

---

## 19. Resumen Ejecutivo

**CometLocal** es una plataforma funcional y completa para automatización de gestión documental CAE. El sistema está listo para desarrollo continuo con:

- ✅ Arquitectura sólida y extensible
- ✅ Funcionalidades core completas
- ✅ Testing robusto
- ✅ Documentación completa
- ✅ UI humanizada y funcional

**Puntos clave para el nuevo desarrollador:**

1. **Backend**: FastAPI con múltiples routers, estructura modular
2. **Frontend**: HTML/JS vanilla, sin frameworks
3. **Persistencia**: JSON + filesystem, sin base de datos
4. **Testing**: pytest (unitarios) + Playwright (E2E)
5. **Configuración**: Variables de entorno + archivos JSON
6. **Estado**: Funcional, listo para mejoras y extensiones

**Próximo paso recomendado:**
1. Leer este documento completo
2. Ejecutar el sistema localmente
3. Revisar tests como ejemplos
4. Explorar código fuente con comentarios
5. Ejecutar test manual: `npx playwright test tests/egestiona_manual_review_readonly.spec.js --headed`

---

**Fin del Handoff Técnico y Funcional Completo**

*Última actualización: 2026-01-15*  
*Versión: v3.0 (Handoff Completo para Traspaso)*
