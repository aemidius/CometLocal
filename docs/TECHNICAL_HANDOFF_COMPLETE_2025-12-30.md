# Handoff Técnico Exhaustivo - CometLocal

**Fecha**: 30 de Diciembre 2025  
**Versión**: 2.0 (Actualización completa)  
**Estado**: Producción (eGestiona Kern - READ-ONLY y WRITE scoped funcionando) + UI v3 completa + Repositorio con series temporales

---

## Tabla de Contenidos

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Stack Tecnológico](#stack-tecnológico)
4. [Estructura del Proyecto](#estructura-del-proyecto)
5. [Componentes Principales](#componentes-principales)
6. [APIs y Endpoints](#apis-y-endpoints)
7. [Modelos de Datos](#modelos-de-datos)
8. [Funcionalidades Implementadas](#funcionalidades-implementadas)
9. [Flujos Principales](#flujos-principales)
10. [UI v3 - Repositorio Documental](#ui-v3---repositorio-documental)
11. [Series Temporales (Period-Based Documents)](#series-temporales-period-based-documents)
12. [Configuración y Despliegue](#configuración-y-despliegue)
13. [Testing y Calidad](#testing-y-calidad)
14. [Estado Actual y Roadmap](#estado-actual-y-roadmap)
15. [Partes en Desarrollo](#partes-en-desarrollo)

---

## 1. Visión General

**CometLocal** es una plataforma de automatización para la gestión documental en portales CAE (Centros de Atención al Empleado). El sistema permite:

- **Automatización de subidas**: Subida automática de documentos a portales CAE (eGestiona, etc.)
- **Repositorio documental**: Gestión centralizada de tipos de documentos, instancias y metadatos
- **Series temporales**: Soporte para documentos periódicos (mensuales/anuales) con gestión por períodos
- **Matching inteligente**: Asociación automática de documentos pendientes con documentos del repositorio
- **Reglas de envío**: Configuración de reglas para matching y envío automático con herencia (GLOBAL/COORD)
- **Historial de envíos**: Trazabilidad completa de todas las subidas realizadas
- **Agentes autónomos**: Agentes LLM para navegación y ejecución de tareas complejas
- **UI v3 humanizada**: Interfaz de usuario orientada a tareas con lenguaje humano

### Características Principales

- ✅ **Backend FastAPI** con arquitectura modular
- ✅ **Playwright** para automatización de navegador
- ✅ **Repositorio documental** con cálculo automático de validez y series temporales
- ✅ **UI v3 completa** con lenguaje humano y flujo por tareas
- ✅ **Catálogo de documentos v4** con filtrado avanzado y CRUD completo
- ✅ **Adaptadores por plataforma** (eGestiona implementado)
- ✅ **Evidencia completa** por ejecución (runs)
- ✅ **Normalización de texto** robusta (sin tildes, case-insensitive)
- ✅ **Dedupe guardrails** para evitar re-subidas
- ✅ **Herencia de reglas** (GLOBAL → COORD)
- ✅ **Period-based matching** determinista

---

## 2. Arquitectura del Sistema

### 2.1 Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   HOME   │  │  CHAT     │  │ REPOSITORY│  │  TRAINING │  │
│  │ Dashboard│  │   UI      │  │    UI v3  │  │    UI     │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   ROUTERS    │  │    AGENTS     │  │   EXECUTOR    │     │
│  │  - Repository│  │  - LLM Agent  │  │  - Runtime     │     │
│  │  - Config    │  │  - Batch      │  │  - Controller │     │
│  │  - eGestiona │  │  - Runner     │  │  - Redaction   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   STORES     │  │   ADAPTERS    │  │   PLANNER    │     │
│  │  - Document  │  │  - eGestiona  │  │  - LLM       │     │
│  │  - Config    │  │  - Flows      │  │  - Simple    │     │
│  │  - Rules     │  │  - Targets    │  │  - Hybrid    │     │
│  │  - History   │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   SERVICES   │  │   MATCHERS    │  │   CALCULATORS│     │
│  │  - Period    │  │  - Document  │  │  - Validity  │     │
│  │  - Planner   │  │  - Rule-based│  │  - Period    │     │
│  │  - Migration │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   JSON       │  │   FILESYSTEM  │  │   MEMORY     │     │
│  │  - Types     │  │  - Documents  │  │  - Platform  │     │
│  │  - Docs      │  │  - Evidence   │  │  - Creds     │     │
│  │  - Rules     │  │  - Runs       │  │              │     │
│  │  - History   │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   LLM API    │  │   PLAYWRIGHT  │  │   PORTALES   │     │
│  │  - OpenAI    │  │  - Chromium   │  │  - eGestiona │     │
│  │  - LM Studio │  │  - Headless   │  │  - Otros     │     │
│  │  - Ollama    │  │  - Headful    │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Separación de Responsabilidades

- **Frontend**: UI estática (HTML/JS) para interacción con el usuario
- **Backend API**: Endpoints RESTful para operaciones CRUD y ejecución
- **Agents**: Lógica de agentes autónomos (LLM-based y deterministas)
- **Adapters**: Adaptadores específicos por plataforma CAE
- **Stores**: Capa de persistencia (JSON filesystem-based)
- **Executor**: Motor de ejecución determinista de acciones de navegador
- **Planner**: Generación de planes de ejecución (LLM y determinista)
- **Services**: Servicios de planificación de períodos y migración
- **Matchers**: Matching de documentos con reglas y herencia

---

## 3. Stack Tecnológico

### 3.1 Backend

- **Python 3.10+**
- **FastAPI**: Framework web asíncrono
- **Pydantic**: Validación de datos y modelos
- **Playwright**: Automatización de navegador
- **OpenAI SDK**: Cliente LLM (compatible con múltiples proveedores)
- **PyPDF**: Extracción de texto de PDFs
- **Uvicorn**: Servidor ASGI

### 3.2 Frontend

- **HTML5/CSS3/JavaScript vanilla**: Sin frameworks (intencional)
- **Fetch API**: Comunicación con backend
- **Hash Routing**: Navegación cliente-side con hash (#)

### 3.3 Persistencia

- **JSON filesystem**: Almacenamiento en archivos JSON
- **Atomic writes**: Escrituras atómicas (temp → rename) para integridad
- **Estructura de directorios**:
  ```
  data/
  ├── refs/              # Configuración (org, people, platforms, secrets)
  ├── repository/        # Repositorio documental
  │   ├── types/         # Tipos de documento
  │   ├── docs/          # Instancias de documentos (PDFs)
  │   ├── meta/          # Metadatos de documentos
  │   ├── rules/         # Reglas de envío
  │   ├── history/       # Historial de envíos
  │   └── overrides/     # Overrides de validez
  ├── runs/              # Ejecuciones (evidence, logs)
  └── tmp/               # Temporales
  ```

### 3.4 Dependencias Principales

```txt
fastapi
uvicorn[standard]
pydantic
playwright
openai>=1.0.0
pypdf>=4.0.0
```

---

## 4. Estructura del Proyecto

```
CometLocal/
├── backend/                    # Código backend
│   ├── adapters/               # Adaptadores por plataforma
│   │   └── egestiona/          # Adaptador eGestiona
│   │       ├── flows.py        # Flujos principales
│   │       ├── targets.py      # Selectores y targets
│   │       ├── profile.py      # Perfil de plataforma
│   │       ├── submission_plan_headful.py
│   │       ├── match_pending_headful.py
│   │       ├── execute_plan_headful.py
│   │       └── frame_scan_headful.py
│   ├── agents/                 # Agentes autónomos
│   │   ├── agent_runner.py     # Runner principal
│   │   ├── batch_runner.py     # Ejecución batch
│   │   ├── cae_batch_adapter.py
│   │   ├── document_analyzer.py
│   │   ├── form_field_mapper.py
│   │   ├── hybrid_planner.py
│   │   ├── llm_planner_hints.py
│   │   ├── outcome_judge.py
│   │   └── reasoning_spotlight.py
│   ├── browser/                # Controlador de navegador
│   │   └── browser.py
│   ├── executor/                # Motor de ejecución
│   │   ├── runtime_h4.py       # Runtime principal
│   │   ├── browser_controller.py
│   │   ├── action_compiler_v1.py
│   │   └── redaction_v1.py
│   ├── inspector/               # Inspector de documentos
│   │   ├── document_inspector_v1.py
│   │   └── criteria_profiles_v1.py
│   ├── memory/                  # Memoria persistente
│   │   └── memory_store.py
│   ├── planner/                 # Planificadores
│   │   ├── llm_planner.py
│   │   └── simple_planner.py
│   ├── repository/               # Repositorio documental
│   │   ├── document_repository_routes.py
│   │   ├── document_repository_store_v1.py
│   │   ├── document_repository_v1.py
│   │   ├── config_routes.py
│   │   ├── config_store_v1.py
│   │   ├── submission_rules_routes.py
│   │   ├── submission_rules_store_v1.py
│   │   ├── submission_history_routes.py
│   │   ├── submission_history_store_v1.py
│   │   ├── document_matcher_v1.py
│   │   ├── rule_based_matcher_v1.py
│   │   ├── validity_calculator_v1.py
│   │   ├── period_planner_v1.py      # NUEVO: Planificación de períodos
│   │   ├── period_migration_v1.py     # NUEVO: Migración de períodos
│   │   └── date_parser_v1.py
│   ├── shared/                  # Modelos y utilidades compartidas
│   │   ├── document_repository_v1.py
│   │   ├── executor_contracts_v1.py
│   │   ├── file_ref_v1.py
│   │   ├── org_v1.py
│   │   ├── people_v1.py
│   │   ├── platforms_v1.py
│   │   ├── text_normalizer.py
│   │   └── models.py
│   ├── simulation/               # Simuladores de portales
│   │   ├── routes.py
│   │   └── simulator.py
│   ├── training/                 # Training UI
│   │   └── routes.py
│   ├── vision/                   # OCR y visión
│   │   ├── ocr_service.py
│   │   └── visual_memory.py
│   ├── app.py                    # Aplicación FastAPI principal
│   └── config.py                 # Configuración
├── frontend/                     # UI estática
│   ├── home.html                 # Dashboard HOME
│   ├── index.html                # Chat UI
│   ├── repository_v3.html        # NUEVO: Repositorio UI v3 completa
│   ├── training.html             # Training UI
│   └── simulation/               # Portales simulados
│       ├── portal_a/
│       └── portal_a_v2/
├── data/                         # Datos persistentes
│   ├── refs/                     # Configuración
│   ├── repository/                # Repositorio
│   ├── runs/                     # Ejecuciones
│   └── tmp/                      # Temporales
├── docs/                         # Documentación
│   ├── E2E_REPORT_*.md          # Reportes E2E
│   ├── REPO_TIME_SERIES_DESIGN.md
│   └── TECHNICAL_HANDOFF_*.md
├── scripts/                      # Scripts de utilidad
│   └── migrate_period_keys.py   # NUEVO: Migración de períodos
└── requirements.txt              # Dependencias
```

---

## 5. Componentes Principales

### 5.1 Backend - Aplicación Principal (`backend/app.py`)

**Responsabilidades**:
- Inicialización de FastAPI
- Registro de routers
- Gestión de navegador compartido
- Endpoints principales de agentes
- Configuración LLM persistente
- Manejo de credenciales en memoria

**Endpoints principales**:
- `POST /agent/answer`: Ejecución de agente LLM
- `POST /agent/batch`: Ejecución batch
- `POST /chat`: Chat simple
- `GET /api/config/llm`: Configuración LLM
- `POST /api/config/llm`: Actualizar configuración LLM
- `GET /api/health/llm`: Health check LLM
- `GET /repository`: UI del repositorio (v3)

### 5.2 Repositorio Documental (`backend/repository/`)

**Componentes**:

#### 5.2.1 Document Repository Store (`document_repository_store_v1.py`)
- Gestión de tipos de documento (`types.json`)
- Gestión de instancias de documentos
- Cálculo automático de validez
- Overrides de validez
- Atomic writes para integridad
- Filtrado por `period_key` (NUEVO)

#### 5.2.2 Document Repository Routes (`document_repository_routes.py`)
**Endpoints**:
- `GET /api/repository/types`: Listar tipos (con filtros avanzados y paginación - NUEVO)
- `GET /api/repository/types/{type_id}`: Obtener tipo
- `POST /api/repository/types`: Crear tipo
- `PUT /api/repository/types/{type_id}`: Actualizar tipo
- `DELETE /api/repository/types/{type_id}`: Eliminar tipo
- `PUT /api/repository/types/{type_id}/toggle_active`: Toggle activo (NUEVO)
- `POST /api/repository/types/{type_id}/duplicate`: Duplicar tipo (NUEVO)
- `GET /api/repository/types/{type_id}/expected`: Períodos esperados (NUEVO)
- `GET /api/repository/docs`: Listar documentos (con filtro `period_key`)
- `GET /api/repository/docs/{doc_id}`: Obtener documento
- `POST /api/repository/docs/upload`: Subir documento (acepta `period_key`)
- `PUT /api/repository/docs/{doc_id}`: Actualizar documento
- `DELETE /api/repository/docs/{doc_id}`: Eliminar documento
- `POST /api/repository/docs/{doc_id}/override`: Override de validez

#### 5.2.3 Document Matcher (`document_matcher_v1.py`)
- Matching de documentos pendientes con repositorio
- Normalización de texto robusta
- Cálculo de confianza
- Matching por tipo, empresa, trabajador, fechas
- **Matching por `period_key` determinista** (NUEVO)
- Detección de `pending_period_key` desde texto (NUEVO)
- Error explícito `MISSING_DOC_FOR_PERIOD` (NUEVO)

#### 5.2.4 Validity Calculator (`validity_calculator_v1.py`)
- Cálculo determinista de validez
- Soporte para modos: monthly, annual, fixed_end_date
- Bases: issue_date, name_date, manual
- Grace days

#### 5.2.5 Period Planner (`period_planner_v1.py`) - **NUEVO**
- Generación de períodos esperados
- Cálculo de estado (AVAILABLE/MISSING/LATE)
- Inferencia de `period_key` desde metadatos
- Soporte para MONTH, YEAR, QUARTER

#### 5.2.6 Period Migration (`period_migration_v1.py`) - **NUEVO**
- Migración de documentos existentes
- Inferencia de `period_key` desde metadatos
- Marcado de documentos con `needs_period=True`

### 5.3 Adaptadores de Plataforma (`backend/adapters/egestiona/`)

**Componentes**:

#### 5.3.1 Flows (`flows.py`)
**Endpoints principales**:
- `POST /runs/egestiona/login_and_snapshot`: Login y snapshot
- `POST /runs/egestiona/list_pending_documents_readonly`: Listar pendientes (READ-ONLY)
- `POST /runs/egestiona/match_pending_documents_readonly`: Matching (READ-ONLY)
- `POST /runs/egestiona/build_submission_plan_readonly`: Generar plan (READ-ONLY)
- `POST /runs/egestiona/execute_submission_plan_scoped`: Ejecutar plan (WRITE)

#### 5.3.2 Submission Plan (`submission_plan_headful.py`)
- Generación de plan de envío
- Matching de pendientes con documentos
- Aplicación de reglas de envío
- Dedupe por fingerprint
- Generación de evidence
- **Matching con `period_key`** (NUEVO)

#### 5.3.3 Execute Plan (`execute_plan_headful.py`)
- Ejecución determinista del plan
- Subida de documentos
- Relleno de formularios
- Registro en historial
- Generación de evidence

#### 5.3.4 Match Pending (`match_pending_headful.py`)
- Extracción de pendientes desde grid
- Matching con repositorio
- Aplicación de reglas
- Cálculo de confianza
- **Detección de `period_key` desde texto** (NUEVO)

### 5.4 Agentes Autónomos (`backend/agents/`)

#### 5.4.1 Agent Runner (`agent_runner.py`)
- Ejecución de agentes LLM
- Integración con Playwright
- Generación de planes de ejecución
- Manejo de contexto y memoria
- Reasoning Spotlight
- Planner Hints
- Outcome Judge
- Execution policies (early stop por SUCCESS)
- Manejo de credenciales en memoria

#### 5.4.2 Batch Runner (`batch_runner.py`)
- Ejecución batch de múltiples objetivos
- Gestión de errores y reintentos
- Resumen de ejecución

#### 5.4.3 CAE Batch Adapter (`cae_batch_adapter.py`)
- Adaptador específico para ejecución batch en contexto CAE
- Integración con repositorio documental
- Gestión de credenciales

### 5.5 Motor de Ejecución (`backend/executor/`)

#### 5.5.1 Runtime H4 (`runtime_h4.py`)
- Runtime principal de ejecución
- Ejecución determinista de acciones
- Manejo de errores y retries
- Redaction de datos sensibles

#### 5.5.2 Browser Controller (`browser_controller.py`)
- Control de navegador Playwright
- Gestión de páginas y frames
- Screenshots y snapshots

#### 5.5.3 Action Compiler (`action_compiler_v1.py`)
- Compilación de acciones a formato ejecutable
- Validación de acciones
- Generación de targets

### 5.6 Stores de Configuración (`backend/repository/`)

#### 5.6.1 Config Store (`config_store_v1.py`)
- Carga de configuración de organización
- Carga de personas
- Carga de plataformas
- Gestión de secrets

#### 5.6.2 Submission Rules Store (`submission_rules_store_v1.py`)
- Gestión de reglas de envío
- Matching por tokens y texto
- Habilitación/deshabilitación
- **Soporte para `RuleScopeV1` (GLOBAL/COORD)** (NUEVO)

#### 5.6.3 Submission History Store (`submission_history_store_v1.py`)
- Registro de historial de envíos
- Fingerprinting determinista
- Dedupe guardrails
- Filtrado y consulta

### 5.7 Frontend - UI Components

#### 5.7.1 HOME Dashboard (`frontend/home.html`)
**Funcionalidades**:
- Quick Links a todas las pantallas
- Configuración LLM persistente
- Monitor de estado LLM (health check)
- Botón "Revisar Pendientes CAE" (avanzado)
- Filtros: empresa, cliente/coord, plataforma, ámbito, trabajador, tipo
- Visualización de submission plan en tabla
- Links a runs y evidence

#### 5.7.2 Repository UI v3 (`frontend/repository_v3.html`) - **NUEVO COMPLETO**
**Funcionalidades**:
- **Sidebar humanizado**: Inicio, Calendario de documentos, Subir documentos, Buscar documentos, Plataformas, Catálogo de documentos, Actividad
- **Pantalla Inicio**: Cards KPI (Faltan este mes, A punto de caducar, Plataformas sin configurar, Subidas recientes)
- **Calendario de documentos**: Grid mensual con meses en español, badges OK/Falta/Tarde, panel lateral con detalle
- **Subir documentos**: Wizard guiado con drag&drop, 4 preguntas por archivo, autodetección, validaciones inline, modal de duplicados
- **Buscar documentos**: Barra de búsqueda con filtros chips
- **Plataformas**: Vista por plataforma con estado (Configurado/Parcial/Sin configurar), lista de clientes, botón "Crear configuración general"
- **Catálogo de documentos v4**: Lista con filtros avanzados, CRUD completo, drawer de crear/editar, acciones por fila
- **Actividad**: Historial de envíos
- **Hash routing**: Navegación cliente-side con hash (#)

#### 5.7.3 Chat UI (`frontend/index.html`)
- Interfaz de chat con agente
- Visualización de steps
- Respuestas estructuradas

---

## 6. APIs y Endpoints

### 6.1 Repositorio Documental (`/api/repository`)

#### Tipos de Documento
- `GET /api/repository/types` - Listar tipos
  - **Filtros nuevos**: `query`, `period`, `scope`, `active`, `page`, `page_size`, `sort`
  - **Respuesta paginada**: `TypesListResponse` si hay paginación, `List[DocumentTypeV1]` si no
- `GET /api/repository/types/{type_id}` - Obtener tipo
- `POST /api/repository/types` - Crear tipo
- `PUT /api/repository/types/{type_id}` - Actualizar tipo
- `DELETE /api/repository/types/{type_id}` - Eliminar tipo
- `PUT /api/repository/types/{type_id}/toggle_active` - Toggle activo (NUEVO)
- `POST /api/repository/types/{type_id}/duplicate` - Duplicar tipo (NUEVO)
- `GET /api/repository/types/{type_id}/expected` - Períodos esperados (NUEVO)
  - Parámetros: `company_key`, `person_key`, `months` (default: 24)

#### Documentos
- `GET /api/repository/docs` - Listar documentos
  - **Filtro nuevo**: `period_key` (para filtrar por período)
- `GET /api/repository/docs/{doc_id}` - Obtener documento
- `POST /api/repository/docs/upload` - Subir documento (multipart/form-data)
  - **Parámetro nuevo**: `period_key` (opcional, se infiere si no se proporciona)
- `PUT /api/repository/docs/{doc_id}` - Actualizar documento
- `DELETE /api/repository/docs/{doc_id}` - Eliminar documento
- `POST /api/repository/docs/{doc_id}/override` - Override de validez

### 6.2 Configuración (`/api/config`)

- `GET /api/config/org` - Obtener organización
- `GET /api/config/people` - Obtener personas
- `GET /api/config/platforms` - Obtener plataformas
- `GET /api/config/llm` - Obtener configuración LLM
- `POST /api/config/llm` - Actualizar configuración LLM
- `GET /api/health/llm` - Health check LLM

### 6.3 Reglas de Envío (`/api/repository/rules`)

- `GET /api/repository/rules` - Listar reglas
- `GET /api/repository/rules/{rule_id}` - Obtener regla
- `POST /api/repository/rules` - Crear regla
- `PUT /api/repository/rules/{rule_id}` - Actualizar regla
- `DELETE /api/repository/rules/{rule_id}` - Eliminar regla

### 6.4 Historial de Envíos (`/api/repository/history`)

- `GET /api/repository/history` - Listar historial (con filtros)
- `GET /api/repository/history/{record_id}` - Obtener registro

**Filtros**:
- `platform_key`: Plataforma
- `coord_label`: Coordinación/cliente
- `company_key`: Empresa
- `person_key`: Persona/trabajador
- `doc_id`: Documento
- `action`: planned, submitted, skipped, failed
- `limit`: Límite de resultados

### 6.5 eGestiona (`/runs/egestiona`)

#### READ-ONLY
- `POST /runs/egestiona/login_and_snapshot` - Login y snapshot
- `POST /runs/egestiona/list_pending_documents_readonly` - Listar pendientes
- `POST /runs/egestiona/match_pending_documents_readonly` - Matching
- `POST /runs/egestiona/build_submission_plan_readonly` - Generar plan

#### WRITE
- `POST /runs/egestiona/execute_submission_plan_scoped` - Ejecutar plan

**Parámetros comunes**:
- `coord`: Coordinación/cliente
- `company_key`: Empresa
- `person_key`: Persona (opcional)
- `only_target`: Solo documentos específicos
- `limit`: Límite de pendientes
- `self_test`: Modo self-test
- `self_test_doc_id`: ID de documento para self-test

### 6.6 Agentes (`/agent`)

- `POST /agent/answer` - Ejecutar agente LLM
- `POST /agent/batch` - Ejecución batch
- `POST /agent/run` - Ejecutar agente simple
- `POST /agent/run_llm` - Ejecutar agente LLM

### 6.7 Runs Viewer (`/runs`)

- `GET /runs` - Listar runs
- `GET /runs/{run_id}` - Ver run
- `GET /runs/{run_id}/file/evidence/{filename}` - Descargar evidence

### 6.8 Config Viewer (`/config`)

- `GET /config` - Ver configuración
- `GET /config/{path}` - Ver archivo de configuración

---

## 7. Modelos de Datos

### 7.1 Document Type (`DocumentTypeV1`)

```python
{
    "type_id": str,                    # ID único (ej: "T104_AUTONOMOS_RECEIPT")
    "name": str,                        # Nombre legible
    "description": Optional[str],       # Descripción
    "scope": "company" | "worker",     # Alcance
    "validity_policy": {
        "mode": "monthly" | "annual" | "fixed_end_date",
        "basis": "issue_date" | "name_date" | "manual",
        "monthly": {...},               # Si mode=monthly
        "annual": {...},                # Si mode=annual
        "fixed_end_date": {...}         # Si mode=fixed_end_date
    },
    "required_fields": List[str],       # Campos requeridos
    "platform_aliases": List[str],      # Aliases para matching
    "allow_late_submission": bool,      # Permitir envío tardío
    "late_submission_max_days": int,    # Días máximos de retraso
    "active": bool                      # Activo/inactivo
}
```

### 7.2 Document Instance (`DocumentInstanceV1`) - **ACTUALIZADO**

```python
{
    "doc_id": str,                      # UUID
    "file_name_original": str,          # Nombre original
    "stored_path": str,                 # Ruta almacenada
    "sha256": str,                      # Hash SHA256
    "type_id": str,                     # Tipo de documento
    "scope": "company" | "worker",     # Alcance
    "company_key": Optional[str],       # Empresa
    "person_key": Optional[str],        # Persona/trabajador
    "period_kind": "NONE" | "MONTH" | "YEAR" | "QUARTER",  # NUEVO
    "period_key": Optional[str],       # NUEVO: "YYYY-MM", "YYYY", "YYYY-Qn"
    "issued_at": Optional[date],        # NUEVO: Fecha de emisión
    "needs_period": bool,               # NUEVO: Si necesita asignación manual
    "extracted": {                      # Metadatos extraídos
        "issue_date": Optional[str],
        "name_date": Optional[str],
        "period_start": Optional[str],
        "period_end": Optional[str]
    },
    "computed_validity": {              # Validez calculada
        "valid_from": str,              # ISO date
        "valid_to": str,                # ISO date
        "confidence": float,             # 0.0-1.0
        "reasons": List[str]            # Razones
    },
    "validity_override": Optional[{     # Override manual
        "valid_from": str,
        "valid_to": str,
        "reason": str
    }],
    "status": "pending" | "submitted" | "expired",
    "created_at": str,                  # ISO datetime
    "updated_at": str                   # ISO datetime
}
```

### 7.3 Submission Rule (`SubmissionRuleV1`) - **ACTUALIZADO**

```python
{
    "rule_id": str,                     # ID único
    "platform_key": str,                # Plataforma (ej: "egestiona")
    "coord_label": Optional[str],        # Coordinación/cliente
    "scope": "GLOBAL" | "COORD",         # NUEVO: Alcance de la regla
    "enabled": bool,                     # Habilitada/deshabilitada
    "match": {
        "pending_text_contains": List[str],  # Tokens para matching
        "empresa_contains": List[str]         # Filtros de empresa
    },
    "document_type_id": str,            # Tipo de documento
    "form": {                           # Configuración de formulario
        "upload_field_selector": str,
        "date_fields": {
            "inicio": {"selector": str, "format": str},
            "fin": {"selector": str, "format": str, "optional": bool}
        },
        "submit_button": {"selector": str, "by_text": Optional[str]},
        "confirmation": {"text_contains": List[str]}
    }
}
```

### 7.4 Submission Record (`SubmissionRecordV1`)

```python
{
    "record_id": str,                   # ID único
    "platform_key": str,                # Plataforma
    "coord_label": str,                 # Coordinación/cliente
    "company_key": Optional[str],       # Empresa
    "person_key": Optional[str],         # Persona/trabajador
    "pending_fingerprint": str,          # Fingerprint determinista
    "pending_snapshot": dict,            # Snapshot del pending
    "doc_id": Optional[str],             # Documento asociado
    "type_id": Optional[str],          # Tipo de documento
    "file_sha256": Optional[str],        # Hash del archivo
    "action": "planned" | "submitted" | "skipped" | "failed",
    "decision": str,                     # Decisión (AUTO_SUBMIT_OK, etc.)
    "run_id": str,                      # ID de ejecución
    "evidence_path": str,                # Ruta de evidence
    "created_at": str,                   # ISO datetime
    "updated_at": str,                  # ISO datetime
    "submitted_at": Optional[str],       # ISO datetime
    "error_message": Optional[str]       # Mensaje de error
}
```

### 7.5 Period Info (`PeriodInfoV1`) - **NUEVO**

```python
{
    "period_key": str,                  # "YYYY-MM", "YYYY", "YYYY-Qn"
    "period_kind": "MONTH" | "YEAR" | "QUARTER",
    "period_start": str,                 # ISO date
    "period_end": str,                   # ISO date
    "status": "AVAILABLE" | "MISSING" | "LATE",
    "doc_id": Optional[str],            # ID del documento (si AVAILABLE)
    "doc_file_name": Optional[str],      # Nombre del archivo
    "days_late": Optional[int]          # Solo si status="LATE"
}
```

### 7.6 Execution Plan

```python
{
    "goal": str,                         # Objetivo
    "sub_goals": List[str],              # Sub-objetivos
    "steps": List[{
        "action": str,                   # Acción
        "selector": Optional[str],       # Selector
        "value": Optional[str],          # Valor
        "url": Optional[str],           # URL
        "expected_actions": List[str]     # Acciones esperadas
    }],
    "execution_profile": {...},        # Perfil de ejecución
    "context_strategies": List[str]      # Estrategias de contexto
}
```

---

## 8. Funcionalidades Implementadas

### 8.1 Repositorio Documental

✅ **Gestión de Tipos de Documento**
- CRUD completo
- Políticas de validez (monthly, annual, fixed_end_date)
- Aliases de plataforma
- Configuración de envío tardío
- **Filtrado avanzado y paginación** (NUEVO)
- **Toggle activo/inactivo** (NUEVO)
- **Duplicación de tipos** (NUEVO)

✅ **Gestión de Documentos**
- Subida de PDFs
- Extracción automática de metadatos (fechas desde nombre de archivo)
- Cálculo automático de validez
- Overrides manuales de validez
- Estado: pending, submitted, expired
- **Soporte para `period_key` y `period_kind`** (NUEVO)
- **Inferencia automática de `period_key`** (NUEVO)

✅ **Matching Inteligente**
- Matching por tipo, empresa, trabajador
- Normalización robusta de texto (sin tildes, case-insensitive)
- Cálculo de confianza
- Aplicación de reglas de envío
- **Matching por `period_key` determinista** (NUEVO)
- **Detección de `pending_period_key` desde texto** (NUEVO)
- **Error explícito `MISSING_DOC_FOR_PERIOD`** (NUEVO)

✅ **Series Temporales** (NUEVO)
- Generación de períodos esperados
- Cálculo de estado (AVAILABLE/MISSING/LATE)
- Inferencia de `period_key` desde metadatos
- Migración de documentos existentes

### 8.2 Reglas de Envío

✅ **Configuración de Reglas**
- Matching por tokens en texto pendiente
- Filtros por empresa
- Configuración de formularios (selectores, formatos de fecha)
- Habilitación/deshabilitación
- **Herencia de reglas (GLOBAL → COORD)** (NUEVO)
- **Prioridad: COORD sobre GLOBAL** (NUEVO)

### 8.3 Historial de Envíos

✅ **Trazabilidad Completa**
- Registro de todos los intentos de envío
- Fingerprinting determinista para dedupe
- Estados: planned, submitted, skipped, failed
- Filtrado y consulta
- Evidence paths

✅ **Dedupe Guardrails**
- Detección de re-subidas por fingerprint
- Decisiones: SKIP_ALREADY_SUBMITTED, SKIP_ALREADY_PLANNED
- Prevención de ejecución duplicada

### 8.4 Adaptador eGestiona

✅ **Funcionalidades READ-ONLY**
- Login y snapshot
- Listado de pendientes desde grid
- Matching de pendientes con repositorio
- Generación de submission plan
- Extracción de datos desde frames
- **Detección de `period_key` desde texto del pending** (NUEVO)

✅ **Funcionalidades WRITE**
- Ejecución de submission plan
- Subida de documentos
- Relleno de formularios
- Navegación determinista
- Generación de evidence completa

✅ **Características**
- Soporte para múltiples frames
- Selectores robustos
- Manejo de errores y retries
- Screenshots y logs
- Self-test mode

### 8.5 Agentes Autónomos

✅ **Agente LLM**
- Planificación con LLM
- Ejecución determinista
- Reasoning Spotlight
- Planner Hints
- Outcome Judge
- Integración con memoria
- Execution policies (early stop por SUCCESS)
- Manejo de credenciales en memoria

✅ **Ejecución Batch**
- Múltiples objetivos secuenciales
- Gestión de errores
- Resumen de ejecución

✅ **Características**
- Modos: live, dry_run
- Perfiles: fast, balanced, thorough
- Context strategies
- Execution policies
- Early stop por SUCCESS

### 8.6 UI y Dashboards

✅ **HOME Dashboard**
- Quick Links
- Configuración LLM persistente
- Monitor de estado LLM
- Revisión de pendientes CAE (avanzado)
- Filtros y visualización de planes

✅ **Repository UI v3** (NUEVO COMPLETO)
- Sidebar humanizado
- Pantalla Inicio con cards KPI
- Calendario de documentos con grid mensual
- Wizard de subida guiado
- Buscar documentos con filtros
- Plataformas con vista de estado
- Catálogo de documentos v4 con CRUD completo
- Actividad (historial)
- Hash routing

✅ **Chat UI**
- Interfaz de chat
- Visualización de steps
- Respuestas estructuradas

### 8.7 Normalización de Texto

✅ **Normalización Robusta**
- Case-insensitive
- Accent-insensitive (sin tildes)
- Eliminación de puntuación innecesaria
- Colapso de espacios
- Aplicado a: nombres, empresas, DNI, tipos de documento, aliases, tokens

### 8.8 Evidence y Trazabilidad

✅ **Evidence Completa**
- Screenshots por step
- Logs detallados
- JSON de planes y resultados
- Manifest de evidence
- Runs viewer

---

## 9. Flujos Principales

### 9.1 Flujo de Subida de Documento (eGestiona)

```
1. Usuario sube PDF → POST /api/repository/docs/upload
2. Sistema extrae metadatos (fechas desde nombre)
3. Sistema infiere period_key (si tipo es periódico) - NUEVO
4. Sistema calcula validez automáticamente
5. Documento queda en estado "pending"

6. Usuario ejecuta: POST /runs/egestiona/build_submission_plan_readonly
   - Sistema lista pendientes desde grid
   - Sistema detecta pending_period_key desde texto - NUEVO
   - Sistema hace matching con repositorio (por period_key si aplica) - NUEVO
   - Sistema aplica reglas de envío (con herencia GLOBAL/COORD) - NUEVO
   - Sistema genera plan con decisiones

7. Usuario revisa plan en UI

8. Usuario ejecuta: POST /runs/egestiona/execute_submission_plan_scoped
   - Sistema registra records en historial (action="planned")
   - Sistema ejecuta subida determinista
   - Sistema actualiza records (action="submitted")
   - Sistema genera evidence completa
```

### 9.2 Flujo de Matching

```
1. Extracción de pendientes desde grid
2. Para cada pending:
   a. Detección de pending_period_key desde texto (NUEVO)
   b. Normalización de texto (tipo_doc, elemento, empresa)
   c. Búsqueda de tipo de documento por aliases
   d. Búsqueda de documento en repositorio:
      - Por type_id
      - Por empresa (normalizada)
      - Por trabajador (normalizada)
      - Por period_key (si aplica) - NUEVO
      - Por fechas (si aplica)
   e. Aplicación de reglas de envío (con herencia) - NUEVO
   f. Cálculo de confianza
   g. Decisión: AUTO_SUBMIT_OK, REVIEW_REQUIRED, NO_MATCH, MISSING_DOC_FOR_PERIOD, SKIP_* - NUEVO
```

### 9.3 Flujo de Dedupe

```
1. Cálculo de fingerprint determinista:
   - Campos: platform_key, coord_label, tipo_doc, elemento, empresa, trabajador
   - Normalización de texto
   - Hash SHA256

2. Consulta de historial:
   - Buscar records con mismo fingerprint
   - Verificar action="submitted"
   - Si existe → decision="SKIP_ALREADY_SUBMITTED"

3. Prevención de ejecución:
   - Si SKIP_ALREADY_SUBMITTED → no ejecutar
   - Registrar en historial con action="skipped"
```

### 9.4 Flujo de Agente LLM

```
1. Usuario envía goal → POST /agent/answer
2. Sistema genera Reasoning Spotlight
3. Sistema genera Execution Plan (si plan_only)
4. Sistema genera Planner Hints (si plan_only)
5. Usuario confirma ejecución
6. Sistema ejecuta steps deterministas:
   - Navegación
   - Acciones (fill, click, select, upload)
   - Generación de acciones desde DOM (si necesario)
   - Múltiples fases si hay cambios de URL/DOM
7. Sistema ejecuta run_llm_task_with_answer (si no hubo policy_stop)
8. Sistema genera Outcome Judge Report
9. Sistema devuelve respuesta final
```

### 9.5 Flujo de Series Temporales (NUEVO)

```
1. Usuario consulta períodos esperados → GET /api/repository/types/{type_id}/expected
2. Sistema genera períodos basándose en:
   - Tipo de documento (period_kind)
   - Sujeto (company_key/person_key)
   - Rango (months_back)
3. Para cada período:
   a. Busca documento con period_key exacto
   b. Calcula estado:
      - AVAILABLE si existe y está dentro de validez
      - MISSING si no existe
      - LATE si existe pero está fuera de validez (con grace_days)
4. Sistema devuelve lista de PeriodInfoV1
```

---

## 10. UI v3 - Repositorio Documental

### 10.1 Estructura General

La UI v3 está implementada en `frontend/repository_v3.html` y utiliza:

- **Hash routing**: Navegación cliente-side con hash (#inicio, #calendario, #subir, #buscar, #plataformas, #catalogo, #actividad)
- **Lenguaje humano**: OK/Falta/Tarde en lugar de AVAILABLE/MISSING/LATE, meses en español
- **Flujo por tareas**: Calendario → Subir, Catálogo → Ver calendario/Subir documento
- **Autocompletado**: Para tipos, personas, empresas
- **Validaciones inline**: Errores claros y visibles
- **Modales y drawers**: Para crear/editar/duplicar

### 10.2 Pantallas Implementadas

#### 10.2.1 Inicio
- Cards KPI: "Faltan este mes", "A punto de caducar", "Plataformas sin configurar", "Subidas recientes"
- Lista de acciones rápidas (preparada para generar desde expected periods)
- Tabla de subidas recientes

#### 10.2.2 Calendario de Documentos
- Selectores: "¿Qué documento?" y "¿De quién / qué empresa?" (autocomplete)
- Grid calendario mensual con meses en español ("Mayo 2023", "Junio 2023")
- Badges de estado: OK / Falta / Tarde
- Panel lateral al click con detalle del mes
- Botón "Subir" en meses "Falta"
- Acción "Subir este mes" pre-llena wizard

#### 10.2.3 Subir Documentos
- Drag&drop multiarchivo
- 4 preguntas por archivo:
  1. ¿Qué documento es? (autocomplete)
  2. ¿De quién / empresa? (autocomplete según scope)
  3. ¿De qué mes/año? (month picker / year picker según period_kind)
  4. (Opcional) Fecha de emisión
- Autodetección desde filename con badges "Detectado"
- Validaciones claras: "El mes es obligatorio", "El trabajador es obligatorio"
- Modal de duplicados con 3 opciones: Cancelar, Guardar como versión, Reemplazar

#### 10.2.4 Buscar Documentos
- Barra de búsqueda
- Filtros chips: documento, sujeto, mes, estado
- Resultados con botón "Ir al calendario"

#### 10.2.5 Plataformas
- Vista por plataforma con cards
- Estado: Configurado / Parcial / Sin configurar (semáforo)
- "Clientes cubiertos: X/Y"
- Lista de clientes con "Regla usada: específica / general / ninguna"
- Botón "Arreglar" para clientes sin regla
- Botón "Crear configuración general" (crea reglas GLOBAL)

#### 10.2.6 Catálogo de Documentos v4
- **Barra superior**: Título, botón "+ Crear documento", botones Exportar/Importar (stub)
- **Filtros avanzados**:
  - Search box principal
  - Filtros multi-select: Periodicidad, Aplica a, Estado
  - Ordenación: Nombre A→Z, Código, Periodicidad, Relevancia
  - Botón "Limpiar filtros"
  - Contador de resultados
- **Tabla de resultados**:
  - Checkbox para selección múltiple
  - Columnas: Documento, Cada cuánto, Aplica a, Activo (toggle), Cómo suele llamarse, Acciones
  - Paginación
- **Drawer de crear/editar**:
  - Campos humanizados (¿Cada cuánto se pide?, ¿A quién aplica?, etc.)
  - Editor de aliases (chips)
  - Botones: Cancelar, Guardar, Guardar y ver calendario
- **Acciones por fila**:
  - Editar, Duplicar, Ver calendario, Subir documento, Ver reglas, Desactivar/Activar, Borrar

#### 10.2.7 Actividad
- Historial de envíos
- Filtros y visualización

### 10.3 Integraciones

- **Prefill desde Catálogo**: "Ver calendario" y "Subir documento" abren con tipo preseleccionado
- **Hash routing**: Soporte para navegación directa con hash (#catalogo, #calendario, etc.)
- **Compatibilidad**: Mantiene compatibilidad con rutas existentes

---

## 11. Series Temporales (Period-Based Documents)

### 11.1 Objetivo

Soportar documentos periódicos (mensuales/anuales/etc.) como series temporales, permitiendo que el agente seleccione determinísticamente el documento del período exacto sin heurísticas.

### 11.2 Cambios Implementados

#### 11.2.1 Extensión del Modelo
- `period_kind: PeriodKindV1`: NONE, MONTH, YEAR, QUARTER
- `period_key: Optional[str]`: "YYYY-MM", "YYYY", "YYYY-Qn"
- `issued_at: Optional[date]`: Fecha de emisión
- `needs_period: bool`: Si necesita asignación manual

#### 11.2.2 Servicio de Planificación
- `PeriodPlannerV1`: Genera períodos esperados y calcula estado
- Endpoint: `GET /api/repository/types/{type_id}/expected`

#### 11.2.3 Migración
- `PeriodMigrationV1`: Migra documentos existentes
- Script: `scripts/migrate_period_keys.py`

#### 11.2.4 Matching
- Detección de `pending_period_key` desde texto
- Búsqueda por `period_key` exacto
- Error explícito `MISSING_DOC_FOR_PERIOD`

### 11.3 Uso

```python
# Generar períodos esperados
GET /api/repository/types/T104_AUTONOMOS_RECEIPT/expected?person_key=Emilio&months=24

# Buscar documento por período
GET /api/repository/docs?type_id=T104_AUTONOMOS_RECEIPT&person_key=Emilio&period_key=2023-05
```

---

## 12. Configuración y Despliegue

### 12.1 Configuración Inicial

**Archivos de configuración** (`data/refs/`):
- `org.json`: Organización (empresas)
- `people.json`: Personas/trabajadores
- `platforms.json`: Plataformas CAE
- `secrets.json`: Credenciales (opcional, puede estar en memoria)
- `llm_config.json`: Configuración LLM

**Estructura mínima**:
```json
// org.json
{
    "companies": [
        {"key": "F63161988", "name": "Empresa Demo"}
    ]
}

// people.json
{
    "people": [
        {"key": "emilio", "name": "Emilio", "dni": "12345678A"}
    ]
}

// platforms.json
{
    "platforms": [
        {
            "key": "egestiona",
            "name": "eGestiona",
            "base_url": "https://portal.example.com"
        }
    ]
}
```

### 12.2 Inicialización

```bash
# Instalar dependencias
pip install -r requirements.txt

# Instalar Playwright
playwright install chromium

# Asegurar estructura de directorios
python -c "from backend.repository.data_bootstrap_v1 import ensure_data_layout; from backend.config import DATA_DIR; ensure_data_layout(DATA_DIR)"

# Arrancar servidor
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

### 12.3 Variables de Entorno

- `OPEN_UI_ON_START=1`: Abrir navegador automáticamente al iniciar
- Variables de configuración LLM (opcional, se puede configurar desde UI)

### 12.4 Estructura de Datos

El sistema crea automáticamente la estructura de directorios en `data/`:
- `refs/`: Configuración
- `repository/`: Repositorio documental
- `runs/`: Ejecuciones
- `tmp/`: Temporales

### 12.5 Migración de Períodos

```bash
# Migrar documentos existentes a period_key
python scripts/migrate_period_keys.py [--dry-run]
```

---

## 13. Testing y Calidad

### 13.1 Tests Implementados

- Tests unitarios en `backend/tests/`
- Tests de integración para adaptadores
- Tests de matching y normalización
- Tests de cálculo de validez
- Tests de planificación de períodos

### 13.2 Pruebas E2E

**Proceso de pruebas E2E**:
1. Arrancar servidor en puerto 8000
2. Verificar endpoints con `curl`
3. Probar UI en navegador
4. Verificar Console y Network
5. Documentar resultados en `docs/E2E_REPORT_*.md`

**Reportes E2E existentes**:
- `docs/E2E_REPORT_repo_ui_v3.md`: UI v3 completa
- `docs/E2E_REPORT_repo_catalog_v4.md`: Catálogo v4
- `docs/E2E_REPORT_repo_timeseries_v1.md`: Series temporales
- `docs/E2E_REPORT_autonomos_match_v1.md`: Matching de autónomos

**Checklist E2E típico**:
- [ ] Backend responde 200 en todos los endpoints
- [ ] UI carga sin errores JS
- [ ] CRUD funciona en Repository UI
- [ ] Matching funciona correctamente
- [ ] Ejecución de plan funciona
- [ ] Evidence se genera correctamente
- [ ] Series temporales funcionan correctamente
- [ ] Herencia de reglas funciona correctamente

### 13.3 Calidad de Código

- **Validación**: Pydantic para todos los modelos
- **Error handling**: Try-catch robusto en todos los endpoints
- **Logging**: Logging estructurado
- **Atomic writes**: Escrituras atómicas para integridad
- **Normalización**: Normalización consistente de texto

---

## 14. Estado Actual y Roadmap

### 14.1 Estado Actual (Diciembre 2025)

✅ **Completado**:
- Repositorio documental completo (tipos, documentos, reglas, historial)
- **Series temporales (period-based documents)** (NUEVO)
- **UI v3 completa con lenguaje humano** (NUEVO)
- **Catálogo de documentos v4 con CRUD completo** (NUEVO)
- **Herencia de reglas (GLOBAL/COORD)** (NUEVO)
- Adaptador eGestiona (READ-ONLY y WRITE)
- Agentes autónomos (LLM, batch)
- Normalización robusta de texto
- Dedupe guardrails
- Evidence completa
- Configuración LLM persistente
- Matching determinista por `period_key`

🔄 **En progreso**:
- Mejoras en matching
- Optimizaciones de performance
- Tests adicionales

📋 **Pendiente**:
- Adaptadores para otras plataformas CAE
- Mejoras en UI/UX
- Documentación adicional
- Optimizaciones de LLM

### 14.2 Roadmap

**Corto plazo**:
- Mejoras en matching y confianza
- Optimizaciones de performance
- Tests adicionales
- Completar pruebas E2E pendientes

**Medio plazo**:
- Adaptadores para más plataformas
- Mejoras en UI/UX
- Analytics y métricas
- Optimizaciones de series temporales

**Largo plazo**:
- Escalabilidad
- Integraciones adicionales
- Machine learning para matching

---

## 15. Partes en Desarrollo

### 15.1 UI v3 - Mejoras Pendientes

- **Inicio**: Generar acciones rápidas desde expected periods
- **Calendario**: Mejorar visualización de períodos LATE
- **Subir**: Completar validaciones y autodetección
- **Buscar**: Implementar filtros avanzados
- **Plataformas**: Completar editor de reglas
- **Actividad**: Mejorar visualización de historial

### 15.2 Series Temporales - Mejoras Pendientes

- **Migración**: Completar migración de todos los documentos existentes
- **Inferencia**: Mejorar inferencia de `period_key` desde metadatos
- **UI**: Completar vista de cobertura por períodos en Calendario

### 15.3 Matching - Mejoras Pendientes

- **Confianza**: Mejorar cálculo de confianza
- **Fallbacks**: Mejorar fallbacks cuando no hay match exacto
- **Reglas**: Completar autogeneración de reglas GLOBAL

### 15.4 Testing - Pendiente

- **E2E**: Completar pruebas E2E para todas las pantallas
- **Unitarios**: Aumentar cobertura de tests unitarios
- **Integración**: Tests de integración para flujos completos

---

## 16. Notas Técnicas Importantes

### 16.1 Normalización de Texto

**CRÍTICO**: Todas las comparaciones de texto deben usar normalización robusta:
- Case-insensitive
- Accent-insensitive (sin tildes)
- Eliminación de puntuación innecesaria
- Colapso de espacios

**Implementación**: `backend/shared/text_normalizer.py`

### 16.2 Atomic Writes

Todas las escrituras a JSON usan patrón atomic:
1. Escribir a archivo temporal
2. Renombrar a archivo final
3. Esto previene corrupción en caso de crash

### 16.3 Fingerprinting

Fingerprints son deterministas y se calculan así:
1. Normalizar campos relevantes
2. Concatenar en orden consistente
3. Hash SHA256
4. Hex string

### 16.4 Evidence

Cada ejecución genera:
- `submission_plan.json`: Plan generado
- `match_results.json`: Resultados de matching
- `pending_items.json`: Pendientes extraídos
- Screenshots por step
- Logs detallados
- Manifest con metadatos

### 16.5 Execution Modes

- `live`: Ejecución real (WRITE)
- `dry_run`: Simulación (READ-ONLY)

### 16.6 Execution Profiles

- `fast`: Ejecución rápida, menos validaciones
- `balanced`: Balance entre velocidad y robustez
- `thorough`: Ejecución exhaustiva, más validaciones

### 16.7 Period Keys

- **Formato**: "YYYY-MM" (MONTH), "YYYY" (YEAR), "YYYY-Qn" (QUARTER)
- **Inferencia**: Desde `issue_date`, `name_date`, `filename`
- **Búsqueda**: Exacta, no aproximada

### 16.8 Herencia de Reglas

- **Prioridad**: COORD sobre GLOBAL
- **Aplicación**: Si no hay regla COORD, se usa GLOBAL
- **Scope**: `RuleScopeV1.GLOBAL` aplica a todas las coords, `RuleScopeV1.COORD` solo a la coord específica

---

## 17. Troubleshooting

### 17.1 Problemas Comunes

**UI se queda en "Cargando..."**:
- Verificar Console para errores JS
- Verificar Network para requests fallidos
- Verificar que backend está corriendo
- Verificar que endpoints responden 200
- Hacer hard refresh (Ctrl+F5)

**Matching no funciona**:
- Verificar normalización de texto
- Verificar que reglas están habilitadas
- Verificar que tipos de documento tienen aliases correctos
- Verificar logs de matching
- Verificar que `period_key` está correcto (si aplica)

**Ejecución falla**:
- Verificar evidence para screenshots
- Verificar logs detallados
- Verificar selectores en reglas
- Verificar credenciales

**Series temporales no funcionan**:
- Verificar que tipo tiene `validity_policy.mode=monthly` (o annual)
- Verificar que documentos tienen `period_key` asignado
- Verificar que `period_key` tiene formato correcto
- Ejecutar migración si documentos existentes no tienen `period_key`

### 17.2 Debugging

**Logs**:
- Backend: Logs en consola
- Frontend: Console del navegador
- Evidence: Logs en `data/runs/{run_id}/evidence/`

**Verificación de endpoints**:
```bash
curl http://127.0.0.1:8000/api/repository/types
curl http://127.0.0.1:8000/api/repository/docs
curl http://127.0.0.1:8000/health
```

---

## 18. Referencias

### 18.1 Documentación Adicional

- `docs/architecture.md`: Arquitectura detallada
- `docs/document_repository_v1.md`: Repositorio documental
- `docs/submission_history_v1.md`: Historial de envíos
- `docs/dashboard_review_pending.md`: Dashboard de revisión
- `docs/home_ui.md`: HOME UI
- `docs/executor_contract_v1.md`: Contratos del ejecutor
- `docs/REPO_TIME_SERIES_DESIGN.md`: Diseño de series temporales
- `docs/E2E_REPORT_*.md`: Reportes E2E

### 18.2 Archivos de Configuración

- `backend/config.py`: Configuración principal
- `data/refs/*.json`: Configuración de datos

### 18.3 Código Clave

- `backend/app.py`: Aplicación principal
- `backend/adapters/egestiona/flows.py`: Flujos eGestiona
- `backend/repository/document_repository_routes.py`: Rutas del repositorio
- `backend/agents/agent_runner.py`: Runner de agentes
- `backend/repository/period_planner_v1.py`: Planificación de períodos
- `backend/repository/rule_based_matcher_v1.py`: Matching con herencia
- `frontend/repository_v3.html`: UI v3 completa

---

## 19. Contacto y Soporte

Para preguntas técnicas o soporte, consultar:
- Documentación en `docs/`
- Código fuente con comentarios
- Logs y evidence de ejecuciones
- Tests como ejemplos de uso
- Reportes E2E para casos de uso reales

---

**Fin del Handoff Técnico**

*Última actualización: 30 de Diciembre 2025*




















