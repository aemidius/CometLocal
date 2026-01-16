# Handoff Técnico Completo — CometLocal
**Fecha:** 2026-01-14  
**Versión:** v2.0 (Completo)  
**Estado:** Proyecto funcional, listo para desarrollo continuo

---

## Índice

1. [Visión General del Proyecto](#1-visión-general-del-proyecto)
2. [Stack Tecnológico](#2-stack-tecnológico)
3. [Arquitectura del Sistema](#3-arquitectura-del-sistema)
4. [Estructura del Proyecto](#4-estructura-del-proyecto)
5. [Componentes Principales](#5-componentes-principales)
6. [APIs y Endpoints](#6-apis-y-endpoints)
7. [Modelos de Datos](#7-modelos-de-datos)
8. [Flujos Principales](#8-flujos-principales)
9. [Configuración y Variables de Entorno](#9-configuración-y-variables-de-entorno)
10. [Testing](#10-testing)
11. [Despliegue y Ejecución](#11-despliegue-y-ejecución)
12. [Estado Actual y Próximos Pasos](#12-estado-actual-y-próximos-pasos)

---

## 1. Visión General del Proyecto

**CometLocal** es una aplicación web para automatización de tareas CAE/PRL en portales empresariales reales. Combina gestión documental inteligente con automatización mediante agentes LLM y navegación automatizada con Playwright.

### Funcionalidades Core

1. **Repositorio Documental (v1)**
   - CRUD completo de tipos de documento configurables
   - Subida y gestión de documentos PDF con metadatos
   - Cálculo automático de validez basado en políticas declarativas
   - Gestión de períodos (mensual, trimestral, anual, ninguno)
   - Calendario de documentos pendientes y próximos vencimientos
   - Búsqueda avanzada y edición de documentos
   - Matching inteligente de documentos pendientes

2. **Motor de Automatización CAE**
   - **eGestiona Adapter**: Integración con plataforma eGestiona real
   - **Connector SDK**: Framework para crear conectores de plataformas CAE
   - Flujos headful/headless con Playwright
   - Matching de documentos pendientes con repositorio
   - Ejecución determinista con evidencias

3. **Sistema de Agentes LLM**
   - Agentes LLM para tareas complejas de navegación
   - Ejecución batch de múltiples objetivos
   - Sistema de memoria persistente
   - Reasoning Spotlight y Planner Hints
   - Outcome Judge para evaluación de resultados

4. **Sistema CAE (Coordinación de Actividades Empresariales)**
   - Planificación de envíos CAE
   - Cola de trabajos asíncrona
   - Coordinación entre empresas y trabajadores
   - Historial de envíos

5. **Simulación y Testing**
   - Portales simulados para desarrollo y testing
   - Tests E2E con Playwright
   - Tests unitarios con pytest

---

## 2. Stack Tecnológico

### Backend
- **Framework:** FastAPI (Python 3.13+)
- **Servidor ASGI:** Uvicorn
- **Validación:** Pydantic v2
- **Navegador automatizado:** Playwright (Python async)
- **LLM:** OpenAI API compatible (LM Studio, OpenAI, Anthropic, etc.)
- **PDF:** PyPDF4 / pypdf
- **Testing:** pytest, pytest-asyncio

### Frontend
- **Tecnología:** HTML5 + JavaScript vanilla (sin frameworks)
- **UI:** Diseño dark theme, responsive
- **Comunicación:** Fetch API (REST)
- **Routing:** Hash-based routing

### Testing E2E
- **Framework:** Playwright (Node.js)
- **Configuración:** `playwright.config.js`
- **Tests:** Archivos `.spec.js` en `tests/`

### Persistencia
- **Formato:** JSON (tipos, metadatos, configuración)
- **Archivos:** Filesystem (PDFs en `data/repository/docs/`)
- **Estructura:** Data-driven (sin base de datos relacional)
- **Atomic writes:** Para integridad de datos

---

## 3. Arquitectura del Sistema

### Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                         │
│  - repository_v3.html (UI principal)                        │
│  - home.html (Dashboard)                                     │
│  - index.html (Chat UI)                                      │
│  - training.html (Training UI)                              │
└────────────────────┬────────────────────────────────────────┘
                     │ REST API
┌────────────────────▼────────────────────────────────────────┐
│              Backend FastAPI (Python)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Routes                                           │  │
│  │  - /api/repository/* (Repositorio)                    │  │
│  │  - /api/connectors/* (Conectores SDK)                 │  │
│  │  - /api/cae/* (Sistema CAE)                           │  │
│  │  - /agent/* (Agentes LLM)                             │  │
│  │  - /api/config/* (Configuración)                       │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Core Services                                        │  │
│  │  - DocumentRepositoryStoreV1                         │  │
│  │  - PeriodPlannerV1                                    │  │
│  │  - ValidityCalculatorV1                               │  │
│  │  - DocumentMatcherV1                                  │  │
│  │  - CAEExecutionRunnerV1                               │  │
│  │  - Connector SDK (BaseConnector)                      │  │
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
│              Persistencia (JSON + Filesystem)                │
│  - data/repository/types/types.json                         │
│  - data/repository/docs/{doc_id}.pdf                        │
│  - data/repository/meta/{doc_id}.json                       │
│  - data/refs/ (org, people, platforms, secrets)            │
│  - data/cae/ (planes, jobs, historial)                     │
│  - memory/ (memoria persistente de agentes)                 │
└─────────────────────────────────────────────────────────────┘
```

### Principios de Diseño

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

## 4. Estructura del Proyecto

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
│   ├── browser/                      # Control de navegador
│   │   └── browser.py                # BrowserController async
│   │
│   ├── cae/                          # Sistema CAE
│   │   ├── submission_planner_v1.py  # Planificación de envíos
│   │   ├── execution_runner_v1.py     # Ejecutor CAE
│   │   ├── coordination_models_v1.py # Modelos de coordinación
│   │   ├── job_queue_v1.py          # Cola de trabajos
│   │   ├── submission_routes.py      # API routes
│   │   ├── coordination_routes.py
│   │   └── job_queue_routes.py
│   │
│   ├── connectors/                   # SDK de Conectores (C2.12.1)
│   │   ├── __init__.py
│   │   ├── models.py                 # PendingRequirement, UploadResult, RunContext
│   │   ├── base.py                   # BaseConnector (ABC)
│   │   ├── registry.py               # Registry de conectores
│   │   ├── runner.py                 # Runner de conectores
│   │   ├── routes.py                 # API routes
│   │   └── egestiona/
│   │       ├── connector.py          # Conector e-gestiona (stub)
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
│   │   └── criteria_profiles_v1.py   # Perfiles de criterios
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
│   ├── rl/                           # Reinforcement Learning
│   │   ├── rl_engine.py
│   │   └── rl_memory.py
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
│   ├── home.html                    # Dashboard
│   ├── index.html                   # Chat UI
│   ├── training.html                # Training UI
│   └── simulation/                  # Portales simulados
│       ├── portal_a/
│       └── portal_a_v2/
│
├── tests/                            # Tests E2E (Playwright)
│   ├── *.spec.js
│   ├── cae_plan_e2e.spec.js
│   └── ...
│
├── data/                             # Datos persistentes
│   ├── repository/                  # Repositorio documental
│   │   ├── types/types.json
│   │   ├── docs/                    # PDFs
│   │   ├── meta/                    # Metadatos JSON
│   │   └── settings.json
│   ├── refs/                        # Referencias
│   │   ├── org.json
│   │   ├── people.json
│   │   ├── platforms.json
│   │   ├── secrets.json
│   │   └── llm_config.json
│   ├── cae/                         # Datos CAE
│   │   ├── plans/
│   │   ├── jobs/
│   │   └── history/
│   ├── connectors/                  # Evidencias de conectores
│   │   └── evidence/
│   └── runs/                        # Runs de ejecución
│
├── memory/                           # Memoria persistente
│   └── platforms/                   # Memoria por plataforma
│
├── docs/                            # Documentación
│   ├── TECHNICAL_HANDOFF_*.md
│   └── evidence/
│
├── requirements.txt                 # Dependencias Python
├── package.json                     # Dependencias Node.js
├── playwright.config.js            # Config Playwright
└── README.md
```

---

## 5. Componentes Principales

### 5.1 Backend - Aplicación Principal (`backend/app.py`)

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
6. `document_repository_router` - API del repositorio
7. `config_routes_router` - Config API
8. `submission_rules_router` - Reglas de envío
9. `submission_history_router` - Historial
10. `repository_settings_router` - Settings del repo
11. `cae_submission_router` - Planificación CAE
12. `cae_coordination_router` - Coordinación CAE
13. `cae_job_queue_router` - Cola de trabajos CAE
14. `test_seed_router` - Seeding para tests (DEV)
15. `connectors_router` - SDK de conectores (DEV)

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

---

### 5.2 Repositorio Documental (`backend/repository/`)

#### 5.2.1 Document Repository Store (`document_repository_store_v1.py`)

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

#### 5.2.2 Document Repository Routes (`document_repository_routes.py`)

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

#### 5.2.3 Document Matcher (`document_matcher_v1.py`)

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

#### 5.2.4 Validity Calculator (`validity_calculator_v1.py`)

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

#### 5.2.5 Period Planner (`period_planner_v1.py`)

**Responsabilidades:**
- Planificación de períodos esperados
- Generación de períodos faltantes
- Cálculo de períodos basado en política de validez

#### 5.2.6 Document Status Calculator (`document_status_calculator_v1.py`)

**Responsabilidades:**
- Cálculo de estado de documentos
- Agregación de estados por tipo/empresa/trabajador
- Cálculo de pendientes

#### 5.2.7 Submission Rules Store (`submission_rules_store_v1.py`)

**Responsabilidades:**
- Gestión de reglas de envío
- Reglas por tipo de documento, empresa, trabajador
- Matching de reglas

#### 5.2.8 Submission History Store (`submission_history_store_v1.py`)

**Responsabilidades:**
- Historial de envíos a plataformas
- Tracking de estado de envíos
- Evidencias de envíos

---

### 5.3 Sistema CAE (`backend/cae/`)

#### 5.3.1 Submission Planner (`submission_planner_v1.py`)

**Responsabilidades:**
- Planificación de envíos CAE
- Generación de planes de ejecución
- Filtrado por empresa, trabajador, tipo de documento

#### 5.3.2 Execution Runner (`execution_runner_v1.py`)

**Responsabilidades:**
- Ejecución de planes CAE
- Coordinación con adapters de plataformas
- Gestión de estado de ejecución

#### 5.3.3 Job Queue (`job_queue_v1.py`)

**Responsabilidades:**
- Cola de trabajos asíncrona
- Worker background para procesar jobs
- Persistencia de jobs en disco

**Endpoints (`job_queue_routes.py`):**
- `GET /api/cae/jobs` - Listar jobs
- `POST /api/cae/jobs` - Crear job
- `GET /api/cae/jobs/{job_id}` - Obtener job
- `PUT /api/cae/jobs/{job_id}/cancel` - Cancelar job

#### 5.3.4 Coordination Models (`coordination_models_v1.py`)

**Modelos:**
- `CoordinationRequestV1`
- `CoordinationResponseV1`
- `CompanyCoordinationV1`
- `WorkerCoordinationV1`

---

### 5.4 Connector SDK (`backend/connectors/`) - C2.12.1

#### 5.4.1 Modelos (`models.py`)

- `PendingRequirement` - Requisito pendiente normalizado
- `UploadResult` - Resultado de subida
- `RunContext` - Contexto de ejecución

#### 5.4.2 Base Connector (`base.py`)

**Interfaz abstracta:**
- `login(page)` - Login en el portal
- `navigate_to_pending(page)` - Navegar a pendientes
- `extract_pending(page)` - Extraer requisitos
- `match_repository(reqs)` - Matching con repo
- `upload_one(page, req, doc_id)` - Subir documento

#### 5.4.3 Registry (`registry.py`)

- Registro de conectores por `platform_id`
- `register_connector()` - Registrar conector
- `get_connector()` - Obtener instancia

#### 5.4.4 Runner (`runner.py`)

**Flujo de ejecución:**
1. Crear RunContext
2. Obtener conector del registry
3. Lanzar Playwright
4. Login
5. Navegar a pendientes
6. Extraer requisitos
7. Matching con repositorio
8. Subir documentos (limitado a `max_items`)
9. Guardar evidencias
10. Retornar resumen

#### 5.4.5 e-Gestiona Connector (`egestiona/connector.py`)

**Estado actual (C2.12.1):** Stub funcional
- Produce evidencias (screenshots)
- Ejecuta pipeline completo
- NO automatiza la web real aún

**Para C2.12.2:**
- Implementar login real
- Implementar extracción real de pendientes
- Implementar subida real

**Endpoints (`routes.py`):**
- `POST /api/connectors/run` - Ejecutar conector (DEV-ONLY)

---

### 5.5 Sistema de Agentes (`backend/agents/`)

#### 5.5.1 Agent Runner (`agent_runner.py`)

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

#### 5.5.2 Batch Runner (`batch_runner.py`)

**Responsabilidades:**
- Ejecución batch de múltiples objetivos
- Gestión de fallos consecutivos
- Persistencia de resultados

#### 5.5.3 Visual Flow (`visual_flow.py`)

**Responsabilidades:**
- Flujo visual de navegación
- Contratos visuales
- Verificación de estado de página

#### 5.5.4 Reasoning Spotlight (`reasoning_spotlight.py`)

**Responsabilidades:**
- Análisis previo del objetivo
- Identificación de requisitos
- Generación de contexto

#### 5.5.5 Planner Hints (`llm_planner_hints.py`)

**Responsabilidades:**
- Generación de hints para el planificador
- Análisis de viabilidad
- Sugerencias de optimización

#### 5.5.6 Outcome Judge (`outcome_judge.py`)

**Responsabilidades:**
- Evaluación post-ejecución
- Análisis de éxito/fallo
- Generación de reporte

---

### 5.6 Browser Controller (`backend/browser/` y `backend/executor/`)

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

### 5.7 Inspector de Documentos (`backend/inspector/`)

#### 5.7.1 Document Inspector (`document_inspector_v1.py`)

**Responsabilidades:**
- Extracción de texto de PDFs
- Análisis de contenido
- Validación de criterios
- Bloqueo de subida si no cumple criterios

#### 5.7.2 Criteria Profiles (`criteria_profiles_v1.py`)

**Perfiles de criterios:**
- Criterios configurables por tipo de documento
- Validación automática en upload

---

### 5.8 Memoria Persistente (`backend/memory/`)

#### 5.8.1 Memory Store (`memory_store.py`)

**Responsabilidades:**
- Persistencia de memoria de agentes
- Memoria por plataforma
- Credenciales en memoria (no en disco)
- Historial de interacciones

**Estructura:**
- `memory/platforms/{platform_id}.json`

---

### 5.9 Visión y OCR (`backend/vision/`)

#### 5.9.1 OCR Service (`ocr_service.py`)

**Responsabilidades:**
- Extracción de texto de imágenes
- Integración con LLM para OCR
- Análisis visual

#### 5.9.2 Visual Memory (`visual_memory.py`)

**Responsabilidades:**
- Memoria visual de páginas
- Comparación de estados visuales
- Detección de cambios

#### 5.9.3 Visual Targets (`visual_targets.py`)

**Responsabilidades:**
- Identificación de targets visuales
- Matching visual de elementos

---

### 5.10 Adapters eGestiona (`backend/adapters/egestiona/`)

#### 5.10.1 Flows (`flows.py`)

**Endpoints:**
- `POST /api/egestiona/match-pending` - Matching de pendientes
- `POST /api/egestiona/submission-plan` - Plan de envío
- `POST /api/egestiona/execute-plan` - Ejecutar plan

#### 5.10.2 Execute Plan (`execute_plan_headful.py`)

**Responsabilidades:**
- Ejecución headful de planes
- Login real en eGestiona
- Navegación y subida
- Evidencias completas

#### 5.10.3 Match Pending (`match_pending_headful.py`)

**Responsabilidades:**
- Extracción de pendientes de eGestiona
- Matching con repositorio
- Generación de reporte

#### 5.10.4 Submission Plan (`submission_plan_headful.py`)

**Responsabilidades:**
- Generación de plan de envío
- Filtrado por empresa/trabajador
- Priorización

---

## 6. APIs y Endpoints

### 6.1 Repositorio Documental (`/api/repository/*`)

Ver sección 5.2.2 para lista completa.

### 6.2 Sistema CAE (`/api/cae/*`)

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

### 6.3 Conectores (`/api/connectors/*`)

- `POST /api/connectors/run` - Ejecutar conector (DEV-ONLY)

### 6.4 Agentes (`/agent/*`)

- `POST /agent/answer` - Ejecutar agente LLM
- `POST /agent/batch` - Ejecución batch
- `POST /agent/run` - Ejecutar agente simple
- `POST /agent/run_llm` - Ejecutar agente LLM

### 6.5 Configuración (`/api/config/*`)

- `GET /api/config/llm` - Configuración LLM
- `POST /api/config/llm` - Actualizar configuración LLM
- `GET /api/config/platforms` - Listar plataformas
- `GET /api/config/people` - Listar personas
- `GET /api/config/org` - Organización

### 6.6 eGestiona (`/api/egestiona/*`)

- `POST /api/egestiona/match-pending` - Matching de pendientes
- `POST /api/egestiona/submission-plan` - Plan de envío
- `POST /api/egestiona/execute-plan` - Ejecutar plan

### 6.7 Tests/Seeding (`/api/test/*`) - DEV-ONLY

- `POST /api/test/seed/reset` - Resetear datos
- `POST /api/test/seed/basic_repository` - Crear repo básico
- Y más...

---

## 7. Modelos de Datos

### 7.1 Document Repository Models (`backend/shared/document_repository_v1.py`)

#### DocumentTypeV1
```python
class DocumentTypeV1(BaseModel):
    type_id: str
    name: str
    description: Optional[str]
    scope: DocumentScopeV1  # "company" | "worker"
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

### 7.2 Connector Models (`backend/connectors/models.py`)

#### PendingRequirement
```python
@dataclass
class PendingRequirement:
    id: str
    subject_type: Literal["empresa", "trabajador"]
    doc_type_hint: str
    subject_id: Optional[str]
    period: Optional[str]  # "YYYY-MM"
    due_date: Optional[str]  # "YYYY-MM-DD"
    status: Literal["missing", "expired", "expiring", "requested"]
    portal_meta: Dict[str, Any]
```

#### UploadResult
```python
@dataclass
class UploadResult:
    success: bool
    requirement_id: str
    uploaded_doc_id: Optional[str]
    portal_reference: Optional[str]
    evidence: Dict[str, str]
    error: Optional[str]
```

#### RunContext
```python
@dataclass
class RunContext:
    run_id: str
    base_url: Optional[str]
    platform_id: str
    tenant_id: Optional[str]
    headless: bool
    timeouts: Dict[str, int]
    evidence_dir: Optional[str]
```

### 7.3 Agent Models (`backend/shared/models.py`)

#### AgentAnswerRequest
```python
class AgentAnswerRequest(BaseModel):
    goal: str
    steps: List[Dict]
    execution_confirmed: Optional[bool]
    plan_only: Optional[bool]
    execution_profile_name: Optional[str]
    context_strategies: Optional[List[str]]
    execution_mode: Optional[str]  # "live" | "dry_run"
```

#### AgentAnswerResponse
```python
class AgentAnswerResponse(BaseModel):
    goal: str
    final_answer: str
    steps: List[StepResult]
    execution_plan: Optional[Dict]
    reasoning_spotlight: Optional[Dict]
    planner_hints: Optional[Dict]
    outcome_judge: Optional[Dict]
    execution_mode: Optional[str]
```

### 7.4 CAE Models (`backend/cae/coordination_models_v1.py`)

Ver archivo para modelos completos de coordinación CAE.

---

## 8. Flujos Principales

### 8.1 Flujo de Subida de Documento

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

### 8.2 Flujo de Matching de Pendientes (eGestiona)

1. Usuario ejecuta `POST /api/egestiona/match-pending`
2. Backend:
   - Lanza Playwright headful
   - Login en eGestiona
   - Navega a pendientes
   - Extrae requisitos pendientes
   - Matching con repositorio (DocumentMatcher)
   - Genera reporte
3. Retorna matches con confidence scores

### 8.3 Flujo de Ejecución de Plan CAE

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

### 8.4 Flujo de Agente LLM

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

### 8.5 Flujo de Conector SDK

1. Usuario ejecuta: `POST /api/connectors/run`
2. Backend:
   - Crea RunContext
   - Obtiene conector del registry
   - Lanza Playwright
   - Ejecuta: login → navigate → extract → match → upload
   - Guarda evidencias
3. Retorna resumen con counts y results

---

## 9. Configuración y Variables de Entorno

### 9.1 Variables de Entorno

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

**Plataformas:**
- `DEFAULT_PORTAL_A_URL` - URL del portal A simulado
- `DEFAULT_PORTAL_B_URL` - URL del portal B simulado
- `CAE_BASE_URL` - URL base CAE

**Testing:**
- `E2E_SEED_ENABLED` - Habilitar endpoints de seeding (default: 0)
- `ENVIRONMENT` - Entorno (dev/development/local para habilitar endpoints DEV)

**Otros:**
- `OPEN_UI_ON_START` - Abrir navegador al iniciar (default: 0)
- `VISION_OCR_ENABLED` - Habilitar OCR (default: true)
- `VISION_OCR_PROVIDER` - Proveedor OCR (default: lmstudio)

### 9.2 Archivos de Configuración

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

**`data/refs/org.json`:**
Organizaciones/empresas

**`data/refs/people.json`:**
Personas/trabajadores

**`data/refs/platforms.json`:**
Plataformas CAE

**`data/refs/secrets.json`:**
Secretos (NO commitear)

**`data/repository/settings.json`:**
Configuración del repositorio

---

## 10. Testing

### 10.1 Tests Unitarios (pytest)

**Ubicación:** `backend/tests/`

**Ejecutar:**
```bash
pytest backend/tests/ -v
pytest backend/tests/test_connector_registry.py -v
```

**Cobertura:**
- Tests de modelos
- Tests de stores
- Tests de calculadores
- Tests de matchers
- Tests de agentes
- Tests de conectores

### 10.2 Tests E2E (Playwright)

**Ubicación:** `tests/*.spec.js`

**Ejecutar:**
```bash
npx playwright test
npx playwright test tests/cae_plan_e2e.spec.js
npx playwright test tests/isolation_repository_data_dir.spec.js
```

**Tests principales:**
- `cae_plan_e2e.spec.js` - Tests de planificación CAE
- `isolation_repository_data_dir.spec.js` - Aislamiento de datos
- `e2e_*.spec.js` - Tests E2E del repositorio

**Configuración:** `playwright.config.js`

---

## 11. Despliegue y Ejecución

### 11.1 Instalación

**Requisitos:**
- Python 3.13+
- Node.js 18+
- Playwright browsers instalados

**Instalar dependencias:**
```bash
pip install -r requirements.txt
npm install
npx playwright install chromium
```

### 11.2 Ejecución

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

### 11.3 Estructura de Datos Inicial

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

## 12. Estado Actual y Próximos Pasos

### 12.1 Estado Actual (2026-01-14)

**Completado:**
- ✅ Repositorio documental completo (v1)
- ✅ Sistema CAE funcional
- ✅ Adapter eGestiona (READ-ONLY y WRITE scoped)
- ✅ Sistema de agentes LLM
- ✅ Connector SDK mínimo (C2.12.1)
- ✅ Tests unitarios y E2E
- ✅ UI completa del repositorio
- ✅ Sistema de memoria persistente

**En desarrollo:**
- 🔄 Connector eGestiona end-to-end (C2.12.2)
- 🔄 Mejoras en matching de documentos
- 🔄 Optimizaciones de performance

### 12.2 Próximos Pasos Conocidos

**Sprint C2.12.2:**
- Implementar login real en eGestiona connector
- Implementar extracción real de pendientes
- Implementar subida real de documentos
- Definir selectores CSS/XPath
- Añadir perfiles por tenant

**Mejoras futuras:**
- Soporte para más plataformas CAE
- Mejoras en UI/UX
- Optimizaciones de performance
- Más tests E2E

### 12.3 Issues Conocidos

- Algunos tests async pueden fallar (requieren configuración de pytest-asyncio)
- Endpoints DEV requieren `E2E_SEED_ENABLED=1` o `ENVIRONMENT=dev`
- Playwright requiere browsers instalados

---

## 13. Referencias y Documentación Adicional

### 13.1 Documentos en `docs/`
- `TECHNICAL_HANDOFF_COMPLETE_*.md` - Handoffs anteriores
- `document_repository_v1.md` - Documentación del repositorio
- `home_ui.md` - Documentación de la UI

### 13.2 Código de Referencia
- `backend/app.py` - Punto de entrada principal
- `backend/repository/document_repository_store_v1.py` - Store principal
- `backend/agents/agent_runner.py` - Runner de agentes
- `backend/connectors/base.py` - SDK de conectores

### 13.3 Tests de Referencia
- `backend/tests/test_document_repository_h7_5.py` - Tests del repo
- `tests/cae_plan_e2e.spec.js` - Tests E2E CAE
- `backend/tests/test_connector_registry.py` - Tests del SDK

---

## 14. Contacto y Soporte

Para preguntas o dudas sobre la implementación:
1. Revisar este documento
2. Revisar código fuente con comentarios
3. Revisar tests como ejemplos de uso
4. Revisar documentación en `docs/`

---

**Fin del Handoff Técnico Completo**

*Última actualización: 2026-01-14*
