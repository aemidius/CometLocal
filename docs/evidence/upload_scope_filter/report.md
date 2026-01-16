# Reporte de Pruebas E2E - Prefiltro por Scope

## Fecha
2026-01-08T21:11:37.591Z

## Objetivo
Verificar que el prefiltro por scope (Empresa/Trabajador/Todos) funciona correctamente en la pantalla de subida de documentos, incluyendo autodetección y bloqueo.

## Pruebas Realizadas

### A) Prefiltro Empresa
- **Objetivo**: Verificar que al seleccionar "Empresa", solo se muestran tipos con scope="company"
- **Resultado**: ✅ El dropdown solo muestra tipos de empresa
- **Evidencia**: `02_filter_company_selected.png`

### B) Prefiltro Trabajador
- **Objetivo**: Verificar que al seleccionar "Trabajador", solo se muestran tipos con scope="worker"
- **Resultado**: ✅ El dropdown solo muestra tipos de trabajador
- **Evidencia**: `04_filter_worker_selected.png`

### C) Cambio de prefiltro limpia tipo incompatible
- **Objetivo**: Verificar que al cambiar el prefiltro, si el tipo seleccionado no coincide, se limpia y muestra error
- **Resultado**: ✅ El tipo se limpia correctamente
- **Evidencia**: `07_after_switch_to_worker.png`

### D) Autodetección bloquea prefiltro
- **Objetivo**: Verificar que cuando se detecta un tipo automáticamente, el prefiltro se ajusta y queda bloqueado
- **Resultado**: ✅ El prefiltro se ajusta al scope detectado y queda realmente bloqueado
- **Evidencia**: `09_autodetect_locked.png`

## Criterios de Aceptación Verificados

✅ Con prefiltro Empresa, jamás se ve un tipo de Trabajador en la lista
✅ Con prefiltro Trabajador, jamás se ve un tipo de Empresa en la lista
✅ El flujo de subida sigue funcionando igual
✅ No hay regresión del autocomplete por teclado
✅ Al cambiar prefiltro con tipo incompatible, se limpia y muestra error
✅ Autodetección => scopeFilter se ajusta y queda bloqueado realmente
✅ Cambio manual de tipo => desbloquea y alinea scopeFilter con el tipo elegido

## Archivos de Evidencia

- `01_initial_upload.png` - Estado inicial después de subir PDF
- `02_filter_company_selected.png` - Prefiltro Empresa seleccionado
- `03_company_type_selected.png` - Tipo empresa seleccionado
- `04_filter_worker_selected.png` - Prefiltro Trabajador seleccionado
- `05_worker_filter_applied.png` - Filtro trabajador aplicado
- `06_company_type_before_switch.png` - Tipo empresa antes de cambiar filtro
- `07_after_switch_to_worker.png` - Después de cambiar a filtro trabajador
- `08_after_autodetect_upload.png` - Después de subir PDF con autodetección
- `09_autodetect_locked.png` - Prefiltro bloqueado por autodetección
- `10_after_manual_change_unlocked.png` - Después de cambiar tipo manualmente (desbloqueado)

## Test IDs Añadidos

- `data-testid="scope-filter-pills"` - Contenedor de pills
- `data-testid="scope-pill-all"` - Pill "Todos"
- `data-testid="scope-pill-company"` - Pill "Empresa"
- `data-testid="scope-pill-worker"` - Pill "Trabajador"
- `data-testid="type-autocomplete"` - Selector de tipo
- `data-testid="type-option-{type_id}"` - Opción de tipo
- `data-testid="detected-badge"` - Badge "Detectado"
- `data-testid="type-error"` - Mensaje de error de tipo

## Notas

- Los tipos de prueba se crean automáticamente si no existen
- Se usa un PDF dummy para las pruebas
- El test D usa un alias único (`ALIAS_DETECT_WORKER_123`) para garantizar autodetección determinista
- Todos los tests usan data-testids para evitar flakiness
- No se usan sleeps arbitrarios, solo waits con expect()
