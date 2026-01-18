# SPRINT C2.21 — Export CAE audit-ready (ZIP por cliente / periodo)

## Resumen

Sistema de exportación CAE que genera un ZIP completo y auditable con toda la evidencia relevante para un cliente y periodo específico.

## Archivos creados/modificados

### Nuevos archivos:
- `backend/export/__init__.py` - Módulo export
- `backend/export/cae_exporter.py` - Lógica de exportación
- `backend/api/export_routes.py` - API endpoints
- `tests/test_cae_exporter.py` - Tests unitarios
- `docs/evidence/c2_21/README.md` - Esta documentación

### Archivos modificados:
- `backend/app.py` - Registro de export_router
- `frontend/repository_v3.html` - Modal de export en plan_review

## Funcionalidades implementadas

### 1. Exporter Backend (`cae_exporter.py`)
- `export_cae()`: Función principal que genera el ZIP
- Recolección automática de:
  - Planes relevantes (filtrados por company_key y period)
  - Decision packs
  - Matching debug (solo items del periodo)
  - Métricas
  - Documentos subidos (evidencias de ejecución)
- Generación de README.md humano
- Generación de summary.json estructurado

### 2. API Endpoints
- `POST /api/export/cae` - Crea un export
  - Body: `{ "company_key": "...", "period": "2025-01" }`
  - Response: `{ "export_id": "...", "zip_path": "...", "download_url": "..." }`
- `GET /api/export/cae/download/{export_id}` - Descarga el ZIP

### 3. UI en plan_review
- Botón "📦 Exportar CAE" en la cabecera
- Modal con:
  - Campo company_key (prefill desde plan)
  - Selector de periodo (año completo o mes específico)
  - Botón Exportar
  - Estado de progreso
  - Link de descarga directa

## Estructura del ZIP

```
CAE_EXPORT_<company_key>_<period>_<timestamp>.zip
├── README.md (documentación humana)
├── summary.json (resumen estructurado)
├── metrics/
│   ├── plan_<plan_id>_metrics.json (métricas por plan)
│   └── metrics_summary.json (resumen agregado)
├── plans/
│   ├── plan_<plan_id>.json (plan completo)
│   ├── plan_<plan_id>/
│   │   ├── decision_packs/
│   │   │   └── pack_<decision_pack_id>.json
│   │   └── matching_debug/
│   │       └── item_<item_id>__debug.json
├── uploads/
│   └── <run_id>/
│       └── (evidencias de uploads: screenshots, logs)
└── logs/
    └── plan_<plan_id>_run_summary.json
```

## Ejemplos

### Ejemplo 1: Request de export

```bash
curl -X POST "http://127.0.0.1:8000/api/export/cae" \
  -H "Content-Type: application/json" \
  -d '{
    "company_key": "COMPANY123",
    "period": "2025-01"
  }'
```

Response:
```json
{
  "export_id": "export_abc123def456",
  "zip_path": "data/exports/CAE_EXPORT_COMPANY123_2025_01_20250115_143022.zip",
  "download_url": "/api/export/cae/download/export_abc123def456",
  "filename": "CAE_EXPORT_COMPANY123_2025_01_20250115_143022.zip"
}
```

### Ejemplo 2: README.md generado

```markdown
# CAE Export - COMPANY123 - 2025-01

## Información General

- **Cliente**: COMPANY123
- **Periodo**: 2025-01
- **Fecha de Exportación**: 2025-01-15 14:30:22 UTC
- **Total de Planes**: 3
- **Total de Items**: 25

## Métricas

- **Items Auto-Upload**: 18 (72.0%)
- **Items con Learning Hints**: 3
- **Items con Presets**: 5

## Estructura del Export

[...]
```

### Ejemplo 3: summary.json

```json
{
  "company_key": "COMPANY123",
  "period": "2025-01",
  "export_date": "2025-01-15T14:30:22.123456",
  "total_plans": 3,
  "total_items": 25,
  "total_auto_upload": 18,
  "total_learning_hints": 3,
  "total_presets": 5,
  "plans": [
    {
      "plan_id": "plan_abc123",
      "items_count": 10
    },
    {
      "plan_id": "plan_def456",
      "items_count": 8
    },
    {
      "plan_id": "plan_ghi789",
      "items_count": 7
    }
  ]
}
```

## Pasos para reproducir manualmente

### 1. Generar export desde UI

1. Abrir plan_review (`#plan_review`)
2. Cargar un plan_id
3. Clic en "📦 Exportar CAE"
4. Completar:
   - Company Key (se prefill automáticamente si hay items)
   - Periodo (seleccionar de dropdown)
