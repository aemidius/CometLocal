const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('Revisar Pendientes CAE (Avanzado) - Manual READ-ONLY', () => {
    test('Ejecutar flujo completo y generar evidencias', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_manual');
        
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
            // También loggear en consola del test
            if (msg.type() === 'error') {
                console.error(`[CONSOLE ERROR] ${msg.text()}`);
            } else if (msg.type() === 'warn') {
                console.warn(`[CONSOLE WARN] ${msg.text()}`);
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
        
        // Verificar que el servidor está corriendo
        console.log('[TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // Navegar al dashboard (usar ruta relativa gracias a baseURL)
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
        if (!buildStamp || typeof buildStamp !== 'string' || buildStamp.trim() === '') {
            throw new Error('UI abierta fuera del backend: window.__buildStamp no existe o está vacío');
        }
        expect(buildStamp, 'window.__buildStamp debe existir (anti-caché)').toBeTruthy();
        
        // Screenshot 01: Home cargado
        console.log('[TEST] Capturando screenshot 01_home_loaded.png...');
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '01_home_loaded.png'), fullPage: true });
        
        // Abrir modal "Revisar Pendientes CAE"
        console.log('[TEST] Abriendo modal "Revisar Pendientes CAE"...');
        let openModalBtn = page.locator('[data-testid="cae-review-open-btn"]');
        let count = await openModalBtn.count();
        if (count === 0) {
            // Fallback: buscar por texto
            openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
            count = await openModalBtn.count();
        }
        if (count === 0) {
            // Fallback adicional: buscar por onclick
            openModalBtn = page.locator('button[onclick*="openPendingReviewModal"]');
            count = await openModalBtn.count();
        }
        expect(count, 'Botón para abrir modal debe existir').toBeGreaterThan(0);
        await openModalBtn.first().click();
        
        // Esperar a que el modal esté visible
        await page.waitForSelector('[data-testid="cae-review-modal"]', { state: 'visible', timeout: 5000 }).catch(() => {
            return page.waitForSelector('.modal, [role="dialog"]', { state: 'visible', timeout: 5000 });
        });
        
        // Screenshot 02: Modal abierto
        console.log('[TEST] Capturando screenshot 02_modal_open.png...');
        await page.waitForTimeout(1000); // Dar tiempo para que el modal se renderice completamente
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '02_modal_open.png'), fullPage: true });
        
        // Función auxiliar para seleccionar opción en dropdown
        const selectDropdownOption = async (inputId, dropdownId, searchTexts) => {
            const input = page.locator(`#${inputId}`);
            await input.click();
            await page.waitForTimeout(500); // Esperar a que se abra el dropdown
            
            // Esperar a que el dropdown tenga opciones
            const dropdown = page.locator(`#${dropdownId}`);
            await dropdown.waitFor({ state: 'visible', timeout: 5000 });
            
            // Buscar la opción que coincida con alguno de los textos de búsqueda
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
                    await page.waitForTimeout(500); // Esperar a que se cierre el dropdown
                    return text;
                }
            }
            
            throw new Error(`No se encontró opción que coincida con: ${searchTexts.join(', ')}`);
        };
        
        // Rellenar campos EXACTAMENTE como se especifica
        console.log('[TEST] Rellenando campos del modal...');
        
        // 1. Empresa propia: "Tedelab Ingeniería SCCL (F63161988)"
        console.log('[TEST] Seleccionando empresa propia: Tedelab Ingeniería SCCL (F63161988)...');
        let companyValue = '';
        try {
            companyValue = await selectDropdownOption('filter-company', 'filter-company-dropdown', ['Tedelab', 'F63161988']);
            console.log(`[TEST] Empresa propia seleccionada: ${companyValue}`);
        } catch (e) {
            console.error(`[TEST] Error seleccionando empresa: ${e.message}`);
            throw e;
        }
        
        // 2. Cliente: "Aigues de Manresa (egestiona)"
        console.log('[TEST] Seleccionando cliente: Aigues de Manresa (egestiona)...');
        let coordValue = '';
        try {
            coordValue = await selectDropdownOption('filter-coord', 'filter-coord-dropdown', ['Aigues', 'Aigües', 'manresa']);
            console.log(`[TEST] Cliente seleccionado: ${coordValue}`);
        } catch (e) {
            console.error(`[TEST] Error seleccionando cliente: ${e.message}`);
            throw e;
        }
        
        // 3. Plataforma CAE: "egestiona"
        console.log('[TEST] Seleccionando plataforma CAE: egestiona...');
        let platformValue = '';
        try {
            platformValue = await selectDropdownOption('filter-platform', 'filter-platform-dropdown', ['egestiona']);
            console.log(`[TEST] Plataforma CAE seleccionada: ${platformValue}`);
        } catch (e) {
            console.error(`[TEST] Error seleccionando plataforma: ${e.message}`);
            throw e;
        }
        
        // VALIDACIÓN: Verificar que la plataforma CAE está realmente seleccionada
        const platformInputValue = await page.evaluate(() => {
            const input = document.getElementById('filter-platform');
            return input ? input.value : '';
        });
        if (!platformInputValue || !platformInputValue.toLowerCase().includes('egestiona')) {
            throw new Error(`Plataforma CAE no está seleccionada correctamente. Valor actual: "${platformInputValue}"`);
        }
        
        // 4. Ámbito del documento: "Trabajador" (NO Ambos)
        console.log('[TEST] Seleccionando ámbito: Trabajador...');
        const scopeWorker = page.locator('[data-testid="cae-review-scope-worker"]');
        const scopeWorkerCount = await scopeWorker.count();
        if (scopeWorkerCount > 0) {
            await scopeWorker.click();
        } else {
            // Fallback: buscar por radio button
            const workerRadio = page.locator('input[type="radio"][value="worker"], input[type="radio"][name="scope"][value="worker"]');
            if (await workerRadio.count() > 0) {
                await workerRadio.click();
            } else {
                // Fallback adicional: buscar por texto
                const workerLabel = page.locator('label:has-text("Trabajador")');
                if (await workerLabel.count() > 0) {
                    await workerLabel.click();
                }
            }
        }
        await page.waitForTimeout(500);
        
        // Verificar que "Ambos" NO está seleccionado
        const ambosSelected = await page.evaluate(() => {
            const ambosRadio = document.querySelector('input[type="radio"][value="both"], input[type="radio"][name="scope"][value="both"]');
            return ambosRadio ? ambosRadio.checked : false;
        });
        if (ambosSelected) {
            throw new Error('Ámbito "Ambos" está seleccionado cuando debería ser "Trabajador"');
        }
        
        // 5. Trabajador: "Emilio Roldán Molina (erm)"
        console.log('[TEST] Seleccionando trabajador: Emilio Roldán Molina (erm)...');
        let workerValue = '';
        try {
            workerValue = await selectDropdownOption('filter-worker', 'filter-worker-dropdown', ['Emilio', 'Roldán', 'erm']);
            console.log(`[TEST] Trabajador seleccionado: ${workerValue}`);
        } catch (e) {
            console.error(`[TEST] Error seleccionando trabajador: ${e.message}`);
            throw e;
        }
        
        // 6. Tipo de documento: "Todos" (vacío o sin filtro)
        console.log('[TEST] Configurando tipo de documento: Todos...');
        await page.evaluate(() => {
            const typeInput = document.getElementById('filter-type');
            if (typeInput) {
                typeInput.value = '';
                typeInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        await page.waitForTimeout(500);
        
        // Screenshot 03: Modal rellenado
        console.log('[TEST] Capturando screenshot 03_modal_filled.png...');
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '03_modal_filled.png'), fullPage: true });
        
        // Preparar para interceptar la respuesta de red ANTES del click
        let networkResponse = null;
        let responseJson = null;
        
        const responsePromise = page.waitForResponse(
            resp => resp.url().includes('/runs/egestiona/build_submission_plan_readonly') && resp.request().method() === 'POST',
            { timeout: 360000 } // 6 minutos timeout
        );
        
        // Click en "Revisar ahora (READ-ONLY)"
        console.log('[TEST] Haciendo click en "Revisar ahora (READ-ONLY)"...');
        let reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        let reviewBtnCount = await reviewBtn.count();
        if (reviewBtnCount === 0) {
            // Fallback: buscar por texto
            reviewBtn = page.locator('button:has-text("Revisar ahora (READ-ONLY)")');
            reviewBtnCount = await reviewBtn.count();
        }
        if (reviewBtnCount === 0) {
            // Fallback adicional: buscar por texto parcial
            reviewBtn = page.locator('button:has-text("Revisar ahora")');
            reviewBtnCount = await reviewBtn.count();
        }
        expect(reviewBtnCount, 'Botón "Revisar ahora (READ-ONLY)" debe existir').toBeGreaterThan(0);
        await expect(reviewBtn.first()).toBeVisible({ timeout: 10000 });
        await expect(reviewBtn.first()).toBeEnabled({ timeout: 10000 });
        
        await reviewBtn.first().scrollIntoViewIfNeeded();
        await reviewBtn.first().click({ force: true, timeout: 10000 });
        
        // Screenshot 04: Justo después del click
        console.log('[TEST] Capturando screenshot 04_after_click.png...');
        await page.waitForTimeout(500); // Pequeña espera para que el botón cambie de estado
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '04_after_click.png'), fullPage: true });
        
        // Esperar la respuesta de red
        console.log('[TEST] Esperando respuesta del endpoint (timeout 6min)...');
        try {
            networkResponse = await responsePromise;
            const status = networkResponse.status();
            console.log(`[TEST] Respuesta HTTP recibida: ${status}`);
            
            if (status === 200) {
                responseJson = await networkResponse.json();
                console.log('[TEST] ✅ Respuesta recibida:', responseJson.status, 'run_id:', responseJson.run_id || responseJson.artifacts?.run_id);
            } else {
                // Si no es 200, intentar leer el error
                try {
                    responseJson = await networkResponse.json();
                } catch {
                    responseJson = { 
                        status: 'error', 
                        error_code: 'http_error', 
                        message: `HTTP ${status}`,
                        http_status: status
                    };
                }
                console.log(`[TEST] ⚠️ Respuesta con error HTTP: ${status}`);
            }
        } catch (error) {
            console.error('[TEST] ❌ No se recibió respuesta del endpoint:', error.message);
            // Continuar para capturar el estado actual de la UI
            responseJson = {
                status: 'error',
                error_code: 'timeout',
                message: `No se recibió respuesta del endpoint en 6 minutos. Error: ${error.message}`
            };
        }
        
        // Guardar JSON de red
        console.log('[TEST] Guardando last_network_response.json...');
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'last_network_response.json'),
            JSON.stringify(responseJson, null, 2),
            'utf-8'
        );
        
        // Esperar a que se renderice completamente (resultado o error)
        console.log('[TEST] Esperando a que se renderice completamente...');
        await page.waitForTimeout(5000);
        
        // Screenshot 05: Estado final
        console.log('[TEST] Capturando screenshot 05_final.png...');
        await page.screenshot({ path: path.join(EVIDENCE_DIR, '05_final.png'), fullPage: true });
        
        // Guardar logs de consola
        console.log('[TEST] Guardando console_log.txt...');
        const consoleLogText = consoleLogs.map(log => 
            `[${log.timestamp}] [${log.type.toUpperCase()}] ${log.text}`
        ).join('\n');
        fs.writeFileSync(path.join(EVIDENCE_DIR, 'console_log.txt'), consoleLogText, 'utf-8');
        
        // Guardar errores de página
        console.log('[TEST] Guardando page_errors.txt...');
        const pageErrorsText = pageErrors.map(err => 
            `[${err.timestamp}]\n${err.message}\n${err.stack || ''}\n---\n`
        ).join('\n');
        fs.writeFileSync(path.join(EVIDENCE_DIR, 'page_errors.txt'), pageErrorsText || 'No hay errores de página', 'utf-8');
        
        // Verificar si hay "run_id_missing" en UI
        const pageText = await page.textContent('body').catch(() => '');
        const hasRunIdMissing = pageText.includes('run_id_missing') || pageText.includes('No se pudo generar run_id');
        
        // Extraer run_id del JSON
        const extractedRunId = responseJson?.run_id || responseJson?.artifacts?.run_id;
        
        // Validaciones finales y resumen
        console.log('\n=== RESUMEN FINAL ===');
        console.log(`✅ ¿Se abrió /home correcto? (buildStamp): ${buildStamp ? 'SÍ' : 'NO'}`);
        console.log(`✅ ¿Se pudo abrir modal?: SÍ`);
        console.log(`✅ ¿Se seleccionaron todos los campos?: SÍ`);
        console.log(`✅ ¿Llegó la respuesta del POST?: ${networkResponse ? 'SÍ' : 'NO'}`);
        if (networkResponse) {
            console.log(`   - HTTP Status: ${networkResponse.status()}`);
        }
        if (responseJson) {
            console.log(`   - Status: ${responseJson.status}`);
            console.log(`   - error_code: ${responseJson.error_code || 'N/A'}`);
            console.log(`   - run_id: ${extractedRunId || 'NO EXISTE'}`);
        }
        console.log(`✅ Ruta exacta de evidencias: ${EVIDENCE_DIR}`);
        
        // Si hay "run_id_missing" en UI pero el JSON tiene run_id, es un BUG
        if (hasRunIdMissing && extractedRunId) {
            console.error('\n❌ BUG DETECTADO: UI muestra "run_id_missing" pero el JSON tiene run_id!');
            console.error(`   JSON run_id: ${extractedRunId}`);
            console.error(`   JSON completo guardado en: ${path.join(EVIDENCE_DIR, 'last_network_response.json')}`);
        }
        
        // Guardar resumen en archivo
        const summary = {
            timestamp: new Date().toISOString(),
            url: currentUrl,
            buildStamp: buildStamp,
            runId: extractedRunId,
            status: responseJson?.status,
            errorCode: responseJson?.error_code,
            httpStatus: networkResponse?.status(),
            hasRunIdMissingInUI: hasRunIdMissing,
            consoleErrors: consoleLogs.filter(log => log.type === 'error').length,
            pageErrors: pageErrors.length,
            evidenceDir: EVIDENCE_DIR,
            fieldsSelected: {
                company: companyValue,
                coord: coordValue,
                platform: platformValue,
                worker: workerValue,
                scope: 'worker'
            }
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'summary.json'),
            JSON.stringify(summary, null, 2),
            'utf-8'
        );
        
        // Si hay error, mostrar detalles
        if (responseJson?.status === 'error') {
            console.log('\n=== ERROR DETECTADO ===');
            console.log(`error_code: ${responseJson.error_code}`);
            console.log(`message: ${responseJson.message}`);
            console.log(`JSON completo guardado en: ${path.join(EVIDENCE_DIR, 'last_network_response.json')}`);
        }
        
        console.log(`\n✅ Test completado. Evidencias guardadas en: ${EVIDENCE_DIR}`);
    });
});
