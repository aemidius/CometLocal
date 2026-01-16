# E2E Report: Modal de Comunicados Prioritarios (v2)

## Fecha
2025-12-30

## Objetivo
Implementar soporte para cerrar automáticamente el modal bloqueante de "Comunicados prioritarios" en eGestiona que aparece después del login en algunos clientes (ej: Aigues de Manresa).

## Cambios Implementados

### 1. Helper `priority_comms_headful.py`
- **Nueva estrategia implementada**:
  1. Detectar modal (iframe `ComunicadosPrioritarios.aspx` o texto visible)
  2. Leer contador "No leído: X"
  3. Mientras X>0:
     a) Abrir un comunicado no leído (click en título/link)
     b) Pulsar "Marcar como leído" (primero en page, luego en frame)
     c) Esperar a que el contador baje
     d) Screenshot por iteración
  4. Cuando X==0: cerrar modal (botón DHTMLX o Escape)
  5. Confirmar modal desaparecido

- **Instrumentación añadida**:
  - DOM dump completo (page.content() + frame.content() para cada frame)
  - Screenshots antes/durante/después de cada iteración
  - HTML del estado del modal cuando falla

- **Búsqueda robusta de elementos**:
  - Uso de `get_by_role()` y `locator()` con regex
  - Búsqueda en page primero, luego en frame
  - Fallback a búsqueda por texto en todos los botones
  - Click forzado como último recurso

### 2. Integración
- Integrado en:
  - `submission_plan_headful.py`
  - `execute_plan_headful.py`
  - `match_pending_headful.py`
- Se ejecuta automáticamente después del login exitoso

### 3. Manejo de Errores
- Endpoints devuelven HTTP 422 (en lugar de 500) cuando el modal no se puede cerrar
- Mensajes de error claros con `run_id` para revisar evidence
- Excepción específica: `PriorityCommsModalNotDismissed`

## Pruebas Realizadas

### Test 1: Cliente "Aigues de Manresa"
- **Endpoint**: `POST /runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=F63161988`
- **Resultado**: ❌ Error 500
- **Run ID**: `r_34b4cfb47874411bb36c394ce6358f95`
- **Evidence generada**:
  - `priority_comms_modal_initial.png` (452.5 KB)
  - `priority_comms_modal_failed.png` (452.62 KB)
  - `priority_comms_modal_failed.html` (29.12 KB)
  - `priority_comms_error.png` (452.62 KB)

**Observaciones**:
- El modal se detecta correctamente (iframe `ComunicadosPrioritarios.aspx` encontrado)
- El helper no logra marcar los comunicados como leídos
- El botón de cerrar está oculto (`display: none; visibility: hidden;`) hasta que todos los comunicados estén marcados
- El DOM dump no se está generando (posible error en la escritura del archivo)

### Test 2: Regresión (pendiente)
- Cliente anterior que ya funcionaba: No probado aún

## Problemas Identificados

1. **El helper detecta el modal pero no logra marcar comunicados**:
   - Posible causa: Los botones "Marcar como leído" no se encuentran dentro del iframe
   - Necesita: Revisar el DOM dump real del iframe para entender la estructura

2. **DOM dump no se genera**:
   - Posible causa: Error en la escritura del archivo o el código no llega a esa sección
   - Solución: Mejorar manejo de errores y verificar que el código se ejecute

3. **Estrategia de "abrir comunicado primero"**:
   - La estrategia está implementada pero puede que los links no sean clickables o que el iframe requiera interacción diferente

## Próximos Pasos

1. **Revisar DOM dump real**:
   - Una vez que se genere correctamente, analizar la estructura del iframe
   - Identificar selectores correctos para botones y links

2. **Ajustar selectores**:
   - Basarse en el DOM dump real para encontrar los elementos correctos
   - Puede requerir selectores más específicos o diferentes estrategias de búsqueda

3. **Probar con cliente real**:
   - Ejecutar nuevamente con "Aigues de Manresa" una vez corregidos los selectores
   - Verificar que el modal se cierre correctamente

4. **Test de regresión**:
   - Probar con cliente anterior (Kern/TEDELAB) para asegurar que no se rompe el flujo existente

## Archivos Modificados

- `backend/adapters/egestiona/priority_comms_headful.py` (reescrito completamente)
- `backend/adapters/egestiona/submission_plan_headful.py` (integración)
- `backend/adapters/egestiona/execute_plan_headful.py` (integración)
- `backend/adapters/egestiona/match_pending_headful.py` (integración)
- `backend/adapters/egestiona/flows.py` (manejo de errores mejorado)

## Conclusión

El helper está implementado con la nueva estrategia pero necesita ajustes en los selectores basados en el DOM real del iframe. La detección del modal funciona correctamente, pero la interacción con los elementos dentro del iframe requiere más investigación.


























