/**
 * E2E: Smoke test para vista "Configuración"
 * - Verifica que la vista carga correctamente
 * - Verifica que los elementos principales están presentes
 * - Verifica estabilidad de la vista
 */
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Configuración - Smoke Test', () => {
  let seedData;
  const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'config');
  
  test.beforeAll(async ({ request }) => {
    // Crear directorio de evidencia
    if (!fs.existsSync(evidenceDir)) {
      fs.mkdirSync(evidenceDir, { recursive: true });
    }
    
    // Reset y seed básico
    await seedReset({ request });
    seedData = await seedBasicRepository({ request });
    console.log('[E2E] Seed data:', seedData);
  });
  
  test.beforeEach(async ({ page }) => {
    // Capturar logs del navegador
    page.on('console', msg => console.log('[BROWSER]', msg.type(), msg.text()));
    page.on('pageerror', err => console.log('[PAGEERROR]', err.message));
  });
  
  test('should load configuracion view and show settings form', async ({ page }) => {
    test.setTimeout(20000);
    
    // 1. Navegar a Configuración
    await gotoHash(page, 'configuracion');
    
    // 2. SPRINT C2.9.3: Esperar view-configuracion-ready con state: 'attached'
    await page.waitForSelector('[data-testid="view-configuracion-ready"]', { timeout: 20000, state: 'attached' });
    console.log('[E2E] View configuracion marked as ready (via alias)');
    
    // 3. SPRINT C2.9.3: Esperar configuracion-view visible/attached
    await page.waitForSelector('[data-testid="configuracion-view"]', { timeout: 20000, state: 'attached' });
    const configView = page.locator('[data-testid="configuracion-view"]');
    await expect(configView).toBeVisible({ timeout: 5000 });
    console.log('[E2E] configuracion-view container found');
    
    // 4. Verificar que NO existe error (SOLO data-testid)
    const errorElement = page.locator('[data-testid="configuracion-error"]');
    await expect(errorElement).toHaveCount(0);
    console.log('[E2E] No error element found (as expected)');
    
    // 5. Verificar que existe el botón guardar (SOLO data-testid)
    const saveButton = page.locator('[data-testid="configuracion-save"]');
    await expect(saveButton).toBeVisible({ timeout: 5000 });
    console.log('[E2E] configuracion-save button found');
    
    // Capturar screenshot: vista lista
    await page.screenshot({ path: path.join(evidenceDir, '01_config_ready.png'), fullPage: true });
    console.log('[E2E] Screenshot saved: 01_config_ready.png');
    
    // El test es mínimo y determinista: solo verifica que la vista carga y muestra los elementos
    // No modificamos la configuración para evitar efectos colaterales
    console.log('[E2E] Test completed successfully - view is stable and ready (100% data-testid, sin fallbacks)');
  });
});
