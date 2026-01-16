const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('HOTFIX C2.12.5.1: Extracción robusta de run_id', () => {
    test('UI NO muestra run_id_missing cuando respuesta contiene plan_id o run_id', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_12_5_1_run_id_fix');
        
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
        
        // Preparar para interceptar la respuesta de red
        let networkResponse = null;
        let responseJson = null;
        
        const responsePromise = page.waitForResponse(
            resp => resp.url().includes('/runs/egestiona/build_submission_plan_readonly') && resp.request().method() === 'POST',
            { timeout: 360000 } // 6 minutos
        );
        
        // Click en "Revisar ahora (READ-ONLY)"
        console.log('[TEST] Haciendo click en "Revisar ahora (READ-ONLY)"...');
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(reviewBtn.first()).toBeVisible({ timeout: 10000 });
        await expect(reviewBtn.first()).toBeEnabled({ timeout: 10000 });
        
        await reviewBtn.first().click();
        
        // Esperar la respuesta de red
        console.log('[TEST] Esperando respuesta del endpoint...');
        try {
            networkResponse = await responsePromise;
            responseJson = await networkResponse.json();
            console.log('[TEST] ✅ Respuesta recibida');
        } catch (error) {
            console.error('[TEST] ❌ No se recibió respuesta del endpoint:', error.message);
            throw error;
        }
        
        // Guardar JSON de red
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'last_network_response.json'),
            JSON.stringify(responseJson, null, 2),
            'utf-8'
        );
        
        // Esperar a que se renderice
        await page.waitForTimeout(5000);
        
        // Screenshot final
        await page.screenshot({ path: path.join(EVIDENCE_DIR, 'final_state.png'), fullPage: true });
        
        // VALIDACIÓN PRINCIPAL: Verificar que NO hay error "run_id_missing" en UI
        const pageText = await page.textContent('body').catch(() => '');
        const hasRunIdMissingError = pageText.includes('run_id_missing') && 
                                     (pageText.includes('No se pudo generar run_id') || 
                                      pageText.includes('run_id_missing'));
        
        // Extraer run_id del JSON usando la misma lógica que el frontend
        const extractRunId = (result) => {
            return (
                result?.run_id ||
                result?.plan_id ||
                result?.runId ||
                result?.artifacts?.run_id ||
                result?.artifacts?.runId ||
                result?.artifacts?.plan_id ||
                result?.data?.run_id ||
                result?.data?.runId ||
                result?.data?.plan_id ||
                null
            );
        };
        
        const extractedRunId = extractRunId(responseJson);
        
        // Guardar logs de consola
        const consoleLogText = consoleLogs.map(log => 
            `[${log.timestamp}] [${log.type.toUpperCase()}] ${log.text}`
        ).join('\n');
        fs.writeFileSync(path.join(EVIDENCE_DIR, 'console_log.txt'), consoleLogText, 'utf-8');
        
        // Guardar resumen
        const summary = {
            timestamp: new Date().toISOString(),
            httpStatus: networkResponse.status(),
            responseStatus: responseJson?.status,
            errorCode: responseJson?.error_code,
            extractedRunId: extractedRunId,
            hasRunIdInResponse: !!responseJson?.run_id,
            hasPlanIdInResponse: !!responseJson?.plan_id,
            hasArtifactsRunId: !!responseJson?.artifacts?.run_id,
            hasRunIdMissingErrorInUI: hasRunIdMissingError,
            responseKeys: Object.keys(responseJson || {}),
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(summary, null, 2),
            'utf-8'
        );
        
        // ASSERT: Si la respuesta tiene run_id o plan_id, NO debe haber error run_id_missing en UI
        if (extractedRunId) {
            expect(hasRunIdMissingError, 
                `UI NO debe mostrar error "run_id_missing" cuando la respuesta contiene run_id/plan_id. ` +
                `Extracted run_id: ${extractedRunId}, Response keys: ${Object.keys(responseJson || {}).join(', ')}`
            ).toBe(false);
        }
        
        // ASSERT: Si status es "ok", debe haber run_id o plan_id
        if (responseJson?.status === 'ok') {
            expect(extractedRunId, 
                `Si status es "ok", debe haber run_id o plan_id en la respuesta. ` +
                `Response: ${JSON.stringify(responseJson, null, 2)}`
            ).toBeTruthy();
        }
        
        console.log('\n=== RESUMEN DEL TEST ===');
        console.log(`HTTP Status: ${networkResponse.status()}`);
        console.log(`Response Status: ${responseJson?.status}`);
        console.log(`Extracted Run ID: ${extractedRunId || 'NO ENCONTRADO'}`);
        console.log(`Has run_id in response: ${!!responseJson?.run_id}`);
        console.log(`Has plan_id in response: ${!!responseJson?.plan_id}`);
        console.log(`Has run_id_missing error in UI: ${hasRunIdMissingError}`);
        console.log(`Evidencias guardadas en: ${EVIDENCE_DIR}`);
        
        // Si hay run_id pero UI muestra error, es un BUG
        if (extractedRunId && hasRunIdMissingError) {
            throw new Error(
                `BUG DETECTADO: UI muestra "run_id_missing" pero la respuesta contiene run_id/plan_id. ` +
                `Extracted: ${extractedRunId}, Response: ${JSON.stringify(responseJson, null, 2)}`
            );
        }
    });
});
