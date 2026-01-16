const { test, expect } = require('@playwright/test');

test.describe('HOTFIX: Modal CAE sin errores JS ni banners inesperados', () => {
    test('Validar que no hay errores JS en consola ni banners de error inesperado', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        
        // Capturar errores de página y consola
        const pageErrors = [];
        const consoleErrors = [];
        const consoleWarnings = [];
        
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
            } else if (type === 'warning') {
                // Filtrar warnings graves
                if (text.includes('deprecated') || 
                    text.includes('experimental') ||
                    text.includes('unexpected') ||
                    text.includes('run_id_missing') ||
                    text.includes('Cannot set properties of null') ||
                    text.includes('escapeHtml is not defined') ||
                    text.includes('is not a function')) {
                    consoleWarnings.push(text);
                }
            }
        });
        
        // Verificar que el servidor está corriendo
        const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
        expect(healthResponse.ok()).toBeTruthy();
        
        // Navegar al dashboard (usar ruta relativa gracias a baseURL en playwright.config.js)
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
        // Abrir modal "Revisar Pendientes CAE (Avanzado)"
        const openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
        if (await openModalBtn.count() === 0) {
            // Intentar con texto alternativo
            const altBtn = page.locator('button').filter({ hasText: /Revisar|CAE|Pendientes/i });
            if (await altBtn.count() > 0) {
                await altBtn.first().click();
            } else {
                throw new Error('No se encontró el botón para abrir el modal CAE');
            }
        } else {
            await openModalBtn.click();
        }
        
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
                // Intentar seleccionar la primera opción disponible
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
        
        // Verificar que el modal está visible y funcional
        const modal = page.locator('[data-testid="cae-review-modal"]');
        await expect(modal).toBeVisible();
        
        // Verificar que no hay errores de página
        const criticalPageErrors = pageErrors.filter(e => {
            const msg = e.message.toLowerCase();
            return msg.includes('cannot set properties of null') ||
                   msg.includes('escapehtml is not defined') ||
                   msg.includes('is not a function') ||
                   msg.includes('undefined is not') ||
                   msg.includes('null is not');
        });
        
        expect(criticalPageErrors.length).toBe(0, 
            `Se encontraron errores críticos de página: ${JSON.stringify(criticalPageErrors, null, 2)}`);
        
        // Verificar que no hay errores críticos en consola
        const criticalConsoleErrors = consoleErrors.filter(text => {
            const lower = text.toLowerCase();
            return lower.includes('run_id_missing') ||
                   lower.includes('unexpected_error') ||
                   lower.includes('cannot set properties of null') ||
                   lower.includes('escapehtml is not defined') ||
                   lower.includes('is not a function');
        });
        
        expect(criticalConsoleErrors.length).toBe(0,
            `Se encontraron errores críticos en consola: ${JSON.stringify(criticalConsoleErrors, null, 2)}`);
        
        // Verificar que no hay warnings críticos
        expect(consoleWarnings.length).toBe(0,
            `Se encontraron warnings críticos: ${JSON.stringify(consoleWarnings, null, 2)}`);
        
        // Verificar que no aparece banner de error inesperado
        const unexpectedErrorBanner = await page.locator('.alert-error, .alert-danger')
            .filter({ hasText: /unexpected_error|error inesperado|run_id_missing/i })
            .count();
        
        expect(unexpectedErrorBanner).toBe(0,
            'Se encontró un banner de error inesperado en la UI');
        
        // Verificar que no hay banners de error inesperado visibles en el modal
        const errorBanners = await page.locator('.alert-error, .alert-danger')
            .filter({ hasText: /unexpected_error|error inesperado|run_id_missing/i })
            .count();
        
        expect(errorBanners).toBe(0,
            'Se encontró un banner de error inesperado en el modal');
        
        // Log final para debugging
        console.log('Page errors:', pageErrors.length);
        console.log('Console errors:', consoleErrors.length);
        console.log('Console warnings:', consoleWarnings.length);
    });
});
