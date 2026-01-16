# Implementación: Selects de Empresa/Trabajador y Ocultar Campo Mes/Año

## Estado: IMPLEMENTADO (pendiente reinicio servidor para pruebas)

## Cambios Realizados

### 1. Backend - Endpoint `/api/repository/subjects`

**Archivo**: `backend/repository/document_repository_routes.py`

- ✅ Añadido endpoint `GET /api/repository/subjects`
- ✅ Devuelve estructura:
  ```json
  {
    "companies": [{"id": "F63161988", "name": "Tedelab Ingeniería SCCL", "tax_id": "F63161988"}],
    "workers_by_company": {
      "F63161988": [
        {"id": "erm", "name": "Emilio Roldán Molina", "tax_id": "37330395S", "role": "Ingeniero"},
        {"id": "ovo", "name": "Oriol Verdés Ochoa", "tax_id": "38133024J", "role": "Ingeniero"}
      ]
    }
  }
  ```

### 2. Frontend - Carga de Subjects

**Archivo**: `frontend/repository_v3.html`

- ✅ Añadida variable global `uploadSubjects`
- ✅ Carga de subjects en `initUploadWizard`:
  ```javascript
  const subjectsResponse = await fetch(`${BACKEND_URL}/api/repository/subjects`);
  uploadSubjects = await subjectsResponse.json();
  ```

### 3. Frontend - Selects de Empresa y Trabajador

**Archivo**: `frontend/repository_v3.html`

- ✅ Reemplazado input de texto por selects:
  - **Empresa**: Select visible si hay >1 empresa, oculto (hidden input) si hay solo 1
  - **Trabajador**: Select siempre visible cuando `scope === 'worker'`
  - **Dependencia**: Select de trabajador se deshabilita si no hay empresa seleccionada (y hay >1 empresa)

- ✅ Funciones añadidas:
  - `updateUploadCompanyFromSelect(fileId, companyKey)`: Maneja cambio de empresa y repobla trabajadores
  - `updateUploadWorker(fileId, workerId)`: Actualiza trabajador seleccionado

### 4. Frontend - Ocultar Campo Mes/Año

**Archivo**: `frontend/repository_v3.html`

- ✅ Lógica añadida en `renderUploadFiles()`:
  ```javascript
  const calculatesFromName = type?.validity_policy?.basis === 'name_date' || 
                           (type?.validity_policy?.monthly?.month_source === 'name_date');
  const shouldHidePeriod = calculatesFromName && file.issue_date;
  ```

- ✅ Derivación automática de `period_key`:
  ```javascript
  if (shouldHidePeriod && file.issue_date && !file.period_key) {
      const date = new Date(file.issue_date);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      file.period_key = `${year}-${month}`;
  }
  ```

- ✅ Campo oculto en UI:
  ```html
  ${shouldHidePeriod ? `
      <div class="wizard-question" style="display: none;">
          <input type="hidden" id="upload-period-${file.id}" value="${file.period_key || ''}">
      </div>
  ` : ''}
  ```

## Problemas Conocidos

1. **Endpoint 404**: El servidor necesita reiniciarse para que el endpoint `/api/repository/subjects` esté disponible
2. **Issue date no visible**: El `issue_date` se parsea correctamente (`2025-11-27`) pero puede no mostrarse en el input si el formato no coincide exactamente con `YYYY-MM-DD`

## Próximos Pasos

1. Reiniciar servidor backend
2. Ejecutar test E2E: `npm run test:e2e:subjects`
3. Verificar que:
   - Endpoint `/api/repository/subjects` responde correctamente
   - Selects de empresa y trabajador aparecen
   - Campo mes/año se oculta cuando corresponde
   - `issue_date` se muestra correctamente en el input

## Archivos Modificados

1. `backend/repository/document_repository_routes.py` - Endpoint `/subjects`
2. `frontend/repository_v3.html` - Selects y lógica de ocultar campo mes/año
3. `tests/e2e_upload_subjects.spec.js` - Test E2E creado
4. `package.json` - Script `test:e2e:subjects` añadido














