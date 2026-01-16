const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Calendar Pending Documents - Smoke Tests', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // Navigate to repository usando helper
        await gotoHash(page, 'calendario');
    });

    test('Test 1: Buscar documentos muestra estados reales (no "Desconocido")', async ({ page }) => {
        // Navigate to buscar usando helper
        await gotoHash(page, 'buscar');
        
        // SPRINT C2.9: Esperar señal de vista ready primero
        // SPRINT C2.9.8: Esperar view-buscar-ready con state: attached (markers hidden)
        await page.waitForSelector('[data-testid="view-buscar-ready"]', { timeout: 15000, state: 'attached' });
        await page.waitForTimeout(500);
        
        // Wait for search results (SOLO data-testid)
        await page.waitForSelector('[data-testid="buscar-results"]', { timeout: 10000, state: 'attached' });
        
        // Check that status badges exist and are not "Desconocido" (usar filas con data-testid)
        const resultRows = page.locator('[data-testid="buscar-row"]');
        const count = await resultRows.count();
        
        if (count > 0) {
            // Get first row and check its validity status via data attributes or badge within row
            const firstRow = resultRows.first();
            // Buscar badge dentro de la fila (no usar .badge directamente, buscar dentro del contexto de la fila)
            const badgeInRow = firstRow.locator('.badge');
            const badgeCount = await badgeInRow.count();
            
            if (badgeCount > 0) {
                const badgeText = await badgeInRow.first().textContent();
                // Should not be "Desconocido" (should be VALID, EXPIRING_SOON, or EXPIRED)
                expect(badgeText).not.toContain('Desconocido');
                
                // Should be one of the valid states
                const validStates = ['Válido', 'Expira pronto', 'Expirado'];
                const hasValidState = validStates.some(state => badgeText.includes(state));
                expect(hasValidState || badgeText.includes('días')).toBeTruthy();
            }
        }
    });

    test('Test 2: Calendario muestra tabs y renderiza correctamente', async ({ page }) => {
        // Ya estamos en calendario por beforeEach
        
        // Esperar a que la vista esté ready primero
        // SPRINT C2.9.8: Esperar view-calendario-ready con state: attached (markers hidden)
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { timeout: 15000, state: 'attached' });
        
        // Esperar un momento adicional para que el innerHTML se renderice
        await page.waitForTimeout(500);
        
        // Check that tabs are visible (SOLO data-testid) - estos aparecen primero
        await page.waitForSelector('[data-testid="calendar-tab-pending"]', { timeout: 10000 });
        const expiredTab = page.locator('[data-testid="calendar-tab-expired"]');
        const expiringSoonTab = page.locator('[data-testid="calendar-tab-expiring"]');
        const missingTab = page.locator('[data-testid="calendar-tab-pending"]');
        
        await expect(expiredTab).toBeVisible({ timeout: 5000 });
        await expect(expiringSoonTab).toBeVisible({ timeout: 5000 });
        await expect(missingTab).toBeVisible({ timeout: 5000 });
        
        // Wait for pending documents container (SOLO data-testid) - después de que los tabs estén visibles
        await page.waitForSelector('[data-testid="calendar-pending-container"]', { timeout: 10000, state: 'attached' });
        const container = page.locator('[data-testid="calendar-pending-container"]');
        await expect(container).toBeAttached({ timeout: 5000 });
        
        // Check that container has content (even if empty message)
        const containerText = await container.textContent();
        expect(containerText).toBeTruthy();
    });

    test('Test 3: Click en tab "Pendientes" renderiza lista', async ({ page }) => {
        // Ya estamos en calendario por beforeEach
        
        // SPRINT C2.9.8: Esperar a que la vista esté ready primero con state: attached (markers hidden)
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { timeout: 15000, state: 'attached' });
        await page.waitForTimeout(500);
        
        // Wait for tabs (SOLO data-testid)
        await page.waitForSelector('[data-testid="calendar-tab-pending"]', { timeout: 10000 });
        const missingTab = page.locator('[data-testid="calendar-tab-pending"]');
        await expect(missingTab).toBeVisible({ timeout: 5000 });
        
        // Click on "Pendientes" tab
        await missingTab.click();
        await page.waitForTimeout(500);
        
        // Check that container is updated (SOLO data-testid)
        await page.waitForSelector('[data-testid="calendar-pending-container"]', { timeout: 5000, state: 'attached' });
        const container = page.locator('[data-testid="calendar-pending-container"]');
        await expect(container).toBeAttached();
        
        const containerText = await container.textContent();
        // Should show either list or "No hay períodos pendientes"
        expect(containerText).toBeTruthy();
        expect(containerText.includes('pendientes') || containerText.includes('Pendiente de subir') || containerText.includes('tabla')).toBeTruthy();
    });

    test('Test 4: Navegación a Upload desde botón de acción', async ({ page }) => {
        // Ya estamos en calendario por beforeEach
        
        // SPRINT C2.9.8: Esperar a que la vista esté ready primero con state: attached (markers hidden)
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { timeout: 15000, state: 'attached' });
        await page.waitForTimeout(500);
        
        // Wait for container (SOLO data-testid)
        await page.waitForSelector('[data-testid="calendar-pending-container"]', { timeout: 10000, state: 'attached' });
        const container = page.locator('[data-testid="calendar-pending-container"]');
        await expect(container).toBeAttached({ timeout: 5000 });
        
        // Look for action buttons (SOLO data-testid)
        const actionButtons = page.locator('[data-testid="calendar-action-resubir"], [data-testid="calendar-action-subir"]');
        const buttonCount = await actionButtons.count();
        
        if (buttonCount > 0) {
            // Click first button
            const firstButton = actionButtons.first();
            await firstButton.click();
            
            // Wait for navigation
            await page.waitForTimeout(1000);
            
            // Check that we're on upload page
            const hash = await page.evaluate(() => window.location.hash);
            expect(hash).toContain('#subir');
            
            // Check that query params are present
            expect(hash).toMatch(/type_id=/);
        } else {
            // If no buttons, just verify the page loaded correctly
            const hash = await page.evaluate(() => window.location.hash);
            expect(hash).toContain('#calendario');
        }
    });
});







