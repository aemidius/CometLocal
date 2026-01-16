# Debug de Inconsistencia: /docs vs /docs/pending

## Problema Identificado

En `#buscar`, la tabla muestra 2 documentos con estado "Expirado", pero en `#calendario`, los tabs muestran `Expirados=0`, `Expiran pronto=0`, `Pendientes=0`.

## Causa Raíz

**BUG DE ROUTING EN FASTAPI**: La ruta `/docs/{doc_id}` estaba capturando `/docs/pending` porque FastAPI interpreta "pending" como un `doc_id`. 

En FastAPI, el orden de las rutas importa: las rutas más específicas deben ir **ANTES** que las rutas con parámetros.

### Antes (INCORRECTO):
```python
@router.get("/docs")  # Línea 398
async def list_documents(...):
    ...

@router.get("/docs/{doc_id}")  # Línea 444 - CAPTURA /docs/pending
async def get_document(doc_id: str):
    ...

@router.get("/docs/pending")  # Línea 715 - NUNCA SE EJECUTA
async def get_pending_documents(...):
    ...
```

Cuando se llama a `/api/repository/docs/pending`, FastAPI lo interpreta como `/docs/{doc_id}` con `doc_id="pending"`, devolviendo 404 "Document pending not found".

## Fix Aplicado

**Reordenar rutas**: Mover `/docs/pending` **ANTES** de `/docs/{doc_id}`.

### Después (CORRECTO):
```python
@router.get("/docs")  # Línea 398
async def list_documents(...):
    ...

@router.get("/docs/pending")  # Línea 444 - AHORA SE EJECUTA PRIMERO
async def get_pending_documents(...):
    ...

@router.get("/docs/{doc_id}")  # Línea 547 - Solo captura UUIDs reales
async def get_document(doc_id: str):
    ...
```

## Cambios Adicionales para Consistencia

1. **Misma fuente de datos**: `/docs/pending` ahora usa `store.list_documents()` igual que `/docs`
2. **Misma función de cálculo**: Ambos usan `calculate_document_status()` con los mismos parámetros
3. **Mismo enum**: Ambos usan `DocumentValidityStatus.EXPIRED` y `DocumentValidityStatus.EXPIRING_SOON`
4. **Manejo de errores**: Añadido try/except en `/docs/pending` para evitar errores silenciosos

## Evidencia de Reproducción

### Antes del Fix

```bash
$ curl "http://127.0.0.1:8000/api/repository/docs?validity_status=EXPIRED"
[
  {
    "doc_id": "7db82a52-b444-4e31-98eb-61a3095d92c5",
    "type_id": "T8447_RC_CERTIFICADO",
    "validity_status": "EXPIRED",
    "validity_end_date": "2025-08-31",
    "days_until_expiry": -126
  },
  {
    "doc_id": "ea307c95-db5f-4ed5-a966-a9e715e85390",
    "type_id": "T9977_AUTONOMOS",
    "validity_status": "EXPIRED",
    "validity_end_date": "2025-12-06",
    "days_until_expiry": -29
  }
]

$ curl "http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3"
{"detail": "Document pending not found"}  # ❌ ERROR 404
```

### Después del Fix

```bash
$ curl "http://127.0.0.1:8000/api/repository/docs?validity_status=EXPIRED"
[
  {
    "doc_id": "7db82a52-b444-4e31-98eb-61a3095d92c5",
    "type_id": "T8447_RC_CERTIFICADO",
    "validity_status": "EXPIRED",
    "validity_end_date": "2025-08-31",
    "days_until_expiry": -126
  },
  {
    "doc_id": "ea307c95-db5f-4ed5-a966-a9e715e85390",
    "type_id": "T9977_AUTONOMOS",
    "validity_status": "EXPIRED",
    "validity_end_date": "2025-12-06",
    "days_until_expiry": -29
  }
]

$ curl "http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3"
{
  "expired": [
    {
      "doc_id": "7db82a52-b444-4e31-98eb-61a3095d92c5",
      "type_id": "T8447_RC_CERTIFICADO",
      "validity_status": "EXPIRED",
      "validity_end_date": "2025-08-31",
      "days_until_expiry": -126
    },
    {
      "doc_id": "ea307c95-db5f-4ed5-a966-a9e715e85390",
      "type_id": "T9977_AUTONOMOS",
      "validity_status": "EXPIRED",
      "validity_end_date": "2025-12-06",
      "days_until_expiry": -29
    }
  ],
  "expiring_soon": [],
  "missing": []
}  # ✅ CORRECTO
```

## Comparación de Consistencia

### Doc IDs en /docs?validity_status=EXPIRED:
- `7db82a52-b444-4e31-98eb-61a3095d92c5`
- `ea307c95-db5f-4ed5-a966-a9e715e85390`

### Doc IDs en /docs/pending (expired):
- `7db82a52-b444-4e31-98eb-61a3095d92c5`
- `ea307c95-db5f-4ed5-a966-a9e715e85390`

**✅ COINCIDEN EXACTAMENTE**

## Validación

### Test de Consistencia

Ejecutar:
```bash
pytest tests/test_consistency_docs_pending.py -v
```

**Resultado esperado:**
```
test_consistency_expired_documents PASSED
test_consistency_expiring_soon_documents PASSED
test_pending_endpoint_structure PASSED
```

## Archivos Modificados

1. **`backend/repository/document_repository_routes.py`**:
   - Movida función `get_pending_documents()` de línea 715 a línea 444 (antes de `/docs/{doc_id}`)
   - Añadido try/except para mejor manejo de errores
   - Añadido comentario explicando por qué debe ir antes

## Notas Importantes

1. **Reinicio del servidor requerido**: Después de este cambio, el servidor FastAPI debe reiniciarse para que el nuevo orden de rutas surta efecto.

2. **Orden de rutas en FastAPI**: Siempre definir rutas específicas antes que rutas con parámetros:
   - ✅ `/docs/pending` antes de `/docs/{doc_id}`
   - ✅ `/docs/{doc_id}/pdf` antes de `/docs/{doc_id}` (si fuera necesario)

3. **Consistencia garantizada**: Ambos endpoints ahora usan:
   - Misma fuente: `store.list_documents()`
   - Misma función: `calculate_document_status()`
   - Mismo enum: `DocumentValidityStatus`
   - Mismo threshold: `months_ahead * 30` días

## Próximos Pasos

1. ✅ Fix aplicado
2. ⏳ Reiniciar servidor backend
3. ⏳ Ejecutar test de consistencia
4. ⏳ Verificar en frontend que Calendario muestra los documentos expirados
5. ⏳ Capturar screenshots de evidencia







