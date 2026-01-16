/**
 * SPRINT B3: Test mínimo para verificar readiness real y capturar errores.
 */
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash, BACKEND_URL } = require('./helpers/e2eSeed');

test.describe('SPRINT B3: Debug mínimo - Verificar readiness', () => {
    const debugDir = path.join(__dirname, '..', 'docs', 'evidence', 'e2e_debug');
    
    test.beforeAll(async () => {
        if (!fs.existsSync(debugDir)) {
            fs.mkdirSync(debugDir, { recursive: true });
        }
    });
    
    test('Verificar readiness real tras gotoHash(#calendario)', async ({ page, request }) => {
        // 1. Seed
        console.log('[DEBUG] Starting seed...');
        await seedReset({ request });
        const seedData = await seedBasicRepository({ request });
        console.log('[DEBUG] Seed completed:', seedData);
        
        // 2. Capturar errores de consola
        const consoleErrors = [];
        const consoleWarnings = [];
        page.on('console', msg => {
            const text = msg.text();
            const type = msg.type();
            if (type === 'error') {
                consoleErrors.push({ type, text, timestamp: new Date().toISOString() });
                console.log(`[CONSOLE ERROR] ${text}`);
            } else if (type === 'warning') {
                consoleWarnings.push({ type, text, timestamp: new Date().toISOString() });
            }
        });
        
        // 3. Capturar errores de página
        const pageErrors = [];
        page.on('pageerror', error => {
            pageErrors.push({
                message: error.message,
                stack: error.stack,
                timestamp: new Date().toISOString()
            });
            console.log(`[PAGE ERROR] ${error.message}`);
        });
        
        // 4. Navegar usando gotoHash
        console.log('[DEBUG] Navigating to #calendario...');
        try {
            await gotoHash(page, 'calendario');
            console.log('[DEBUG] gotoHash completed');
        } catch (error) {
            console.log(`[DEBUG] gotoHash failed: ${error.message}`);
            
            // Capturar estado de la página
            const content = await page.content();
            const screenshot = await page.screenshot({ fullPage: true });
            
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test.html'),
                content
            );
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test.png'),
                screenshot
            );
            
            // Guardar errores
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test_console_errors.json'),
                JSON.stringify({ consoleErrors, consoleWarnings, pageErrors }, null, 2)
            );
            
            throw error;
        }
        
        // 5. Verificar que el elemento existe
        console.log('[DEBUG] Checking for view-calendar-ready...');
        const element = page.locator('[data-testid="view-calendar-ready"]');
        const count = await element.count();
        console.log(`[DEBUG] Found ${count} elements with view-calendar-ready`);
        
        if (count === 0) {
            // Capturar estado de la página
            const content = await page.content();
            const screenshot = await page.screenshot({ fullPage: true });
            
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test_no_element.html'),
                content
            );
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test_no_element.png'),
                screenshot
            );
            
            // Verificar qué elementos existen
            const allTestIds = await page.evaluate(() => {
                const elements = document.querySelectorAll('[data-testid]');
                return Array.from(elements).map(el => ({
                    testId: el.getAttribute('data-testid'),
                    tag: el.tagName,
                    id: el.id,
                    className: el.className
                }));
            });
            
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test_all_testids.json'),
                JSON.stringify(allTestIds, null, 2)
            );
            
            console.log('[DEBUG] All data-testid elements:', allTestIds);
            
            // Guardar errores
            fs.writeFileSync(
                path.join(debugDir, 'minimal_test_console_errors.json'),
                JSON.stringify({ consoleErrors, consoleWarnings, pageErrors }, null, 2)
            );
        }
        
        // 6. Verificar health endpoint
        const healthResponse = await request.get(`${BACKEND_URL}/api/health`);
        const health = await healthResponse.json();
        console.log('[DEBUG] Health response:', health);
        
        fs.writeFileSync(
            path.join(debugDir, 'minimal_test_health.json'),
            JSON.stringify(health, null, 2)
        );
        
        // Assert final
        await expect(element).toBeAttached({ timeout: 15000 });
    });
});


