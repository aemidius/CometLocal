# Discrepancias Encontradas en HANDOFF_TECNICO_FUNCIONAL_COMPLETO.md v4.0

**Fecha de revisión:** 2026-01-20  
**Versión revisada:** v4.0  
**Versión corregida:** v4.1

---

## 1. OMISIÓN CRÍTICA: C2.34 (Matching Debug Report)

**Severidad:** ALTA

**Descripción:**
La funcionalidad C2.34 (Observabilidad de Matching) NO está documentada en el handoff, a pesar de ser una funcionalidad completa y activa en el sistema.

**Evidencia:**
- Existe `docs/evidence/c2_34/README.md` con documentación completa
- Existe `backend/repository/matching_debug_codes_v1.py` con taxonomía de códigos
- Existe `backend/repository/document_matcher_v1.py` con función `build_matching_debug_report()`
- Existe `backend/api/matching_debug_routes.py` con endpoints API
- Existe `frontend/repository_v3.html` con función `renderMatchingDebugPanel()`
- Existe `tests/matching_debug_report_ui.spec.js` con tests E2E

**Qué falta:**
- Sección en "2. Funcionalidades Principales" sobre Matching Debug Report
- Endpoint `/api/runs/{run_id}/matching_debug` en "7. APIs y Endpoints"
- Referencia en "9. Flujos Principales" sobre flujo de debug report
- Test `matching_debug_report_ui.spec.js` en "12. Testing"
- Componente `DocumentMatcherV1.build_matching_debug_report()` en "6. Componentes Principales"

**Corrección necesaria:**
Añadir sección completa sobre C2.34 con:
- Descripción de la funcionalidad
- Códigos de razón implementados (9 códigos)
- Panel UI "¿Por qué no se ha subido?"
- Endpoints API
- Flujo de generación de reporte

---

## 2. C2.35.2 (TrainingGate) - Detalle Insuficiente

**Severidad:** MEDIA

**Descripción:**
C2.35.2 está mencionado en sección 10.3 pero no está en "2. Funcionalidades Principales" como funcionalidad independiente.

**Evidencia:**
- Existe `docs/evidence/c2_35/README.md` con sección C2.35.2
- Existe `tests/training_no_overlap.spec.js` con tests E2E
- Existe código en `frontend/repository_v3.html` con TrainingGate

**Qué falta:**
- Mención explícita en "2. Funcionalidades Principales" como subsección de Training
- Referencia más clara a la solución del problema de solape

**Corrección necesaria:**
Añadir subsección 2.4.1 sobre C2.35.2 con:
- Problema histórico (solape legacy + C2.35)
- Solución TrainingGate
- Hard-guard visual

---

## 3. Tests E2E - Omisión de matching_debug_report_ui.spec.js

**Severidad:** BAJA

**Descripción:**
El test E2E `matching_debug_report_ui.spec.js` no está listado en la sección de tests.

**Evidencia:**
- Existe `tests/matching_debug_report_ui.spec.js`

**Corrección necesaria:**
Añadir a la lista de tests principales en sección 12.1.

---

## 4. Endpoints API - Omisión de matching_debug

**Severidad:** MEDIA

**Descripción:**
Los endpoints de matching debug no están documentados en "7. APIs y Endpoints".

**Evidencia:**
- Existe `backend/api/matching_debug_routes.py` con endpoints:
  - `GET /api/runs/{run_id}/matching_debug`
  - `GET /api/runs/{run_id}/matching_debug/{item_id}`

**Corrección necesaria:**
Añadir sección 7.8 "Matching Debug (C2.34)" con tabla de endpoints.

---

## 5. Componentes Principales - Omisión de build_matching_debug_report

**Severidad:** BAJA

**Descripción:**
La función `build_matching_debug_report()` de `DocumentMatcherV1` no está mencionada.

**Corrección necesaria:**
Añadir mención en sección 6.1 o crear subsección sobre matching debug.

---

## Resumen de Correcciones

| Discrepancia | Severidad | Acción |
|--------------|-----------|--------|
| C2.34 no documentado | ALTA | Añadir sección completa en funcionalidades principales |
| C2.35.2 detalle insuficiente | MEDIA | Añadir subsección en funcionalidades principales |
| Test E2E omitido | BAJA | Añadir a lista de tests |
| Endpoints API omitidos | MEDIA | Añadir sección de endpoints matching_debug |
| Componente omitido | BAJA | Añadir mención en componentes |

---

## Confirmación

**Estado:** Todas las discrepancias han sido identificadas y corregidas en v4.1.
