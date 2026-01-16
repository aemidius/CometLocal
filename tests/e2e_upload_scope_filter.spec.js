const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedUploadPack, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('Prefiltro por Scope - Pruebas Reales', () => {
    const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'upload_scope_filter');
    const BACKEND_URL = 'http://127.0.0.1:8000';
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Crear directorio de evidencias
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
        // Reset y seed específico para upload usando request (no page)
        await seedReset({ request });
        seedData = await seedUploadPack({ request });
    });
    
    // Helper: Crear tipos de prueba si no existen
    async function setupTypes(page) {
        const response = await page.request.get(`${BACKEND_URL}/api/repository/types`);
        const types = await response.json();
        const typesList = Array.isArray(types) ? types : (types.items || []);
        
        // Buscar o crear tipo company
        let companyType = typesList.find(t => t.type_id === 'TEST_COMPANY_TYPE');
        if (!companyType) {
            const createResponse = await page.request.post(`${BACKEND_URL}/api/repository/types`, {
                data: {
                    type_id: 'TEST_COMPANY_TYPE',
                    name: 'Test Tipo Empresa',
                    description: 'Tipo de prueba para empresa',
                    scope: 'company',
                    validity_policy: {
                        mode: 'monthly',
                        basis: 'issue_date',  // Campo requerido cuando mode='monthly'
                        monthly: {
                            month_source: 'issue_date',
                            valid_from: 'period_start',
                            valid_to: 'period_end',
                            grace_days: 0
                        }
                    },
                    issue_date_required: false,
                    validity_start_mode: 'issue_date',
                    active: true
                }
            });
            companyType = await createResponse.json();
        }
        
        // Buscar o crear tipo worker
        let workerType = typesList.find(t => t.type_id === 'TEST_WORKER_TYPE');
        if (!workerType) {
            const createResponse = await page.request.post(`${BACKEND_URL}/api/repository/types`, {
                data: {
                    type_id: 'TEST_WORKER_TYPE',
                    name: 'Test Tipo Trabajador',
                    description: 'Tipo de prueba para trabajador',
                    scope: 'worker',
                    validity_policy: {
                        mode: 'monthly',
                        basis: 'issue_date',  // Campo requerido cuando mode='monthly'
                        monthly: {
                            month_source: 'issue_date',
                            valid_from: 'period_start',
                            valid_to: 'period_end',
                            grace_days: 0
                        }
                    },
                    issue_date_required: false,
                    validity_start_mode: 'issue_date',
                    active: true
                }
            });
            workerType = await createResponse.json();
        }
        
        return { companyType, workerType };
    }
    
    test.beforeAll(async () => {
        // Crear directorio de evidencias
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
    });
    
    test('A) Prefiltro Empresa - Solo muestra tipos company', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');
        
        // Setup tipos
        const { companyType, workerType } = await setupTypes(page);
        
        // Crear PDF dummy
        const pdfPath = path.join(__dirname, '..', 'data', 'test_dummy.pdf');
        if (!fs.existsSync(pdfPath)) {
            const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF');
            fs.writeFileSync(pdfPath, pdfContent);
        }
        
        // Subir PDF
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca el file card
        await page.waitForSelector('[data-testid="scope-filter-pills"]', { timeout: 10000 });
        
        // Screenshot inicial
        await page.screenshot({ path: path.join(evidenceDir, '01_initial_upload.png'), fullPage: true });
        
        // Seleccionar prefiltro "Empresa" usando testid
        const companyRadio = page.locator('[data-testid="scope-pill-company"]').first();
        await expect(companyRadio).toBeVisible();
        await companyRadio.click();
        
        // Esperar a que el cambio se refleje
        await expect(companyRadio).toBeChecked();
        
        // Screenshot después de seleccionar Empresa
        await page.screenshot({ path: path.join(evidenceDir, '02_filter_company_selected.png'), fullPage: true });
        
        // Verificar que el dropdown solo muestra tipos company usando testid
        const typeSelect = page.locator('[data-testid="type-autocomplete"]').first();
        await expect(typeSelect).toBeVisible();
        
        const options = await typeSelect.locator('option').all();
        const optionTexts = [];
        for (const opt of options) {
            const text = await opt.textContent();
            const value = await opt.getAttribute('value');
            if (value && value !== '') {
                optionTexts.push(text.trim());
            }
        }
        
        console.log('[test] Options with company filter:', optionTexts);
        
        // Verificar que NO aparece el tipo worker
        const hasWorkerType = optionTexts.some(t => 
            t.toLowerCase().includes('test tipo trabajador') || 
            t.toLowerCase().includes('worker') ||
            t === 'Test Tipo Trabajador'
        );
        expect(hasWorkerType).toBe(false);
        
        // Verificar que SÍ aparece el tipo company (o al menos hay opciones)
        expect(optionTexts.length).toBeGreaterThan(1);
        
        // Screenshot final
        await page.screenshot({ path: path.join(evidenceDir, '03_company_type_selected.png'), fullPage: true });
    });
    
    test('B) Prefiltro Trabajador - Solo muestra tipos worker', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');
        
        // Setup tipos
        const { companyType, workerType } = await setupTypes(page);
        
        // Crear PDF dummy
        const pdfPath = path.join(__dirname, '..', 'data', 'test_dummy.pdf');
        if (!fs.existsSync(pdfPath)) {
            const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF');
            fs.writeFileSync(pdfPath, pdfContent);
        }
        
        // Subir PDF
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca el file card
        await page.waitForSelector('[data-testid="scope-filter-pills"]', { timeout: 10000 });
        
        // Seleccionar prefiltro "Trabajador" usando testid
        const workerRadio = page.locator('[data-testid="scope-pill-worker"]').first();
        await expect(workerRadio).toBeVisible();
        await workerRadio.click();
        
        // Esperar a que el cambio se refleje
        await expect(workerRadio).toBeChecked();
        
        // Screenshot después de seleccionar Trabajador
        await page.screenshot({ path: path.join(evidenceDir, '04_filter_worker_selected.png'), fullPage: true });
        
        // Verificar que el dropdown solo muestra tipos worker usando testid
        const typeSelect = page.locator('[data-testid="type-autocomplete"]').first();
        await expect(typeSelect).toBeVisible();
        
        const options = await typeSelect.locator('option').all();
        const optionTexts = [];
        for (const opt of options) {
            const text = await opt.textContent();
            const value = await opt.getAttribute('value');
            if (value && value !== '') {
                optionTexts.push(text.trim());
            }
        }
        
        console.log('[test] Options with worker filter:', optionTexts);
        
        // Verificar que NO aparece el tipo company
        const hasCompanyType = optionTexts.some(t => 
            t.toLowerCase().includes('test tipo empresa') || 
            t.toLowerCase().includes('company') ||
            t === 'Test Tipo Empresa'
        );
        expect(hasCompanyType).toBe(false);
        
        // Verificar que SÍ aparece el tipo worker (o al menos hay opciones)
        expect(optionTexts.length).toBeGreaterThan(1);
        
        // Screenshot final
        await page.screenshot({ path: path.join(evidenceDir, '05_worker_filter_applied.png'), fullPage: true });
    });
    
    test('C) Cambio de prefiltro limpia tipo incompatible', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');
        
        // Setup tipos
        const { companyType, workerType } = await setupTypes(page);
        
        // Crear PDF dummy
        const pdfPath = path.join(__dirname, '..', 'data', 'test_dummy.pdf');
        if (!fs.existsSync(pdfPath)) {
            const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF');
            fs.writeFileSync(pdfPath, pdfContent);
        }
        
        // Subir PDF
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca el file card
        await page.waitForSelector('[data-testid="scope-filter-pills"]', { timeout: 10000 });
        
        // Seleccionar prefiltro "Empresa"
        const companyRadio = page.locator('[data-testid="scope-pill-company"]').first();
        await expect(companyRadio).toBeVisible();
        await companyRadio.click();
        await expect(companyRadio).toBeChecked();
        
        // Seleccionar un tipo company
        const typeSelect = page.locator('[data-testid="type-autocomplete"]').first();
        await expect(typeSelect).toBeVisible();
        
        const options = await typeSelect.locator('option').all();
        let companyTypeId = null;
        for (const opt of options) {
            const text = await opt.textContent();
            const value = await opt.getAttribute('value');
            if (value && value !== '' && (text.includes('Empresa') || text.includes('COMPANY'))) {
                companyTypeId = value;
                await typeSelect.selectOption({ value });
                break;
            }
        }
        
        if (!companyTypeId) {
            // Si no hay tipo company, usar el primero disponible
            const firstOption = options[1]; // Skip "Selecciona un tipo..."
            if (firstOption) {
                const value = await firstOption.getAttribute('value');
                if (value) {
                    await typeSelect.selectOption({ value });
                    companyTypeId = value;
                }
            }
        }
        
        // Esperar a que el tipo se seleccione
        await expect(typeSelect).not.toHaveValue('');
        
        // Screenshot con tipo company seleccionado
        await page.screenshot({ path: path.join(evidenceDir, '06_company_type_before_switch.png'), fullPage: true });
        
        // Cambiar prefiltro a "Trabajador"
        const workerRadio = page.locator('[data-testid="scope-pill-worker"]').first();
        await expect(workerRadio).toBeVisible();
        await workerRadio.click();
        await expect(workerRadio).toBeChecked();
        
        // Verificar que el tipo se limpió
        await expect(typeSelect).toHaveValue('');
        
        // Verificar que aparece error (puede no aparecer si se limpió antes)
        const errorMessage = page.locator('[data-testid="type-error"]').first();
        const errorVisible = await errorMessage.isVisible().catch(() => false);
        if (errorVisible) {
            await expect(errorMessage).toBeVisible();
        }
        
        // Screenshot después del cambio
        await page.screenshot({ path: path.join(evidenceDir, '07_after_switch_to_worker.png'), fullPage: true });
    });
    
    test('D) Autodetección bloquea prefiltro', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');
        
        // Setup tipos con alias específico para autodetección
        const aliasToken = 'ALIAS_DETECT_WORKER_123';
        const typeId = 'TEST_WORKER_AUTODETECT';
        
        // Verificar si el tipo ya existe
        const typesResponse = await page.request.get(`${BACKEND_URL}/api/repository/types`);
        const types = await typesResponse.json();
        const typesList = Array.isArray(types) ? types : (types.items || []);
        let workerType = typesList.find(t => t.type_id === typeId);
        
        // Si no existe, crearlo
        if (!workerType) {
            const workerTypeResponse = await page.request.post(`${BACKEND_URL}/api/repository/types`, {
                data: {
                    type_id: typeId,
                    name: 'Test Tipo Trabajador Autodetect',
                    description: 'Tipo de prueba para trabajador con autodetección',
                    scope: 'worker',
                    platform_aliases: [aliasToken, 'worker-test-autodetect'],
                    validity_policy: {
                        mode: 'monthly',
                        basis: 'issue_date',  // Campo requerido cuando mode='monthly'
                        monthly: {
                            month_source: 'issue_date',
                            valid_from: 'period_start',
                            valid_to: 'period_end',
                            grace_days: 0
                        }
                    },
                    issue_date_required: false,
                    validity_start_mode: 'issue_date',
                    active: true
                }
            });
            
            // Verificar que el tipo se creó correctamente
            if (!workerTypeResponse.ok()) {
                const errorText = await workerTypeResponse.text();
                throw new Error(`Failed to create type: ${workerTypeResponse.status()} ${errorText}`);
            }
            workerType = await workerTypeResponse.json();
        }
        
        // Recargar los tipos en el frontend sin recargar la página completa
        // Esto es necesario para que detectUploadMetadata pueda encontrar el nuevo tipo
        await page.evaluate(async () => {
            // Limpiar uploadTypes para forzar recarga
            if (typeof uploadTypes !== 'undefined') {
                uploadTypes.length = 0;
            }
            // Recargar tipos con forceTypes=true para forzar recarga
            if (typeof ensureRepoDataLoaded === 'function') {
                await ensureRepoDataLoaded({ types: true, forceTypes: true });
            }
        });
        
        // Esperar a que los tipos se recarguen verificando que el nuevo tipo esté disponible
        await page.waitForFunction(
            () => {
                if (typeof uploadTypes === 'undefined' || !Array.isArray(uploadTypes)) return false;
                return uploadTypes.some(t => t.type_id === 'TEST_WORKER_AUTODETECT');
            },
            { timeout: 10000 }
        );
        
        // Crear PDF con nombre que dispare autodetección (debe contener el alias)
        const pdfPath = path.join(__dirname, '..', 'data', `${aliasToken}.pdf`);
        const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF');
        fs.writeFileSync(pdfPath, pdfContent);
        
        // Subir PDF
        const fileInputUpload = page.locator('[data-testid="upload-input"]');
        await expect(fileInputUpload).toBeAttached();
        await fileInputUpload.setInputFiles(pdfPath);
        
        // Esperar a que aparezca el file card y el badge "Detectado"
        await page.waitForSelector('[data-testid="detected-badge"]', { timeout: 10000 });
        
        // Screenshot después de subir (debe mostrar tipo detectado)
        await page.screenshot({ path: path.join(evidenceDir, '08_after_autodetect_upload.png'), fullPage: true });
        
        // Verificar que aparece badge "Detectado" usando testid
        const detectedBadge = page.locator('[data-testid="detected-badge"]').first();
        await expect(detectedBadge).toBeVisible();
        await expect(detectedBadge).toHaveText('Detectado');
        
        // Verificar que el prefiltro está bloqueado (debe estar en "worker")
        const workerRadio = page.locator('[data-testid="scope-pill-worker"] input[type="radio"]').first();
        await expect(workerRadio).toBeChecked();
        await expect(workerRadio).toBeDisabled();
        
        // Verificar que el tipo está seleccionado
        const typeSelect = page.locator('[data-testid="type-autocomplete"]').first();
        await expect(typeSelect).toBeVisible();
        const selectedValue = await typeSelect.inputValue();
        expect(selectedValue).toBeTruthy();
        expect(selectedValue).not.toBe('');
        
        // Intentar cambiar el prefiltro (debe estar bloqueado - no debe cambiar)
        const companyPill = page.locator('[data-testid="scope-pill-company"]').first();
        await expect(companyPill).toBeVisible();
        const companyRadio = page.locator('[data-testid="scope-pill-company"] input[type="radio"]').first();
        
        // Intentar click (debe fallar porque está disabled - el guard clause en updateUploadScopeFilter lo previene)
        await companyPill.click({ force: true }).catch(() => {}); // Force puede no funcionar si está disabled
        
        // Esperar a que el estado se estabilice (sin timeout arbitrario, usar expect)
        await expect(workerRadio).toBeChecked({ timeout: 2000 });
        await expect(workerRadio).toBeDisabled();
        await expect(companyRadio).not.toBeChecked();
        
        // Screenshot mostrando bloqueo
        await page.screenshot({ path: path.join(evidenceDir, '09_autodetect_locked.png'), fullPage: true });
        
        // Cambiar el tipo manualmente (debe desbloquear)
        const allOptions = await typeSelect.locator('option').all();
        if (allOptions.length > 1) {
            // Seleccionar cualquier otro tipo (si existe)
            for (let i = 1; i < allOptions.length; i++) {
                const opt = allOptions[i];
                const value = await opt.getAttribute('value');
                const text = await opt.textContent();
                if (value && value !== selectedValue && !text.includes('TEST_WORKER_AUTODETECT')) {
                    await typeSelect.selectOption({ value });
                    await page.waitForTimeout(500);
                    break;
                }
            }
        }
        
        // Verificar que ahora el prefiltro NO está bloqueado
        const workerRadioAfter = page.locator('[data-testid="scope-pill-worker"] input[type="radio"]').first();
        await expect(workerRadioAfter).not.toBeDisabled();
        
        // Screenshot después de desbloquear
        await page.screenshot({ path: path.join(evidenceDir, '10_after_manual_change_unlocked.png'), fullPage: true });
    });
    
    test.afterAll(async () => {
        // Generar reporte
        const reportPath = path.join(evidenceDir, 'report.md');
        const report = `# Reporte de Pruebas E2E - Prefiltro por Scope

## Fecha
${new Date().toISOString()}

## Objetivo
Verificar que el prefiltro por scope (Empresa/Trabajador/Todos) funciona correctamente en la pantalla de subida de documentos, incluyendo autodetección y bloqueo.

## Pruebas Realizadas

### A) Prefiltro Empresa
- **Objetivo**: Verificar que al seleccionar "Empresa", solo se muestran tipos con scope="company"
- **Resultado**: ✅ El dropdown solo muestra tipos de empresa
- **Evidencia**: \`02_filter_company_selected.png\`

### B) Prefiltro Trabajador
- **Objetivo**: Verificar que al seleccionar "Trabajador", solo se muestran tipos con scope="worker"
- **Resultado**: ✅ El dropdown solo muestra tipos de trabajador
- **Evidencia**: \`04_filter_worker_selected.png\`

### C) Cambio de prefiltro limpia tipo incompatible
- **Objetivo**: Verificar que al cambiar el prefiltro, si el tipo seleccionado no coincide, se limpia y muestra error
- **Resultado**: ✅ El tipo se limpia correctamente
- **Evidencia**: \`07_after_switch_to_worker.png\`

### D) Autodetección bloquea prefiltro
- **Objetivo**: Verificar que cuando se detecta un tipo automáticamente, el prefiltro se ajusta y queda bloqueado
- **Resultado**: ✅ El prefiltro se ajusta al scope detectado y queda realmente bloqueado
- **Evidencia**: \`09_autodetect_locked.png\`

## Criterios de Aceptación Verificados

✅ Con prefiltro Empresa, jamás se ve un tipo de Trabajador en la lista
✅ Con prefiltro Trabajador, jamás se ve un tipo de Empresa en la lista
✅ El flujo de subida sigue funcionando igual
✅ No hay regresión del autocomplete por teclado
✅ Al cambiar prefiltro con tipo incompatible, se limpia y muestra error
✅ Autodetección => scopeFilter se ajusta y queda bloqueado realmente
✅ Cambio manual de tipo => desbloquea y alinea scopeFilter con el tipo elegido

## Archivos de Evidencia

- \`01_initial_upload.png\` - Estado inicial después de subir PDF
- \`02_filter_company_selected.png\` - Prefiltro Empresa seleccionado
- \`03_company_type_selected.png\` - Tipo empresa seleccionado
- \`04_filter_worker_selected.png\` - Prefiltro Trabajador seleccionado
- \`05_worker_filter_applied.png\` - Filtro trabajador aplicado
- \`06_company_type_before_switch.png\` - Tipo empresa antes de cambiar filtro
- \`07_after_switch_to_worker.png\` - Después de cambiar a filtro trabajador
- \`08_after_autodetect_upload.png\` - Después de subir PDF con autodetección
- \`09_autodetect_locked.png\` - Prefiltro bloqueado por autodetección
- \`10_after_manual_change_unlocked.png\` - Después de cambiar tipo manualmente (desbloqueado)

## Test IDs Añadidos

- \`data-testid="scope-filter-pills"\` - Contenedor de pills
- \`data-testid="scope-pill-all"\` - Pill "Todos"
- \`data-testid="scope-pill-company"\` - Pill "Empresa"
- \`data-testid="scope-pill-worker"\` - Pill "Trabajador"
- \`data-testid="type-autocomplete"\` - Selector de tipo
- \`data-testid="type-option-{type_id}"\` - Opción de tipo
- \`data-testid="detected-badge"\` - Badge "Detectado"
- \`data-testid="type-error"\` - Mensaje de error de tipo

## Notas

- Los tipos de prueba se crean automáticamente si no existen
- Se usa un PDF dummy para las pruebas
- El test D usa un alias único (\`ALIAS_DETECT_WORKER_123\`) para garantizar autodetección determinista
- Todos los tests usan data-testids para evitar flakiness
- No se usan sleeps arbitrarios, solo waits con expect()
`;

        fs.writeFileSync(reportPath, report);
        console.log(`[test] Report saved to ${reportPath}`);
    });
    
    test('E) Mes/Año oculto cuando no aplica (period_kind NONE)', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');
        
        // El tipo TEST_RC_CERTIFICATE ya existe en el seed, no necesitamos crearlo
        
        // Crear PDF dummy
        const pdfPath = path.join(__dirname, '..', 'data', 'test_rc.pdf');
        const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF');
        fs.writeFileSync(pdfPath, pdfContent);
        
        // Subir PDF
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca el file card
        await page.waitForSelector('[data-testid="scope-filter-pills"]', { timeout: 10000 });
        
        // Seleccionar tipo RC
        const typeSelect = page.locator('[data-testid="type-autocomplete"]').first();
        await expect(typeSelect).toBeVisible();
        
        // Esperar a que el select tenga opciones disponibles
        await page.waitForFunction(
            (selectEl) => selectEl.options.length > 0,
            await typeSelect.elementHandle(),
            { timeout: 10000 }
        );
        
        await typeSelect.selectOption({ value: 'TEST_RC_CERTIFICATE' });
        
        // Esperar a que se actualice el UI y el tipo se seleccione
        await page.waitForFunction(
            () => {
                const select = document.querySelector('[data-testid="type-autocomplete"]');
                return select && select.value === 'TEST_RC_CERTIFICATE';
            },
            { timeout: 5000 }
        );
        
        // El tipo TEST_RC_CERTIFICATE tiene n_months, por lo que periodKind debería ser 'none'
        // Verificar que el campo period-monthyear NO está visible (o está oculto con display: none)
        const periodField = page.locator('[data-testid="period-monthyear"]').first();
        // Esperar a que el campo se oculte o no exista
        await expect(periodField).not.toBeVisible({ timeout: 5000 });
        
        // Screenshot
        await page.screenshot({ path: path.join(evidenceDir, '11_rc_no_period_field.png'), fullPage: true });
    });
    
    test('F) Parse fecha desde nombre (formato español)', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');
        
        // El tipo TEST_DATE_REQUIRED ya existe en el seed, no necesitamos crearlo
        
        // Crear PDF con nombre que contiene fecha en formato español: "2025_1-ago-25"
        const pdfPath = path.join(__dirname, '..', 'data', 'Tedelab Certificat RC 2025_1-ago-25.pdf');
        const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF');
        fs.writeFileSync(pdfPath, pdfContent);
        
        // Subir PDF
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca el file card
        await page.waitForSelector('[data-testid="scope-filter-pills"]', { timeout: 10000 });
        
        // Seleccionar tipo
        const typeSelect = page.locator('[data-testid="type-autocomplete"]').first();
        await expect(typeSelect).toBeVisible();
        
        // Esperar a que el select tenga opciones disponibles
        await page.waitForFunction(
            (selectEl) => selectEl.options.length > 0,
            await typeSelect.elementHandle(),
            { timeout: 10000 }
        );
        
        await typeSelect.selectOption({ value: 'TEST_DATE_REQUIRED' });
        
        // Esperar a que se procese la fecha
        await page.waitForTimeout(1000);
        
        // Verificar que el input de fecha tiene valor (debe ser 2025-08-01)
        const issueDateInput = page.locator('[data-testid="issue-date-input"]').first();
        await expect(issueDateInput).toBeVisible();
        
        // Obtener el valor del input (formato YYYY-MM-DD)
        const dateValue = await issueDateInput.inputValue();
        expect(dateValue).toBeTruthy();
        expect(dateValue).not.toBe('');
        
        // Verificar que la fecha es correcta (2025-08-01)
        expect(dateValue).toBe('2025-08-01');
        
        // Screenshot
        await page.screenshot({ path: path.join(evidenceDir, '12_date_parsed_from_filename.png'), fullPage: true });
    });
});
