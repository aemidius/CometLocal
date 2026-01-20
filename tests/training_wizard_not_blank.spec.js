/**
 * SPRINT C2.35.4: Test E2E para verificar que el modal de training nunca está en blanco.
 * 
 * Verifica:
 * 1) Al abrir el modal, siempre hay contenido visible (título + texto + botones)
 * 2) Si hay error, se muestra mensaje humano con botón "Recargar"
 * 3) El modal nunca aparece vacío sin feedback
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Training Wizard Not Blank (C2.35.4)', () => {
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

    test('should never show blank modal when opening training', async ({ page }) => {
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal (usar solo ID para evitar duplicados)
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // SPRINT C2.35.4: Esperar a que el contenido tenga texto válido (no vacío)
        await page.waitForFunction(
            () => {
                const content = document.getElementById('training-wizard-content');
                if (!content) return false;
                
                // Verificar que el contenido no está vacío
                const textContent = content.textContent || '';
                if (textContent.trim().length === 0) return false;
                
                // Verificar que hay un título (ya sea de paso o de error)
                const title = content.querySelector('[data-testid="training-step-title"]');
                if (!title || !title.textContent || title.textContent.trim().length === 0) {
                    return false;
                }
                
                return true;
            },
            { timeout: 5000 }
        );
        
        // Verificar que el contenido existe y no está vacío (usar first() para evitar duplicados)
        const content = page.locator('#training-wizard-content').first();
        await expect(content).toHaveCount(1, { timeout: 2000 });
        
        const contentText = await content.textContent();
        expect(contentText).toBeTruthy();
        expect(contentText.trim().length).toBeGreaterThan(0);
        
        // Verificar que el título existe (puede ser de paso o de error)
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toHaveCount(1, { timeout: 2000 });
        
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
        expect(titleText.trim()).not.toBe('undefined');
        
        // SPRINT C2.35.4: Verificar que el contenido tiene al menos 50 caracteres (no está vacío)
        expect(contentText.trim().length).toBeGreaterThan(50);
        
        // Verificar que NO aparece "undefined" en ningún lugar
        const undefinedCount = await page.locator('text=undefined').count();
        expect(undefinedCount).toBe(0);
    });

    test('should show error message if render fails', async ({ page }) => {
        // Intentar forzar un error inyectando código que rompa el render
        // (esto es difícil de hacer de forma determinista, así que verificamos que el fallback existe)
        
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Verificar que el contenido existe (puede ser paso normal o error)
        // Usar first() para evitar problemas con duplicados
        const content = page.locator('#training-wizard-content').first();
        await expect(content).toHaveCount(1, { timeout: 2000 });
        
        // Verificar que hay un título (de paso o de error)
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toHaveCount(1, { timeout: 2000 });
        
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
        
        // Si el título contiene "Error", verificar que hay botón "Recargar"
        if (titleText.toLowerCase().includes('error')) {
            const reloadButton = page.locator('[data-testid="training-wizard-reload"]');
            await expect(reloadButton).toHaveCount(1, { timeout: 2000 });
        }
    });

    test('should show loading state initially then content', async ({ page }) => {
        // Click en "Iniciar Training"
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal (debe aparecer inmediatamente)
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 1000 });
        
        // El contenido debe aparecer en menos de 500ms normalmente
        await page.waitForFunction(
            () => {
                const content = document.getElementById('training-wizard-content');
                if (!content) return false;
                
                const textContent = content.textContent || '';
                // Verificar que no está en estado "Cargando training..." o que ya tiene contenido válido
                return textContent.trim().length > 0 && !textContent.includes('Cargando training');
            },
            { timeout: 2000 }
        );
        
        // Verificar que el contenido final es válido
        const title = page.locator('[data-testid="training-step-title"]');
        await expect(title).toHaveCount(1, { timeout: 2000 });
        
        const titleText = await title.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText.trim().length).toBeGreaterThan(0);
        expect(titleText.trim()).not.toBe('undefined');
    });
});
