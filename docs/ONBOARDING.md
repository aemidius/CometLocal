# Onboarding — CometLocal (5 minutos)

**Objetivo:** Probar CometLocal en ≤5 minutos sin configurar datos reales.

---

## Requisitos

- Python 3.10+
- Dependencias instaladas: `pip install -r requirements.txt`

---

## Inicio Rápido

### 1. Arrancar en modo DEMO

```bash
# Windows
set ENVIRONMENT=demo
python -m uvicorn backend.app:app --reload

# Linux/Mac
export ENVIRONMENT=demo
python -m uvicorn backend.app:app --reload
```

### 2. Abrir la aplicación

Abre tu navegador en: **http://127.0.0.1:8000/repository_v3.html**

### 3. Verás:

- **Badge "Modo DEMO"** en la esquina superior izquierda
- **Banner de bienvenida** con botón "⚡ Ejecutar run demo"
- **Contexto demo auto-seleccionado:**
  - Empresa propia: "Empresa Demo SL"
  - Plataforma: "Plataforma Demo"
  - Empresa coordinada: "Cliente Demo SA"

---

## Qué Probar (3 pasos)

### Paso 1: Ejecutar Run Demo

1. Haz clic en **"⚡ Ejecutar run demo"** en el banner
2. Espera a que se complete (dry-run, no toca CAE real)
3. Se abrirá automáticamente el `summary.md` en una nueva pestaña

### Paso 2: Ver Resultados

- **Summary.md**: Resumen legible del run
- **Evidencias**: En `data/tenants/<tenant_id>/runs/<run_id>/evidence/`
- **Input/Result JSON**: En el mismo directorio del run

### Paso 3: Explorar UI

- **Vista "Ejecuciones"**: Lista de runs ejecutados
- **Vista "Programación"**: Schedules configurados (demo schedule deshabilitado por defecto)
- **Vista "Documentos"**: Tipos y documentos demo creados

---

## Dónde Ver Resultados

### Runs

```
data/tenants/<tenant_id>/runs/<YYYYMMDD_HHMMSS>__<run_id>/
├── input.json          # Input del run
├── result.json         # Resultado del run
├── summary.md          # Resumen legible (abre automáticamente)
├── summary.json        # Summary en JSON
├── evidence/           # Evidencias generadas (si aplica)
└── export/             # Exportaciones (si aplica)
```

### Dataset Demo

El dataset demo incluye:

- **Empresa propia**: "Empresa Demo SL" (`DEMO_COMPANY`)
- **Plataforma**: "Plataforma Demo" (`demo_platform`)
- **Empresa coordinada**: "Cliente Demo SA" (`DEMO_CLIENT`)
- **3 tipos de documentos**: Recibo SS, Contrato, Seguro
- **3 documentos demo**: Metadata sin PDFs reales
- **1 plan CAE demo**: `demo_plan_001`
- **1 schedule demo**: Deshabilitado por defecto

---

## Notas

- **Modo DEMO**: No ejecuta integraciones reales (uploader deshabilitado)
- **Dry-run**: Los runs demo son siempre dry-run (simulación)
- **Datos seguros**: El dataset demo no afecta datos reales
- **Primera vez**: El dataset demo se crea automáticamente al arrancar con `ENVIRONMENT=demo`

---

## Siguiente Paso

Una vez probado el demo, puedes:

1. **Configurar datos reales**: Edita `data/refs/org.json`, `platforms.json`, etc.
2. **Arrancar sin demo**: `ENVIRONMENT=dev` o sin variable
3. **Revisar documentación**: `docs/` para más detalles

---

## Troubleshooting

### El banner no aparece

- Verifica que `ENVIRONMENT=demo` está configurado
- Recarga la página (F5)
- Revisa la consola del navegador (F12)

### Error al ejecutar run demo

- Verifica que el backend está corriendo
- Revisa los logs del backend
- Asegúrate de que el dataset demo se creó correctamente

### No se abre summary.md

- Verifica que el run se completó correctamente
- Revisa `data/tenants/<tenant_id>/runs/` para ver los runs creados
- Abre manualmente el `summary.md` desde el directorio del run
