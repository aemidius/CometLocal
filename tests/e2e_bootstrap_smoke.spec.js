const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { BACKEND_URL } = require('./helpers/e2eSeed');

test.describe('Bootstrap Smoke Test', () => {
    test('should bootstrap correctly and expose runRoutingNow', async ({ page }) => {
        const debugDir = path.join(__dirname, '..', 'docs', 'evidence', 'e2e_debug');
        if (!fs.existsSync(debugDir)) {
            fs.mkdirSync(debugDir, { recursive: true });
        }

        // Capturar errores del navegador
        page.on('console', msg => {
            const type = msg.type();
            const text = msg.text();
            console.log(`[BROWSER ${type}] ${text}`);
        });

        page.on('pageerror', err => {
            console.log('[PAGEERROR]', err.message);
            console.log('[PAGEERROR] Stack:', err.stack);
        });

        page.on('crash', () => {
            console.log('[CRASH] page crashed');
        });

        // Navegar a la página
        await page.goto(`${BACKEND_URL}/repository`, { waitUntil: 'domcontentloaded' });

        // Esperar app-ready
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });

        // Verificar que runRoutingNow está disponible
        const hasRun = await page.evaluate(() => typeof window.runRoutingNow);
        console.log('typeof runRoutingNow:', hasRun);

        // Capturar evidencia
        await page.screenshot({ path: path.join(debugDir, 'bootstrap_smoke.png'), fullPage: true });
        const html = await page.content();
        fs.writeFileSync(path.join(debugDir, 'bootstrap_smoke.html'), html);

        // Fallar si runRoutingNow no es función
        expect(hasRun).toBe('function');
    });
});
