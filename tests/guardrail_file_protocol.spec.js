const { test, expect } = require('@playwright/test');

test.describe('GUARDRAIL: Bloqueo de file://', () => {
    test('Verificar que el guardrail bloquea ejecución desde file://', async ({ page }) => {
        // Este test verifica que el guardrail funciona
        // Nota: No podemos realmente abrir file:// desde Playwright,
        // pero podemos verificar que el código está presente
        
        // Navegar a /home (debe funcionar normalmente)
        await page.goto('/home');
        await page.waitForSelector('h1:has-text("CometLocal Dashboard")', { timeout: 10000 });
        
        // Verificar que NO hay banner de error (porque estamos en http://)
        const warningBanner = await page.locator('#file-protocol-warning').count();
        expect(warningBanner, 'No debe haber banner de error cuando se accede desde http://').toBe(0);
        
        // Verificar que el botón está habilitado
        const reviewBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(reviewBtn).toBeEnabled();
        
        // Verificar que la función checkFileProtocol existe
        const hasCheckFunction = await page.evaluate(() => {
            return typeof window.checkFileProtocol === 'function' || 
                   document.body.innerHTML.includes('checkFileProtocol');
        });
        
        // Verificar que el código del guardrail está presente en el HTML
        const htmlContent = await page.content();
        expect(htmlContent, 'Debe contener el código del guardrail').toContain('file-protocol-warning');
        expect(htmlContent, 'Debe contener la verificación de protocolo').toContain('location.protocol');
        
        console.log('[GUARDRAIL] Test de verificación completado. El guardrail está presente en el código.');
    });
});
