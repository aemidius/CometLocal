# Explicación: Estado de Tramitación vs Estado de Validez

## Resumen

En el sistema de documentos existen **dos conceptos de "estado"** que deben distinguirse claramente:

1. **Estado de Tramitación** (Workflow Status) - EDITABLE
2. **Estado de Validez** (Validity Status) - READONLY (calculado)

## Estado de Tramitación (Workflow Status)

### ¿Qué es?

El estado de tramitación indica en qué fase del proceso interno se encuentra el documento, desde su preparación hasta su envío a plataformas externas (ej: CAE).

### Valores Posibles

| Valor | Label | Descripción |
|-------|-------|-------------|
| `draft` | Borrador | Datos en preparación |
| `reviewed` | Revisado | Verificado internamente |
| `ready_to_submit` | Listo para enviar | Preparado para plataforma CAE |
| `submitted` | Enviado | Ya subido/enviado a plataforma |

### Características

- ✅ **EDITABLE**: El usuario puede cambiar este estado manualmente
- 📝 **Propósito**: Seguimiento interno del proceso de preparación y envío
- 🔄 **Flujo**: Generalmente va de Borrador → Revisado → Listo para enviar → Enviado
- ⚠️ **NO afecta caducidad**: Este estado no influye en cuándo caduca el documento

### Dónde se muestra

- Modal "Editar documento" (editable)
- Tabla "Buscar documentos" (opcional: badge "Enviado" si `submitted`)

## Estado de Validez (Validity Status)

### ¿Qué es?

El estado de validez indica si el documento está vigente, próximo a expirar o ya expirado, basado en la fecha de caducidad calculada.

### Valores Posibles

| Valor | Label | Badge | Descripción |
|-------|-------|-------|-------------|
| `VALID` | Válido | 🟢 Verde | Documento vigente |
| `EXPIRING_SOON` | Expira pronto | 🟡 Amarillo | Expira dentro del threshold (default: 30 días) |
| `EXPIRED` | Expirado | 🔴 Rojo | Ya expirado |
| `UNKNOWN` | Desconocido | ⚪ Gris | No se puede calcular (falta información) |

### Características

- 🔒 **READONLY**: Se calcula automáticamente, no es editable
- 📅 **Basado en fechas**: Depende de `validity_end_date` calculada desde:
  - `computed_validity.valid_to`
  - `validity_override.valid_to` (si existe override manual)
- 🧮 **Cálculo dinámico**: Se recalcula automáticamente al cambiar fechas
- ⏰ **Threshold configurable**: "Expira pronto" usa threshold (default: 30 días)

### Dónde se muestra

- Tabla "Buscar documentos" (badge con color)
- Modal "Editar documento" (readonly, con fecha de caducidad y días restantes)
- Vista "Calendario / Pendientes" (tabs: Expirados, Expiran pronto)

## Comparación Visual

### En el Modal "Editar documento"

```
┌─────────────────────────────────────────┐
│ Estado de validez (calculado)           │
│ 🟢 Válido                               │
│ Caduca: 2025-12-31                      │
│ 45 días restantes                       │
│ Este estado se calcula automáticamente. │
│ No es editable.                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Estado de tramitación                   │
│ [Select: Borrador ▼]                    │
│                                         │
│ Borrador: Datos en preparación          │
│ Revisado: Verificado internamente      │
│ Listo para enviar: Preparado para CAE  │
│ Enviado: Ya subido/enviado             │
│                                         │
│ Nota: Este estado no afecta a la       │
│ caducidad. La caducidad depende de     │
│ las fechas.                             │
└─────────────────────────────────────────┘
```

## Ejemplos de Uso

### Ejemplo 1: Documento en preparación

- **Estado de tramitación**: `draft` (Borrador)
- **Estado de validez**: `VALID` (Válido hasta 2025-12-31)
- **Interpretación**: El documento está en preparación pero aún es válido.

### Ejemplo 2: Documento listo para enviar pero próximo a expirar

- **Estado de tramitación**: `ready_to_submit` (Listo para enviar)
- **Estado de validez**: `EXPIRING_SOON` (Expira en 15 días)
- **Interpretación**: Está listo para enviar pero debe hacerse pronto porque expira.

### Ejemplo 3: Documento enviado pero expirado

- **Estado de tramitación**: `submitted` (Enviado)
- **Estado de validez**: `EXPIRED` (Expirado hace 10 días)
- **Interpretación**: Ya fue enviado pero ha expirado. Puede necesitar renovación.

## Reglas de Negocio

1. **Independencia**: El estado de tramitación NO afecta al estado de validez
2. **Caducidad**: Solo las fechas (`issue_date`, `validity_start_date`, `period_key`) afectan la caducidad
3. **Cálculo automático**: El estado de validez se recalcula automáticamente al cambiar fechas
4. **Workflow**: El estado de tramitación puede cambiar independientemente de la validez

## Implementación Técnica

### Backend

- **Estado de tramitación**: Campo `status` en `DocumentInstanceV1` (enum `DocumentStatusV1`)
- **Estado de validez**: Calculado por `calculate_document_status()` en `document_status_calculator_v1.py`

### Frontend

- **Estado de tramitación**: Select editable en modal
- **Estado de validez**: Badge readonly con información calculada

## Conclusión

La separación clara entre estos dos conceptos permite:
- ✅ Seguimiento interno del proceso (tramitación)
- ✅ Control de caducidad basado en fechas (validez)
- ✅ Mejor UX: el usuario entiende qué puede editar y qué es automático
- ✅ Prevención de errores: no se puede "editar" un estado calculado







