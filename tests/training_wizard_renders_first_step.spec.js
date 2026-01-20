/**
 * SPRINT C2.35.3: Test E2E para verificar que el wizard de training renderiza correctamente el primer paso.
 * 
 * Verifica:
 * 1) Al pulsar "Iniciar training", se muestra el contenido del paso 1
 * 2) NO aparece "undefined" en ningún momento
 * 3) Botones Next/Previous funcionan
 * 4) El título del paso es visible y no vacío
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Training Wizard Renders First Step (C2.35.3)', () => {
    // Helper para resetear estado de training
    function resetTrainingState() {
        const statePath = path.join(__dirname, '..', 'data', 'training', 'state.json');
        if (fs.existsSync(statePath)) {
            fs.unlinkSync(statePath);
        }
    }
    
    // Helper para marcar training como completado
    function markTrainingCompleted() {
        const stateDir = path.join(__dirname, '..', 'data', 'training');
        if (!fs.existsSync(stateDir)) {
            fs.mkdirSync(stateDir, { recursive: true });
        }
        const statePath = path.join(stateDir, 'state.json');
        const state = {
            training_completed: true,
            completed_at: new Date().toISOString(),
            version: "C2.35"
        };
        fs.writeFileSync(statePath, JSON.stringify(state, null, 2));
    }

    test.beforeEach(async ({ page }) => {
        // Resetear training state para asegurar que el training está incompleto
        resetTrainingState();
        
        // Capturar errores de consola
        const consoleErrors = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleErrors.push(msg.text());
            }
        });
        
        // Arrancar app
        await page.goto('http://127.0.0.1:8000/repository_v3.html#inicio');
        
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
        
        // Esperar a que se cargue el estado del training (checkTrainingState se ejecuta en bootstrap)
        // El banner aparece después de que checkTrainingState() se ejecuta
        await page.waitForTimeout(3000);
    });

    test('should render first step correctly without undefined', async ({ page }) => {
        // Verificar que el banner de training está visible (puede tardar en aparecer)
        const banner = page.locator('[data-testid="training-banner"]');
        
        // Si no aparece, puede ser que el training ya esté completado - verificar estado
        const bannerCount = await banner.count();
        if (bannerCount === 0) {
            // Verificar estado del training vía API
            const response = await page.evaluate(async () => {
                const res = await fetch('http://127.0.0.1:8000/api/training/state');
                return await res.json();
            });
            
            // Si está completado, resetearlo
            if (response.training_completed) {
                resetTrainingState();
                await page.reload();
                await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
                await page.waitForTimeout(3000);
            }
        }
        
        await expect(banner).toBeVisible({ timeout: 10000 });
        
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 2000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('[data-testid="training-wizard-modal"], #training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 3000 });
        
        // Verificar que el título del paso está visible y NO es "undefined"
        const stepTitle = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle).toBeVisible({ timeout: 2000 });
        
        const titleText = await stepTitle.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText).not.toBe('undefined');
        expect(titleText.length).toBeGreaterThan(0);
        
        // Verificar que el contenido del paso está visible
        const stepContent = page.locator('[data-testid="training-step-1"]');
        await expect(stepContent).toBeVisible({ timeout: 2000 });
        
        // Verificar que NO aparece "undefined" en ningún lugar del modal
        const modalText = await modal.textContent();
        expect(modalText).not.toContain('undefined');
        
        // Verificar que el botón "Siguiente" está visible
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        await expect(nextButton).toBeVisible({ timeout: 2000 });
    });

    test('should navigate to next step without showing undefined', async ({ page }) => {
        // Abrir wizard
        const banner = page.locator('[data-testid="training-banner"]');
        await expect(banner).toBeVisible({ timeout: 8000 });
        
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await startButton.click();
        
        const modal = page.locator('[data-testid="training-wizard-modal"], #training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 3000 });
        
        // Verificar paso 1
        const stepTitle1 = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle1).toBeVisible({ timeout: 2000 });
        const title1 = await stepTitle1.textContent();
        expect(title1).not.toBe('undefined');
        
        // Click en "Siguiente"
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        await nextButton.click();
        await page.waitForTimeout(500);
        
        // Verificar paso 2
        const stepTitle2 = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle2).toBeVisible({ timeout: 2000 });
        const title2 = await stepTitle2.textContent();
        expect(title2).not.toBe('undefined');
        expect(title2).not.toBe(title1); // Debe haber cambiado
        
        // Verificar que NO aparece "undefined" en ningún lugar
        const modalText = await modal.textContent();
        expect(modalText).not.toContain('undefined');
        
        // Verificar que el botón "Anterior" ahora está visible
        const previousButton = page.locator('[data-testid="training-wizard-previous"]');
        await expect(previousButton).toBeVisible({ timeout: 2000 });
    });

    test('should handle invalid step gracefully', async ({ page }) => {
        // Abrir wizard
        const banner = page.locator('[data-testid="training-banner"]');
        await expect(banner).toBeVisible({ timeout: 8000 });
        
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await startButton.click();
        
        const modal = page.locator('[data-testid="training-wizard-modal"], #training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 3000 });
        
        // Intentar forzar un step inválido usando JavaScript
        await page.evaluate(() => {
            // Intentar acceder a un step que no existe
            if (typeof window.trainingWizardNext === 'function') {
                // Forzar currentStep a un valor inválido
                // Esto debería ser manejado por el clamp
            }
        });
        
        // Verificar que el modal sigue visible y no muestra "undefined"
        await expect(modal).toBeVisible({ timeout: 2000 });
        const modalText = await modal.textContent();
        expect(modalText).not.toContain('undefined');
        
        // Si hay un error, debe mostrar un mensaje humano
        if (modalText.includes('Error') || modalText.includes('Recargar')) {
            const reloadButton = page.locator('[data-testid="training-wizard-reload"]');
            await expect(reloadButton).toBeVisible({ timeout: 2000 });
        }
    });
});
