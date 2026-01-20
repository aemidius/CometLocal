# 06_DEBUGGING_GUIDE — CometLocal

## Diagnóstico rápido por síntoma

### Matching sin resultados (NO_MATCH / REVIEW_REQUIRED)
**Síntoma**: El plan devuelve `AUTO_UPLOAD=0` (no se sube nada).  
**Diagnóstico rápido**: Revisar `matching_debug_report` (y el panel UI “¿Por qué no se ha subido?”).

**Causas típicas**:
- `NO_LOCAL_DOCS`: no hay documentos del tipo en el repositorio
- `PERIOD_MISMATCH`: existe el tipo, pero no cubre el periodo solicitado
- `COMPANY_MISMATCH` / `PERSON_MISMATCH`: el documento está asignado a otra empresa/trabajador
- `ALIAS_NOT_MATCHING` / `TYPE_NOT_FOUND`: falta alias o el tipo no se reconoce para esa plataforma
- `VALIDITY_MISMATCH`: existen documentos, pero ninguno es usable por validez/override

**Qué hacer**: corregir datos (subir documento, ajustar periodo/asignación) o actualizar alias del tipo de forma **aditiva** (acción asistida tras training).

### No aparecen acciones asistidas (botones) en el panel
**Síntoma**: Se ve el panel de diagnóstico pero no hay botones de “Asignar” / “Crear tipo”.  
**Causa**: Training no completado (`data/training/state.json` → `training_completed=false`).  
**Solución**: completar el training (5 pasos) desde el banner. Tras completar, se desbloquean acciones asistidas.

### Training “Completar” falla o no persiste
**Síntoma**: Al pulsar “Completar training”, vuelve a aparecer tras recargar.  
**Causas típicas**:
- Falta de headers de coordinación (endpoints /api/training/* requieren contexto humano).  
**Solución**: el frontend debe usar `fetchWithContext` (no `fetch` directo).

---

## Errores comunes recientes (histórico)

### NameError: response is not defined
**Causa**: Código JavaScript incrustado accidentalmente en backend Python.  
**Solución**: Revisar `config_viewer.py` y eliminar interpolaciones JS.

### 500 en /config/people
**Causa**: Guardrail de contexto bloqueando sin headers.  
**Solución aplicada**: Devolver 400 explícito + interceptar submit frontend.

## Regla de oro
Un 500 es siempre bug del sistema, nunca error del usuario.

### Se muestra un tutorial/modal legacy encima del training nuevo
**Síntoma**: Aparece un modal tipo “Paso X de Y” (legacy) mientras el banner/wizard de training C2.35 está activo.
**Estado esperado**: No debe ocurrir (C2.35.2 lo bloquea).
**Si ocurre**:
- Asegura estar en la última versión (commit >= 4600b16).
- Hard refresh (Ctrl+F5) para limpiar cache.
- Verifica que `GET /api/training/state` devuelve `training_completed=false` y que el frontend aplica TrainingGate.

