/**
 * Test para tomar screenshot de Config People con filtrado por empresa propia.
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test('take screenshot of Config People filtered by own company', async ({ page }) => {
    // Navegar a Config People
    await page.goto('http://127.0.0.1:8000/config/people');
    
    // Esperar a que la página cargue
    await page.waitForSelector('table', { timeout: 10000 });
    await page.waitForTimeout(1000);
    
    // Tomar screenshot
    const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'c2_32a');
    if (!fs.existsSync(evidenceDir)) {
        fs.mkdirSync(evidenceDir, { recursive: true });
    }
    
    await page.screenshot({ 
        path: path.join(evidenceDir, 'config_people_filtered.png'), 
        fullPage: true 
    });
    
    // Verificar que existe el selector de filtro
    const filterSelect = page.locator('#filter-own-company');
    await expect(filterSelect).toBeVisible();
    
    // Verificar que existe la columna "Empresa propia"
    const table = page.locator('table');
    const tableText = await table.textContent();
    expect(tableText).toContain('Empresa propia');
    
    console.log(`[SCREENSHOT] Guardado en: ${path.join(evidenceDir, 'config_people_filtered.png')}`);
});
