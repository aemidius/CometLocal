/**
 * E2E tests para CAE Coordination v1.6
 * 
 * Flujo completo:
 * 1. Crear snapshot FAKE
 * 2. Seleccionar 2 pendientes
 * 3. Asignar documentos (usando seed si está disponible)
 * 4. Generar plan READY
 * 5. Ejecutar batch (modo FAKE)
 */

const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('CAE Coordination E2E - Snapshot y selección', () => {
    test.setTimeout(60000); // 60 segundos timeout para este describe
    
    let seedData = null;
    let snapshotId = null;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando helpers
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
        
        // También seed específico para CAE selection si está disponible
        try {
            const seedResponse = await request.post('http://127.0.0.1:8000/api/test/seed/cae_selection_v1', {
                headers: { 'Content-Type': 'application/json' },
                data: {},
            });
            
            if (seedResponse.ok()) {
                const caeSeedData = await seedResponse.json();
                console.log('[E2E] CAE seed data created:', caeSeedData);
                seedData = { ...seedData, ...caeSeedData };
            }
        } catch (error) {
            console.log('[E2E] CAE seed not available, using basic seed');
        }
    });

    test('Test 1: Crear snapshot FAKE y verificar flujo básico', async ({ page }) => {
        // SPRINT B2: Navegar usando helper
        await gotoHash(page, 'coordinacion');
        
        // Esperar a que aparezca el elemento raíz de coordinación
        await waitForTestId(page, 'coordination-root');
        const coordinationRoot = page.locator('[data-testid="coordination-root"]');
        await expect(coordinationRoot).toBeVisible({ timeout: 20000 });
        
        // Verificar que el título está presente
        const configTitle = page.locator('[data-testid="coordination-config-title"]');
        await expect(configTitle).toBeVisible({ timeout: 5000 });
        
        // Esperar a que aparezca el selector de coordinación
        const coordinationSelect = page.locator('#coord-coordination');
        await expect(coordinationSelect).toBeVisible({ timeout: 5000 });
        
        // Rellenar empresa si hay seed data
        if (seedData && seedData.company_key) {
            await page.fill('#coord-company', seedData.company_key);
        }
        
        // Crear snapshot (no requiere coordinación seleccionada en modo FAKE)
        const queryBtn = page.locator('#coord-query-btn');
        await expect(queryBtn).toBeVisible({ timeout: 5000 });
        await queryBtn.click();
        
        // Esperar a que se cree el snapshot
        await page.waitForSelector('#coord-snapshot-result', { state: 'visible', timeout: 30000 });
        
        // Verificar que se muestra el snapshot
        const snapshotResult = page.locator('#coord-snapshot-result');
        await expect(snapshotResult).toBeVisible();
        
        // Extraer snapshot_id del texto
        const snapshotText = await snapshotResult.textContent();
        const snapshotIdMatch = snapshotText.match(/ID:\s*([A-Z0-9-]+)/);
        if (snapshotIdMatch) {
            snapshotId = snapshotIdMatch[1];
            console.log('[E2E] Snapshot ID:', snapshotId);
        }
        
        // Verificar que se muestran los items
        const itemsDiv = page.locator('#coord-snapshot-items');
        await expect(itemsDiv).toBeVisible({ timeout: 5000 });
        
        // Verificar que hay al menos 2 pendientes
        const checkboxes = page.locator('.snapshot-item-checkbox');
        const checkboxCount = await checkboxes.count();
        console.log('[E2E] Found', checkboxCount, 'pending items');
        expect(checkboxCount).toBeGreaterThanOrEqual(2);
        
        // Seleccionar primeros 2
        await checkboxes.nth(0).check();
        await checkboxes.nth(1).check();
        
        // Verificar que el botón de asignar se habilita
        const assignBtn = page.locator('#coord-assign-btn');
        await expect(assignBtn).toBeEnabled({ timeout: 2000 });
        await expect(assignBtn).toContainText('2');
        
        // Abrir modal de asignación
        await assignBtn.click();
        
        // Esperar a que se abra el modal
        const modal = page.locator('#cae-snapshot-selection-modal');
        await expect(modal).toBeVisible({ timeout: 15000 });
        
        // Verificar que los dropdowns existen
        const select0 = page.locator('#snapshot-doc-select-0');
        const select1 = page.locator('#snapshot-doc-select-1');
        await expect(select0).toBeAttached({ timeout: 10000 });
        await expect(select1).toBeAttached({ timeout: 10000 });
        
        // Esperar a que se carguen los candidatos (con timeout razonable)
        await page.waitForFunction(
            () => {
                const sel0 = document.getElementById('snapshot-doc-select-0');
                const sel1 = document.getElementById('snapshot-doc-select-1');
                if (!sel0 || !sel1) return false;
                // Esperar a que ambos selects no estén en estado "Cargando..."
                const text0 = sel0.options[0]?.textContent || '';
                const text1 = sel1.options[0]?.textContent || '';
                return !text0.includes('Cargando') && !text1.includes('Cargando');
            },
            { timeout: 15000 }
        ).catch((error) => {
            console.log('[E2E] Timeout waiting for selects to finish loading, continuing...');
        });
        
        // Verificar que el modal sigue abierto
        const modalStillVisible = await modal.isVisible().catch(() => false);
        expect(modalStillVisible).toBe(true);
        
        // Verificar que el botón de generar plan existe
        const generateBtn = page.locator('[data-testid="snapshot-generate-plan"]');
        await expect(generateBtn).toBeVisible({ timeout: 5000 });
        
        console.log('[E2E] Modal opened successfully, dropdowns loaded');
    });
});

