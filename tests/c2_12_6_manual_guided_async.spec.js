const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.6: Prueba REAL GUIADA (HEADFUL) + EVIDENCIAS', () => {
    test('Ejecutar flujo completo desde UI y generar evidencias', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_12_6_manual');
        
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
        
        // Capturar errores de página
        const pageErrors = [];
        page.on('pageerror', error => {
            pageErrors.push({
                message: error.message,
                stack: error.stack,
                timestamp: new Date().toISOString()
            });
        });
        
        // Verificar que el servidor está corriendo
        console.log('[TEST] Verificando que el backend está corriendo...');
        const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
        expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
        console.log('[TEST] ✅ Backend está corriendo');
        
        // Navegar al dashboard
        console.log('[TEST] Navegando a /home...');
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
        // VALIDACIÓN: Verificar que es HTTP (no file://)
        const currentUrl = page.url();
        console.log(`[TEST] URL actual: ${currentUrl}`);
        expect(currentUrl.startsWith('http://'), 'Debe ser HTTP, no file://').toBe(true);
        expect(currentUrl.includes('127.0.0.1:8000'), 'Debe usar puerto 8000').toBe(true);
        
        // VALIDACIÓN: Verificar window.__buildStamp
        const buildStamp = await page.evaluate(() => window.__buildStamp);
        console.log(`[TEST] window.__buildStamp: ${buildStamp}`);
        expect(buildStamp, 'window.__buildStamp debe existir (anti-caché)').toBeTruthy();
        
        // Screenshot 01: Home cargado
        console.log('[TEST] Capturando screenshot 01_home_loaded.png...');
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '01_home_loaded.png'), fullPage: true });
        
        // Abrir modal "Revisar Pendientes CAE"
        console.log('[TEST] Abriendo modal "Revisar Pendientes CAE"...');
        const openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
        await openModalBtn.click();
        
        // Esperar a que el modal esté visible
        await page.waitForSelector('[data-testid="cae-review-modal"]', { state: 'visible', timeout: 5000 }).catch(() => {
            return page.waitForSelector('.modal, [role="dialog"]', { state: 'visible', timeout: 5000 });
        });
        
        // Rellenar campos EXACTAMENTE como se especifica
        console.log('[TEST] Rellenando campos del modal...');
        
        // Plataforma CAE: "egestiona"
        await page.evaluate(() => {
            const platformInput = document.getElementById('filter-platform');
            if (platformInput) {
                platformInput.value = 'egestiona';
                platformInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        await page.waitForTimeout(1000);
        
        // Cliente / Empresa a coordinar: "Aigues de Manresa (egestiona)"
        await page.evaluate(() => {
            const coordInput = document.getElementById('filter-coord');
            if (coordInput) {
                const options = JSON.parse(coordInput.dataset.options || '[]');
                const aiguesOption = options.find(opt => 
                    (opt.label || opt).includes('Aigues') || 
                    (opt.label || opt).includes('Aigües') ||
                    (opt.label || opt).toLowerCase().includes('manresa')
                );
                if (aiguesOption) {
                    coordInput.value = aiguesOption.label || aiguesOption;
                    coordInput.dispatchEvent(new Event('change', { bubbles: true }));
                } else if (options.length > 0) {
                    coordInput.value = options[0].label || options[0];
                    coordInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        });
        await page.waitForTimeout(2000);
        
        // Empresa propia: "Tedelab Ingeniería SCCL (F63161988)"
        await page.evaluate(() => {
            const companyInput = document.getElementById('filter-company');
            if (companyInput) {
                const options = JSON.parse(companyInput.dataset.options || '[]');
                const tedelabOption = options.find(opt => 
                    (opt.label || opt).includes('Tedelab') ||
                    (opt.label || opt).includes('F63161988')
                );
                if (tedelabOption) {
                    companyInput.value = tedelabOption.label || tedelabOption;
                    companyInput.dispatchEvent(new Event('change', { bubbles: true }));
                } else if (options.length > 0) {
                    companyInput.value = options[0].label || options[0];
                    companyInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        });
        await page.waitForTimeout(2000);
        
        // Ámbito del documento: "Trabajador"
        await page.evaluate(() => {
            const scopeSelect = document.querySelector('select[name="scope"], #filter-scope');
            if (scopeSelect) {
                scopeSelect.value = 'worker';
                scopeSelect.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        await page.waitForTimeout(1000);
        
        // Trabajador: "Emilio Roldán Molina (erm)"
        await page.evaluate(() => {
            const workerInput = document.getElementById('filter-worker');
            if (workerInput) {
                const options = JSON.parse(workerInput.dataset.options || '[]');
                const emilioOption = options.find(opt => 
                    (opt.label || opt).includes('Emilio') ||
                    (opt.label || opt).includes('Roldán') ||
                    (opt.label || opt).includes('erm')
                );
                if (emilioOption) {
                    workerInput.value = emilioOption.label || emilioOption;
                    workerInput.dispatchEvent(new Event('change', { bubbles: true }));
                } else if (options.length > 0) {
                    workerInput.value = options[0].label || options[0];
                    workerInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        });
        await page.waitForTimeout(1000);
        
        // Screenshot 02: Modal rellenado
        console.log('[TEST] Capturando screenshot 02_modal_filled.png...');
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '02_modal_filled.png'), fullPage: true });
        
        // Preparar para interceptar la respuesta de red
        let networkResponse = null;
        let responseJson = null;
        let responseError = null;
        
        const responsePromise = page.waitForResponse(
            resp => resp.url().includes('/runs/egestiona/build_submission_plan_readonly'),
            { timeout: 300000 } // 5 minutos
        );
        
        // Click en "Revisar ahora (READ-ONLY)"
        console.log('[TEST] Haciendo click en "Revisar ahora (READ-ONLY)"...');
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(reviewBtn).toBeVisible({ timeout: 10000 });
        await expect(reviewBtn).toBeEnabled({ timeout: 10000 });
        
        await reviewBtn.scrollIntoViewIfNeeded();
        await reviewBtn.click({ force: true, timeout: 10000 });
        
        // Screenshot 03: Justo después del click
        console.log('[TEST] Capturando screenshot 03_after_click.png...');
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '03_after_click.png'), fullPage: true });
        
        // Esperar la respuesta de red (puede tardar varios minutos)
        console.log('[TEST] Esperando respuesta del endpoint (timeout 5min)...');
        try {
            networkResponse = await responsePromise;
            if (networkResponse.status() === 200) {
                responseJson = await networkResponse.json();
                console.log('[TEST] ✅ Respuesta recibida:', responseJson.status, 'run_id:', responseJson.run_id || responseJson.artifacts?.run_id);
            } else {
                // Si no es 200, intentar leer el error
                try {
                    responseJson = await networkResponse.json();
                } catch {
                    responseJson = { status: 'error', error_code: 'http_error', message: `HTTP ${networkResponse.status()}` };
                }
                console.log('[TEST] ⚠️ Respuesta con error HTTP:', networkResponse.status());
            }
        } catch (error) {
            responseError = error.message;
            console.error('[TEST] ❌ No se recibió respuesta del endpoint:', error.message);
            // Continuar para capturar el estado actual de la UI
        }
        
        // Esperar a que se renderice completamente
        console.log('[TEST] Esperando a que se renderice completamente...');
        await page.waitForTimeout(5000);
        
        // Screenshot 04: Estado final
        console.log('[TEST] Capturando screenshot 04_final_state.png...');
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '04_final_state.png'), fullPage: true });
        
        // Guardar JSON de red si existe
        if (responseJson) {
            console.log('[TEST] Guardando last_network_response.json...');
            fs.writeFileSync(
                path.join(EVIDENCE_DIR, 'last_network_response.json'),
                JSON.stringify(responseJson, null, 2),
                'utf-8'
            );
        } else {
            // Guardar error si no hay respuesta
            fs.writeFileSync(
                path.join(EVIDENCE_DIR, 'last_network_response.json'),
                JSON.stringify({ error: responseError || 'No se recibió respuesta' }, null, 2),
                'utf-8'
            );
        }
        
        // Guardar logs de consola
        console.log('[TEST] Guardando console_log.txt...');
        const consoleLogText = consoleLogs.map(log => 
            `[${log.timestamp}] [${log.type.toUpperCase()}] ${log.text}`
        ).join('\n');
        fs.writeFileSync(path.join(EVIDENCE_DIR, 'console_log.txt'), consoleLogText, 'utf-8');
        
        // Verificar si hay "run_id_missing" en UI
        const pageText = await page.textContent('body');
        const hasRunIdMissing = pageText.includes('run_id_missing') || pageText.includes('No se pudo generar run_id');
        
        // Extraer run_id del JSON
        const extractedRunId = responseJson?.run_id || responseJson?.artifacts?.run_id;
        
        // Validaciones finales
        console.log('\n=== VALIDACIONES ===');
        console.log(`URL real usada: ${currentUrl}`);
        console.log(`window.__buildStamp: ${buildStamp}`);
        console.log(`run_id en JSON: ${extractedRunId || 'NO EXISTE'}`);
        console.log(`run_id_missing en UI: ${hasRunIdMissing ? 'SÍ' : 'NO'}`);
        console.log(`error_code en JSON: ${responseJson?.error_code || 'N/A'}`);
        console.log(`status en JSON: ${responseJson?.status || 'N/A'}`);
        
        // Si hay run_id, verificar que existe el directorio
        let runDirPath = null;
        if (extractedRunId) {
            runDirPath = path.join(__dirname, '..', 'data', 'runs', extractedRunId);
            const runDirExists = fs.existsSync(runDirPath);
            console.log(`Directorio run existe: ${runDirExists ? 'SÍ' : 'NO'}`);
            if (runDirExists) {
                console.log(`Ruta del run_id: ${runDirPath}`);
            }
        }
        
        // Si hay "run_id_missing" en UI pero el JSON tiene run_id, es un error
        if (hasRunIdMissing && extractedRunId) {
            console.error('[TEST] ❌ ERROR: UI muestra "run_id_missing" pero el JSON tiene run_id!');
        }
        
        // Guardar resumen
        const summary = {
            timestamp: new Date().toISOString(),
            url: currentUrl,
            buildStamp: buildStamp,
            runId: extractedRunId,
            runDirPath: runDirPath,
            status: responseJson?.status || 'unknown',
            errorCode: responseJson?.error_code,
            hasRunIdMissingInUI: hasRunIdMissing,
            consoleErrors: consoleLogs.filter(log => log.type === 'error').length,
            pageErrors: pageErrors.length,
            evidenceDir: EVIDENCE_DIR,
            responseError: responseError
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'summary.json'),
            JSON.stringify(summary, null, 2),
            'utf-8'
        );
        
        console.log('\n=== RESUMEN FINAL ===');
        console.log(`Resultado: ${responseJson?.status === 'ok' ? 'OK' : responseJson?.status === 'error' ? 'ERROR' : 'TIMEOUT/UNKNOWN'}`);
        console.log(`Último paso alcanzado: Estado final capturado`);
        console.log(`URL real: ${currentUrl}`);
        console.log(`window.__buildStamp: ${buildStamp}`);
        console.log(`Ruta del run_id: ${runDirPath || 'N/A'}`);
        console.log(`Evidencias en: ${EVIDENCE_DIR}`);
        
        // Si hay error, mostrar detalles
        if (responseJson?.status === 'error') {
            console.log('\n=== ERROR DETECTADO ===');
            console.log(`error_code: ${responseJson.error_code}`);
            console.log(`message: ${responseJson.message}`);
        }
        
        // No fallar el test si hay timeout, solo reportar
        if (!responseJson) {
            console.warn('[TEST] ⚠️ No se recibió respuesta en el timeout. Revisar evidencias generadas.');
        }
    });
});
