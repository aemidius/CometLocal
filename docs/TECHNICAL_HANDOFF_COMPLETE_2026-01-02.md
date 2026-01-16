# Handoff Técnico Exhaustivo - CometLocal

**Fecha**: 2 de Enero 2026  
**Versión**: 3.0 (Actualización completa)  
**Estado**: Producción (eGestiona Kern - READ-ONLY y WRITE scoped funcionando) + UI v3 completa + Repositorio con series temporales + Configuración de ruta + Validity Start Date

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
12. [Configuración del Repositorio](#configuración-del-repositorio)
13. [Validity Start Date (Fecha de Inicio de Vigencia)](#validity-start-date-fecha-de-inicio-de-vigencia)
14. [Configuración y Despliegue](#configuración-y-despliegue)
15. [Testing y Calidad](#testing-y-calidad)
16. [Estado Actual y Roadmap](#estado-actual-y-roadmap)
17. [Partes en Desarrollo](#partes-en-desarrollo)

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
- **Configuración flexible**: Ruta del repositorio configurable desde UI
- **Validity Start Date**: Fecha de inicio de vigencia independiente de fecha de emisión

### Características Principales

- ✅ **Backend FastAPI** con arquitectura modular
- ✅ **Playwright** para automatización de navegador
- ✅ **Repositorio documental** con cálculo automático de validez
- ✅ **Adaptadores por plataforma** (eGestiona implementado)
- ✅ **UI completa** para gestión y monitoreo
- ✅ **Evidencia completa** por ejecución (runs)
- ✅ **Normalización de texto** robusta (sin tildes, case-insensitive)
- ✅ **Configuración de ruta** del repositorio desde UI
- ✅ **Validity Start Date** configurable por tipo de documento

---

## 2. Arquitectura del Sistema

### 2.1 Componentes Principales

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                       │
│  - home.html (Dashboard)                                    │
│  - index.html (Chat UI)                                     │
│  - repository_v3.html (Repositorio UI completa)            │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/REST
┌──────────────────────▼──────────────────────────────────────┐
│              Backend FastAPI (Python)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Routes                                           │  │
│  │  - /api/repository/* (Repositorio)                   │  │
│  │  - /api/repository/settings (Configuración)          │  │
│  │  - /api/egestiona/* (eGestiona flows)                │  │
│  │  - /api/agents/* (Agentes LLM)                       │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Core Services                                        │  │
│  │  - DocumentRepositoryStoreV1                         │  │
│  │  - PeriodPlannerV1                                    │  │
│  │  - ValidityCalculatorV1                               │  │
│  │  - DocumentMatcherV1                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Persistencia (JSON + Filesystem)               │
│  - data/repository/types/types.json                         │
│  - data/repository/settings.json (NUEVO)                    │
│  - data/repository/docs/*.pdf                               │
│  - data/repository/meta/*.json                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Flujo de Datos

1. **Subida de Documentos**: Frontend → Backend → Filesystem + JSON
2. **Configuración**: Frontend → Backend → `settings.json`
3. **Cálculo de Validez**: Backend calcula usando `validity_start_date` como base
4. **Matching**: Backend compara documentos con pendientes
5. **Envío**: Backend → Playwright → Portal CAE

---

## 3. Stack Tecnológico

- **Backend**: Python 3.11+, FastAPI, Pydantic v2
- **Frontend**: HTML5, JavaScript (vanilla), CSS3
- **Automatización**: Playwright
- **Persistencia**: JSON (tipos, metadatos) + Filesystem (PDFs)
- **Validación**: Pydantic models con validadores personalizados
- **Testing**: Playwright E2E tests

---

## 4. Estructura del Proyecto

```
CometLocal/
├── backend/                     # Backend FastAPI
│   ├── repository/              # Repositorio documental
│   │   ├── document_repository_routes.py
│   │   ├── document_repository_store_v1.py
│   │   ├── settings_routes.py  # NUEVO: Configuración de ruta
│   │   ├── period_planner_v1.py
│   │   ├── period_migration_v1.py
│   │   ├── validity_calculator_v1.py
│   │   ├── date_parser_v1.py
│   │   └── ...
│   ├── shared/                  # Modelos y utilidades compartidas
│   │   ├── document_repository_v1.py  # Actualizado: validity_start_mode
│   │   ├── executor_contracts_v1.py
│   │   └── ...
│   ├── app.py                  # Aplicación FastAPI principal
│   └── config.py              # Configuración
├── frontend/                   # UI estática
│   ├── repository_v3.html     # UI v3 completa (actualizada)
│   └── ...
├── data/                       # Datos persistentes
│   ├── repository/
│   │   ├── types/types.json
│   │   ├── settings.json      # NUEVO: Configuración de ruta
│   │   ├── docs/               # PDFs (ruta configurable)
│   │   └── meta/               # Metadatos JSON
│   └── ...
├── tests/                      # Tests E2E
│   ├── e2e_repository_settings.spec.js  # NUEVO
│   ├── e2e_validity_start.spec.js       # NUEVO
│   └── ...
└── docs/                       # Documentación
    ├── evidence/
    │   ├── repo_settings/      # NUEVO
    │   └── validity_start/     # NUEVO
    └── ...
```

---

## 5. Componentes Principales

### 5.1 Repositorio Documental

**DocumentRepositoryStoreV1** (`backend/repository/document_repository_store_v1.py`):
- Gestión de tipos de documento (CRUD)
- Gestión de instancias de documentos (CRUD)
- Persistencia en JSON + Filesystem
- **NUEVO**: Carga configuración de ruta desde `settings.json`
- **NUEVO**: Soporte para `validity_start_mode` en tipos

**DocumentRepositoryRoutes** (`backend/repository/document_repository_routes.py`):
- Endpoints REST para tipos y documentos
- Upload de PDFs con validación
- **NUEVO**: Recibe `issue_date` y `validity_start_date` en upload
- **NUEVO**: Resuelve `validity_start_date` según `validity_start_mode`
- **NUEVO**: Cálculo de `period_key` usa `validity_start_date` como base

**SettingsRoutes** (`backend/repository/settings_routes.py`) - **NUEVO**:
- `GET /api/repository/settings`: Obtiene configuración actual
- `PUT /api/repository/settings`: Actualiza configuración (con validación)
- Validación de rutas (absolutas, escribibles, creación automática)
- Persistencia en `data/repository/settings.json`

### 5.2 Modelos de Datos

**DocumentTypeV1** (`backend/shared/document_repository_v1.py`):
```python
class DocumentTypeV1(BaseModel):
    type_id: str
    name: str
    scope: DocumentScopeV1  # "company" | "worker"
    validity_policy: ValidityPolicyV1
    issue_date_required: bool = True
    validity_start_mode: Literal["issue_date", "manual"] = "issue_date"  # NUEVO
    # ... otros campos
```

**ExtractedMetadataV1**:
```python
class ExtractedMetadataV1(BaseModel):
    issue_date: Optional[date]
    name_date: Optional[date]
    validity_start_date: Optional[date]  # NUEVO
    period_start: Optional[date]
    period_end: Optional[date]
```

---

## 6. APIs y Endpoints

### 6.1 Repositorio Documental

#### Tipos de Documento
- `GET /api/repository/types` - Lista tipos
- `POST /api/repository/types` - Crea tipo
- `GET /api/repository/types/{type_id}` - Obtiene tipo
- `PUT /api/repository/types/{type_id}` - Actualiza tipo
- `DELETE /api/repository/types/{type_id}` - Elimina tipo

#### Documentos
- `POST /api/repository/docs/upload` - Sube documento
  - **NUEVO**: Parámetros `issue_date` y `validity_start_date` (Form)
  - Resuelve `validity_start_date` según `validity_start_mode`
- `GET /api/repository/docs` - Lista documentos
- `GET /api/repository/docs/{doc_id}` - Obtiene documento
- `PUT /api/repository/docs/{doc_id}` - Actualiza documento
- `DELETE /api/repository/docs/{doc_id}` - Elimina documento
- `GET /api/repository/docs/{doc_id}/pdf` - Sirve PDF
- `PUT /api/repository/docs/{doc_id}/pdf` - Reemplaza PDF

#### Configuración - **NUEVO**
- `GET /api/repository/settings` - Obtiene configuración
  ```json
  {
    "repository_root_dir": "D:\\Proyectos_Cursor\\CometLocal\\data\\repository"
  }
  ```
- `PUT /api/repository/settings` - Actualiza configuración
  - Query param `dry_run=true` para validar sin guardar
  - Valida: ruta absoluta, escribible, crea directorio si no existe

#### Sujetos
- `GET /api/repository/subjects` - Obtiene empresas y trabajadores

---

## 7. Modelos de Datos

### 7.1 DocumentTypeV1

```python
class DocumentTypeV1(BaseModel):
    type_id: str
    name: str
    description: str = ""
    scope: DocumentScopeV1  # "company" | "worker"
    validity_policy: ValidityPolicyV1
    issue_date_required: bool = True
    validity_start_mode: Literal["issue_date", "manual"] = "issue_date"  # NUEVO
    platform_aliases: List[str] = []
    active: bool = True
    allow_late_submission: bool = False
    late_submission_max_days: Optional[int] = None
```

**validity_start_mode**:
- `"issue_date"` (default): Inicio de vigencia = fecha de emisión
- `"manual"`: Usuario introduce inicio de vigencia al subir

### 7.2 ExtractedMetadataV1

```python
class ExtractedMetadataV1(BaseModel):
    issue_date: Optional[date]
    name_date: Optional[date]
    validity_start_date: Optional[date]  # NUEVO
    period_start: Optional[date]
    period_end: Optional[date]
```

### 7.3 RepositorySettingsV1 - **NUEVO**

```python
class RepositorySettingsV1(BaseModel):
    repository_root_dir: str  # Ruta absoluta donde se guardan los documentos
```

---

## 8. Funcionalidades Implementadas

### 8.1 Repositorio Documental

✅ **Gestión de Tipos**:
- CRUD completo desde UI
- Configuración de periodicidad (mensual, anual, cada N meses, una vez)
- Configuración de validez (desde nombre, desde emisión, manual)
- **NUEVO**: Configuración de `validity_start_mode`
- Aliases para matching con plataformas
- Activo/inactivo

✅ **Subida de Documentos**:
- Drag & drop o selección de archivos
- Auto-detección de tipo desde nombre
- Parsing de fecha desde nombre (múltiples formatos)
- Validación de campos obligatorios
- **NUEVO**: Campo condicional "Fecha de inicio de vigencia" cuando `validity_start_mode="manual"`
- **NUEVO**: Sincronización automática cuando `validity_start_mode="issue_date"`
- Pre-llenado de valores por defecto
- Detección de duplicados

✅ **Búsqueda y Filtrado**:
- Búsqueda por nombre, tipo, empresa, trabajador
- Filtros por tipo, estado, empresa, trabajador
- Ordenación por fecha, nombre, tipo
- Paginación

✅ **Gestión de Documentos**:
- Ver PDF
- Editar metadatos (empresa, trabajador, estado)
- Eliminar (si no está "submitted")
- Re-subir PDF (reemplazar)

### 8.2 Configuración del Repositorio - **NUEVO**

✅ **Configuración de Ruta**:
- Pantalla "Configuración" en UI
- Campo para editar ruta del repositorio
- Botón "Probar" para validar sin guardar
- Botón "Guardar" para persistir cambios
- Validación: ruta absoluta, escribible, creación automática
- Persistencia en `data/repository/settings.json`
- **Integración**: `DocumentRepositoryStoreV1` carga configuración dinámicamente

### 8.3 Validity Start Date - **NUEVO**

✅ **Configuración por Tipo**:
- Campo en catálogo: "Fecha de inicio de vigencia"
  - Opción 1: "Igual a la fecha de emisión" (`issue_date`)
  - Opción 2: "Se introduce al subir el documento" (`manual`)

✅ **Subida de Documentos**:
- **Modo `issue_date`**: Campo "inicio de vigencia" NO aparece, se sincroniza automáticamente
- **Modo `manual`**: Campo "Fecha de inicio de vigencia *" aparece y es obligatorio
- Validación: bloquea guardar si falta cuando es obligatorio

✅ **Cálculo de Periodo**:
- `period_key` se calcula desde `validity_start_date` (no desde `issue_date`)
- Permite documentos con vigencia distinta de fecha de emisión

---

## 9. Flujos Principales

### 9.1 Subida de Documento

```
1. Usuario arrastra PDF → Frontend crea file card
2. Usuario selecciona tipo → Frontend carga configuración del tipo
3. Si validity_start_mode="issue_date":
   - NO muestra campo "inicio de vigencia"
   - validity_start_date = issue_date (automático)
4. Si validity_start_mode="manual":
   - Muestra campo "Fecha de inicio de vigencia *" (obligatorio)
   - Usuario debe rellenarlo
5. Usuario completa empresa/trabajador según scope
6. Frontend envía FormData con:
   - file, type_id, scope, company_key, person_key
   - issue_date, validity_start_date
7. Backend:
   - Resuelve validity_start_date según validity_start_mode
   - Calcula period_key desde validity_start_date
   - Guarda PDF en ruta configurada (settings.json)
   - Guarda metadatos en JSON
```

### 9.2 Configuración de Ruta

```
1. Usuario navega a "Configuración"
2. Frontend carga configuración actual (GET /api/repository/settings)
3. Usuario edita ruta
4. Usuario hace clic en "Probar" → PUT con dry_run=true
5. Backend valida y crea directorio si no existe
6. Frontend muestra resultado
7. Usuario hace clic en "Guardar" → PUT sin dry_run
8. Backend guarda en settings.json
9. Próximos uploads usan nueva ruta
```

---

## 10. UI v3 - Repositorio Documental

### 10.1 Estructura de Navegación

- **Inicio**: Dashboard con KPIs
- **Calendario**: Visualización de documentos faltantes por mes
- **Subir documentos**: Wizard de subida con validación
- **Buscar documentos**: Búsqueda y filtrado avanzado
- **Plataformas**: Estado de configuración
- **Catálogo**: Gestión de tipos de documento
- **Configuración**: **NUEVO** - Configuración de ruta del repositorio
- **Actividad**: Historial (en desarrollo)

### 10.2 Catálogo de Documentos

**Funcionalidades**:
- Lista de tipos con filtros (búsqueda, scope, periodicidad)
- Crear/editar tipo con drawer modal
- **NUEVO**: Campo "Fecha de inicio de vigencia" en drawer
- Exportar/importar tipos
- Activar/desactivar tipos
- Eliminar tipos

**Campos del Drawer**:
- Nombre, descripción
- Alcance (empresa/trabajador)
- Periodicidad (mensual, cada N meses, anual, una vez)
- Cómo se calcula el periodo
- Fecha de expedición obligatoria
- **NUEVO**: Fecha de inicio de vigencia (issue_date/manual)
- Permitir envío tardío
- Aliases para matching

### 10.3 Subida de Documentos

**Wizard de Subida**:
1. Arrastrar/seleccionar PDFs
2. Seleccionar tipo de documento
3. Seleccionar empresa/trabajador según scope
4. Fecha de emisión (parseada desde nombre o manual)
5. **NUEVO**: Fecha de inicio de vigencia (si `validity_start_mode="manual"`)
6. Periodo (si aplica)
7. Validación y guardado

**Características**:
- Auto-detección de tipo desde nombre
- Parsing de fecha desde nombre (múltiples formatos)
- Valores por defecto aplicables a todos
- Validación en tiempo real
- Detección de duplicados

### 10.4 Buscar Documentos

**Funcionalidades**:
- Búsqueda por nombre, tipo, empresa, trabajador
- Filtros múltiples (tipo, estado, empresa, trabajador, fecha)
- Ordenación (fecha, nombre, tipo)
- Acciones por documento:
  - Ver PDF
  - Editar metadatos
  - Eliminar
  - Re-subir PDF

### 10.5 Configuración - **NUEVO**

**Pantalla de Configuración**:
- Campo "Ruta del repositorio" (input texto)
- Texto de ayuda con ejemplos (Windows/Linux)
- Botón "Probar" (valida sin guardar)
- Botón "Guardar" (persiste cambios)
- Mensajes de feedback (éxito/error)

---

## 11. Series Temporales (Period-Based Documents)

### 11.1 Conceptos

- **Period Kind**: MONTH, YEAR, QUARTER, NONE
- **Period Key**: Clave del período (ej: "2025-11" para noviembre 2025)
- **Validity Start Date**: **NUEVO** - Fecha base para calcular periodo (puede ser distinta de issue_date)

### 11.2 Cálculo de Period Key

**Antes** (usando `issue_date`):
```python
period_key = infer_period_key(
    doc_type=type,
    issue_date=extracted.issue_date,  # Base
    name_date=name_date,
    filename=filename
)
```

**Ahora** (usando `validity_start_date`):
```python
base_date = extracted.validity_start_date or extracted.issue_date or name_date
period_key = infer_period_key(
    doc_type=type,
    issue_date=base_date,  # Usa validity_start_date como base
    name_date=name_date,
    filename=filename
)
```

### 11.3 Ejemplo: AEAT No deuda (12 meses)

- `issue_date`: 2025-10-16 (parseada desde nombre)
- `validity_start_mode`: "manual"
- `validity_start_date`: 2025-11-01 (introducida manualmente)
- `period_key`: "2025-11" (calculado desde `validity_start_date`, no desde `issue_date`)
- Validez: 12 meses desde 2025-11-01

---

## 12. Configuración del Repositorio - **NUEVO**

### 12.1 Endpoints

**GET /api/repository/settings**:
```json
{
  "repository_root_dir": "D:\\Proyectos_Cursor\\CometLocal\\data\\repository"
}
```

**PUT /api/repository/settings**:
- Body: `{ "repository_root_dir": "..." }`
- Query param `dry_run=true`: Solo valida sin guardar
- Validaciones:
  - Ruta debe ser absoluta
  - No permite rutas relativas con `..`
  - Crea directorio si no existe
  - Verifica permisos de escritura

### 12.2 Persistencia

Archivo: `data/repository/settings.json`
```json
{
  "repository_root_dir": "D:\\Proyectos_Cursor\\CometLocal\\data\\repository"
}
```

Si no existe, se crea automáticamente con ruta por defecto.

### 12.3 Integración

`DocumentRepositoryStoreV1` carga configuración en `__init__`:
```python
def __init__(self, *, base_dir: str | Path = "data"):
    try:
        settings = load_settings()
        repository_root = Path(settings.repository_root_dir)
    except Exception:
        # Fallback a comportamiento anterior
        repository_root = (Path(base_dir) / "repository").resolve()
    
    self.repo_dir = repository_root.resolve()
    # ... resto de inicialización
```

### 12.4 UI

Pantalla "Configuración" en menú lateral:
- Campo de texto para ruta
- Botón "Probar" (dry_run)
- Botón "Guardar"
- Mensajes de feedback

---

## 13. Validity Start Date (Fecha de Inicio de Vigencia) - **NUEVO**

### 13.1 Concepto

Permite que la fecha de inicio de vigencia sea independiente de la fecha de emisión del documento.

**Casos de uso**:
- Documento emitido el 16/10/2025 pero válido desde 01/11/2025
- Cálculo de periodo basado en inicio de vigencia, no en emisión

### 13.2 Configuración por Tipo

**Campo en Catálogo**: "Fecha de inicio de vigencia"
- Opción 1: "Igual a la fecha de emisión" (`validity_start_mode="issue_date"`) [DEFAULT]
- Opción 2: "Se introduce al subir el documento" (`validity_start_mode="manual"`)

### 13.3 Comportamiento en Subida

**Modo `issue_date`**:
- Campo "inicio de vigencia" NO aparece
- `validity_start_date` = `issue_date` (automático)
- Si cambia `issue_date`, `validity_start_date` se actualiza automáticamente

**Modo `manual`**:
- Campo "Fecha de inicio de vigencia *" aparece y es obligatorio
- `validity_start_date` es independiente de `issue_date`
- Validación: bloquea guardar si está vacío

### 13.4 Cálculo de Periodo

El cálculo de `period_key` usa `validity_start_date` como fecha base:

```python
# En document_repository_routes.py
base_date = extracted.validity_start_date or extracted.issue_date or name_date
period_key = planner.infer_period_key(
    doc_type=doc_type,
    issue_date=base_date,  # Usa validity_start_date
    name_date=name_date,
    filename=filename
)
```

### 13.5 Ejemplo Real

**AEAT No deuda (T5612_NO_DEUDA_HACIENDA)**:
- Archivo: `AEAT-16-oct-2025.pdf`
- `issue_date`: 2025-10-16 (parseada desde nombre)
- `validity_start_mode`: "manual"
- `validity_start_date`: 2025-11-01 (introducida manualmente)
- `period_key`: "2025-11" (calculado desde `validity_start_date`)
- Validez: 12 meses desde 2025-11-01 (no desde 2025-10-16)

---

## 14. Configuración y Despliegue

### 14.1 Requisitos

- Python 3.11+
- Node.js 18+ (para tests E2E)
- Playwright (instalado con `npx playwright install`)

### 14.2 Instalación

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend (tests)
npm install
npx playwright install
```

### 14.3 Ejecución

```bash
# Backend
cd backend
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Tests E2E
npm run test:e2e
```

### 14.4 Configuración Inicial

1. **Ruta del Repositorio** (opcional):
   - Navegar a "Configuración" en UI
   - Editar ruta si es necesario
   - Guardar

2. **Tipos de Documento**:
   - Crear tipos desde "Catálogo"
   - Configurar `validity_start_mode` según necesidad

### 14.5 Variables de Entorno

- `COMETLOCAL_DATA_DIR`: Ruta base de datos (opcional)
- `BATCH_RUNS_DIR`: Ruta de ejecuciones (opcional)

---

## 15. Testing y Calidad

### 15.1 Tests E2E

**Tests Implementados**:
- `tests/e2e_upload_subjects.spec.js` - Subida con sujetos
- `tests/e2e_upload_aeat.spec.js` - Subida AEAT (bugs específicos)
- `tests/e2e_search_docs_actions.spec.js` - Acciones en búsqueda
- `tests/e2e_fix_pdf_viewing.spec.js` - Visualización y edición
- `tests/e2e_repository_settings.spec.js` - **NUEVO**: Configuración de ruta
- `tests/e2e_validity_start.spec.js` - **NUEVO**: Validity start date

**Ejecución**:
```bash
npm run test:e2e -- tests/e2e_validity_start.spec.js
npm run test:e2e -- tests/e2e_repository_settings.spec.js
```

### 15.2 Evidencias

**Carpetas de Evidencias**:
- `docs/evidence/repo_settings/` - Configuración de ruta
- `docs/evidence/validity_start/` - Validity start date
- `docs/evidence/repo_upload_aeat/` - Subida AEAT
- `docs/evidence/repo_upload_subjects/` - Subida con sujetos

Cada carpeta contiene:
- Screenshots (`.png`)
- Logs (`console.log`)
- Reportes (`report.md`)

---

## 16. Estado Actual y Roadmap

### 16.1 Funcionalidades Completadas

✅ Repositorio documental completo
✅ UI v3 con todas las funcionalidades
✅ Series temporales con period_key
✅ Matching inteligente con herencia
✅ Reglas de envío configurables
✅ Historial de envíos
✅ **Configuración de ruta del repositorio** - **NUEVO**
✅ **Validity Start Date** - **NUEVO**
✅ Tests E2E completos
✅ Evidencias documentadas

### 16.2 En Desarrollo

- Actividad: Historial de actividad (placeholder)
- Mejoras de UX según feedback

### 16.3 Roadmap Futuro

- Migración de documentos existentes a period_key
- Dashboard de cobertura por período
- Notificaciones de documentos próximos a vencer
- Integración con más plataformas CAE

---

## 17. Partes en Desarrollo

### 17.1 Actividad

La pantalla "Actividad" está en desarrollo. Actualmente muestra un placeholder.

### 17.2 Debugging

**Logs**:
- Backend: Logs en consola
- Frontend: Console del navegador
- Evidence: Logs en `data/runs/{run_id}/evidence/`

**Verificación de endpoints**:
```bash
curl http://127.0.0.1:8000/api/repository/types
curl http://127.0.0.1:8000/api/repository/docs
curl http://127.0.0.1:8000/api/repository/settings  # NUEVO
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
- `docs/evidence/repo_settings/report.md`: **NUEVO** - Configuración de ruta
- `docs/evidence/validity_start/report.md`: **NUEVO** - Validity start date

### 18.2 Archivos de Configuración

- `backend/config.py`: Configuración principal
- `data/refs/*.json`: Configuración de datos
- `data/repository/settings.json`: **NUEVO** - Configuración de ruta

### 18.3 Código Clave

- `backend/app.py`: Aplicación principal
- `backend/adapters/egestiona/flows.py`: Flujos eGestiona
- `backend/repository/document_repository_routes.py`: Rutas del repositorio
- `backend/repository/settings_routes.py`: **NUEVO** - Configuración de ruta
- `backend/agents/agent_runner.py`: Runner de agentes
- `backend/repository/period_planner_v1.py`: Planificación de períodos
- `backend/repository/rule_based_matcher_v1.py`: Matching con herencia
- `frontend/repository_v3.html`: UI v3 completa (actualizada)

---

## 19. Cambios Recientes (Enero 2026)

### 19.1 Configuración de Ruta del Repositorio

**Fecha**: Enero 2026

**Archivos Modificados**:
- `backend/repository/settings_routes.py` (NUEVO)
- `backend/repository/document_repository_store_v1.py`
- `backend/app.py`
- `frontend/repository_v3.html`
- `tests/e2e_repository_settings.spec.js` (NUEVO)

**Funcionalidades**:
- Endpoints GET/PUT `/api/repository/settings`
- Pantalla "Configuración" en UI
- Validación de rutas (absolutas, escribibles)
- Persistencia en `data/repository/settings.json`
- Integración con `DocumentRepositoryStoreV1`

**Evidencias**: `docs/evidence/repo_settings/`

### 19.2 Validity Start Date

**Fecha**: Enero 2026

**Archivos Modificados**:
- `backend/shared/document_repository_v1.py`
- `backend/repository/document_repository_routes.py`
- `backend/repository/document_repository_store_v1.py`
- `frontend/repository_v3.html`
- `data/repository/types/types.json`
- `tests/e2e_validity_start.spec.js` (NUEVO)

**Funcionalidades**:
- Campo `validity_start_mode` en `DocumentTypeV1`
- Campo `validity_start_date` en `ExtractedMetadataV1`
- UI en catálogo para configurar modo
- Campo condicional en subida cuando `mode="manual"`
- Cálculo de `period_key` desde `validity_start_date`
- Retrocompatibilidad mantenida

**Evidencias**: `docs/evidence/validity_start/`

---

## 20. Contacto y Soporte

Para preguntas técnicas o soporte, consultar:
- Documentación en `docs/`
- Código fuente con comentarios
- Logs y evidence de ejecuciones
- Tests como ejemplos de uso
- Reportes E2E para casos de uso reales
- Evidencias en `docs/evidence/`

---

**Fin del Handoff Técnico**

*Última actualización: 2 de Enero 2026*












