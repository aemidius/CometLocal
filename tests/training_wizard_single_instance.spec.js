/**
 * SPRINT C2.35.10: Test E2E para verificar que el training wizard tiene una única instancia DOM.
 * 
 * Verifica:
 * 1) Solo existe 1 elemento [data-testid="training-wizard-modal"]
 * 2) Solo existe 1 elemento [data-testid="training-wizard-content"]
 * 3) El texto "Cargando training" desaparece después del render
 * 4) El título del paso 1 aparece correctamente
 * 5) Al hacer Next, sigue sin "Cargando training"
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Training Wizard Single Instance (C2.35.10)', () => {
    // Helper para resetear estado de training
    function resetTrainingState() {
        const statePath = path.join(__dirname, '..', 'data', 'training', 'state.json');
        if (fs.existsSync(statePath)) {
            fs.unlinkSync(statePath);
        }
    }

    // Helper para setup común de la app
    async function setupApp(page, view = 'inicio') {
        // Resetear training state para asegurar que el training está incompleto
        resetTrainingState();
        
        // Arrancar app en la vista especificada
        const hash = view === 'catalog' ? '#catalog' : '#inicio';
        await page.goto(`http://127.0.0.1:8000/repository_v3.html${hash}`);
        
        // Esperar a que la app esté lista
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        
        // Establecer contexto mínimo
        const ownCompanySelect = page.locator('[data-testid="ctx-own-company"]');
        const platformSelect = page.locator('[data-testid="ctx-platform"]');
        const coordinatedSelect = page.locator('[data-testid="ctx-coordinated-company"]');
        
        // Seleccionar primera opción disponible
        const ownOptions = await ownCompanySelect.locator('option').count();
        if (ownOptions > 1) {
            await ownCompanySelect.selectOption({ index: 1 });
            await page.waitForTimeout(300);
        }
        
        const platformOptions = await platformSelect.locator('option').count();
        if (platformOptions > 1) {
            await platformSelect.selectOption({ index: 1 });
            await page.waitForTimeout(500);
        }
        
        const coordinatedOptions = await coordinatedSelect.locator('option').count();
        if (coordinatedOptions > 1) {
            await coordinatedSelect.selectOption({ index: 1 });
            await page.waitForTimeout(300);
        }
        
        // Esperar a que aparezca el banner o el botón "Iniciar Training"
        const banner = page.locator('[data-testid="training-banner"]');
        const startButton = page.locator('button:has-text("Iniciar Training")');
        
        try {
            await expect(banner.or(startButton).first()).toBeVisible({ timeout: 10000 });
        } catch (e) {
            // Si no aparece, verificar estado del training vía API
            const response = await page.evaluate(async () => {
                const res = await fetch('http://127.0.0.1:8000/api/training/state');
                return await res.json();
            });
            
            // Si está completado, resetearlo y recargar
            if (response.training_completed) {
                resetTrainingState();
                await page.reload();
                await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
                await expect(banner.or(startButton).first()).toBeVisible({ timeout: 10000 });
            } else {
                throw e;
            }
        }
    }

    test.beforeEach(async ({ page }) => {
        await setupApp(page, 'inicio');
    });

    test('should have only one modal and one content instance', async ({ page }) => {
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('[data-testid="training-wizard-modal"]');
        await expect(modal).toBeVisible({ timeout: 1000 });
        
        // SPRINT C2.35.10: Verificar que solo hay 1 modal
        const modalCount = await page.locator('[data-testid="training-wizard-modal"]').count();
        expect(modalCount).toBe(1);
        
        // SPRINT C2.35.10: Verificar que solo hay 1 content
        const contentCount = await page.locator('[data-testid="training-wizard-content"]').count();
        expect(contentCount).toBe(1);
        
        // SPRINT C2.35.10: Verificar que "Cargando training" desaparece
        await page.waitForFunction(
            () => {
                const content = document.querySelector('[data-testid="training-wizard-content"]');
                if (!content) return false;
                const text = content.textContent || '';
                return !text.includes('Cargando training');
            },
            { timeout: 3000 }
        );
        
        // Verificar que NO hay texto "Cargando training"
        const loadingText = page.locator('text=Cargando training');
        const loadingCount = await loadingText.count();
        expect(loadingCount).toBe(0);
        
        // SPRINT C2.35.10: Verificar que el título del paso 1 aparece
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toBeVisible({ timeout: 2000 });
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
        expect(titleText.trim()).not.toBe('undefined');
    });
    
    test('should not show loading text after Next', async ({ page }) => {
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal y se renderice el paso 1
        const modal = page.locator('[data-testid="training-wizard-modal"]');
        await expect(modal).toBeVisible({ timeout: 1000 });
        
        // Esperar a que desaparezca "Cargando training"
        await page.waitForFunction(
            () => {
                const content = document.querySelector('[data-testid="training-wizard-content"]');
                if (!content) return false;
                const text = content.textContent || '';
                return !text.includes('Cargando training');
            },
            { timeout: 3000 }
        );
        
        // Verificar que hay botón "Siguiente"
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        await expect(nextButton).toBeVisible({ timeout: 2000 });
        
        // Click en "Siguiente"
        await nextButton.click();
        
        // Esperar a que se renderice el paso 2
        await page.waitForTimeout(500);
        
        // SPRINT C2.35.10: Verificar que NO aparece "Cargando training" después de Next
        const loadingText = page.locator('text=Cargando training');
        const loadingCount = await loadingText.count();
        expect(loadingCount).toBe(0);
        
        // Verificar que el título del paso 2 aparece
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toBeVisible({ timeout: 2000 });
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
    });
});
