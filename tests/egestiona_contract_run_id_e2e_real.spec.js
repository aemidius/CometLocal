const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.6: Validación de contrato run_id REAL (E2E sin falsos positivos)', () => {
    test('Validar que run_id está presente en respuesta REAL de red y UI no muestra run_id_missing falso', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_contract');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Capturar errores de página y consola
        const pageErrors = [];
        const consoleErrors = [];
        
        page.on('pageerror', error => {
            pageErrors.push({
                message: error.message,
                stack: error.stack,
            });
        });
        
        page.on('console', msg => {
            const type = msg.type();
            const text = msg.text();
            
            if (type === 'error') {
                consoleErrors.push(text);
            }
        });
        
        // Verificar que el servidor está corriendo
        const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
        expect(healthResponse.ok(), 'Backend debe estar corriendo').toBe(true);
        
        // Navegar al dashboard (usar ruta relativa gracias a baseURL en playwright.config.js)
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
        // Verificar build stamp (anti-caché)
        const buildStamp = await page.evaluate(() => window.__buildStamp);
        expect(buildStamp, 'Build stamp debe existir (anti-caché)').toBeTruthy();
        console.log(`[E2E] Build stamp: ${buildStamp}`);
        
        // Abrir modal "Revisar Pendientes CAE"
        const openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
        await openModalBtn.click();
        
        // Esperar a que el modal esté visible
        await page.waitForSelector('[data-testid="cae-review-modal"]', { state: 'visible', timeout: 5000 }).catch(() => {
            // Si no existe el data-testid, buscar por clase o contenido
            return page.waitForSelector('.modal, [role="dialog"], .cae-review-modal', { state: 'visible', timeout: 5000 });
        });
        
        // Seleccionar plataforma "egestiona" usando JavaScript
        await page.evaluate(() => {
            const platformInput = document.getElementById('filter-platform');
            if (platformInput) {
                platformInput.value = 'egestiona';
                platformInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        
        // Esperar un poco para que se actualice el estado
        await page.waitForTimeout(500);
        
        // Seleccionar coordinación (si hay selector)
        try {
            const coordSelect = page.locator('#filter-coord, select[name="coord"]');
            if (await coordSelect.count() > 0) {
                await coordSelect.selectOption({ index: 0 }); // Primera opción
                await page.waitForTimeout(300);
            }
        } catch (e) {
            // Si no hay selector, continuar
        }
        
        // Seleccionar empresa (si hay selector)
        try {
            const companySelect = page.locator('#filter-company, select[name="company"]');
            if (await companySelect.count() > 0) {
                await companySelect.selectOption({ index: 0 }); // Primera opción
                await page.waitForTimeout(300);
            }
        } catch (e) {
            // Si no hay selector, continuar
        }
        
        // Preparar para interceptar la respuesta REAL de red
        let networkResponse = null;
        let responseJson = null;
        
        const responsePromise = page.waitForResponse(
            resp => resp.url().includes('/runs/egestiona/build_submission_plan_readonly') && resp.status() === 200,
            { timeout: 300000 } // 5 minutos timeout
        );
        
        // Hacer click REAL en el botón usando data-testid
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(reviewBtn, 'Botón "Revisar ahora" debe existir').toBeVisible();
        
        // Scroll y click
        await reviewBtn.scrollIntoViewIfNeeded();
        await reviewBtn.click({ force: true, timeout: 10000 });
        
        // Esperar a que el botón se deshabilite (indica que el request se inició)
        await page.waitForFunction(
            () => {
                const btn = document.querySelector('[data-testid="cae-review-run-btn"]');
                return btn && btn.disabled;
            },
            { timeout: 10000 }
        ).catch(() => {
            // Si no se deshabilita, continuar de todas formas
        });
        
        // Esperar la respuesta REAL de red
        try {
            networkResponse = await responsePromise;
            responseJson = await networkResponse.json();
        } catch (error) {
            // Si no se captura la respuesta, el test debe FALLAR
            throw new Error(`No se capturó la respuesta del endpoint. Error: ${error.message}`);
        }
        
        // ASSERT 1: Se recibió una respuesta
        expect(networkResponse, 'Debe haber una respuesta de red').not.toBeNull();
        expect(responseJson, 'La respuesta debe ser JSON válido').not.toBeNull();
        
        // Guardar evidencia: JSON de red
        const evidencePath = path.join(EVIDENCE_DIR, 'last_network_response.json');
        fs.writeFileSync(evidencePath, JSON.stringify(responseJson, null, 2), 'utf-8');
        console.log(`[E2E] Evidence guardado en: ${evidencePath}`);
        
        // ASSERT 2: json.status in ["ok","error"]
        expect(['ok', 'error']).toContain(responseJson.status);
        
        // ASSERT 3: Si json.status == "ok" => json.run_id debe existir (string no vacía)
        if (responseJson.status === 'ok') {
            expect(responseJson.run_id, 'Si status=ok, run_id debe existir').toBeTruthy();
            expect(typeof responseJson.run_id, 'run_id debe ser string').toBe('string');
            expect(responseJson.run_id.length, 'run_id no debe estar vacío').toBeGreaterThan(0);
        }
        
        // ASSERT 4: Si json.status == "error" y existe artifacts.run_id => json.run_id también debe existir y ser igual
        if (responseJson.status === 'error') {
            const artifactsRunId = responseJson.artifacts?.run_id;
            if (artifactsRunId) {
                expect(responseJson.run_id, 'Si artifacts.run_id existe, run_id top-level también debe existir').toBeTruthy();
                expect(responseJson.run_id, 'run_id top-level debe ser igual a artifacts.run_id').toBe(artifactsRunId);
            }
        }
        
        // Esperar a que se renderice completamente la UI
        await page.waitForTimeout(3000);
        
        // ASSERT 5: El UI NO debe contener el texto "run_id_missing" salvo que json.error_code == "run_id_missing"
        const pageText = await page.textContent('body');
        const hasRunIdMissingText = pageText.includes('run_id_missing') || pageText.includes('No se pudo generar run_id');
        
        if (responseJson.error_code !== 'run_id_missing') {
            expect(hasRunIdMissingText, 
                `UI no debe mostrar "run_id_missing" cuando error_code es "${responseJson.error_code}". Response: ${JSON.stringify(responseJson, null, 2)}`
            ).toBe(false);
        }
        
        // ASSERT 6: No debe haber console errors (filtrando warnings)
        const criticalConsoleErrors = consoleErrors.filter(err => 
            !err.includes('Warning') && 
            !err.includes('warn') &&
            !err.toLowerCase().includes('deprecated')
        );
        expect(criticalConsoleErrors.length, 
            `No debe haber errores críticos en consola. Errores encontrados: ${JSON.stringify(criticalConsoleErrors)}`
        ).toBe(0);
        
        // ASSERT 7: No debe haber page errors
        expect(pageErrors.length, 
            `No debe haber errores de página. Errores encontrados: ${JSON.stringify(pageErrors)}`
        ).toBe(0);
        
        // Guardar screenshot del modal final
        const screenshotPath = path.join(EVIDENCE_DIR, 'modal_final.png');
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.log(`[E2E] Screenshot guardado en: ${screenshotPath}`);
        
        // Verificar que el seq mostrado coincide con el último (no render antiguo)
        const lastSeq = await page.evaluate(() => window.__caeRenderSeq);
        const lastReqId = await page.evaluate(() => window.__lastCaeReqId);
        console.log(`[E2E] Último seq: ${lastSeq}, Último reqId: ${lastReqId}`);
        
        // Si hay run_id, verificar que aparece en UI
        if (responseJson.run_id) {
            const runIdInUI = await page.textContent('body');
            const runIdVisible = runIdInUI.includes(responseJson.run_id) || 
                                await page.locator(`a[href*="${responseJson.run_id}"]`).count() > 0;
            // No fallar si no aparece, solo loggear
            if (!runIdVisible) {
                console.warn(`[E2E] Warning: run_id ${responseJson.run_id} no aparece visible en UI`);
            }
        }
        
        console.log(`[E2E] Test completado exitosamente. Response: ${JSON.stringify({
            status: responseJson.status,
            error_code: responseJson.error_code,
            run_id: responseJson.run_id,
            artifacts_run_id: responseJson.artifacts?.run_id
        }, null, 2)}`);
    });
});
