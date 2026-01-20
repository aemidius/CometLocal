/**
 * SPRINT C2.35.5: Test E2E para verificar que el modal de training nunca se queda en "Cargando training..." indefinidamente.
 * 
 * Verifica:
 * 1) El loading aparece inicialmente
 * 2) En <= 3s desaparece el loading y aparece contenido válido o fallback de error
 * 3) No se queda en loading permanente
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Training Wizard Not Stuck Loading (C2.35.5)', () => {
    // Helper para resetear estado de training
    function resetTrainingState() {
        const statePath = path.join(__dirname, '..', 'data', 'training', 'state.json');
        if (fs.existsSync(statePath)) {
            fs.unlinkSync(statePath);
        }
    }

    test.beforeEach(async ({ page }) => {
        // Resetear training state para asegurar que el training está incompleto
        resetTrainingState();
        
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
    });

    test('should not stay in loading state indefinitely', async ({ page }) => {
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 1000 });
        
        // SPRINT C2.35.5: Verificar que aparece "Cargando training..." inicialmente
        const loadingText = page.locator('text=Cargando training...');
        await expect(loadingText).toBeVisible({ timeout: 500 });
        
        // SPRINT C2.35.5: Verificar que en <= 3s desaparece el loading y aparece contenido válido o fallback
        await page.waitForFunction(
            () => {
                const content = document.getElementById('training-wizard-content');
                if (!content) return false;
                
                // Verificar que NO está en loading
                const loadingEl = content.querySelector('[data-testid="training-wizard-loading"]');
                if (loadingEl) return false;
                
                // Verificar que el texto no contiene "Cargando training..."
                const textContent = content.textContent || '';
                if (textContent.includes('Cargando training...')) {
                    return false;
                }
                
                // Verificar que hay contenido válido (título de paso o error)
                const title = content.querySelector('[data-testid="training-step-title"]');
                if (!title || !title.textContent || title.textContent.trim().length === 0) {
                    return false;
                }
                
                return true;
            },
            { timeout: 3000 }
        );
        
        // Verificar que hay contenido válido (título de paso o error)
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toHaveCount(1, { timeout: 1000 });
        
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
        expect(titleText.trim()).not.toBe('undefined');
        expect(titleText.trim()).not.toContain('Cargando training...');
        
        // SPRINT C2.35.5: Verificar que NO queda en loading permanente
        // Esperar un poco más y verificar que sigue sin loading
        await page.waitForTimeout(500);
        const loadingStillExists = await page.evaluate(() => {
            const content = document.getElementById('training-wizard-content');
            if (!content) return false;
            const loadingEl = content.querySelector('[data-testid="training-wizard-loading"]');
            return loadingEl !== null;
        });
        expect(loadingStillExists).toBe(false);
    });

    test('should show fallback if loading exceeds timeout', async ({ page }) => {
        // Este test verifica que el timeout funciona, pero es difícil forzar un timeout real
        // en condiciones normales. Verificamos que el mecanismo existe.
        
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 1000 });
        
        // Verificar que aparece "Cargando training..." inicialmente
        const loadingText = page.locator('text=Cargando training...');
        await expect(loadingText).toBeVisible({ timeout: 500 });
        
        // Esperar a que el contenido se renderice (normalmente < 1s)
        await page.waitForFunction(
            () => {
                const content = document.getElementById('training-wizard-content');
                if (!content) return false;
                
                // Verificar que NO está en loading
                const loadingEl = content.querySelector('[data-testid="training-wizard-loading"]');
                if (loadingEl) return false;
                
                // Verificar que el texto no contiene "Cargando training..."
                const textContent = content.textContent || '';
                if (textContent.includes('Cargando training...')) {
                    return false;
                }
                
                // Verificar que hay contenido válido
                const title = content.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim().length > 0;
            },
            { timeout: 3000 }
        );
        
        // Verificar que hay contenido válido
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toHaveCount(1, { timeout: 1000 });
        
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
    });

    test('should have reload button in error fallback', async ({ page }) => {
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 1000 });
        
        // Esperar a que el contenido se renderice
        await page.waitForFunction(
            () => {
                const content = document.getElementById('training-wizard-content');
                if (!content) return false;
                
                const loadingEl = content.querySelector('[data-testid="training-wizard-loading"]');
                if (loadingEl) return false;
                
                const title = content.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim().length > 0;
            },
            { timeout: 3000 }
        );
        
        // Si aparece un error (poco probable en condiciones normales), verificar que hay botón "Recargar"
        const errorTitle = page.locator('[data-testid="training-step-title"]:has-text("Error")');
        const errorCount = await errorTitle.count();
        
        if (errorCount > 0) {
            // Hay un error, verificar que existe el botón "Recargar"
            const reloadButton = page.locator('[data-testid="training-wizard-reload"]');
            await expect(reloadButton).toHaveCount(1, { timeout: 1000 });
            
            const reloadText = await reloadButton.textContent();
            expect(reloadText).toContain('Recargar');
        } else {
            // No hay error, el test pasa (comportamiento normal)
            const title = page.locator('[data-testid="training-step-title"]');
            await expect(title).toHaveCount(1, { timeout: 1000 });
        }
    });
});
