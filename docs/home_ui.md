# HOME UI + LLM Config/Status

## Descripción

La nueva interfaz HOME (`/`) proporciona un dashboard centralizado para CometLocal con:

- **Navegación completa**: Accesos directos a todas las pantallas del sistema
- **Configuración LLM persistente**: Gestión de servidor, modelo y parámetros
- **Monitor de estado LLM**: Verificación en tiempo real del estado del servidor externo

## Rutas Implementadas

### Frontend
- `GET /` - **HOME Dashboard** (nueva página principal)
- `GET /home` - Alias para HOME Dashboard
- `GET /index.html` - Chat UI (legacy)

### Backend APIs
- `GET /api/config/llm` - Obtiene configuración LLM actual
- `POST /api/config/llm` - Actualiza configuración LLM (persiste en disco)
- `GET /api/health/llm` - Verifica estado del servidor LLM externo

## Funcionalidades

### 1. Quick Links (Accesos Rápidos)
Navegación a todas las pantallas existentes:
- 💬 Chat Principal (`/index.html`)
- 📝 Form Sandbox (`/form-sandbox`)
- 🎓 CAE Training (`/training`)
- 🏢 Portal CAE A (`/simulation/portal_a/login.html`)
- 🏭 Portal CAE A v2 (`/simulation/portal_a_v2/login.html`)
- 📊 Runs Viewer (`/runs`)
- ⚙️ Configuración (`/config`)
- 📚 API Docs (`/docs`)
- ❤️ Health Check (`/health`)

### 2. Configuración LLM
Campos editables con persistencia:
- **Base URL**: URL del servidor LLM (ej: `http://127.0.0.1:1234/v1`)
- **API Key**: Clave de autenticación
- **Proveedor**: lm-studio, openai, anthropic, ollama
- **Modelo**: Nombre/identificador del modelo
- **Timeout**: Segundos de espera (1-300)

**Persistencia**: Se guarda automáticamente en `data/refs/llm_config.json`

### 3. Monitor de Estado LLM
Verificación automática cada 30 segundos:
- **Estado**: 🟢 Online / 🟡 Degradado / 🔴 Offline
- **Latencia**: Tiempo de respuesta en ms
- **Último check**: Timestamp del último chequeo
- **Servidor**: URL del servidor verificado
- **Botón manual**: "Verificar Ahora"

## Configuración Técnica

### Archivos
- `frontend/home.html` - UI principal del dashboard
- `backend/app.py` - APIs y rutas backend
- `backend/config.py` - Configuración LLM persistente
- `data/refs/llm_config.json` - Archivo de configuración persistente

### Dependencias
- `aiohttp` - Para health checks HTTP
- `openai` - Cliente LLM (ya existente)

## Cómo Probar

### 1. Levantar Backend
```bash
cd CometLocal
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

### 2. Acceder al Dashboard
- Abrir `http://127.0.0.1:8000/` en navegador
- Verificar que se muestran todos los Quick Links
- Verificar que se carga la configuración LLM

### 3. Probar Configuración
- Cambiar Base URL a `http://127.0.0.1:9999/v1` (puerto inexistente)
- Guardar configuración
- Verificar que el estado cambia a 🔴 Offline
- Reiniciar backend y verificar que la configuración persiste

### 4. Probar Estado LLM
- Configurar URL válida de servidor LLM (ej: LM Studio en puerto 1234)
- Verificar que el estado muestra 🟢 Online con latencia
- Usar botón "Verificar Ahora" para actualización manual

## Estados del Monitor LLM

### Online (🟢)
- Respuesta HTTP 200 del endpoint `/models`
- Se muestra latencia en ms
- Estado: "online"

### Degradado (🟡)
- Respuesta HTTP no 200 pero válida
- Se muestra código de error HTTP
- Estado: "degraded"

### Offline (🔴)
- Timeout o error de conexión
- Se muestra detalle del error
- Estado: "offline"

## API Reference

### GET /api/config/llm
**Respuesta:**
```json
{
  "base_url": "http://127.0.0.1:1234/v1",
  "api_key": "lm-studio",
  "provider": "lm-studio",
  "model": "local-model",
  "timeout_seconds": 30
}
```

### POST /api/config/llm
**Cuerpo:**
```json
{
  "base_url": "http://127.0.0.1:1234/v1",
  "api_key": "your-key",
  "provider": "lm-studio",
  "model": "model-name",
  "timeout_seconds": 30
}
```

**Respuesta:**
```json
{
  "status": "ok",
  "message": "LLM config updated successfully"
}
```

### GET /api/health/llm
**Respuesta:**
```json
{
  "ok": true,
  "latency_ms": 45,
  "base_url": "http://127.0.0.1:1234/v1",
  "status": "online"
}
```

O cuando offline:
```json
{
  "ok": false,
  "latency_ms": null,
  "base_url": "http://127.0.0.1:9999/v1",
  "status": "offline",
  "detail": "Timeout"
}
```

## Notas de Implementación

- **Thread Safety**: El health check usa aiohttp con timeout corto para evitar bloquear el servidor
- **Persistencia**: Configuración se guarda atómicamente en JSON
- **Fallback**: Si no hay configuración, usa valores por defecto
- **Auto-refresh**: UI actualiza estado cada 30 segundos automáticamente
- **Validación**: Campos requeridos se validan antes de guardar

## Troubleshooting

### Problema: APIs devuelven "Not Found"
- Verificar que el backend se reinició completamente
- Revisar logs del servidor por errores de importación

### Problema: Configuración no persiste
- Verificar permisos de escritura en `data/refs/`
- Revisar que `llm_config.json` se crea correctamente

### Problema: Health check siempre offline
- Verificar que el servidor LLM esté ejecutándose
- Probar conectividad manual: `curl http://127.0.0.1:1234/v1/models`
- Revisar configuración de firewall/antivirus
