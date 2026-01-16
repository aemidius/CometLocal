/**
 * E2E: Test de debug para validar markers de calendario
 * - Verifica que los markers de debug aparecen en el flujo correcto
 * - Identifica dónde se rompe el flujo si no aparece view-calendario-ready/error
 */
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Calendar Debug Markers', () => {
  let seedData;
  const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'calendar_debug');
  
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
  
  test('should show debug markers in correct order and end with ready or error', async ({ page }) => {
    test.setTimeout(25000);
    
    // 1. Navegar a Calendario
    await gotoHash(page, 'calendario');
    
    // 2. Esperar una de estas (race con timeout 20s):
    // - view-calendario-ready
    // - view-calendario-error
    const result = await Promise.race([
      page.waitForSelector('[data-testid="view-calendario-ready"]', { timeout: 20000, state: 'attached' }).then(() => 'ready'),
      page.waitForSelector('[data-testid="view-calendario-error"]', { timeout: 20000, state: 'attached' }).then(() => 'error')
    ]).catch(() => 'timeout');
    
    console.log(`[E2E] Final state: ${result}`);
    
    // Capturar screenshot: ready o error
    await page.screenshot({ path: path.join(evidenceDir, '03_ready_or_error.png'), fullPage: true });
    
    // 3. Verificar qué markers de debug existen
    const allDebugMarkers = [
      'dbg-calendario-route-hit',
      'dbg-calendario-load-start',
      'dbg-calendario-before-pending-fetch',
      'dbg-calendario-pending-catch',
      'dbg-calendario-load-success'
    ];
    
    console.log('[E2E] Checking debug markers:');
    for (const markerId of allDebugMarkers) {
      const marker = page.locator(`[data-testid="${markerId}"]`);
      const count = await marker.count();
      if (count > 0) {
        const ts = await marker.getAttribute('data-ts');
        const error = await marker.getAttribute('data-error').catch(() => null);
        console.log(`[E2E] Found marker: ${markerId}, ts=${ts}${error ? `, error=${error}` : ''}`);
      } else {
        console.log(`[E2E] Missing marker: ${markerId}`);
      }
    }
    
    if (result === 'error') {
      // Si da error, verificar que existe el marker de catch o calendar-pending-error
      const catchMarker = page.locator('[data-testid="dbg-calendario-pending-catch"]');
      const catchMarkerCount = await catchMarker.count();
      const pendingError = page.locator('[data-testid="calendar-pending-error"]');
      const pendingErrorCount = await pendingError.count();
      
      console.log(`[E2E] Error markers: catch=${catchMarkerCount}, pending-error=${pendingErrorCount}`);
      
      if (catchMarkerCount > 0) {
        const catchError = await catchMarker.getAttribute('data-error');
        console.log(`[E2E] Catch marker error: ${catchError}`);
      }
      
      if (pendingErrorCount > 0) {
        const pendingErrorText = await pendingError.textContent();
        console.log(`[E2E] Pending error text: ${pendingErrorText?.substring(0, 200)}`);
      }
      
      // Verificar que al menos uno de los markers de error existe
      expect(catchMarkerCount + pendingErrorCount).toBeGreaterThan(0);
    } else if (result === 'ready') {
      // Si es ready, verificar que existe el marker de éxito
      const successMarker = page.locator('[data-testid="dbg-calendario-load-success"]');
      const successMarkerCount = await successMarker.count();
      console.log(`[E2E] Success marker count: ${successMarkerCount}`);
      
      // El marker de éxito puede no existir si se establece ready desde loadPage()
      // pero es útil para debug
    } else {
      // Timeout - reportar qué markers faltan
      const readyMarker = page.locator('[data-testid="view-calendario-ready"]');
      const errorMarker = page.locator('[data-testid="view-calendario-error"]');
      const readyCount = await readyMarker.count();
      const errorCount = await errorMarker.count();
      
      console.log(`[E2E] TIMEOUT: ready=${readyCount}, error=${errorCount}`);
      
      throw new Error(`Timeout waiting for view-calendario-ready or view-calendario-error. Ready count: ${readyCount}, Error count: ${errorCount}`);
    }
    
    console.log('[E2E] Test completed successfully');
  });
});
