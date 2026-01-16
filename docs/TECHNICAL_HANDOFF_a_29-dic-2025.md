# Handoff Técnico Exhaustivo - CometLocal

**Fecha**: Diciembre 2025  
**Versión**: 1.0  
**Estado**: Producción (eGestiona Kern - READ-ONLY y WRITE scoped funcionando)

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
10. [Configuración y Despliegue](#configuración-y-despliegue)
11. [Testing y Calidad](#testing-y-calidad)
12. [Estado Actual y Roadmap](#estado-actual-y-roadmap)

---

## 1. Visión General

**CometLocal** es una plataforma de automatización para la gestión documental en portales CAE (Centros de Atención al Empleado). El sistema permite:

- **Automatización de subidas**: Subida automática de documentos a portales CAE (eGestiona, etc.)
- **Repositorio documental**: Gestión centralizada de tipos de documentos, instancias y metadatos
- **Matching inteligente**: Asociación automática de documentos pendientes con documentos del repositorio
- **Reglas de envío**: Configuración de reglas para matching y envío automático
- **Historial de envíos**: Trazabilidad completa de todas las subidas realizadas
- **Agentes autónomos**: Agentes LLM para navegación y ejecución de tareas complejas

### Características Principales

- ✅ **Backend FastAPI** con arquitectura modular
- ✅ **Playwright** para automatización de navegador
- ✅ **Repositorio documental** con cálculo automático de validez
- ✅ **Adaptadores por plataforma** (eGestiona implementado)
- ✅ **UI completa** para gestión y monitoreo
- ✅ **Evidencia completa** por ejecución (runs)
- ✅ **Normalización de texto** robusta (sin tildes, case-insensitive)
- ✅ **Dedupe guardrails** para evitar re-subidas

---

## 2. Arquitectura del Sistema

### 2.1 Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   HOME   │  │  CHAT     │  │ REPOSITORY│  │  TRAINING │  │
│  │ Dashboard│  │   UI      │  │    UI     │  │    UI     │  │
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
│  │  - Rules     │  │  - Targets    │  │              │     │
│  │  - History   │  │              │  │              │     │
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
- **DHTMLX Grid**: (mencionado en código, posible uso futuro)

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
│   ├── repository.html           # Repositorio documental UI
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
├── tests/                        # Tests
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

**Endpoints principales**:
- `POST /agent/answer`: Ejecución de agente LLM
- `POST /agent/batch`: Ejecución batch
- `POST /chat`: Chat simple
- `GET /api/config/llm`: Configuración LLM
- `POST /api/config/llm`: Actualizar configuración LLM
- `GET /api/health/llm`: Health check LLM

### 5.2 Repositorio Documental (`backend/repository/`)

**Componentes**:

#### 5.2.1 Document Repository Store (`document_repository_store_v1.py`)
- Gestión de tipos de documento (`types.json`)
- Gestión de instancias de documentos
- Cálculo automático de validez
- Overrides de validez
- Atomic writes para integridad

#### 5.2.2 Document Repository Routes (`document_repository_routes.py`)
**Endpoints**:
- `GET /api/repository/types`: Listar tipos
- `GET /api/repository/types/{type_id}`: Obtener tipo
- `POST /api/repository/types`: Crear tipo
- `PUT /api/repository/types/{type_id}`: Actualizar tipo
- `DELETE /api/repository/types/{type_id}`: Eliminar tipo
- `GET /api/repository/docs`: Listar documentos
- `GET /api/repository/docs/{doc_id}`: Obtener documento
- `POST /api/repository/docs`: Subir documento
- `PUT /api/repository/docs/{doc_id}`: Actualizar documento
- `DELETE /api/repository/docs/{doc_id}`: Eliminar documento
- `POST /api/repository/docs/{doc_id}/override`: Override de validez

#### 5.2.3 Document Matcher (`document_matcher_v1.py`)
- Matching de documentos pendientes con repositorio
- Normalización de texto robusta
- Cálculo de confianza
- Matching por tipo, empresa, trabajador, fechas

#### 5.2.4 Validity Calculator (`validity_calculator_v1.py`)
- Cálculo determinista de validez
- Soporte para modos: monthly, annual, fixed_end_date
- Bases: issue_date, name_date, manual
- Grace days

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

### 5.4 Agentes Autónomos (`backend/agents/`)

#### 5.4.1 Agent Runner (`agent_runner.py`)
- Ejecución de agentes LLM
- Integración con Playwright
- Generación de planes de ejecución
- Manejo de contexto y memoria
- Reasoning Spotlight
- Planner Hints
- Outcome Judge

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

#### 5.7.2 Repository UI (`frontend/repository.html`)
**Funcionalidades**:
- Gestión de tipos de documento (CRUD)
- Gestión de documentos (CRUD)
- Gestión de reglas de envío (CRUD)
- Visualización de historial (READ-ONLY)
- Filtros y búsqueda
- Modales para crear/editar/duplicar

#### 5.7.3 Chat UI (`frontend/index.html`)
- Interfaz de chat con agente
- Visualización de steps
- Respuestas estructuradas

---

## 6. APIs y Endpoints

### 6.1 Repositorio Documental (`/api/repository`)

#### Tipos de Documento
- `GET /api/repository/types` - Listar tipos
- `GET /api/repository/types/{type_id}` - Obtener tipo
- `POST /api/repository/types` - Crear tipo
- `PUT /api/repository/types/{type_id}` - Actualizar tipo
- `DELETE /api/repository/types/{type_id}` - Eliminar tipo

#### Documentos
- `GET /api/repository/docs` - Listar documentos
- `GET /api/repository/docs/{doc_id}` - Obtener documento
- `POST /api/repository/docs` - Subir documento (multipart/form-data)
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

### 7.2 Document Instance (`DocumentInstanceV1`)

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

### 7.3 Submission Rule (`SubmissionRuleV1`)

```python
{
    "rule_id": str,                     # ID único
    "platform_key": str,                # Plataforma (ej: "egestiona")
    "coord_label": Optional[str],        # Coordinación/cliente
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
    "type_id": Optional[str],            # Tipo de documento
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

### 7.5 Execution Plan

```python
{
    "goal": str,                         # Objetivo
    "sub_goals": List[str],              # Sub-objetivos
    "steps": List[{
        "action": str,                   # Acción
        "selector": Optional[str],       # Selector
        "value": Optional[str],          # Valor
        "url": Optional[str],            # URL
        "expected_actions": List[str]     # Acciones esperadas
    }],
    "execution_profile": {...},          # Perfil de ejecución
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

✅ **Gestión de Documentos**
- Subida de PDFs
- Extracción automática de metadatos (fechas desde nombre de archivo)
- Cálculo automático de validez
- Overrides manuales de validez
- Estado: pending, submitted, expired

✅ **Matching Inteligente**
- Matching por tipo, empresa, trabajador
- Normalización robusta de texto (sin tildes, case-insensitive)
- Cálculo de confianza
- Aplicación de reglas de envío

### 8.2 Reglas de Envío

✅ **Configuración de Reglas**
- Matching por tokens en texto pendiente
- Filtros por empresa
- Configuración de formularios (selectores, formatos de fecha)
- Habilitación/deshabilitación

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

✅ **Repository UI**
- Gestión completa de tipos, documentos, reglas, historial
- Modales para CRUD
- Filtros y búsqueda
- Manejo robusto de errores

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
1. Usuario sube PDF → POST /api/repository/docs
2. Sistema extrae metadatos (fechas desde nombre)
3. Sistema calcula validez automáticamente
4. Documento queda en estado "pending"

5. Usuario ejecuta: POST /runs/egestiona/build_submission_plan_readonly
   - Sistema lista pendientes desde grid
   - Sistema hace matching con repositorio
   - Sistema aplica reglas de envío
   - Sistema genera plan con decisiones

6. Usuario revisa plan en UI

7. Usuario ejecuta: POST /runs/egestiona/execute_submission_plan_scoped
   - Sistema registra records en historial (action="planned")
   - Sistema ejecuta subida determinista
   - Sistema actualiza records (action="submitted")
   - Sistema genera evidence completa
```

### 9.2 Flujo de Matching

```
1. Extracción de pendientes desde grid
2. Para cada pending:
   a. Normalización de texto (tipo_doc, elemento, empresa)
   b. Búsqueda de tipo de documento por aliases
   c. Búsqueda de documento en repositorio:
      - Por tipo_id
      - Por empresa (normalizada)
      - Por trabajador (normalizada)
      - Por fechas (si aplica)
   d. Aplicación de reglas de envío
   e. Cálculo de confianza
   f. Decisión: AUTO_SUBMIT_OK, REVIEW_REQUIRED, NO_MATCH, SKIP_*
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

---

## 10. Configuración y Despliegue

### 10.1 Configuración Inicial

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

### 10.2 Inicialización

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

### 10.3 Variables de Entorno

- `OPEN_UI_ON_START=1`: Abrir navegador automáticamente al iniciar
- Variables de configuración LLM (opcional, se puede configurar desde UI)

### 10.4 Estructura de Datos

El sistema crea automáticamente la estructura de directorios en `data/`:
- `refs/`: Configuración
- `repository/`: Repositorio documental
- `runs/`: Ejecuciones
- `tmp/`: Temporales

---

## 11. Testing y Calidad

### 11.1 Tests Implementados

- Tests unitarios en `backend/tests/`
- Tests de integración para adaptadores
- Tests de matching y normalización
- Tests de cálculo de validez

### 11.2 Pruebas E2E

**Proceso de pruebas E2E**:
1. Arrancar servidor en puerto 8000
2. Verificar endpoints con `curl`
3. Probar UI en navegador
4. Verificar Console y Network
5. Documentar resultados en `docs/E2E_REPORT_*.md`

**Checklist E2E típico**:
- [ ] Backend responde 200 en todos los endpoints
- [ ] UI carga sin errores JS
- [ ] CRUD funciona en Repository UI
- [ ] Matching funciona correctamente
- [ ] Ejecución de plan funciona
- [ ] Evidence se genera correctamente

### 11.3 Calidad de Código

- **Validación**: Pydantic para todos los modelos
- **Error handling**: Try-catch robusto en todos los endpoints
- **Logging**: Logging estructurado
- **Atomic writes**: Escrituras atómicas para integridad
- **Normalización**: Normalización consistente de texto

---

## 12. Estado Actual y Roadmap

### 12.1 Estado Actual (Diciembre 2025)

✅ **Completado**:
- Repositorio documental completo (tipos, documentos, reglas, historial)
- Adaptador eGestiona (READ-ONLY y WRITE)
- UI completa (HOME, Repository, Chat)
- Agentes autónomos (LLM, batch)
- Normalización robusta de texto
- Dedupe guardrails
- Evidence completa
- Configuración LLM persistente

🔄 **En progreso**:
- Mejoras en matching
- Optimizaciones de performance
- Tests adicionales

📋 **Pendiente**:
- Adaptadores para otras plataformas CAE
- Mejoras en UI/UX
- Documentación adicional
- Optimizaciones de LLM

### 12.2 Roadmap

**Corto plazo**:
- Mejoras en matching y confianza
- Optimizaciones de performance
- Tests adicionales

**Medio plazo**:
- Adaptadores para más plataformas
- Mejoras en UI/UX
- Analytics y métricas

**Largo plazo**:
- Escalabilidad
- Integraciones adicionales
- Machine learning para matching

---

## 13. Notas Técnicas Importantes

### 13.1 Normalización de Texto

**CRÍTICO**: Todas las comparaciones de texto deben usar normalización robusta:
- Case-insensitive
- Accent-insensitive (sin tildes)
- Eliminación de puntuación innecesaria
- Colapso de espacios

**Implementación**: `backend/shared/text_normalizer.py`

### 13.2 Atomic Writes

Todas las escrituras a JSON usan patrón atomic:
1. Escribir a archivo temporal
2. Renombrar a archivo final
3. Esto previene corrupción en caso de crash

### 13.3 Fingerprinting

Fingerprints son deterministas y se calculan así:
1. Normalizar campos relevantes
2. Concatenar en orden consistente
3. Hash SHA256
4. Hex string

### 13.4 Evidence

Cada ejecución genera:
- `submission_plan.json`: Plan generado
- `match_results.json`: Resultados de matching
- `pending_items.json`: Pendientes extraídos
- Screenshots por step
- Logs detallados
- Manifest con metadatos

### 13.5 Execution Modes

- `live`: Ejecución real (WRITE)
- `dry_run`: Simulación (READ-ONLY)

### 13.6 Execution Profiles

- `fast`: Ejecución rápida, menos validaciones
- `balanced`: Balance entre velocidad y robustez
- `thorough`: Ejecución exhaustiva, más validaciones

---

## 14. Troubleshooting

### 14.1 Problemas Comunes

**UI se queda en "Cargando..."**:
- Verificar Console para errores JS
- Verificar Network para requests fallidos
- Verificar que backend está corriendo
- Verificar que endpoints responden 200

**Matching no funciona**:
- Verificar normalización de texto
- Verificar que reglas están habilitadas
- Verificar que tipos de documento tienen aliases correctos
- Verificar logs de matching

**Ejecución falla**:
- Verificar evidence para screenshots
- Verificar logs detallados
- Verificar selectores en reglas
- Verificar credenciales

### 14.2 Debugging

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

## 15. Referencias

### 15.1 Documentación Adicional

- `docs/architecture.md`: Arquitectura detallada
- `docs/document_repository_v1.md`: Repositorio documental
- `docs/submission_history_v1.md`: Historial de envíos
- `docs/dashboard_review_pending.md`: Dashboard de revisión
- `docs/home_ui.md`: HOME UI
- `docs/executor_contract_v1.md`: Contratos del ejecutor

### 15.2 Archivos de Configuración

- `backend/config.py`: Configuración principal
- `data/refs/*.json`: Configuración de datos

### 15.3 Código Clave

- `backend/app.py`: Aplicación principal
- `backend/adapters/egestiona/flows.py`: Flujos eGestiona
- `backend/repository/document_repository_routes.py`: Rutas del repositorio
- `backend/agents/agent_runner.py`: Runner de agentes

---

## 16. Contacto y Soporte

Para preguntas técnicas o soporte, consultar:
- Documentación en `docs/`
- Código fuente con comentarios
- Logs y evidence de ejecuciones
- Tests como ejemplos de uso

---

**Fin del Handoff Técnico**

*Última actualización: Diciembre 2025*

