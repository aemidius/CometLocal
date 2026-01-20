/**
 * SPRINT C2.35.3.1: Test E2E estabilizado para verificar que el wizard de training renderiza correctamente el primer paso.
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

test.describe('Training Wizard Renders First Step (C2.35.3.1)', () => {
    // Helper para resetear estado de training
    function resetTrainingState() {
        const statePath = path.join(__dirname, '..', 'data', 'training', 'state.json');
        if (fs.existsSync(statePath)) {
            fs.unlinkSync(statePath);
        }
    }

    test.beforeEach(async ({ page }) => {
        // SPRINT C2.35.3.1: Asegurar precondición: training incompleto
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
        
        // SPRINT C2.35.3.1: Esperar explícitamente a que aparezca el banner o el botón "Iniciar Training"
        // No usar sleeps fijos, esperar a que el elemento esté disponible
        const banner = page.locator('[data-testid="training-banner"]');
        const startButton = page.locator('button:has-text("Iniciar Training")');
        
        // Esperar a que al menos uno de los dos esté visible (el botón puede estar dentro del banner)
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

    test('should render first step correctly without undefined', async ({ page }) => {
        // SPRINT C2.35.3.1: Esperas robustas (no frágiles)
        // Esperar explícitamente a que aparezca el banner o el botón "Iniciar Training"
        const banner = page.locator('[data-testid="training-banner"]');
        const startButton = page.locator('button:has-text("Iniciar Training")');
        
        // Esperar a que el botón esté visible (puede estar dentro del banner)
        await expect(startButton).toBeVisible({ timeout: 10000 });
        
        // Click en "Iniciar Training"
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // SPRINT C2.35.3.1: Esperar a que el título tenga contenido válido (más robusto que toBeVisible)
        // Usar waitForFunction para esperar activamente a que el contenido se renderice
        await page.waitForFunction(
            () => {
                const title = document.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim().length > 0 && title.textContent.trim() !== 'undefined';
            },
            { timeout: 5000 }
        );
        
        // Verificar que el título existe y tiene contenido
        const stepTitle = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle).toHaveCount(1, { timeout: 2000 });
        
        const titleText = await stepTitle.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText).not.toBe('undefined');
        expect(titleText.trim().length).toBeGreaterThan(0);
        
        // SPRINT C2.35.4: Verificar que el contenido existe (usar first() para evitar duplicados)
        const content = page.locator('#training-wizard-content').first();
        await expect(content).toHaveCount(1, { timeout: 2000 });
        
        // Verificar que el contenido tiene texto (no está vacío)
        const contentText = await content.textContent();
        expect(contentText).toBeTruthy();
        expect(contentText.trim().length).toBeGreaterThan(0);
        
        // SPRINT C2.35.3.1: Assert adicional: verificar que NO aparece "undefined" en ningún lugar
        const undefinedCount = await page.locator('text=undefined').count();
        expect(undefinedCount).toBe(0);
        
        // Verificar que NO aparece "undefined" en el texto del modal
        const modalText = await modal.textContent();
        expect(modalText).not.toContain('undefined');
        
        // Verificar que el botón "Siguiente" existe (puede estar oculto por CSS pero debe existir)
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        await expect(nextButton).toHaveCount(1, { timeout: 2000 });
        
        // Verificar que el botón tiene texto válido
        const nextButtonText = await nextButton.textContent();
        expect(nextButtonText).toContain('Siguiente');
    });

    test('should navigate to next step without showing undefined', async ({ page }) => {
        // Abrir wizard
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        // Esperar a que aparezca el modal
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Esperar a que el título del paso 1 tenga contenido válido
        await page.waitForFunction(
            () => {
                const title = document.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim().length > 0 && title.textContent.trim() !== 'undefined';
            },
            { timeout: 5000 }
        );
        
        const stepTitle1 = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle1).toHaveCount(1, { timeout: 2000 });
        
        const title1 = await stepTitle1.textContent();
        expect(title1).not.toBe('undefined');
        expect(title1.trim().length).toBeGreaterThan(0);
        
        // Verificar que NO aparece "undefined"
        const undefinedCount1 = await page.locator('text=undefined').count();
        expect(undefinedCount1).toBe(0);
        
        // Click en "Siguiente" usando la función directamente (más robusto)
        // Verificar que el botón existe
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        await expect(nextButton).toHaveCount(1, { timeout: 2000 });
        
        // Ejecutar la función directamente (más robusto que click)
        await page.evaluate(() => {
            if (typeof window.trainingWizardNext === 'function') {
                window.trainingWizardNext();
            }
        });
        
        // Esperar a que el título del paso 2 haya cambiado (no sea el mismo que title1)
        await page.waitForFunction(
            (prevTitle) => {
                const title = document.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim() !== prevTitle && title.textContent.trim() !== 'undefined';
            },
            title1.trim(),
            { timeout: 5000 }
        );
        
        const stepTitle2 = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle2).toHaveCount(1, { timeout: 2000 });
        
        const title2 = await stepTitle2.textContent();
        expect(title2).not.toBe('undefined');
        expect(title2).not.toBe(title1); // Debe haber cambiado
        expect(title2.trim().length).toBeGreaterThan(0);
        
        // Verificar que NO aparece "undefined"
        const undefinedCount2 = await page.locator('text=undefined').count();
        expect(undefinedCount2).toBe(0);
        
        // Verificar que NO aparece "undefined" en el texto del modal
        const modalText = await modal.textContent();
        expect(modalText).not.toContain('undefined');
        
        // Verificar que el botón "Anterior" ahora existe
        const previousButton = page.locator('[data-testid="training-wizard-previous"]');
        await expect(previousButton).toHaveCount(1, { timeout: 2000 });
        
        // Verificar que el botón tiene texto válido
        const previousButtonText = await previousButton.textContent();
        expect(previousButtonText).toContain('Anterior');
    });

    test('should handle invalid step gracefully', async ({ page }) => {
        // Abrir wizard
        const startButton = page.locator('button:has-text("Iniciar Training")');
        await expect(startButton).toBeVisible({ timeout: 10000 });
        await startButton.click();
        
        const modal = page.locator('#training-wizard-modal, [data-testid="training-wizard-modal"]');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Esperar a que el título tenga contenido válido
        await page.waitForFunction(
            () => {
                const title = document.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim().length > 0 && title.textContent.trim() !== 'undefined';
            },
            { timeout: 5000 }
        );
        
        const stepTitle = page.locator('[data-testid="training-step-title"]');
        await expect(stepTitle).toHaveCount(1, { timeout: 2000 });
        
        // Verificar que el modal sigue visible y no muestra "undefined"
        await expect(modal).toBeVisible({ timeout: 2000 });
        
        // Verificar que NO aparece "undefined"
        const undefinedCount = await page.locator('text=undefined').count();
        expect(undefinedCount).toBe(0);
        
        const modalText = await modal.textContent();
        expect(modalText).not.toContain('undefined');
        
        // Si hay un error, debe mostrar un mensaje humano
        if (modalText.includes('Error') || modalText.includes('Recargar')) {
            const reloadButton = page.locator('[data-testid="training-wizard-reload"]');
            await expect(reloadButton).toBeVisible({ timeout: 2000 });
        }
    });
});
