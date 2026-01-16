# Conector e-gestiona

## Estado actual (Sprint C2.12.1)

**STUB FUNCIONAL**: El conector está implementado como esqueleto que:
- Produce evidencias (screenshots)
- Ejecuta el pipeline completo (login → pending → extract → match → upload)
- NO automatiza la web real aún

## Próximos pasos (Sprint C2.12.2)

Para automatizar e-gestiona end-to-end, implementar:

1. **Login real** (`connector.py::login`):
   - Navegar a URL de login
   - Rellenar formulario con credenciales
   - Manejar captchas/2FA si aplica
   - Esperar post-login

2. **Navegación a pendientes** (`connector.py::navigate_to_pending`):
   - Navegar a sección de documentos pendientes
   - Manejar frames si aplica (e-gestiona usa frames)
   - Esperar carga de tabla/grid

3. **Extracción de requisitos** (`connector.py::extract_pending`):
   - Parsear tabla/grid de pendientes
   - Extraer: tipo doc, trabajador/empresa, fecha vencimiento, estado
   - Normalizar a `PendingRequirement`

4. **Matching mejorado** (`connector.py::match_repository`):
   - Usar `DocumentMatcherV1` completo
   - Considerar empresa, trabajador, período, fechas
   - Retornar confidence scores

5. **Subida real** (`connector.py::upload_one`):
   - Navegar a formulario de subida
   - Seleccionar trabajador/empresa
   - Seleccionar tipo de documento
   - Subir archivo desde repositorio
   - Confirmar y verificar éxito

## Estructura

- `connector.py`: Implementación principal
- `tenants.py`: Configuración por empresa (futuro)
- `selectors.py`: Selectores CSS/XPath (futuro)
- `README.md`: Esta documentación
