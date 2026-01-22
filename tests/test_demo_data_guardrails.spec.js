/**
 * SPRINT C2.36.1: Test E2E smoke para verificar que no hay datos demo en UI.
 * 
 * Verifica:
 * 1) El catálogo no contiene tipos demo (TEST_*, E2E_TYPE_*, etc.)
 * 2) La búsqueda de documentos no muestra documentos demo
 * 3) Los tipos demo no aparecen en la lista de tipos
 */

import { test, expect } from '@playwright/test';

test.describe('Demo Data Guardrails (C2.36.1)', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://127.0.0.1:8000/repository');
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
    });

    test('should not show demo types in catalog', async ({ page }) => {
        // Navegar al catálogo si no estamos ya ahí
        const catalogLink = page.locator('a[href*="#catalog"], button:has-text("Catálogo")');
        if (await catalogLink.count() > 0) {
            await catalogLink.click();
            await page.waitForTimeout(500);
        }

        // Buscar tipos demo en la lista
        const demoPatterns = ['TEST_TYPE', 'E2E_TYPE_', 'T999_', 'DEMO_'];
        
        for (const pattern of demoPatterns) {
            // Buscar en el contenido de la página
            const pageContent = await page.content();
            const regex = new RegExp(pattern, 'i');
            
            // Verificar que no aparece en el catálogo (puede aparecer en otros lugares como logs)
            // Buscar específicamente en elementos de tipo
            const typeElements = page.locator('[data-testid*="type"], .type-item, [class*="type"]');
            const count = await typeElements.count();
            
            if (count > 0) {
                for (let i = 0; i < count; i++) {
                    const text = await typeElements.nth(i).textContent();
                    if (text && regex.test(text)) {
                        // Verificar que no es un tipo demo visible
                        const typeId = await typeElements.nth(i).getAttribute('data-type-id');
                        if (typeId && regex.test(typeId)) {
                            throw new Error(`Tipo demo encontrado en catálogo: ${typeId}`);
                        }
                    }
                }
            }
        }
    });

    test('should not show demo documents in search', async ({ page }) => {
        // Buscar documentos
        const searchInput = page.locator('input[type="search"], input[placeholder*="buscar"], input[placeholder*="Buscar"]');
        if (await searchInput.count() > 0) {
            await searchInput.fill('test');
            await page.waitForTimeout(500);
            
            // Verificar que no aparecen documentos demo
            const demoDocPatterns = ['TEST_DOC_', 'E2E_DOC_', 'real_doc_001'];
            const documentElements = page.locator('[data-testid*="doc"], .document-item, [class*="document"]');
            const count = await documentElements.count();
            
            if (count > 0) {
                for (let i = 0; i < count; i++) {
                    const text = await documentElements.nth(i).textContent();
                    for (const pattern of demoDocPatterns) {
                        if (text && text.includes(pattern)) {
                            throw new Error(`Documento demo encontrado en búsqueda: ${text}`);
                        }
                    }
                }
            }
        }
    });

    test('should have showDemoDocs disabled by default', async ({ page }) => {
        // Verificar que el checkbox "Mostrar demo" está desactivado por defecto
        const demoCheckbox = page.locator('#search-show-demo, [data-testid="show-demo"], input[type="checkbox"][id*="demo"]');
        
        if (await demoCheckbox.count() > 0) {
            const isChecked = await demoCheckbox.isChecked();
            expect(isChecked).toBe(false);
        }
    });
});
