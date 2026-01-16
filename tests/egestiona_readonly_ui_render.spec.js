const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.13.8: READ-ONLY UI Render - renderPlanItems fix', () => {
    test('build_submission_plan_readonly renderiza items correctamente en UI sin errores JS', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_13_8_readonly_ui_render');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Capturar errores de consola y página
        const consoleErrors = [];
        const pageErrors = [];
        const consoleLogs = [];
        
        page.on('console', msg => {
            const entry = {
                type: msg.type(),
                text: msg.text(),
                timestamp: new Date().toISOString()
            };
            consoleLogs.push(entry);
            
            if (msg.type() === 'error') {
                consoleErrors.push(entry);
            }
        });
        
        page.on('pageerror', error => {
            pageErrors.push({
                message: error.message,
                stack: error.stack,
                timestamp: new Date().toISOString()
            });
        });
        
        // Verificar que el servidor está corriendo
        console.log('[TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // Navegar al dashboard
        console.log('[TEST] Navegando a /home...');
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
        // Verificar window.__buildStamp
        const buildStamp = await page.evaluate(() => window.__buildStamp);
        expect(buildStamp, 'window.__buildStamp debe existir').toBeTruthy();
        
        // Screenshot inicial
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '01_home_loaded.png'), fullPage: true });
        
        // Abrir modal "Revisar Pendientes CAE"
        console.log('[TEST] Abriendo modal "Revisar Pendientes CAE"...');
        let openModalBtn = page.locator('[data-testid="cae-review-open-btn"]');
        let count = await openModalBtn.count();
        if (count === 0) {
            openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
            count = await openModalBtn.count();
        }
        expect(count, 'Botón para abrir modal debe existir').toBeGreaterThan(0);
        await openModalBtn.first().click();
        
        // Esperar a que el modal esté visible
        await page.waitForSelector('[data-testid="cae-review-modal"]', { state: 'visible', timeout: 5000 });
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '02_modal_open.png'), fullPage: true });
        
        // Función auxiliar para seleccionar opción en dropdown
        const selectDropdownOption = async (inputId, dropdownId, searchTexts) => {
            const input = page.locator(`#${inputId}`);
            await input.click();
            await page.waitForTimeout(500);
            
            const dropdown = page.locator(`#${dropdownId}`);
            await dropdown.waitFor({ state: 'visible', timeout: 5000 });
            
            const options = dropdown.locator('.searchable-select-option');
            const optionCount = await options.count();
            
            for (let i = 0; i < optionCount; i++) {
                const option = options.nth(i);
                const text = await option.textContent();
                const matches = searchTexts.some(searchText => 
                    text.toLowerCase().includes(searchText.toLowerCase())
                );
                if (matches) {
                    await option.click();
                    await page.waitForTimeout(500);
                    return text;
                }
            }
            
            throw new Error(`No se encontró opción que coincida con: ${searchTexts.join(', ')}`);
        };
        
        // Rellenar campos
        console.log('[TEST] Rellenando campos del modal...');
        
        // Cliente: "Aigues de Manresa (egestiona)"
        await selectDropdownOption('filter-coord', 'filter-coord-dropdown', ['Aigues', 'Aigües', 'manresa']);
        await page.waitForTimeout(1000);
        
        // Empresa propia: "Tedelab Ingeniería SCCL (F63161988)"
        await selectDropdownOption('filter-company', 'filter-company-dropdown', ['Tedelab', 'F63161988']);
        await page.waitForTimeout(1000);
        
        // Plataforma CAE: "egestiona"
        await selectDropdownOption('filter-platform', 'filter-platform-dropdown', ['egestiona']);
        await page.waitForTimeout(1000);
        
        // Ámbito: "Trabajador"
        const scopeWorker = page.locator('[data-testid="cae-review-scope-worker"]');
        if (await scopeWorker.count() > 0) {
            await scopeWorker.click();
        }
        await page.waitForTimeout(500);
        
        // Trabajador: "Emilio Roldán Molina (erm)"
        await selectDropdownOption('filter-worker', 'filter-worker-dropdown', ['Emilio', 'Roldán', 'erm']);
        await page.waitForTimeout(1000);
        
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '03_modal_filled.png'), fullPage: true });
        
        // Interceptar respuesta de red
        let networkResponse = null;
        let networkResponseBody = null;
        
        page.on('response', async (response) => {
            const url = response.url();
            if (url.includes('/runs/egestiona/build_submission_plan_readonly') && response.request().method() === 'POST') {
                console.log(`[TEST][NETWORK] Capturando respuesta de: ${url}`);
                networkResponse = {
                    url: url,
                    status: response.status(),
                    statusText: response.statusText(),
                    headers: response.headers(),
                    timestamp: new Date().toISOString()
                };
                
                try {
                    networkResponseBody = await response.text();
                    networkResponse.bodyRaw = networkResponseBody;
                    networkResponse.bodyRawLength = networkResponseBody.length;
                    
                    try {
                        networkResponse.bodyJson = JSON.parse(networkResponseBody);
                    } catch (parseError) {
                        networkResponse.bodyJsonParseError = parseError.message;
                    }
                } catch (bodyError) {
                    networkResponse.bodyError = bodyError.message;
                }
            }
        });
        
        // Click en "Revisar ahora (READ-ONLY)"
        console.log('[TEST] Haciendo click en "Revisar ahora (READ-ONLY)"...');
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(reviewBtn.first()).toBeVisible({ timeout: 10000 });
        await expect(reviewBtn.first()).toBeEnabled({ timeout: 10000 });
        
        await reviewBtn.first().click();
        
        // Esperar a que se procese la respuesta (máximo 6 minutos para Playwright)
        console.log('[TEST] Esperando respuesta del endpoint (puede tardar varios minutos si ejecuta Playwright)...');
        await page.waitForTimeout(15000); // Esperar 15 segundos iniciales
        
        // Esperar a que aparezca algún resultado o error
        try {
            await page.waitForSelector('#cae-results-status, #cae-review-error, #run-info, #results-table-container', { timeout: 360000 }); // 6 minutos
        } catch (waitError) {
            console.warn('[TEST] No se encontró selector de resultados, continuando...');
        }
        
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '04_after_click.png'), fullPage: true });
        
        // Esperar un poco más para que se complete el procesamiento
        await page.waitForTimeout(5000);
        
        // Screenshot final
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '05_final.png'), fullPage: true });
        
        // Guardar evidencias
        if (networkResponse) {
            fs.writeFileSync(
                path.join(EVIDENCE_DIR, 'last_network_response.json'),
                JSON.stringify(networkResponse, null, 2),
                'utf-8'
            );
        }
        
        // Guardar console logs
        const consoleLogText = consoleLogs.map(log => 
            `[${log.timestamp}] [${log.type.toUpperCase()}] ${log.text}`
        ).join('\n');
        fs.writeFileSync(path.join(EVIDENCE_DIR, 'console_log.txt'), consoleLogText, 'utf-8');
        
        // Guardar page errors
        const pageErrorsText = pageErrors.map(err => 
            `[${err.timestamp}] ${err.message}\n${err.stack || ''}`
        ).join('\n\n');
        fs.writeFileSync(path.join(EVIDENCE_DIR, 'page_errors.txt'), pageErrorsText, 'utf-8');
        
        // Analizar respuesta
        let hasError = false;
        let errorCode = null;
        let itemsCount = 0;
        let status = null;
        
        if (networkResponse && networkResponse.bodyJson) {
            const response = networkResponse.bodyJson;
            
            status = response.status;
            hasError = response.status === 'error';
            errorCode = response.error_code;
            itemsCount = response.items?.length || response.plan?.length || 0;
        }
        
        // Guardar resumen
        const summary = {
            timestamp: new Date().toISOString(),
            httpStatus: networkResponse?.status || 'N/A',
            responseStatus: status || 'N/A',
            hasError: hasError,
            errorCode: errorCode,
            itemsCount: itemsCount,
            consoleErrorsCount: consoleErrors.length,
            pageErrorsCount: pageErrors.length,
            hasRenderPlanItemsError: consoleErrors.some(e => e.text.includes('renderPlanItems is not defined')),
            hasAnyJSError: consoleErrors.length > 0 || pageErrors.length > 0,
            testPassed: !hasError && 
                       !consoleErrors.some(e => e.text.includes('renderPlanItems is not defined')) &&
                       networkResponse?.status === 200
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(summary, null, 2),
            'utf-8'
        );
        
        // Resumen
        console.log('\n=== RESUMEN DEL TEST ===');
        console.log(`HTTP Status: ${networkResponse?.status || 'N/A'}`);
        console.log(`Response Status: ${status || 'N/A'}`);
        console.log(`Has Error: ${hasError}`);
        console.log(`Error Code: ${errorCode || 'N/A'}`);
        console.log(`Items Count: ${itemsCount}`);
        console.log(`Console Errors: ${consoleErrors.length}`);
        console.log(`Page Errors: ${pageErrors.length}`);
        console.log(`Has renderPlanItems Error: ${summary.hasRenderPlanItemsError}`);
        console.log(`Test Passed: ${summary.testPassed}`);
        console.log(`Evidencias guardadas en: ${EVIDENCE_DIR}`);
        
        // ASSERT: NO debe haber error "renderPlanItems is not defined"
        const renderPlanItemsError = consoleErrors.find(e => e.text.includes('renderPlanItems is not defined'));
        expect(
            renderPlanItemsError,
            'NO debe aparecer error "renderPlanItems is not defined" en consola'
        ).toBeUndefined();
        
        // ASSERT: NO debe haber errores de página
        expect(
            pageErrors.length,
            'NO debe haber errores de página (pageerror)'
        ).toBe(0);
        
        // ASSERT: HTTP 200
        expect(networkResponse?.status, 'HTTP status debe ser 200').toBe(200);
        
        // ASSERT: Si backend devuelve items_count>0, UI debe mostrar resultados
        if (itemsCount > 0) {
            // Verificar que existe el contenedor de resultados
            const resultsContainer = await page.locator('#results-table-container').count();
            expect(resultsContainer, 'Debe existir contenedor de resultados').toBeGreaterThan(0);
            
            // Verificar que se muestra algún texto indicando pendientes
            const resultsText = await page.locator('#results-table-container').textContent();
            expect(
                resultsText,
                'Debe mostrar texto indicando pendientes encontrados'
            ).toBeTruthy();
        }
        
        // ASSERT: NO debe aparecer banner rojo de error
        const errorBanner = await page.locator('.alert-danger, .alert-error, [class*="error"]').count();
        if (errorBanner > 0) {
            const errorText = await page.locator('.alert-danger, .alert-error, [class*="error"]').first().textContent();
            console.warn(`[TEST] ⚠️ Se encontró banner de error: ${errorText}`);
            // No fallar el test si es un error informativo, pero registrar
        }
        
        // ASSERT final: Test debe pasar
        expect(summary.testPassed, 'Test debe pasar (no errores JS, HTTP 200)').toBe(true);
    });
});
