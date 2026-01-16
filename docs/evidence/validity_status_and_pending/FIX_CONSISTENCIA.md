# Fix de Inconsistencia: /docs vs /docs/pending

## Resumen Ejecutivo

**Problema**: Inconsistencia entre `#buscar` (muestra expirados) y `#calendario` (muestra 0 expirados).

**Causa**: Bug de routing en FastAPI - `/docs/{doc_id}` capturaba `/docs/pending`.

**Fix**: Reordenar rutas - `/docs/pending` debe ir ANTES de `/docs/{doc_id}`.

**Estado**: ✅ Código corregido. ⏳ Servidor necesita reiniciarse.

## Instrucciones de Aplicación

### 1. Reiniciar Servidor Backend

El servidor FastAPI debe reiniciarse para que el nuevo orden de rutas surta efecto:

```bash
# Detener servidor actual (Ctrl+C)
# Reiniciar:
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

### 2. Verificar Fix

```bash
# Debe devolver 200 (no 404)
curl "http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3"

# Debe mostrar los mismos doc_ids que /docs?validity_status=EXPIRED
curl "http://127.0.0.1:8000/api/repository/docs?validity_status=EXPIRED" | jq '.[].doc_id'
curl "http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3" | jq '.expired[].doc_id'
```

### 3. Ejecutar Test de Consistencia

```bash
pytest tests/test_consistency_docs_pending.py -v
```

**Resultado esperado**: 3 tests PASSED

### 4. Verificar en Frontend

1. Abrir `http://127.0.0.1:8000/repository_v3.html#buscar`
   - Verificar que muestra documentos expirados con badges rojos

2. Abrir `http://127.0.0.1:8000/repository_v3.html#calendario`
   - Verificar que el tab "Expirados" muestra el mismo número de documentos
   - Verificar que los doc_ids coinciden

## Archivos Modificados

- `backend/repository/document_repository_routes.py`:
  - Línea 444: Movida función `get_pending_documents()` antes de `/docs/{doc_id}`
  - Añadido try/except para mejor manejo de errores

- `tests/test_consistency_docs_pending.py` (NUEVO):
  - Test de consistencia entre ambos endpoints

- `docs/evidence/validity_status_and_pending/CONSISTENCY_DEBUG.md` (NUEVO):
  - Documentación completa del bug y fix

## Evidencia Requerida

Después de reiniciar el servidor:

1. ✅ Screenshot de `#buscar` mostrando documentos expirados
2. ✅ Screenshot de `#calendario` tab "Expirados" mostrando los mismos documentos
3. ✅ Output PASS del test de consistencia
4. ✅ Comparación de doc_ids (deben coincidir)

## Notas Técnicas

- **Orden de rutas en FastAPI**: Siempre definir rutas específicas antes que rutas con parámetros
- **Consistencia garantizada**: Ambos endpoints usan la misma lógica de cálculo
- **Sin breaking changes**: El fix solo reordena rutas, no cambia la API