5. Clic en "Exportar"
6. Esperar generación (puede tardar unos segundos)
7. Clic en "📥 Descargar ZIP"

### 2. Generar export desde API

```bash
# 1. Crear export
curl -X POST "http://127.0.0.1:8000/api/export/cae" \
  -H "Content-Type: application/json" \
  -d '{
    "company_key": "COMPANY123",
    "period": "2025-01"
  }'

# 2. Descargar (usar export_id del response)
curl -O "http://127.0.0.1:8000/api/export/cae/download/{export_id}"
```

### 3. Verificar contenido del ZIP

```bash
# Extraer ZIP
unzip CAE_EXPORT_COMPANY123_2025_01_*.zip -d export_test

# Ver estructura
tree export_test

# Ver README
cat export_test/README.md

# Ver summary
cat export_test/summary.json | jq
```

## Tests

Ejecutar tests unitarios:

```bash
python -m pytest tests/test_cae_exporter.py -v
```

Tests incluidos:
- `test_export_cae_basic` - Verifica generación básica de ZIP
- `test_export_cae_filters_by_period` - Verifica filtrado por periodo
- `test_export_cae_filters_by_company` - Verifica filtrado por company_key
- `test_generate_readme` - Verifica generación de README

## Filtrado y alcance

### Filtrado por company_key
- Solo se incluyen planes donde `artifacts.company_key` coincide
- Si no hay coincidencias, el ZIP se genera vacío (0 items)

### Filtrado por periodo
- **Periodo anual (YYYY)**: Incluye items cuyo `periodo` o `period_key` empieza con el año
  - Ejemplo: `period="2025"` incluye `"2025-01"`, `"2025-02"`, etc.
- **Periodo mensual (YYYY-MM)**: Incluye solo items con periodo exacto
  - Ejemplo: `period="2025-01"` incluye solo `"2025-01"`

### Matching Debug
- Solo se incluyen debug reports de items que pasan el filtro de periodo
- Se busca por `item_id` en el nombre del archivo

### Uploads
- Solo se incluyen evidencias de ejecuciones asociadas a planes incluidos
- Se busca `run_id` desde `artifacts.run_id` o `run_summary.json`

## Ubicación de exports

- **Directorio**: `data/exports/`
- **Formato nombre**: `CAE_EXPORT_{company_key}_{period}_{timestamp}.zip`
- **Ejemplo**: `CAE_EXPORT_COMPANY123_2025_01_20250115_143022.zip`

## Notas importantes

1. **Store temporal**: Los exports se guardan en memoria (`_exports_store`). En producción, usar cache/DB persistente.

2. **Tamaño del ZIP**: Puede ser grande si hay muchos planes/items. Considerar compresión y límites de tamaño.

3. **Periodo vacío**: Si no hay items para el periodo, el ZIP se genera pero con `total_items: 0`.

4. **Documentos subidos**: Se copian evidencias (screenshots, logs), no los PDFs originales (por tamaño).

5. **Seguridad**: Validar permisos antes de exportar (no implementado en MVP).

## Comandos útiles

```bash
# Crear export
curl -X POST "http://127.0.0.1:8000/api/export/cae" \
  -H "Content-Type: application/json" \
  -d '{"company_key": "COMPANY123", "period": "2025-01"}'

# Descargar export
curl -O "http://127.0.0.1:8000/api/export/cae/download/{export_id}"

# Ver exports generados
ls -lh data/exports/

# Verificar contenido
unzip -l CAE_EXPORT_*.zip
```

## Evidencias generadas

Ejemplo de estructura de ZIP generado:

```
CAE_EXPORT_COMPANY123_2025_01_20250115_143022.zip
├── README.md
├── summary.json
├── metrics/
│   ├── plan_abc123_metrics.json
│   ├── plan_def456_metrics.json
│   └── metrics_summary.json
├── plans/
│   ├── plan_abc123.json
│   ├── plan_abc123/
│   │   ├── decision_packs/
│   │   │   └── pack_xyz789.json
│   │   └── matching_debug/
│   │       ├── item_1__debug.json
│   │       └── item_2__debug.json
│   ├── plan_def456.json
│   └── plan_def456/
│       └── matching_debug/
│           └── item_3__debug.json
├── uploads/
│   └── run_abc123/
│       ├── before_upload.png
│       ├── after_upload.png
│       └── upload_log.txt
└── logs/
    ├── plan_abc123_run_summary.json
    └── plan_def456_run_summary.json
```
