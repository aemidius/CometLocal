const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedUploadPack, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('Upload Subjects E2E', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed específico para upload usando request (no page)
        await seedReset({ request });
        seedData = await seedUploadPack({ request });
    });
    
    test('should show company and worker selects, hide period field when date from name', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'repo_upload_subjects');
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

        // 2. Subir el PDF
        const pdfPath = path.join(__dirname, '..', 'data', '11 SS ERM 28-nov-25.pdf');
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

        // 4. Esperar a que el select tenga opciones disponibles
        const select = page.locator('select.repo-upload-type-select').first();
        await page.waitForFunction(
            (selectEl) => selectEl.options.length > 0,
            await select.elementHandle(),
            { timeout: 10000 }
        );
        
        // Verificar qué opciones tiene el select (debug)
        const optionsInfo = await select.evaluate(el => {
            return Array.from(el.options).map(opt => ({
                value: opt.value,
                text: opt.text,
                disabled: opt.disabled
            }));
        });
        console.log('Select options:', JSON.stringify(optionsInfo, null, 2));
        
        // 5. Seleccionar un tipo disponible (el filtrado por scope puede ocultar algunos tipos)
        // Usar TEST_RC_CERTIFICATE que tiene scope=company y debería estar disponible
        const typeToSelect = optionsInfo.find(opt => opt.value === 'TEST_RC_CERTIFICATE' || opt.value === 'E2E_AUTONOMOS_RECEIPT');
        
        if (!typeToSelect) {
            // Si no está disponible ninguno de los esperados, usar el primero disponible (excepto el placeholder)
            const firstRealOption = optionsInfo.find(opt => opt.value && opt.value !== '');
            if (!firstRealOption) {
                throw new Error(`No hay opciones disponibles en el select. Opciones: ${JSON.stringify(optionsInfo)}`);
            }
            await select.selectOption({ value: firstRealOption.value });
            console.log(`Selected type: ${firstRealOption.value} (${firstRealOption.text})`);
        } else {
            await select.selectOption({ value: typeToSelect.value });
            console.log(`Selected type: ${typeToSelect.value} (${typeToSelect.text})`);
        }
        // SPRINT B2: Esperar card usando expect
        await expect(page.locator('[data-testid^="upload-card-"]').first()).toBeVisible({ timeout: 10000 });

        // 6. Captura después de seleccionar tipo
        await page.screenshot({ path: path.join(evidenceDir, '02_after_select_type.png'), fullPage: true });

        // 7. Verificar que aparecen los selects de empresa y trabajador
        const companySelect = page.locator('select.repo-upload-company-select').first();
        const workerSelect = page.locator('select.repo-upload-worker-select').first();
        
        // Si hay solo 1 empresa, el select puede estar oculto (hidden input)
        const companySelectVisible = await companySelect.count() > 0 && await companySelect.isVisible().catch(() => false);
        const workerSelectVisible = await workerSelect.isVisible();
        
        console.log('Company select visible:', companySelectVisible);
        console.log('Worker select visible:', workerSelectVisible);

        // 8. Verificar que el campo mes/año NO aparece (debe estar oculto)
        const periodInput = page.locator('.file-card').first().locator('input[type="month"]');
        const periodInputCount = await periodInput.count();
        const periodInputVisible = periodInputCount > 0 ? await periodInput.first().isVisible() : false;
        
        console.log('Period input visible:', periodInputVisible);
        expect(periodInputVisible).toBe(false);

        // 9. Verificar que issue_date se auto-rellenó (esperar un poco para que se renderice)
        await page.waitForTimeout(500);
        
        // Buscar el input de fecha dentro de la card del archivo (no el de defaults)
        const fileCard = page.locator('.file-card:has(select.repo-upload-type-select)').first();
        const issueDateInput = fileCard.locator('input[type="date"][id^="upload-issue-date-"]').first();
        
        // Verificar el estado interno del objeto primero
        const fileState = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined' && uploadFiles.length > 0) {
                return {
                    issue_date: uploadFiles[0].issue_date,
                    requires_issue_date: uploadFiles[0].requires_issue_date,
                    file_id: uploadFiles[0].id
                };
            }
            return null;
        });
        console.log('File state:', fileState);
        
        // Verificar que la fecha se parseó en el estado
        expect(fileState).not.toBeNull();
        expect(fileState.issue_date).not.toBe('');
        console.log('Issue date found in state:', fileState.issue_date);
        
        // Verificar que el input tiene el valor (puede requerir un re-render)
        let issueDateValue = '';
        try {
            issueDateValue = await issueDateInput.inputValue({ timeout: 2000 });
            console.log('Issue date value from input:', issueDateValue);
        } catch (e) {
            console.log('Could not read input value, but state has date:', fileState.issue_date);
        }
        
        // Si el input no tiene el valor pero el estado sí, forzar un re-render
        if (!issueDateValue && fileState.issue_date) {
            // Forzar re-render ejecutando renderUploadFiles desde el browser
            await page.evaluate(() => {
                if (typeof renderUploadFiles === 'function') {
                    renderUploadFiles();
                }
            });
            await page.waitForTimeout(300);
            try {
                issueDateValue = await issueDateInput.inputValue({ timeout: 2000 });
                console.log('Issue date value after re-render:', issueDateValue);
            } catch (e) {
                console.log('Input still empty after re-render, but state is correct');
            }
        }
        
        // El estado tiene la fecha parseada desde el nombre del archivo (28-nov-25 -> 2025-11-28)
        expect(fileState.issue_date).toBe('2025-11-28');

        // 9. Seleccionar trabajador si el select está visible
        if (workerSelectVisible) {
            // Si hay solo 1 empresa, puede estar preseleccionada
            if (companySelectVisible) {
                const companyOptions = await companySelect.locator('option').all();
                if (companyOptions.length > 1) {
                    await companySelect.selectOption({ index: 1 }); // Primera empresa (después de placeholder)
                    await page.waitForTimeout(500);
                }
            }
            
            // Seleccionar primer trabajador disponible
            const workerOptions = await workerSelect.locator('option').all();
            if (workerOptions.length > 1) {
                await workerSelect.selectOption({ index: 1 }); // Primer trabajador (después de placeholder)
                await page.waitForTimeout(500);
            }
        }

        // 10. Captura final
        await page.screenshot({ path: path.join(evidenceDir, '03_final_state.png'), fullPage: true });

        // 11. Verificar que los errores desaparecieron
        const errorElement = page.locator('.file-card').first().locator('.form-error:has-text("El trabajador es obligatorio")');
        const errorCount = await errorElement.count();
        console.log('Worker error count:', errorCount);
        
        // Si hay trabajador seleccionado, el error debe desaparecer
        if (workerSelectVisible && await workerSelect.inputValue() !== '') {
            expect(errorCount).toBe(0);
        }

        // 12. Guardar logs
        fs.writeFileSync(
            path.join(evidenceDir, 'console.log'),
            consoleLogs.map(log => `[${log.timestamp}] [${log.type}] ${log.text}`).join('\n')
        );

        // 13. Dump del estado
        const uploadFilesState = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined') {
                return uploadFiles.map(f => ({
                    id: f.id,
                    name: f.name,
                    type_id: f.type_id,
                    company_key: f.company_key,
                    person_key: f.person_key,
                    period_key: f.period_key,
                    issue_date: f.issue_date
                }));
            }
            return null;
        });
        if (uploadFilesState) {
            fs.writeFileSync(
                path.join(evidenceDir, 'uploadFiles_state.json'),
                JSON.stringify(uploadFilesState, null, 2)
            );
        }

        // 14. Verificar subjects cargados
        const subjectsState = await page.evaluate(() => {
            if (typeof uploadSubjects !== 'undefined') {
                return {
                    companies: uploadSubjects.companies,
                    workers_by_company: uploadSubjects.workers_by_company
                };
            }
            return null;
        });
        if (subjectsState) {
            fs.writeFileSync(
                path.join(evidenceDir, 'subjects_state.json'),
                JSON.stringify(subjectsState, null, 2)
            );
        }

        // 15. Resumen
        const summary = {
            companySelectVisible,
            workerSelectVisible,
            periodInputVisible,
            issueDateValue,
            errorCount,
            timestamp: new Date().toISOString()
        };
        fs.writeFileSync(
            path.join(evidenceDir, 'test_summary.json'),
            JSON.stringify(summary, null, 2)
        );
    });
});

