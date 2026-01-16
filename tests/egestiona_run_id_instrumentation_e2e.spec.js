const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('HOTFIX C2.12.5.2: Instrumentación completa de respuesta y extracción robusta de run_id', () => {
    test('Capturar respuesta EXACTA del endpoint y validar extracción de run_id', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_12_5_2_run_id_debug');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Capturar errores de consola
        const consoleLogs = [];
        page.on('console', msg => {
            const entry = {
                type: msg.type(),
                text: msg.text(),
                timestamp: new Date().toISOString()
            };
            consoleLogs.push(entry);
            
            // Loggear en consola del test también
            if (msg.type() === 'error') {
                console.error(`[CONSOLE ERROR] ${msg.text()}`);
            } else if (msg.type() === 'warn') {
                console.warn(`[CONSOLE WARN] ${msg.text()}`);
            } else if (msg.text().includes('[CAE][INSTRUMENTATION]') || msg.text().includes('[CAE][NET]')) {
                console.log(`[CONSOLE] ${msg.text()}`);
            }
        });
        
        // Capturar errores de página
        const pageErrors = [];
        page.on('pageerror', error => {
            pageErrors.push({
                message: error.message,
                stack: error.stack,
                timestamp: new Date().toISOString()
            });
            console.error(`[PAGE ERROR] ${error.message}`);
        });
        
        // Interceptar respuesta de red ANTES de que el frontend la procese
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
                    networkResponse.bodyRawPreview = networkResponseBody.substring(0, 300);
                    
                    // Intentar parsear JSON
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
        
        // Click en "Revisar ahora (READ-ONLY)"
        console.log('[TEST] Haciendo click en "Revisar ahora (READ-ONLY)"...');
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(reviewBtn.first()).toBeVisible({ timeout: 10000 });
        await expect(reviewBtn.first()).toBeEnabled({ timeout: 10000 });
        
        await reviewBtn.first().click();
        
        // Esperar a que se procese la respuesta (máximo 6 minutos)
        console.log('[TEST] Esperando respuesta del endpoint...');
        await page.waitForTimeout(10000); // Esperar 10 segundos para que se procese
        
        // Esperar a que aparezca algún resultado o error
        try {
            await page.waitForSelector('#cae-results-status, #cae-review-error, #run-info', { timeout: 300000 });
        } catch (waitError) {
            console.warn('[TEST] No se encontró selector de resultados, continuando...');
        }
        
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '04_after_click.png'), fullPage: true });
        
        // Esperar un poco más para que se complete el procesamiento
        await page.waitForTimeout(5000);
        
        // Screenshot final
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '05_final.png'), fullPage: true });
        
        // Extraer información de instrumentación del frontend
        const frontendInstrumentation = await page.evaluate(() => {
            return {
                lastCaeResponse: window.__lastCaeResponse || null,
                lastCaeResponseParsed: window.__lastCaeResponseParsed || null,
                lastCaeReqId: window.__lastCaeReqId || null,
            };
        });
        
        // Función helper para extraer run_id (igual que el frontend)
        const extractRunId = (result) => {
            if (!result) return null;
            return (
                result.run_id ||
                result.plan_id ||
                result.runId ||
                result.data?.run_id ||
                result.data?.plan_id ||
                result.artifacts?.run_id ||
                result.artifacts?.plan_id ||
                result.artifacts?.runId ||
                result.result?.run_id ||
                result.result?.plan_id ||
                null
            );
        };
        
        // Analizar respuesta de red capturada
        let extractedRunId = null;
        if (networkResponse && networkResponse.bodyJson) {
            extractedRunId = extractRunId(networkResponse.bodyJson);
        }
        
        // Analizar respuesta del frontend
        let frontendExtractedRunId = null;
        if (frontendInstrumentation.lastCaeResponseParsed) {
            frontendExtractedRunId = frontendInstrumentation.lastCaeResponseParsed.extractedRunId;
        }
        
        // Verificar que NO hay error "run_id_missing" en UI
        const pageText = await page.textContent('body').catch(() => '');
        const hasRunIdMissingError = pageText.includes('run_id_missing') && 
                                     (pageText.includes('No se pudo generar run_id') || 
                                      pageText.includes('missing_run_id_in_response'));
        
        // Guardar evidencias
        const evidence = {
            timestamp: new Date().toISOString(),
            networkResponse: networkResponse,
            frontendInstrumentation: frontendInstrumentation,
            extractedRunId: extractedRunId,
            frontendExtractedRunId: frontendExtractedRunId,
            hasRunIdMissingErrorInUI: hasRunIdMissingError,
            pageErrors: pageErrors,
        };
        
        // Guardar JSON completo
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'last_network_response.json'),
            JSON.stringify(networkResponse, null, 2),
            'utf-8'
        );
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'frontend_instrumentation.json'),
            JSON.stringify(frontendInstrumentation, null, 2),
            'utf-8'
        );
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_evidence.json'),
            JSON.stringify(evidence, null, 2),
            'utf-8'
        );
        
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
        
        // Guardar body raw si existe
        if (networkResponseBody) {
            fs.writeFileSync(
                path.join(EVIDENCE_DIR, 'response_body_raw.txt'),
                networkResponseBody,
                'utf-8'
            );
        }
        
        // Resumen
        console.log('\n=== RESUMEN DEL TEST ===');
        console.log(`HTTP Status: ${networkResponse?.status || 'N/A'}`);
        console.log(`Response Status: ${networkResponse?.bodyJson?.status || 'N/A'}`);
        console.log(`Extracted Run ID (from network): ${extractedRunId || 'NO ENCONTRADO'}`);
        console.log(`Extracted Run ID (from frontend): ${frontendExtractedRunId || 'NO ENCONTRADO'}`);
        console.log(`Has run_id in response: ${!!networkResponse?.bodyJson?.run_id}`);
        console.log(`Has plan_id in response: ${!!networkResponse?.bodyJson?.plan_id}`);
        console.log(`Has run_id_missing error in UI: ${hasRunIdMissingError}`);
        console.log(`Evidencias guardadas en: ${EVIDENCE_DIR}`);
        
        // ASSERT: Si la respuesta tiene run_id o plan_id, NO debe haber error run_id_missing en UI
        if (extractedRunId || frontendExtractedRunId) {
            expect(hasRunIdMissingError, 
                `UI NO debe mostrar error "run_id_missing" cuando la respuesta contiene run_id/plan_id. ` +
                `Extracted (network): ${extractedRunId}, Extracted (frontend): ${frontendExtractedRunId}, ` +
                `Response keys: ${Object.keys(networkResponse?.bodyJson || {}).join(', ')}`
            ).toBe(false);
        }
        
        // ASSERT: Si status es "ok", debe haber run_id o plan_id
        if (networkResponse?.bodyJson?.status === 'ok') {
            expect(extractedRunId || frontendExtractedRunId, 
                `Si status es "ok", debe haber run_id o plan_id en la respuesta. ` +
                `Response: ${JSON.stringify(networkResponse?.bodyJson, null, 2)}`
            ).toBeTruthy();
        }
        
        // Si hay run_id pero UI muestra error, es un BUG
        if ((extractedRunId || frontendExtractedRunId) && hasRunIdMissingError) {
            throw new Error(
                `BUG DETECTADO: UI muestra "run_id_missing" pero la respuesta contiene run_id/plan_id. ` +
                `Extracted (network): ${extractedRunId}, Extracted (frontend): ${frontendExtractedRunId}, ` +
                `Response: ${JSON.stringify(networkResponse?.bodyJson, null, 2)}`
            );
        }
    });
});
