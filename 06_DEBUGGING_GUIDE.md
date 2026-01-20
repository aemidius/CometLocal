# 06_DEBUGGING_GUIDE — CometLocal

## Errores comunes recientes

### Matching sin resultados (NO_MATCH / REVIEW_REQUIRED)
**Síntoma**: El plan devuelve `AUTO_UPLOAD=0` (no se sube nada).
**Diagnóstico rápido**: Revisar `matching_debug_report` (y el panel UI “¿Por qué no se ha subido?”).
**Causas típicas**:
- `NO_LOCAL_DOCS`: no hay documentos del tipo en el repositorio
- `PERIOD_MISMATCH`: existe el tipo, pero no cubre el periodo solicitado
- `COMPANY_MISMATCH` / `PERSON_MISMATCH`: el documento está asignado a otra empresa/trabajador
- `ALIAS_NOT_MATCHING` / `TYPE_NOT_FOUND`: falta alias o el tipo no se reconoce para esa plataforma
- `VALIDITY_MISMATCH`: existen documentos, pero ninguno es usable por validez/override

**Qué hacer**: corregir datos (subir documento, ajustar periodo/asignación) o actualizar alias del tipo de forma aditiva.


### NameError: response is not defined
**Causa**: Código JavaScript incrustado accidentalmente en backend Python.
**Solución**: Revisar `config_viewer.py` y eliminar interpolaciones JS.

### 500 en /config/people
**Causa**: Guardrail de contexto bloqueando sin headers.
**Solución aplicada**: Devolver 400 explícito + interceptar submit frontend.

## Regla de oro
Un 500 es siempre bug del sistema, nunca error del usuario.
