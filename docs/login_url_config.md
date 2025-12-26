# Configuración de URL de Login para eGestiona

## Problema
El sistema usaba URLs de login hardcodeadas que no funcionan para tenants específicos de eGestiona.

## Solución
Se añade un campo `login_url` configurable en `data/refs/platforms.json`.

## Configuración

### 1. Obtener la URL correcta
1. Abre tu navegador web
2. Ve al sitio de eGestiona de tu empresa
3. Copia la URL completa de la página de login (incluyendo parámetros de query)

**Ejemplo de URL válida:**
```
https://tu-empresa.egestiona.es/login?origen=subcontrata
```

### 2. Configurar en platforms.json

Edita el archivo `data/refs/platforms.json`:

```json
{
  "schema_version": "v1",
  "platforms": [
    {
      "key": "egestiona",
      "base_url": "https://coordinate.egestiona.es/login?origen=subcontrata",
      "login_url": "https://tu-empresa.egestiona.es/login?origen=subcontrata",
      "login_fields": {
        ...
      },
      "coordinations": [
        ...
      ]
    }
  ]
}
```

### 3. Campo login_url

- **Tipo:** `string` (opcional)
- **Prioridad:** Si está presente, se usa esta URL en lugar de `base_url` o defaults
- **Requerido:** Si no se configura y `base_url` no funciona, el sistema abortará con mensaje claro
- **Ejemplo:** `"https://midominio.egestiona.es/login?origen=subcontrata"`

### 4. Verificación

Después de configurar, ejecuta un test:
```bash
curl -X POST http://127.0.0.1:8001/runs/egestiona/send_pending_document
```

Si la URL es correcta, deberías ver que el navegador navega a la página de login correcta antes del error de autenticación.

### 5. Troubleshooting

**Error: "No login URL configured for platform 'egestiona'"**
- Añade el campo `login_url` a tu configuración

**Error: "AUTH_FAILED"**
- Verifica que la URL sea correcta (puedes copiarla del navegador)
- Asegúrate de que la URL no requiera VPN o acceso especial

**Login funciona pero luego falla:**
- La URL de login es correcta, pero las credenciales no lo son
- Configura credenciales válidas en secrets
