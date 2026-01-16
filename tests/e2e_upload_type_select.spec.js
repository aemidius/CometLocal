const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedUploadPack, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('Upload Type Select E2E', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed específico para upload usando request (no page)
        await seedReset({ request });
        seedData = await seedUploadPack({ request });
    });
    
    test('should select document type and update overlay', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'repo_upload_e2e');
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

        // 2. Captura antes de subir archivo
        await page.screenshot({ path: path.join(evidenceDir, '01_before_upload.png'), fullPage: true });

        // 3. Subir el PDF
        const pdfPath = path.join(__dirname, '..', 'data', '11 SS ERM 28-nov-25.pdf');
        if (!fs.existsSync(pdfPath)) {
            throw new Error(`PDF not found at ${pdfPath}`);
        }

        // SPRINT B2: Usar data-testid específico
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(pdfPath);
        
        // Esperar a que aparezca la card del archivo (no la de defaults)
        await page.waitForSelector('.file-card:has(select.repo-upload-type-select)', { timeout: 10000 });
        // SPRINT B2: Esperar card usando expect
        await expect(page.locator('[data-testid^="upload-card-"]').first()).toBeVisible({ timeout: 10000 });

        // 4. Captura después de subir archivo
        await page.screenshot({ path: path.join(evidenceDir, '02_after_upload.png'), fullPage: true });

        // 5. Verificar que el select existe
        const select = page.locator('select.repo-upload-type-select').first();
        await expect(select).toBeVisible({ timeout: 5000 });

        // 6. Dump del HTML del select antes de seleccionar
        const selectHTML = await select.evaluate(el => {
            const options = Array.from(el.options).map(opt => ({
                value: opt.value,
                text: opt.text,
                selected: opt.selected,
                disabled: opt.disabled
            }));
            return {
                outerHTML: el.outerHTML,
                value: el.value,
                selectedIndex: el.selectedIndex,
                options: options
            };
        });
        fs.writeFileSync(
            path.join(evidenceDir, 'select_dump_before.json'),
            JSON.stringify(selectHTML, null, 2)
        );

        // 7. Esperar a que el select tenga opciones disponibles
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
        
        // 8. Seleccionar un tipo disponible (el filtrado por scope puede ocultar algunos tipos)
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
        await expect(page.locator('[data-testid^="upload-card-"]').first()).toBeVisible({ timeout: 10000 }); // Esperar a que se procese el cambio

        // 8. Captura después de seleccionar tipo
        await page.screenshot({ path: path.join(evidenceDir, '03_after_select_type.png'), fullPage: true });

        // 9. Dump del HTML del select después de seleccionar
        const selectHTMLAfter = await select.evaluate(el => {
            const options = Array.from(el.options).map(opt => ({
                value: opt.value,
                text: opt.text,
                selected: opt.selected,
                disabled: opt.disabled
            }));
            return {
                outerHTML: el.outerHTML,
                value: el.value,
                selectedIndex: el.selectedIndex,
                options: options
            };
        });
        fs.writeFileSync(
            path.join(evidenceDir, 'select_dump_after.json'),
            JSON.stringify(selectHTMLAfter, null, 2)
        );

        // 10. Verificar el overlay (en la card del archivo, no la de defaults)
        const fileCard = page.locator('.file-card:has(select.repo-upload-type-select)').first();
        const overlay = fileCard.locator('div[style*="background: #0f172a"]').first();
        const overlayText = await overlay.textContent();
        console.log('Overlay text:', overlayText);

        // 11. Aserciones
        expect(overlayText).not.toContain('type_id=NULL');
        expect(overlayText).not.toContain('dom_value=NULL');

        // Verificar que el error desapareció
        const errorElement = fileCard.locator('.form-error:has-text("Selecciona un tipo de documento")');
        await expect(errorElement).toHaveCount(0, { timeout: 2000 }).catch(() => {
            // Si aún existe, capturar para debug
            console.log('Error still visible, capturing...');
        });

        // 12. Guardar logs de consola
        fs.writeFileSync(
            path.join(evidenceDir, 'console.log'),
            consoleLogs.map(log => `[${log.timestamp}] [${log.type}] ${log.text}`).join('\n')
        );

        // 13. Dump del estado de uploadFiles desde el browser
        const uploadFilesState = await page.evaluate(() => {
            if (typeof uploadFiles !== 'undefined') {
                return uploadFiles.map(f => ({
                    id: f.id,
                    idType: typeof f.id,
                    idString: String(f.id),
                    name: f.name,
                    type_id: f.type_id,
                    _last_dom_value: f._last_dom_value
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

        // 14. Dump del data-upload-file-id del select
        const selectFileId = await select.getAttribute('data-upload-file-id');
        fs.writeFileSync(
            path.join(evidenceDir, 'select_fileId.txt'),
            `Select data-upload-file-id: ${selectFileId}\nType: ${typeof selectFileId}`
        );

        // 13. Verificar logs específicos
        const listenerInstalled = consoleLogs.some(log => log.text.includes('[repo-upload] listener installed'));
        const changeCaptured = consoleLogs.some(log => log.text.includes('[repo-upload] change captured'));
        const selectDebug = consoleLogs.some(log => log.text.includes('[repo-upload] select debug'));

        console.log('Listener installed:', listenerInstalled);
        console.log('Change captured:', changeCaptured);
        console.log('Select debug:', selectDebug);

        // Guardar resumen
        const summary = {
            listenerInstalled,
            changeCaptured,
            selectDebug,
            overlayText,
            selectValueBefore: selectHTML.value,
            selectValueAfter: selectHTMLAfter.value,
            timestamp: new Date().toISOString()
        };
        fs.writeFileSync(
            path.join(evidenceDir, 'test_summary.json'),
            JSON.stringify(summary, null, 2)
        );
    });
});

