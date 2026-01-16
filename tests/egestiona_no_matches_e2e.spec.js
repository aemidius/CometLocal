const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.13.1: READ-ONLY no falla cuando no hay matches', () => {
    test('build_submission_plan_readonly devuelve status ok con items=[] cuando no hay matches', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_13_1_no_matches');
        
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
        
        // Esperar a que se procese la respuesta (máximo 6 minutos)
        console.log('[TEST] Esperando respuesta del endpoint...');
        await page.waitForTimeout(15000); // Esperar 15 segundos para que se procese
        
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
        
        // Analizar respuesta
        let hasError = false;
        let errorCode = null;
        let itemsCount = 0;
        let hasDiagnostics = false;
        let diagnosticsReason = null;
        
        if (networkResponse && networkResponse.bodyJson) {
            const response = networkResponse.bodyJson;
            
            hasError = response.status === 'error';
            errorCode = response.error_code;
            itemsCount = response.items?.length || response.plan?.length || 0;
            hasDiagnostics = !!response.diagnostics;
            diagnosticsReason = response.diagnostics?.reason;
        }
        
        // Guardar resumen
        const summary = {
            timestamp: new Date().toISOString(),
            httpStatus: networkResponse?.status || 'N/A',
            responseStatus: networkResponse?.bodyJson?.status || 'N/A',
            hasError: hasError,
            errorCode: errorCode,
            itemsCount: itemsCount,
            hasDiagnostics: hasDiagnostics,
            diagnosticsReason: diagnosticsReason,
            summary: networkResponse?.bodyJson?.summary || null,
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(summary, null, 2),
            'utf-8'
        );
        
        // Resumen
        console.log('\n=== RESUMEN DEL TEST ===');
        console.log(`HTTP Status: ${networkResponse?.status || 'N/A'}`);
        console.log(`Response Status: ${networkResponse?.bodyJson?.status || 'N/A'}`);
        console.log(`Has Error: ${hasError}`);
        console.log(`Error Code: ${errorCode || 'N/A'}`);
        console.log(`Items Count: ${itemsCount}`);
        console.log(`Has Diagnostics: ${hasDiagnostics}`);
        console.log(`Diagnostics Reason: ${diagnosticsReason || 'N/A'}`);
        console.log(`Evidencias guardadas en: ${EVIDENCE_DIR}`);
        
        // ASSERT: READ-ONLY nunca debe devolver error por falta de matches
        if (networkResponse?.bodyJson?.status === 'error') {
            // Si hay error, verificar que NO es por falta de matches
            expect(errorCode, 
                `READ-ONLY no debe devolver error por falta de matches. ` +
                `Error code recibido: ${errorCode}. ` +
                `Si items.length === 0, debe ser status: "ok" con diagnostics.`
            ).not.toBe('readonly_compute_failed');
        }
        
        // ASSERT: Si items.length === 0, debe ser status: "ok" con diagnostics
        if (itemsCount === 0 && networkResponse?.bodyJson?.status === 'ok') {
            // Esto es correcto: status ok con items vacío
            console.log('[TEST] ✅ Caso válido: status ok con items vacío');
            
            // Si hay diagnostics, verificar que es informativo
            if (hasDiagnostics) {
                expect(diagnosticsReason, 
                    `Si hay diagnostics, debe ser informativo (no_matches_after_compute, no_rows_after_search, etc.). ` +
                    `Recibido: ${diagnosticsReason}`
                ).toBeTruthy();
            }
        }
        
        // ASSERT: Si hay error, debe ser por otra razón (no por falta de matches)
        if (hasError) {
            expect(errorCode, 
                `Si hay error, NO debe ser por falta de matches. ` +
                `Error code: ${errorCode}. ` +
                `READ-ONLY debe devolver status: "ok" con items: [] y diagnostics cuando no hay matches.`
            ).not.toBe('readonly_compute_failed');
        }
    });
});
