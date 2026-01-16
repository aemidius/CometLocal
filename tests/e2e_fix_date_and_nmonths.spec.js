const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('Fix Date Parse and N Months Save', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test('BUG 2: Fecha debe extraerse de AEAT-16-oct-2025.pdf', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'fix_date_nmonths');
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
        await page.waitForTimeout(1000);

        // 3. Captura después de subir archivo
        await page.screenshot({ path: path.join(evidenceDir, '01_after_upload.png'), fullPage: true });

        // 4. Seleccionar tipo "No deuda Hacienda"
        const select = page.locator('select.repo-upload-type-select').first();
        await select.selectOption({ label: 'No deuda Hacienda' });
        // SPRINT B2: Eliminado waitForTimeout - usar expect en su lugar

        // 5. Captura después de seleccionar tipo
        await page.screenshot({ path: path.join(evidenceDir, '02_after_select_type.png'), fullPage: true });

        // 6. Verificar que issue_date se parseó correctamente
        const fileState = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined' && uploadFiles.length > 0) {
                return {
                    name: uploadFiles[0].name,
                    issue_date: uploadFiles[0].issue_date,
                    requires_issue_date: uploadFiles[0].requires_issue_date,
                    type_id: uploadFiles[0].type_id
                };
            }
            return null;
        });
        
        console.log('File state after type selection:', fileState);
        
        // Verificar que la fecha se parseó
        expect(fileState.issue_date).toBe('2025-10-16');
        console.log('✅ BUG 2: Fecha parseada correctamente:', fileState.issue_date);

        // 7. Guardar logs
        fs.writeFileSync(
            path.join(evidenceDir, 'console.log'),
            consoleLogs.map(log => `[${log.timestamp}] [${log.type}] ${log.text}`).join('\n')
        );

        // 8. Captura final
        await page.screenshot({ path: path.join(evidenceDir, '03_final_state.png'), fullPage: true });
    });

    test('BUG 4: Guardar "Cada N meses" debe persistir correctamente', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'fix_date_nmonths');
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
            if (msg.text().includes('saveType') || msg.text().includes('renderTypeDrawer') || msg.text().includes('n_months')) {
                console.log(`[Browser Console ${msg.type()}] ${msg.text()}`);
            }
        });

        // 1. Navegar al catálogo
        await page.goto('http://127.0.0.1:8000/repository#catalogo');
        // SPRINT B2: Eliminado waitForTimeout - usar expect en su lugar

        // 2. Buscar tipo "No deuda Hacienda"
        const searchInput = page.locator('#catalog-search');
        if (await searchInput.count() > 0) {
            await searchInput.fill('deuda');
            await page.waitForTimeout(1000);
        }

        // 3. Abrir edición
        const actionMenuButton = page.locator('.action-menu-button').first();
        if (await actionMenuButton.count() > 0) {
            await actionMenuButton.click();
            await page.waitForTimeout(500);
        }
        
        const editButton = page.locator('.action-menu-item:has-text("Editar")').first();
        if (await editButton.count() > 0) {
            await editButton.click({ force: true });
        }
        // SPRINT B2: Eliminado waitForTimeout - usar expect en su lugar

        // 4. Captura antes de modificar
        await page.screenshot({ path: path.join(evidenceDir, '04_catalog_before.png'), fullPage: true });

        // 5. Verificar estado inicial
        const periodModeSelect = page.locator('#drawer-period-mode');
        const initialMode = await periodModeSelect.inputValue();
        console.log('Initial period mode:', initialMode);

        // 6. Seleccionar "Cada N meses" y N=12
        await periodModeSelect.selectOption({ value: 'n_months' });
        await page.waitForTimeout(500);
        
        const nMonthsInput = page.locator('#drawer-n-months');
        await nMonthsInput.fill('12');
        await page.waitForTimeout(500);

        // 7. Captura después de modificar
        await page.screenshot({ path: path.join(evidenceDir, '05_catalog_after_modify.png'), fullPage: true });

        // 8. Guardar
        const drawer = page.locator('#type-drawer');
        const saveButton = drawer.locator('button:has-text("Guardar")').first();
        await saveButton.scrollIntoViewIfNeeded();
        await page.waitForTimeout(300);
        await saveButton.click({ force: true });
        await page.waitForTimeout(3000);

        // 9. Verificar que no hay error
        const errorAlert = page.locator('.alert-error, .alert.alert-error');
        const errorCount = await errorAlert.count();
        expect(errorCount).toBe(0);

        // 10. Captura después de guardar
        await page.screenshot({ path: path.join(evidenceDir, '06_catalog_after_save.png'), fullPage: true });

        // 11. Recargar la página y verificar que persiste
        await page.reload();
        // SPRINT B2: Eliminado waitForTimeout - usar expect en su lugar
        
        // Buscar de nuevo
        if (await searchInput.count() > 0) {
            await searchInput.fill('deuda');
            await page.waitForTimeout(1000);
        }
        
        // Abrir edición de nuevo
        const actionMenuButton2 = page.locator('.action-menu-button').first();
        if (await actionMenuButton2.count() > 0) {
            await actionMenuButton2.click();
            await page.waitForTimeout(500);
        }
        
        const editButton2 = page.locator('.action-menu-item:has-text("Editar")').first();
        if (await editButton2.count() > 0) {
            await editButton2.click({ force: true });
        }
        // SPRINT B2: Eliminado waitForTimeout - usar expect en su lugar

        // 12. Verificar que persiste
        const periodModeSelect2 = page.locator('#drawer-period-mode');
        const persistedMode = await periodModeSelect2.inputValue();
        const nMonthsInput2 = page.locator('#drawer-n-months');
        const persistedNMonths = await nMonthsInput2.inputValue();
        
        console.log('Persisted values:', { mode: persistedMode, nMonths: persistedNMonths });
        
        expect(persistedMode).toBe('n_months');
        expect(persistedNMonths).toBe('12');
        
        console.log('✅ BUG 4: "Cada N meses" persiste correctamente');

        // 13. Captura final
        await page.screenshot({ path: path.join(evidenceDir, '07_catalog_reopen_verify.png'), fullPage: true });

        // 14. Guardar logs
        fs.writeFileSync(
            path.join(evidenceDir, 'console_nmonths.log'),
            consoleLogs.map(log => `[${log.timestamp}] [${log.type}] ${log.text}`).join('\n')
        );
    });
});













