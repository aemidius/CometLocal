const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('CAE Plan E2E - Preparar envío CAE (filtrado)', () => {
    // SPRINT C2.9.14: Timeout aumentado a 90s para evitar timeout durante gotoHash(calendario)
    test.describe.configure({ timeout: 90000 });
    
    test.beforeAll(async ({ request }) => {
        // Verificar que el servidor está corriendo con el código correcto
        // Esperar a que el servidor esté listo (puede tardar unos segundos)
        const maxRetries = 10;
        const retryDelay = 1000; // 1 segundo
        
        for (let i = 0; i < maxRetries; i++) {
            try {
                const response = await request.get('http://127.0.0.1:8000/api/health');
                if (response.ok()) {
                    const health = await response.json();
                    // Verificar que el patch version es correcto
                    expect(health.status).toBe('ok');
                    expect(health.cae_plan_patch).toBe('v1.1.1');
                    console.log(`[E2E] Server health OK - patch: ${health.cae_plan_patch}, build_id: ${health.build_id}`);
                    return; // Servidor correcto, continuar
                }
            } catch (error) {
                // Servidor aún no está listo, esperar y reintentar
                if (i < maxRetries - 1) {
                    console.log(`[E2E] Waiting for server... (attempt ${i + 1}/${maxRetries})`);
                    await new Promise(resolve => setTimeout(resolve, retryDelay));
                    continue;
                }
                throw new Error(`Server health check failed after ${maxRetries} attempts: ${error.message}`);
            }
        }
        throw new Error(`Server health check failed: server not responding or wrong version`);
    });

    let seedData;
    let calendarioNavigated = false;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        const { seedReset, seedBasicRepository } = require('./helpers/e2eSeed');
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // SPRINT C2.9.15: Navegar a calendario solo 1 vez (reutilizar estado si ya navegamos)
        if (!calendarioNavigated) {
            const { gotoHash } = require('./helpers/e2eSeed');
            await gotoHash(page, 'calendario');
            
            // SPRINT C2.9.19: Esperar API ready (gotoHash ya espera app-ready + API ready)
            await page.waitForFunction(() => window.__REPO_API_READY__ === true, { timeout: 15000 });
            
            await page.evaluate(async () => {
                await window.ensureCalendarioLoaded();
            });
            
            // Esperar señal invariante del calendario
            await page.waitForSelector('[data-testid="view-calendario-ready"]', { state: 'attached', timeout: 60000 });
            
            calendarioNavigated = true;
            console.log('[E2E] Calendario navigated once');
        } else {
            // Verificar que ya estamos en calendario (fallback si no)
            try {
                await page.waitForSelector('[data-testid="view-calendario-ready"]', { state: 'attached', timeout: 5000 });
                console.log('[E2E] Already in calendario, reusing state');
            } catch (e) {
                // Fallback: si no está en calendario, navegar
                console.log('[E2E] Not in calendario, navigating...');
                const { gotoHash } = require('./helpers/e2eSeed');
                await gotoHash(page, 'calendario');
                
                // SPRINT C2.9.19: Esperar API ready (gotoHash ya espera app-ready + API ready)
                await page.waitForFunction(() => window.__REPO_API_READY__ === true, { timeout: 15000 });
                
                await page.evaluate(async () => {
                    await window.ensureCalendarioLoaded();
                });
                
                // Esperar señal invariante del calendario
                await page.waitForSelector('[data-testid="view-calendario-ready"]', { state: 'attached', timeout: 60000 });
            }
        }
    });

    test('Test 1: Abre modal de CAE plan desde tab Pendientes', async ({ page }) => {
        // Ya estamos en calendario por beforeEach
        
        // Wait for pending documents container (SOLO data-testid)
        const container = page.locator('[data-testid="calendar-pending-container"]');
        await expect(container).toBeAttached({ timeout: 10000 });
        
        // Click on "Pendientes" tab (SOLO data-testid)
        const missingTab = page.locator('[data-testid="calendar-tab-pending"]');
        await expect(missingTab).toBeVisible({ timeout: 10000 });
        await missingTab.click();
        await page.waitForTimeout(500);
        
        // Look for CAE plan button
        const caePlanButton = page.locator('[data-testid="cae-plan-button"]');
        await expect(caePlanButton).toBeVisible({ timeout: 5000 });
        
        // Click button to open modal
        await caePlanButton.click();
        await page.waitForTimeout(500);
        
        // Check that modal is visible (SOLO data-testid)
        const modal = page.locator('[data-testid="cae-plan-modal"]');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Check that modal has required fields
        const platformSelect = page.locator('[data-testid="cae-plan-platform"]');
        const typeModeSelect = page.locator('[data-testid="cae-plan-type-mode"]');
        const subjectModeSelect = page.locator('[data-testid="cae-plan-subject-mode"]');
        const periodModeSelect = page.locator('[data-testid="cae-plan-period-mode"]');
        const modeSelect = page.locator('[data-testid="cae-plan-mode"]');
        
        await expect(platformSelect).toBeVisible();
        await expect(typeModeSelect).toBeVisible();
        await expect(subjectModeSelect).toBeVisible();
        await expect(periodModeSelect).toBeVisible();
        await expect(modeSelect).toBeVisible();
        
        // Take screenshot
        await page.screenshot({ 
            path: path.join(__dirname, '../docs/evidence/cae_plans/modal_opened.png'),
            fullPage: true 
        });
    });

    test('Test 2: Genera plan con scope mínimo', async ({ page }) => {
        // SPRINT C2.9.9: Usar gotoHash para navegación determinista
        const { gotoHash } = require('./helpers/e2eSeed');
        await gotoHash(page, 'calendario');
        
        // SPRINT C2.9.19: Esperar API ready (gotoHash ya espera app-ready + API ready)
        await page.waitForFunction(() => window.__REPO_API_READY__ === true, { timeout: 15000 });
        
        await page.evaluate(async () => {
            await window.ensureCalendarioLoaded();
        });
        
        // Esperar señal invariante del calendario
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { state: 'attached', timeout: 60000 });
        
        // SPRINT C2.9.10: Click on "Pendientes" tab y esperar contenido renderizado (sin sleep)
        const missingTab = page.locator('[data-testid="calendar-tab-pending"]');
        await expect(missingTab).toBeVisible({ timeout: 10000 });
        await missingTab.click();
        
        // Esperar a que el contenido de la pestaña "missing" esté renderizado
        // El botón cae-plan-button siempre se renderiza en la sección 'missing'
        await page.waitForSelector('[data-testid="cae-plan-button"]', { state: 'attached', timeout: 15000 });
        
        // Verificar que el tab está activo (tiene border-bottom)
        const tabStyle = await missingTab.evaluate(el => window.getComputedStyle(el).borderBottom);
        expect(tabStyle).toContain('solid');
        
        // Open modal
        const caePlanButton = page.locator('[data-testid="cae-plan-button"]');
        await expect(caePlanButton).toBeVisible({ timeout: 5000 });
        await caePlanButton.click();
        await page.waitForTimeout(500);
        
        // Wait for modal (SOLO data-testid)
        const modal = page.locator('[data-testid="cae-plan-modal"]');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Select platform (should default to egestiona)
        const platformSelect = page.locator('[data-testid="cae-plan-platform"]');
        await expect(platformSelect).toBeVisible();
        
        // Select type mode: "Todos los tipos visibles"
        const typeModeSelect = page.locator('[data-testid="cae-plan-type-mode"]');
        await typeModeSelect.selectOption('all');
        await page.waitForTimeout(200);
        
        // Select subject mode: "Todos los sujetos visibles"
        const subjectModeSelect = page.locator('[data-testid="cae-plan-subject-mode"]');
        await subjectModeSelect.selectOption('all');
        await page.waitForTimeout(200);
        
        // Select period mode: "Todos los períodos visibles"
        const periodModeSelect = page.locator('[data-testid="cae-plan-period-mode"]');
        await periodModeSelect.selectOption('all');
        await page.waitForTimeout(200);
        
        // Mode should default to READ_ONLY
        const modeSelect = page.locator('[data-testid="cae-plan-mode"]');
        await expect(modeSelect).toHaveValue('READ_ONLY');
        
        // Click generate button
        const generateButton = page.locator('[data-testid="cae-plan-generate"]');
        await expect(generateButton).toBeVisible();
        await generateButton.click();
        
        // Wait for result (SOLO data-testid)
        const resultDiv = page.locator('[data-testid="cae-plan-result"]');
        await expect(resultDiv).toBeVisible({ timeout: 10000 });
        
        // SPRINT C2.9.11: Esperar por marker invariante de estado (no por badge)
        const stateMarker = page.locator('[data-testid="cae-plan-generation-state"]');
        await page.waitForSelector('[data-testid="cae-plan-generation-state"]', { state: 'attached', timeout: 30000 });
        
        // Esperar a que el estado sea "done" (no "running")
        await expect(stateMarker).toHaveAttribute('data-state', 'done', { timeout: 30000 });
        
        // Verificar outcome
        const outcome = await stateMarker.getAttribute('data-outcome');
        
        if (outcome === 'error') {
            const errorMsg = await stateMarker.getAttribute('data-error') || 'Unknown error';
            throw new Error(`CAE Plan generation failed: ${errorMsg}`);
        }
        
        expect(outcome).toBe('success');
        
        // Si success, validar el badge
        const decisionElement = page.locator('[data-testid="cae-plan-decision"]');
        await expect(decisionElement).toBeAttached({ timeout: 5000 });
        
        // Obtener decisión desde atributo data-decision
        const decision = await decisionElement.getAttribute('data-decision');
        expect(decision).toBeTruthy();
        expect(['READY', 'NEEDS_CONFIRMATION', 'BLOCKED']).toContain(decision);
        
        console.log(`[E2E] CAE Plan decision: ${decision}`);
        
        // En caso de repositorio vacío, debe mostrar BLOCKED (no error 500)
        // La decisión ya está validada arriba (debe ser READY, NEEDS_CONFIRMATION, o BLOCKED)
        
        // SPRINT C2.9.25: Obtener resultText antes de usarlo
        let resultText = '';
        try {
            resultText = await resultDiv.textContent() || '';
        } catch (e) {
            console.warn('[E2E] Could not get result text:', e);
            resultText = 'No se pudo obtener el texto del resultado';
        }
        
        // Take screenshot
        await page.screenshot({ 
            path: path.join(__dirname, '../docs/evidence/cae_plans/plan_generated.png'),
            fullPage: true 
        });
        
        // Save result text to file
        const evidenceDir = path.join(__dirname, '../docs/evidence/cae_plans');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
        fs.writeFileSync(
            path.join(evidenceDir, 'plan_result.txt'),
            `Plan generado:\n${resultText}\n\nTimestamp: ${new Date().toISOString()}`
        );
    });

    test('Test 3: Verifica que decision y reasons son visibles', async ({ page }) => {
        // Navigate to calendario
        const { gotoHash } = require('./helpers/e2eSeed');
        await gotoHash(page, 'calendario');
        
        // SPRINT C2.9.19: Esperar API ready (gotoHash ya espera app-ready + API ready)
        await page.waitForFunction(() => window.__REPO_API_READY__ === true, { timeout: 15000 });
        
        await page.evaluate(async () => {
            await window.ensureCalendarioLoaded();
        });
        
        // Esperar señal invariante del calendario
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { state: 'attached', timeout: 60000 });
        
        // Click on "Pendientes" tab (SOLO data-testid)
        const missingTab = page.locator('[data-testid="calendar-tab-pending"]');
        await expect(missingTab).toBeVisible({ timeout: 10000 });
        await missingTab.click();
        await page.waitForTimeout(500);
        
        // Open modal
        const caePlanButton = page.locator('[data-testid="cae-plan-button"]');
        await expect(caePlanButton).toBeVisible({ timeout: 5000 });
        await caePlanButton.click();
        await page.waitForTimeout(500);
        
        // Wait for modal (SOLO data-testid)
        const modal = page.locator('[data-testid="cae-plan-modal"]');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Generate plan with minimal scope
        const generateButton = page.locator('[data-testid="cae-plan-generate"]');
        await generateButton.click();
        
        // Wait for result (SOLO data-testid)
        const resultDiv = page.locator('[data-testid="cae-plan-result"]');
        await expect(resultDiv).toBeVisible({ timeout: 10000 });
        
        // SPRINT C2.9.25: Esperar por marker invariante de estado (igual que Test 2)
        const stateMarker = page.locator('[data-testid="cae-plan-generation-state"]');
        await page.waitForSelector('[data-testid="cae-plan-generation-state"]', { state: 'attached', timeout: 30000 });
        
        // Esperar a que el estado sea "done" (no "running")
        await expect(stateMarker).toHaveAttribute('data-state', 'done', { timeout: 30000 });
        
        // Verificar outcome
        const outcome = await stateMarker.getAttribute('data-outcome');
        if (outcome === 'error') {
            const errorMsg = await stateMarker.getAttribute('data-error') || 'Unknown error';
            throw new Error(`CAE Plan generation failed: ${errorMsg}`);
        }
        expect(outcome).toBe('success');
        
        // SPRINT C2.7: Usar testid determinista en lugar de selector frágil .badge
        const decisionElement = page.locator('[data-testid="cae-plan-decision"]');
        await expect(decisionElement).toBeAttached({ timeout: 5000 });
        await expect(decisionElement).toBeVisible({ timeout: 5000 });
        
        // Obtener decisión desde atributo data-decision
        const decision = await decisionElement.getAttribute('data-decision');
        expect(decision).toBeTruthy();
        expect(['READY', 'NEEDS_CONFIRMATION', 'BLOCKED']).toContain(decision);
        
        // En caso de repositorio vacío, debe ser BLOCKED (no error)
        const resultText = await resultDiv.textContent();
        expect(resultText).not.toContain('Error 500');
        expect(resultText).not.toContain('Internal Server Error');
        
        // Check that summary is visible
        expect(resultText).toContain('Resumen');
        expect(resultText.includes('Items pendientes') || resultText.includes('Total items')).toBeTruthy();
        
        // Take screenshot
        await page.screenshot({ 
            path: path.join(__dirname, '../docs/evidence/cae_plans/decision_and_reasons_visible.png'),
            fullPage: true 
        });
    });

    test('Test 4: Cierra modal correctamente', async ({ page }) => {
        // Navigate to calendario
        const { gotoHash } = require('./helpers/e2eSeed');
        await gotoHash(page, 'calendario');
        
        // SPRINT C2.9.19: Esperar API ready (gotoHash ya espera app-ready + API ready)
        await page.waitForFunction(() => window.__REPO_API_READY__ === true, { timeout: 15000 });
        
        await page.evaluate(async () => {
            await window.ensureCalendarioLoaded();
        });
        
        // Esperar señal invariante del calendario
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { state: 'attached', timeout: 60000 });
        
        // Click on "Pendientes" tab (SOLO data-testid)
        const missingTab = page.locator('[data-testid="calendar-tab-pending"]');
        await expect(missingTab).toBeVisible({ timeout: 10000 });
        await missingTab.click();
        await page.waitForTimeout(500);
        
        // Open modal
        const caePlanButton = page.locator('[data-testid="cae-plan-button"]');
        await expect(caePlanButton).toBeVisible({ timeout: 5000 });
        await caePlanButton.click();
        await page.waitForTimeout(500);
        
        // Wait for modal (SOLO data-testid)
        const modal = page.locator('[data-testid="cae-plan-modal"]');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Click cancel button
        const cancelButton = page.locator('[data-testid="cae-plan-cancel"]');
        await expect(cancelButton).toBeVisible();
        await cancelButton.click();
        await page.waitForTimeout(500);
        
        // Check that modal is closed
        await expect(modal).not.toBeVisible();
    });
});

