# Repositorio Documental v1

## Descripción

El Repositorio Documental es un sistema data-driven para gestionar tipos de documento y documentos (PDFs) con cálculo automático de validez canónica usando políticas declarativas.

## Características

- **CRUD de Tipos de Documento**: Gestión completa por UI sin tocar código
- **Upload de Documentos**: Subida de PDFs con asociación a tipo + sujeto (empresa/trabajador)
- **Cálculo de Validez Determinista**: Políticas declarativas sin lógica hardcodeada por tipo
- **Parser de Fechas**: Extracción automática de fechas desde nombres de archivo
- **Metadatos Sidecar**: JSON por documento con información extraída y calculada

## Estructura en Disco

```
data/repository/
├── types/
│   └── types.json              # Tipos de documento (CRUD por UI)
├── docs/
│   └── <doc_id>.pdf            # PDFs almacenados
├── meta/
│   └── <doc_id>.json           # Metadatos sidecar por documento
├── rules/
│   └── submission_rules.json   # Reglas de envío (placeholder)
└── overrides/
    └── overrides.json          # Overrides de validez (placeholder)
```

## Modelos

### DocumentTypeV1

Tipo de documento editable por UI:

- `type_id`: Identificador único (ej: `T104_AUTONOMOS_RECEIPT`)
- `name`: Nombre legible
- `description`: Descripción opcional
- `scope`: `company` o `worker`
- `validity_policy`: Política declarativa de validez
- `required_fields`: Campos requeridos
- `active`: Si está activo

### DocumentInstanceV1

Instancia de documento (PDF + metadatos):

- `doc_id`: UUID del documento
- `file_name_original`: Nombre original del archivo
- `stored_path`: Ruta relativa al PDF
- `sha256`: Hash del archivo
- `type_id`: ID del tipo
- `scope`: `company` o `worker`
- `company_key`: Clave de empresa (obligatorio según scope)
- `person_key`: Clave de persona (obligatorio si `scope=worker`, null si `scope=company`)
- `extracted`: Metadatos extraídos (fechas, períodos)
- `computed_validity`: Validez calculada (determinista)
- `status`: `draft` | `reviewed` | `ready_to_submit` | `submitted`

**Reglas de validación:**
- Si `scope=company`: `company_key` obligatorio, `person_key` debe ser `null`
- Si `scope=worker`: `company_key` y `person_key` obligatorios

### ValidityPolicyV1

Política declarativa de validez:

- `mode`: `monthly` | `annual` | `fixed_end_date`
- `basis`: `issue_date` | `name_date` | `manual`
- Configuración específica según `mode`:
  - `monthly`: `month_source`, `grace_days`
  - `annual`: `months`
  - `fixed_end_date`: requiere fecha manual

## API Endpoints

### Tipos de Documento

- `GET /api/repository/types` - Lista todos los tipos
- `GET /api/repository/types/{type_id}` - Obtiene un tipo
- `POST /api/repository/types` - Crea un tipo
- `PUT /api/repository/types/{type_id}` - Actualiza un tipo
- `POST /api/repository/types/{type_id}/duplicate` - Duplica un tipo
- `DELETE /api/repository/types/{type_id}` - Elimina un tipo

### Documentos

- `GET /api/repository/docs` - Lista documentos (con filtros opcionales)
- `GET /api/repository/docs/{doc_id}` - Obtiene un documento
- `POST /api/repository/docs/upload` - Sube un PDF (multipart/form-data)
  - Requiere: `file`, `type_id`, `scope` (se determina del tipo), `company_key`, `person_key` (si `scope=worker`)
- `PUT /api/repository/docs/{doc_id}` - Actualiza campos editables de un documento
  - Body: `{ "company_key"?, "person_key"?, "status"? }`
  - Valida según scope del tipo asociado

### Configuración (para poblar selects en UI)

- `GET /api/config/org` - Obtiene configuración de organización (solo lectura)
- `GET /api/config/people` - Obtiene lista de personas (solo lectura)

## UI

### Acceso

- **URL**: `/repository`
- **Link desde HOME**: "📚 Repositorio Documental"

### Funcionalidades

#### Tab: Tipos de Documento

- Lista de tipos con filtros
- Crear nuevo tipo (formulario guiado)
- Editar tipo existente
- Duplicar tipo
- Activar/Desactivar tipo
- Borrar tipo

#### Tab: Documentos

- Lista de documentos con columnas: Archivo, Tipo, Alcance, **Empresa**, **Trabajador**, Validez, Estado
- Subir PDF (drag&drop o file picker)
- Seleccionar tipo (dropdown) - el scope se determina automáticamente del tipo
- Seleccionar sujeto según scope:
  - Si `scope=company` => seleccionar empresa (obligatorio)
  - Si `scope=worker` => seleccionar empresa + trabajador (ambos obligatorios)
- Ver propuesta de validez (computed)
- Estado inicial: `draft`
- **Modal de detalle**: Ver y editar empresa/trabajador/estado

## Cálculo de Validez

