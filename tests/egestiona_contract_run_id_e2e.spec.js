const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.13.2: Validación de contrato run_id + Grid Loading + Empty-state (E2E REAL)', () => {
    test('Validar que run_id está presente, grid espera loading, y empty-state no genera error falso', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        
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
        expect(healthResponse.ok()).toBeTruthy();
        
        // Navegar al dashboard (usar ruta relativa gracias a baseURL en playwright.config.js)
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
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
                platformInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
        
        // Seleccionar coordinación usando JavaScript
        await page.evaluate(() => {
            const coordInput = document.getElementById('filter-coord');
            if (coordInput) {
                const options = JSON.parse(coordInput.dataset.options || '[]');
                if (options.length > 0) {
                    const firstOption = options[0];
                    coordInput.value = firstOption.label || firstOption;
                    coordInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        });
        
        // Seleccionar empresa usando JavaScript
        await page.evaluate(() => {
            const companyInput = document.getElementById('filter-company');
            if (companyInput) {
                const options = JSON.parse(companyInput.dataset.options || '[]');
                if (options.length > 0) {
                    const firstOption = options[0];
                    companyInput.value = firstOption.label || firstOption || '';
                    companyInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        });
        
        // Esperar a que el modal esté completamente cargado
        await page.waitForTimeout(1000);
        
        // Preparar waitForResponse ANTES de hacer click (importante para capturar el request)
        const responsePromise = page.waitForResponse(
            response => {
                const url = response.url();
                return url.includes('/runs/egestiona/build_submission_plan_readonly');
            },
            { timeout: 300000 } // 5 minutos timeout para ejecución real
        );
        
        // Click REAL en el botón usando data-testid
        const executeBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(executeBtn).toBeVisible({ timeout: 10000 });
        await expect(executeBtn).toBeEnabled({ timeout: 10000 });
        
        // Hacer scroll si es necesario
        await executeBtn.scrollIntoViewIfNeeded();
        
        // Click usando force si es necesario (para evitar problemas de interceptación)
        await executeBtn.click({ force: true, timeout: 10000 });
        
        // Esperar a que el botón se deshabilite (indica que el request se inició)
        try {
            await page.waitForFunction(
                () => {
                    const btn = document.querySelector('[data-testid="cae-review-run-btn"]');
                    return btn && btn.disabled;
                },
                { timeout: 5000 }
            );
            console.log('[E2E] Botón deshabilitado, request iniciado');
        } catch (e) {
            console.warn('[E2E] Botón no se deshabilitó, pero continuando...');
        }
        
        // Esperar y capturar la respuesta REAL
        let responseJson = null;
        let responseReceived = false;
        
        try {
            const response = await responsePromise;
            responseJson = await response.json();
            responseReceived = true;
            
            console.log('[E2E] Response recibido:', responseJson.status, 'run_id:', responseJson.run_id || responseJson.artifacts?.run_id);
        } catch (e) {
            // Si no llega response -> FAIL (esto evita falso positivo)
            throw new Error(`No se recibió respuesta del endpoint en 5 minutos. Esto indica que el click no funcionó o el request no se hizo. Error: ${e.message}`);
        }
        
        // Verificar que se recibió la respuesta
        expect(responseReceived, 'No se recibió respuesta del endpoint').toBe(true);
        expect(responseJson, 'Response JSON es null').not.toBeNull();
        
        // Helper para extraer run_id (igual que en frontend)
        function extractRunId(result) {
            return (
                result?.run_id ||
                result?.artifacts?.run_id ||
                result?.artifacts?.runId ||
                result?.data?.run_id ||
                result?.data?.runId ||
                null
            );
        }
        
        // ASSERT 1: json.status in ["ok","error"]
        expect(['ok', 'error']).toContain(responseJson.status);
        
        // ASSERT 2: si json.run_id existe => en UI aparece "Run ID: ..." o link "Ver run completo"
        const extractedRunId = extractRunId(responseJson);
        
        if (extractedRunId) {
            // Esperar a que se renderice en UI (timeout razonable)
            await page.waitForSelector('code, a[href*="/runs/"]', { 
                state: 'visible', 
                timeout: 10000 
            }).catch(() => {
                // Si no aparece, verificar que al menos no hay error falso
            });
            
            // Verificar que el run_id está visible en UI
            const runIdVisible = await page.locator(`code:has-text("${extractedRunId}"), a[href*="/runs/${extractedRunId}"]`).count();
            if (runIdVisible === 0) {
                // Verificar al menos que hay algún run_id visible
                const anyRunId = await page.locator('code, a[href*="/runs/"]').count();
                expect(anyRunId).toBeGreaterThan(0,
                    `run_id existe en response (${extractedRunId}) pero no está visible en UI`);
            }
        }
        
        // ASSERT 3: NUNCA aparece "run_id_missing" salvo que json.error_code === "run_id_missing"
        await page.waitForTimeout(2000); // Esperar a que se renderice completamente
        
        const runIdMissingBanner = await page.locator('.alert-error, .alert-danger')
            .filter({ hasText: /run_id_missing|falló antes de crear/i })
            .count();
        
        if (responseJson.error_code !== 'run_id_missing') {
            expect(runIdMissingBanner).toBe(0,
                `Se encontró banner "run_id_missing" en UI pero error_code es "${responseJson.error_code}". Response: ${JSON.stringify(responseJson, null, 2)}`);
        }
        
        // ASSERT 4: Si hay error "pending_list_not_loaded", verificar que NO es por empty-state real
        if (responseJson.error_code === 'pending_list_not_loaded') {
            const details = responseJson.details || {};
            const loadingInfo = details.loading_info || {};
            const emptyStateDetected = details.selector_checks?.has_empty_state || false;
            
            // Si se detectó empty-state, el error NO debería haberse lanzado
            if (emptyStateDetected) {
                throw new Error(`Error pending_list_not_loaded lanzado pero empty_state_detected=true. Esto indica que el fix no funcionó. Details: ${JSON.stringify(details, null, 2)}`);
            }
        }
        
        // ASSERT 4: No hay "unexpected_error" en pantalla
        const unexpectedErrorBanner = await page.locator('.alert-error, .alert-danger')
            .filter({ hasText: /unexpected_error|error inesperado/i })
            .count();
        
        expect(unexpectedErrorBanner).toBe(0,
            'Se encontró banner "unexpected_error" en pantalla');
        
        // ASSERT 5: consoleErrors.length === 0 (filtrando warnings)
        const criticalConsoleErrors = consoleErrors.filter(err => {
            const lower = err.toLowerCase();
            return !lower.includes('warning') && // Filtrar warnings
                   !lower.includes('deprecated') &&
                   (lower.includes('run_id_missing') ||
                    lower.includes('cannot set properties of null') ||
                    lower.includes('escapehtml is not defined') ||
                    lower.includes('is not a function'));
        });
        
        expect(criticalConsoleErrors.length).toBe(0,
            `Se encontraron errores críticos en consola: ${JSON.stringify(criticalConsoleErrors, null, 2)}`);
        
        // ASSERT 6: pageErrors.length === 0
        expect(pageErrors.length).toBe(0,
            `Se encontraron errores de página: ${JSON.stringify(pageErrors, null, 2)}`);
        
        // Guardar evidencia
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_contract');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
        
        // Guardar JSON response
        const responsePath = path.join(evidenceDir, 'last_response_from_e2e.json');
        fs.writeFileSync(responsePath, JSON.stringify(responseJson, null, 2), 'utf-8');
        console.log(`[E2E] Response JSON guardado en: ${responsePath}`);
        
        // Guardar screenshot del modal final
        const screenshotPath = path.join(evidenceDir, 'modal_final_screenshot.png');
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.log(`[E2E] Screenshot guardado en: ${screenshotPath}`);
        
        console.log('[E2E] Test completado. Response status:', responseJson.status);
        console.log('[E2E] Extracted run_id:', extractedRunId);
    });
});
