const { test, expect } = require('@playwright/test');

test.describe('HOTFIX: Frontend Page Contract Error Render (E2E)', () => {
    test('Validar que el frontend renderiza errores estructurados sin crashear', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        
        // Capturar errores de consola
        const consoleErrors = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleErrors.push(msg.text());
            }
        });
        
        // Navegar al dashboard
        // Usar ruta relativa gracias a baseURL en playwright.config.js
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
        // Abrir modal "Revisar Pendientes CAE"
        const openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
        await openModalBtn.click();
        
        // Esperar a que el modal esté visible
        await page.waitForSelector('[data-testid="cae-review-modal"]', { state: 'visible' });
        
        // Seleccionar plataforma "egestiona" usando JavaScript (dropdown puede estar oculto)
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
                // Intentar seleccionar "Aigues de Manresa" o la primera opción disponible
                const options = JSON.parse(coordInput.dataset.options || '[]');
                if (options.length > 0) {
                    const firstOption = options[0];
                    coordInput.value = firstOption.label;
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
                    companyInput.value = firstOption.label;
                    companyInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        });
        
        // Interceptar la llamada al endpoint para forzar un error estructurado
        await page.route(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly*`, async route => {
            // Simular respuesta de error estructurado
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    status: 'error',
                    error_code: 'wrong_page',
                    message: 'No se está en la vista correcta de pendientes',
                    details: {
                        current_url: 'http://example.com/wrong',
                        frame_url: 'http://example.com/wrong_frame.asp',
                        expected_url_pattern: 'buscador.asp?Apartado_ID=3'
                    },
                    artifacts: {
                        run_id: 'r_test_error_123',
                        evidence: {
                            screenshot: 'wrong_page.png',
                            dump: 'wrong_page_dump.txt'
                        }
                    }
                })
            });
        });
        
        // Click en "Revisar ahora (READ-ONLY)"
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await reviewBtn.click();
        
        // Esperar a que aparezca el error (no debe crashear)
        await page.waitForTimeout(2000);
        
        // Verificar que NO hay errores de consola relacionados con null.innerHTML o escapeHtml
        const nullErrors = consoleErrors.filter(err => 
            err.includes('Cannot set properties of null') || 
            err.includes('innerHTML') ||
            err.includes('null') ||
            err.includes('escapeHtml is not defined') ||
            err.includes('escapeHtml is not a function')
        );
        expect(nullErrors.length).toBe(0);
        
        // Verificar que el modal sigue operativo (no se cerró por error)
        const modal = page.locator('[data-testid="cae-review-modal"]');
        await expect(modal).toBeVisible();
        
        // Verificar que aparece algún mensaje de error (puede estar en diferentes lugares)
        // Buscar texto de error en el modal
        const errorText = page.locator('text=/error|Error|wrong_page/i');
        const errorCount = await errorText.count();
        expect(errorCount).toBeGreaterThan(0);
        
        // Lo importante: NO debe haber errores de consola por null.innerHTML
        // El modal debe seguir operativo
    });
});
