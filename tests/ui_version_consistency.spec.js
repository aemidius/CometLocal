/**
 * SPRINT C2.35.8: Test E2E para verificar consistencia de versión UI entre backend y frontend.
 * 
 * Verifica:
 * 1) GET /api/version devuelve ui_version no vacío
 * 2) El footer muestra "UI: <hash>"
 * 3) El hash del footer coincide con ui_version del API
 * 4) El header X-CometLocal-UI-Version coincide con ui_version
 */

import { test, expect } from '@playwright/test';

test.describe('UI Version Consistency (C2.35.8)', () => {
    test('should have consistent UI version between API, footer, and header', async ({ page }) => {
        // 1) GET /api/version (obtiene hash del git)
        const versionResponse = await page.request.get('http://127.0.0.1:8000/api/version');
        expect(versionResponse.ok()).toBeTruthy();
        
        const versionInfo = await versionResponse.json();
        expect(versionInfo).toHaveProperty('ui_version');
        expect(versionInfo.ui_version).toBeTruthy();
        expect(versionInfo.ui_version).not.toBe('');
        expect(versionInfo.ui_version).not.toBe('unknown');
        
        // Verificar header X-CometLocal-UI-Version en /api/version
        const apiHeaderVersion = versionResponse.headers()['x-cometlocal-ui-version'];
        expect(apiHeaderVersion).toBeTruthy();
        expect(apiHeaderVersion).toBe(versionInfo.ui_version);
        
        // 2) Abrir /repository y leer footer "UI: ..."
        await page.goto('http://127.0.0.1:8000/repository');
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        
        // Esperar a que el fetch de /api/version complete y actualice el footer
        await page.waitForFunction(
            () => {
                const el = document.getElementById('version-stamp-commit');
                return el && el.textContent && el.textContent !== '...' && el.textContent.trim().length > 0;
            },
            { timeout: 5000 }
        );
        
        // Leer el hash del footer
        const versionStampEl = page.locator('#version-stamp-commit');
        await expect(versionStampEl).toBeVisible({ timeout: 5000 });
        const footerVersion = await versionStampEl.textContent();
        expect(footerVersion).toBeTruthy();
        expect(footerVersion.trim().length).toBeGreaterThan(0);
        expect(footerVersion.trim()).not.toBe('...');
        
        // 3) Assert: el hash del git (ui_version del API) debe coincidir con el footer
        expect(footerVersion.trim()).toBe(versionInfo.ui_version);
        
        // 4) Verificar header X-CometLocal-UI-Version en /repository
        const response = await page.request.get('http://127.0.0.1:8000/repository');
        const headerVersion = response.headers()['x-cometlocal-ui-version'];
        expect(headerVersion).toBeTruthy();
        expect(headerVersion).toBe(versionInfo.ui_version);
        expect(headerVersion).toBe(footerVersion.trim());
        
        // 5) Verificar window.__COMETLOCAL_VERSION_STAMP (debe coincidir con el footer y API)
        const windowVersion = await page.evaluate(() => {
            return window.__COMETLOCAL_VERSION_STAMP;
        });
        expect(windowVersion).toBeTruthy();
        expect(windowVersion).toBe(footerVersion.trim());
        expect(windowVersion).toBe(versionInfo.ui_version);
    });
    
    test('should not show version mismatch banner when versions match', async ({ page }) => {
        await page.goto('http://127.0.0.1:8000/repository');
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        
        // Esperar a que el fetch de /api/version complete
        await page.waitForFunction(
            () => {
                const el = document.getElementById('version-stamp-commit');
                return el && el.textContent && el.textContent !== '...' && el.textContent.trim().length > 0;
            },
            { timeout: 5000 }
        );
        
        // Esperar un poco más para que el check de versión se complete
        await page.waitForTimeout(1000);
        
        // Verificar que NO aparece el banner de desincronización
        const mismatchBanner = page.locator('[data-testid="ui-version-mismatch-banner"]');
        await expect(mismatchBanner).not.toBeVisible({ timeout: 2000 });
    });
});