### Parser de Fechas

Soporta estos patrones desde el nombre de archivo:

- `28-nov-25` (DD-MMM-YY, meses en español)
- `28-11-2025` (DD-MM-YYYY)
- `2025-11-28` (YYYY-MM-DD)
- `28/11/2025` (DD/MM/YYYY)

### Políticas de Validez

#### Monthly (Mensual)

- `month_source`: `issue_date` o `name_date`
- Calcula período mensual (inicio y fin de mes)
- `valid_from`: `period_start`
- `valid_to`: `period_end` + `grace_days`

#### Annual (Anual)

- `months`: Número de meses de validez (default: 12)
- `valid_from`: `issue_date`
- `valid_to`: `issue_date` + `months`

#### Fixed End Date (Fecha Fija)

- `valid_from`: `issue_date`
- `valid_to`: `manual_end_date` (requiere fecha manual)

### Confianza (Confidence)

- `0.0 - 1.0`: Nivel de confianza en el cálculo
- Factores:
  - Parseo exitoso de fecha: +0.4
  - Política aplicable: +0.3
  - Datos completos: +0.3

## Seed Inicial

Al crear el repositorio, se crea automáticamente:

- **T104_AUTONOMOS_RECEIPT**: Recibo autónomos mensual
  - `scope`: `worker`
  - `mode`: `monthly`
  - `basis`: `name_date`
  - `month_source`: `name_date`

## Ejemplo de Uso

### 1. Crear Tipo

```bash
curl -X POST "http://127.0.0.1:8000/api/repository/types" \
  -H "Content-Type: application/json" \
  -d '{
    "type_id": "T105_APTITUD_MEDICA",
    "name": "Aptitud médica",
    "scope": "worker",
    "validity_policy": {
      "mode": "annual",
      "basis": "issue_date",
      "annual": {
        "months": 12,
        "valid_from": "issue_date",
        "valid_to": "issue_date_plus_months"
      }
    },
    "required_fields": ["valid_from", "valid_to"],
    "active": true
  }'
```

### 2. Subir Documento

```bash
curl -X POST "http://127.0.0.1:8000/api/repository/docs/upload" \
  -F "file=@documento.pdf" \
  -F "type_id=T104_AUTONOMOS_RECEIPT" \
  -F "scope=worker" \
  -F "person_key=Emilio"
```

### 3. Ver Documento

```bash
curl "http://127.0.0.1:8000/api/repository/docs/{doc_id}"
```

## Guardrails

- **Hard-stop si `matches != 1`**: En operaciones que requieren exactamente un resultado
- **Validación de scope**: El tipo y el documento deben tener el mismo scope
- **Validación de PDF**: Solo se aceptan archivos `.pdf`
- **Thread-safe writes**: Escritura atómica (temp → rename)

## Matching & Aliases

### Platform Aliases

Los tipos de documento pueden tener `platform_aliases` para matching con plataformas externas (eGestiona, etc.).

**Ejemplo:**
```json
{
  "type_id": "T104_AUTONOMOS_RECEIPT",
  "platform_aliases": ["T104.0", "recibo bancario", "cuota autónomos"]
}
```

### Matching de Pendientes

El endpoint `POST /runs/egestiona/match_pending_documents_readonly` hace matching determinista:

1. **Normaliza texto**: `(Tipo Documento + " " + Elemento).lower()`
2. **Encuentra tipos candidatos**: Busca `platform_aliases` en el texto normalizado
3. **Filtra documentos**: Por `company_key` y `person_key` (según scope)
4. **Scoring**:
   - +0.6 si type match por alias
   - +0.3 si `status` in (reviewed, ready_to_submit)
   - +0.2 si validity cubre el período solicitado
   - -0.2 si `status=draft`
5. **Retorna**: `best_doc`, `alternatives[]`, `confidence`, `reasons[]`, `needs_operator`

**Parámetros:**
- `company_key`: Clave de empresa (obligatorio)
- `person_key`: Clave de persona (opcional, según scope)
- `limit`: Máximo de pendientes a procesar (default: 20)
- `only_target`: Si `true`, solo procesa pendientes del sujeto especificado

**Respuesta:**
```json
{
  "run_id": "...",
  "runs_url": "/runs/..."
}
```

Evidence generada:
- `01_dashboard_tiles.png`
- `02_listado_grid.png`
- `pending_items.json`
- `match_results.json`
- `meta.json`

## Próximos Pasos (Placeholder)

- **SubmissionRuleV1**: Reglas de envío a plataformas
- **ValidityOverrideV1**: Overrides manuales de validez
- Integración con submissions CAE

## Notas Técnicas

- **Storage**: JSON files (sin base de datos)
- **Atomic writes**: `_atomic_write_json` (temp → validate → rename)
- **Thread-safe**: Operaciones de escritura protegidas
- **Seed automático**: Se crea `T104_AUTONOMOS_RECEIPT` si no existe `types.json`
- **Versionado**: Solo `types.json` inicial se versiona; documentos reales no



