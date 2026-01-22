# Limpieza de Datos Demo/Seed (C2.36.1)

**Fecha:** 2026-01-22T23:41:20.672617
**Script:** `scripts/cleanup_demo_data.py`
**Modo:** APPLY (ejecutado)

## Resumen

### Tipos de Documento
- **Antes:** 13
- **Eliminados:** 4
- **Protegidos:** 0
- **Después:** 9

### Documentos
- **Antes:** 1
- **Eliminados:** 1
- **Después:** 0

### Archivos PDF
- **Antes:** 89
- **Eliminados:** 12
- **Después:** 77

## Tipos Eliminados


### TEST_TYPE
- **Nombre:** Test Type
- **Descripción:** 
- **Scope:** company
- **Motivo:** demo_type_no_references
- **Patrón:** TEST_TYPE...


### TEST_TYPE_NO_DUP
- **Nombre:** Test Type No Dup
- **Descripción:** 
- **Scope:** company
- **Motivo:** demo_type_no_references
- **Patrón:** TEST_TYPE_...


### TEST_TYPE_NO_DELETE
- **Nombre:** Test Type No Delete
- **Descripción:** 
- **Scope:** company
- **Motivo:** demo_type_no_references
- **Patrón:** TEST_TYPE_...


### TEST_TYPE_ADD
- **Nombre:** Test Type Add
- **Descripción:** 
- **Scope:** company
- **Motivo:** demo_type_no_references
- **Patrón:** TEST_TYPE_...


## Tipos Protegidos (NO eliminados)


## Documentos Eliminados


- **doc_id:** real_doc_001
- **file_name:** real_doc_001.pdf
- **type_id:** ss_receipt
- **company_key:** None
- **person_key:** worker_real_001


## Archivos PDF Eliminados

- D:\Proyectos_Cursor\CometLocal\data\test_preview_esc.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_clear_all_1.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_nav_1.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_validity_start.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_dummy.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_nav_3.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_validity_persistence.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_drag_drop.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_preview.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_nav_2.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_rc.pdf
- D:\Proyectos_Cursor\CometLocal\data\test_clear_all_2.pdf

## Patrones Utilizados

### Tipos
- TEST_
- T999_
- E2E_TYPE_
- E2E_
- DEMO_

### Nombres
- Test Type
- Test 
- Demo 
- E2E Test

### Documentos
- TEST_DOC_
- E2E_DOC_
- T999_DOC_
- DEMO_DOC_

### Archivos
- test_
- real_doc_
- e2e_
- demo_
- worker_real_

## Confirmación

OK: **No se ha eliminado ningún dato creado por el usuario.**

Todos los elementos eliminados cumplían patrones de prueba/demo y no tenían referencias en datos reales.
