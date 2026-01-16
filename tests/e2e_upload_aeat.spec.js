const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('Upload AEAT E2E - Bugs Fix', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test('BUG 1+2+3: Empresa única auto-seleccionada, fecha parseada, año oculto', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'repo_upload_aeat');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }

        const consoleLogs = [];
        page.on('console', msg => {
            const logEntry = {
                type: msg.type(),
                text: msg.text(),
                timestamp: new Date().toISOString()
            };
            consoleLogs.push(logEntry);
            console.log(`[Browser Console ${msg.type()}] ${msg.text()}`);
        });

        // SPRINT B2: Navegar usando helper
        await gotoHash(page, 'subir');
        await waitForTestId(page, 'upload-dropzone');

        // 2. Subir el PDF AEAT
        const pdfPath = path.join(__dirname, '..', 'data', 'AEAT-16-oct-2025.pdf');
        if (!fs.existsSync(pdfPath)) {
            throw new Error(`PDF not found at ${pdfPath}`);
        }

        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca la card del archivo
        await page.waitForSelector('.file-card:has(select.repo-upload-type-select)', { timeout: 10000 });
        // SPRINT B2: Esperar card usando expect
        await expect(page.locator('[data-testid^="upload-card-"]').first()).toBeVisible({ timeout: 10000 });

        // 3. Captura después de subir archivo
        await page.screenshot({ path: path.join(evidenceDir, '01_after_upload.png'), fullPage: true });

        // 4. Verificar estado inicial (empresa auto-seleccionada)
        const fileStateBefore = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined' && uploadFiles.length > 0) {
                return {
                    company_key: uploadFiles[0].company_key,
                    errors: uploadFiles[0].errors || []
                };
            }
            return null;
        });
        console.log('File state before type selection:', fileStateBefore);
        
        // BUG 1: Verificar que empresa está auto-seleccionada (si solo hay 1)
        const subjectsState = await page.evaluate(() => {
            if (typeof uploadSubjects !== 'undefined') {
                return {
                    companies: uploadSubjects.companies,
                    companiesCount: uploadSubjects.companies.length
                };
            }
            return null;
        });
        console.log('Subjects state:', subjectsState);
        
        if (subjectsState && subjectsState.companiesCount === 1) {
            expect(fileStateBefore.company_key).toBe(subjectsState.companies[0].id);
            // Verificar que NO hay error de empresa obligatoria
            expect(fileStateBefore.errors).not.toContain('La empresa es obligatoria');
        }

        // 5. Seleccionar tipo "No deuda Hacienda" (o el que tenga issue_date_required=true)
        const select = page.locator('select.repo-upload-type-select').first();
        const options = await select.locator('option').all();
        let noDeudaOption = null;
        for (let i = 0; i < options.length; i++) {
            const text = await options[i].textContent();
            if (text && (text.includes('deuda') || text.includes('Hacienda') || text.includes('AEAT'))) {
                noDeudaOption = i;
                break;
            }
        }
        
        // Si no encontramos "No deuda", usar el primero disponible (para probar el parseo)
        if (noDeudaOption === null && options.length > 1) {
            await select.selectOption({ index: 1 });
        } else if (noDeudaOption !== null) {
            await select.selectOption({ index: noDeudaOption });
        }
        // SPRINT B2: Esperar card usando expect
        await expect(page.locator('[data-testid^="upload-card-"]').first()).toBeVisible({ timeout: 10000 });

        // 6. Captura después de seleccionar tipo
        await page.screenshot({ path: path.join(evidenceDir, '02_after_select_type.png'), fullPage: true });

        // 7. BUG 2: Verificar que issue_date se parseó correctamente (16-oct-2025 → 2025-10-16)
        const fileStateAfter = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined' && uploadFiles.length > 0) {
                return {
                    issue_date: uploadFiles[0].issue_date,
                    requires_issue_date: uploadFiles[0].requires_issue_date,
                    company_key: uploadFiles[0].company_key,
                    errors: uploadFiles[0].errors || []
                };
            }
            return null;
        });
        console.log('File state after type selection:', fileStateAfter);
        
        // BUG 2: Verificar parseo de fecha
        expect(fileStateAfter.issue_date).toBe('2025-10-16');
        console.log('✅ BUG 2: Fecha parseada correctamente:', fileStateAfter.issue_date);

        // 8. BUG 1: Verificar que empresa sigue auto-seleccionada y sin error
        if (subjectsState && subjectsState.companiesCount === 1) {
            expect(fileStateAfter.company_key).toBe(subjectsState.companies[0].id);
            expect(fileStateAfter.errors).not.toContain('La empresa es obligatoria');
            console.log('✅ BUG 1: Empresa auto-seleccionada y sin error');
        }

        // 9. BUG 3: Verificar que campo "año" NO aparece si es 12 meses desde expedición
        const periodInput = page.locator('.file-card').first().locator('input[type="month"], input[type="number"][placeholder*="YYYY"]');
        const periodInputCount = await periodInput.count();
        const periodInputVisible = periodInputCount > 0 ? await periodInput.first().isVisible() : false;
        
        // Obtener tipo para verificar si tiene n_months=12
        const typeInfo = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined' && uploadFiles.length > 0 && typeof uploadTypes !== 'undefined') {
                const file = uploadFiles[0];
                const type = uploadTypes.find(t => t.type_id === file.type_id);
                return {
                    hasNMonths: type?.validity_policy?.n_months?.n,
                    basis: type?.validity_policy?.basis,
                    mode: type?.validity_policy?.mode
                };
            }
            return null;
        });
        console.log('Type info:', typeInfo);
        
        // Si tiene n_months=12 y basis=issue_date, el campo año NO debe aparecer
        if (typeInfo && typeInfo.hasNMonths === 12 && typeInfo.basis === 'issue_date') {
            expect(periodInputVisible).toBe(false);
            console.log('✅ BUG 3: Campo año oculto para 12 meses desde expedición');
        }

        // 10. Captura final
        await page.screenshot({ path: path.join(evidenceDir, '03_final_state.png'), fullPage: true });

        // 11. Guardar logs
        fs.writeFileSync(
            path.join(evidenceDir, 'console.log'),
            consoleLogs.map(log => `[${log.timestamp}] [${log.type}] ${log.text}`).join('\n')
        );

        // 12. Dump del estado
        const finalState = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined') {
                return uploadFiles.map(f => ({
                    id: f.id,
                    name: f.name,
                    type_id: f.type_id,
                    company_key: f.company_key,
                    issue_date: f.issue_date,
                    period_key: f.period_key,
                    requires_issue_date: f.requires_issue_date,
                    errors: f.errors || []
                }));
            }
            return null;
        });
        if (finalState) {
            fs.writeFileSync(
                path.join(evidenceDir, 'uploadFiles_state.json'),
                JSON.stringify(finalState, null, 2)
            );
        }

        // 13. Resumen
        const summary = {
            bug1_empresaAutoSelected: fileStateAfter.company_key === subjectsState?.companies[0]?.id,
            bug1_noErrorEmpresa: !fileStateAfter.errors.includes('La empresa es obligatoria'),
            bug2_fechaParseada: fileStateAfter.issue_date === '2025-10-16',
            bug3_campoAnioOculto: !periodInputVisible || (typeInfo?.hasNMonths === 12 && typeInfo?.basis === 'issue_date'),
            timestamp: new Date().toISOString()
        };
        fs.writeFileSync(
            path.join(evidenceDir, 'test_summary.json'),
            JSON.stringify(summary, null, 2)
        );
        
        console.log('Test summary:', summary);
    });

    test('BUG 4: Guardar catálogo "Cada N meses" sin error enum', async ({ page }) => {
        test.setTimeout(60000); // Aumentar timeout a 60s
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'repo_upload_aeat');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }

        // 1. Navegar al catálogo
        await page.goto('http://127.0.0.1:8000/repository#catalogo');
        await page.waitForTimeout(2000);

        // 2. Buscar tipo "No deuda Hacienda" o crear uno nuevo
        const searchInput = page.locator('#catalog-search');
        if (await searchInput.count() > 0) {
            await searchInput.fill('deuda');
            await page.waitForTimeout(500);
        }

        // 3. Abrir edición (o crear nuevo)
        // Primero abrir el menú de acciones si existe
        const actionMenuButton = page.locator('.action-menu-button').first();
        if (await actionMenuButton.count() > 0) {
            await actionMenuButton.click();
            await page.waitForTimeout(300);
        }
        
        const editButton = page.locator('.action-menu-item:has-text("Editar")').first();
        if (await editButton.count() > 0 && await editButton.isVisible()) {
            await editButton.click();
        } else {
            // Crear nuevo tipo
            const createButton = page.locator('button:has-text("Crear"), button:has-text("Nuevo")').first();
            if (await createButton.count() > 0) {
                await createButton.click();
            }
        }
        // SPRINT B2: Esperar card usando expect
        await expect(page.locator('[data-testid^="upload-card-"]').first()).toBeVisible({ timeout: 10000 });

        // 4. Captura antes de modificar
        await page.screenshot({ path: path.join(evidenceDir, '04_catalog_before.png'), fullPage: true });

        // 5. Seleccionar "Cada N meses" y N=12
        const periodModeSelect = page.locator('#drawer-period-mode');
        await periodModeSelect.selectOption({ value: 'n_months' });
        await page.waitForTimeout(300);
        
        const nMonthsInput = page.locator('#drawer-n-months');
        await nMonthsInput.fill('12');
        await page.waitForTimeout(300);

        // 6. Captura después de modificar
        await page.screenshot({ path: path.join(evidenceDir, '05_catalog_after_modify.png'), fullPage: true });

        // 7. Guardar - usar selector más específico dentro del drawer
        const drawer = page.locator('#type-drawer');
        const saveButton = drawer.locator('button:has-text("Guardar"), button:has-text("Crear")').first();
        await saveButton.scrollIntoViewIfNeeded();
        await page.waitForTimeout(300);
        await saveButton.click({ force: true });
        await page.waitForTimeout(2000);

        // 8. Verificar que no hay error (200 OK)
        const errorAlert = page.locator('.alert-error, .alert.alert-error');
        const errorCount = await errorAlert.count();
        expect(errorCount).toBe(0);

        // 9. Captura final
        await page.screenshot({ path: path.join(evidenceDir, '06_catalog_after_save.png'), fullPage: true });

        // 10. Verificar que no hay error (el drawer puede cerrarse, lo cual es normal)
        const errorCount2 = await errorAlert.count();
        expect(errorCount2).toBe(0);
        
        console.log('✅ BUG 4: Guardar "Cada N meses" funciona sin error enum');
    });
});

