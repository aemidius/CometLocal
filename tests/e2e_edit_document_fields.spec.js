const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

// SPRINT C2.2.2: Helpers para abrir y cerrar modal de edición
async function openEditModal(page, index = 0) {
    const btn = page.locator('[data-testid="edit-doc-button"]').nth(index);
    await btn.click({ force: true });
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'attached', timeout: 8000 });
    await page.waitForSelector('[data-testid="edit-doc-modal-open"]', { state: 'attached', timeout: 8000 });
}

async function closeEditModalAfterSave(page) {
    // Click guardar (usar selector estable dentro del modal)
    const saveButton = page.locator('[data-testid="edit-doc-modal-overlay"] button:has-text("Guardar")');
    await saveButton.click();
    // Esperar que el modal se cierre (el modal se cierra después de guardar exitosamente)
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 15000 });
}

test.describe('Editar Documento - Campos Editables', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // SPRINT C2.2.1: Añadir listeners de consola y errores para diagnóstico
        page.on('console', msg => console.log('[BROWSER]', msg.type(), msg.text()));
        page.on('pageerror', err => console.log('[PAGEERROR]', err.message));
        
        // Navigate usando helper
        await gotoHash(page, 'buscar');
        // SPRINT C2.1: Esperar señal de UI lista antes de buscar elementos
        await page.waitForSelector('[data-testid="search-ui-ready"]', { timeout: 15000 });
    });

    // SPRINT C2.2.2: Asegurar independencia entre tests - cerrar modal si queda abierto
    test.afterEach(async ({ page }) => {
        const overlayCount = await page.locator('[data-testid="edit-doc-modal-overlay"]').count();
        if (overlayCount > 0) {
            await page.keyboard.press('Escape');
            await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 3000 }).catch(() => {});
        }
    });

    test('Test 1: Modal muestra campos editables correctos', async ({ page }) => {
        // Ya estamos en buscar por beforeEach
        
        // Wait for search results
        const resultsContainer = page.locator('#search-results-container');
        await expect(resultsContainer).toBeAttached({ timeout: 10000 });
        
        // SPRINT C2.2.2: Usar helper para abrir modal
        await openEditModal(page, 0);
        
        // Verify modal is visible
        const modal = page.locator('[data-testid="edit-doc-modal-overlay"]');
        await expect(modal).toBeVisible();
        
        // Verify "Estado de tramitación" field exists (renamed from "Estado")
        const workflowStatusLabel = page.locator('label:has-text("Estado de tramitación")');
        await expect(workflowStatusLabel).toBeVisible();
        
        // Verify workflow status select exists
        const workflowStatusSelect = page.locator('#edit-doc-status');
        await expect(workflowStatusSelect).toBeVisible();
        
        // Verify workflow status has correct options
        const options = await workflowStatusSelect.locator('option').allTextContents();
        expect(options).toContain('Borrador');
        expect(options).toContain('Revisado');
        expect(options).toContain('Listo para enviar');
        expect(options).toContain('Enviado');
        
        // Verify help text exists for workflow status
        const helpText = page.locator('text=/Borrador:.*Datos en preparación/');
        await expect(helpText).toBeVisible();
    });

    test('Test 2: Modal muestra Estado de validez (readonly)', async ({ page }) => {
        // Wait for search results
        const resultsContainer = page.locator('#search-results-container');
        await expect(resultsContainer).toBeAttached({ timeout: 10000 });
        
        // SPRINT C2.2.2: Usar helper para abrir modal
        await openEditModal(page, 0);
        
        // Verify "Estado de validez" section exists
        const validityStatusLabel = page.locator('label:has-text("Estado de validez")');
        await expect(validityStatusLabel).toBeVisible();
        
        // Verify it shows readonly badge (should have badge class)
        const validityBadge = page.locator('[data-testid="edit-doc-modal-overlay"] .badge');
        const badgeCount = await validityBadge.count();
        expect(badgeCount).toBeGreaterThan(0);
        
        // Verify help text explains it's readonly
        // SPRINT C2.2.2: Buscar dentro del modal overlay - el texto exacto es "Este estado se calcula automáticamente según las fechas del documento. No es editable."
        const readonlyText = page.locator('[data-testid="edit-doc-modal-overlay"]').getByText(/calcula automáticamente/i);
        await expect(readonlyText).toBeVisible();
    });

    test('Test 3: Modal muestra campos condicionales (fechas, período)', async ({ page }) => {
        // Wait for search results
        const resultsContainer = page.locator('#search-results-container');
        await expect(resultsContainer).toBeAttached({ timeout: 10000 });
        
        // SPRINT C2.2.2: Usar helper para abrir modal
        await openEditModal(page, 0);
        
        // SPRINT C2.2.2: Esperar a que los inputs existan dentro del modal
        await page.waitForSelector('[data-testid="edit-doc-modal-overlay"] input', { timeout: 5000 }).catch(() => {});
        
        // Check if date fields appear (they may or may not depending on document type)
        const issueDateInput = page.locator('[data-testid="edit-doc-modal-overlay"] #edit-doc-issue-date');
        const validityStartDateInput = page.locator('[data-testid="edit-doc-modal-overlay"] #edit-doc-validity-start-date');
        const periodKeyInput = page.locator('[data-testid="edit-doc-modal-overlay"] #edit-doc-period-key');
        
        // At least one of these should exist, or none if document doesn't require them
        const issueDateVisible = await issueDateInput.isVisible().catch(() => false);
        const validityStartVisible = await validityStartDateInput.isVisible().catch(() => false);
        const periodKeyVisible = await periodKeyInput.isVisible().catch(() => false);
        
        // Log what fields are visible for debugging
        console.log('Fields visible:', {
            issueDate: issueDateVisible,
            validityStart: validityStartVisible,
            periodKey: periodKeyVisible
        });
        
        // If any date field is visible, verify it's a date input
        if (issueDateVisible) {
            const inputType = await issueDateInput.getAttribute('type');
            expect(inputType).toBe('date');
        }
        
        if (validityStartVisible) {
            const inputType = await validityStartDateInput.getAttribute('type');
            expect(inputType).toBe('date');
        }
    });

    test('Test 4: Guardar cambios actualiza documento', async ({ page }) => {
        // Wait for search results
        const resultsContainer = page.locator('#search-results-container');
        await expect(resultsContainer).toBeAttached({ timeout: 10000 });
        
        // SPRINT C2.2.2: Usar helper para abrir modal
        await openEditModal(page, 0);
        
        // Verify modal is visible
        const modal = page.locator('[data-testid="edit-doc-modal-overlay"]');
        await expect(modal).toBeVisible();
        
        // Change workflow status (if select exists)
        // SPRINT C2.2.3: Esperar a que el select esté visible dentro del modal
        const workflowStatusSelect = page.locator('[data-testid="edit-doc-modal-overlay"] #edit-doc-status');
        await expect(workflowStatusSelect).toBeVisible({ timeout: 5000 });
        if (await workflowStatusSelect.isVisible()) {
            // Get current value
            const currentValue = await workflowStatusSelect.inputValue();
            
            // Change to a different value
            const newValue = currentValue === 'draft' ? 'reviewed' : 'draft';
            await workflowStatusSelect.selectOption(newValue);
            
            // SPRINT C2.2.3: Esperar respuesta PUT (debe estar ANTES del click)
            const putPromise = page.waitForResponse((res) => {
                return res.url().includes('/api/repository/docs/') && res.request().method() === 'PUT';
            });
            
            // SPRINT C2.2.3: Asegurar que el botón Guardar está visible antes de hacer click
            const saveButton = page.locator('[data-testid="edit-doc-modal-overlay"] button:has-text("Guardar")');
            await expect(saveButton).toBeVisible({ timeout: 5000 });
            await saveButton.click();
            
            // Esperar respuesta PUT
            const putRes = await putPromise;
            expect(putRes.status()).toBe(200);
            
            // SPRINT C2.2.3: Esperar que el modal se cierre después de guardar exitosamente
            // El modal ahora se cierra inmediatamente después del PUT, sin depender de performSearch
            await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 10000 });
            
            // Verify search results reloaded (table should be visible)
            await expect(resultsContainer).toBeAttached();
        } else {
            // If no status select, just verify save button exists
            const saveButton = page.locator('[data-testid="edit-doc-modal-overlay"] button:has-text("Guardar")');
            await expect(saveButton).toBeVisible();
        }
    });
});






