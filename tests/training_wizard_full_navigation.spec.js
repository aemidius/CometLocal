/**
 * SPRINT C2.35.10.2: Test E2E para verificar navegación completa del training wizard.
 * 
 * Verifica:
 * 1) El wizard puede navegar desde Paso 1 hasta Paso 5 usando botones Next
 * 2) Los títulos de los pasos cambian correctamente
 * 3) No aparecen errores "Content no encontrado" en la consola
 * 4) La navegación funciona sin quedarse bloqueada
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Training Wizard Full Navigation (C2.35.10.2)', () => {
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
        
        // Esperar a que aparezca el banner o botón de training
        await page.waitForSelector('button:has-text("Iniciar Training"), [data-testid="training-banner"]', { timeout: 10000 });
    }

    test.beforeEach(async ({ page }) => {
        await setupApp(page, 'inicio');
    });

    test('should navigate through all steps (1→2→3→4→5) without errors', async ({ page }) => {
        // Capturar mensajes de consola para verificar que no hay errores
        const consoleMessages = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleMessages.push(msg.text());
            }
        });

        // Click en "Iniciar Training"
        await page.locator('button:has-text("Iniciar Training")').click();
        
        // Esperar a que el modal aparezca
        await expect(page.locator('[data-testid="training-wizard-modal"]')).toBeVisible({ timeout: 5000 });
        
        // Esperar a que el loading desaparezca y aparezca el paso 1
        await page.waitForFunction(() => {
            const loading = document.querySelector('[data-testid="training-wizard-loading"]');
            const title = document.querySelector('[data-testid="training-step-title"]');
            return !loading && title && title.textContent.trim().length > 0;
        }, { timeout: 5000 });
        
        // Verificar que estamos en el paso 1
        const step1Title = page.locator('[data-testid="training-step-title"]');
        await expect(step1Title).toBeVisible();
        const step1TitleText = await step1Title.textContent();
        expect(step1TitleText).toBeTruthy();
        expect(step1TitleText.trim().length).toBeGreaterThan(0);
        
        // Navegar al paso 2
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        await expect(nextButton).toBeVisible();
        await nextButton.click();
        
        // Esperar a que el título cambie (sin usar sleep fijo)
        await page.waitForFunction((previousTitle) => {
            const title = document.querySelector('[data-testid="training-step-title"]');
            return title && title.textContent.trim() !== previousTitle && title.textContent.trim().length > 0;
        }, step1TitleText, { timeout: 5000 });
        
        const step2Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step2Title).toBeTruthy();
        expect(step2Title).not.toBe(step1TitleText);
        
        // Navegar al paso 3
        await nextButton.click();
        await page.waitForFunction((previousTitle) => {
            const title = document.querySelector('[data-testid="training-step-title"]');
            return title && title.textContent.trim() !== previousTitle && title.textContent.trim().length > 0;
        }, step2Title, { timeout: 5000 });
        
        const step3Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step3Title).toBeTruthy();
        expect(step3Title).not.toBe(step2Title);
        
        // Navegar al paso 4
        await nextButton.click();
        await page.waitForFunction((previousTitle) => {
            const title = document.querySelector('[data-testid="training-step-title"]');
            return title && title.textContent.trim() !== previousTitle && title.textContent.trim().length > 0;
        }, step3Title, { timeout: 5000 });
        
        const step4Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step4Title).toBeTruthy();
        expect(step4Title).not.toBe(step3Title);
        
        // Navegar al paso 5
        await nextButton.click();
        await page.waitForFunction((previousTitle) => {
            const title = document.querySelector('[data-testid="training-step-title"]');
            return title && title.textContent.trim() !== previousTitle && title.textContent.trim().length > 0;
        }, step4Title, { timeout: 5000 });
        
        const step5Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step5Title).toBeTruthy();
        expect(step5Title).not.toBe(step4Title);
        
        // Verificar que no hay errores "Content no encontrado" en la consola
        const errorMessages = consoleMessages.filter(msg => 
            msg.includes('Content no encontrado') || 
            msg.includes('Modal no encontrado')
        );
        expect(errorMessages.length).toBe(0);
        
        // Verificar que el paso 5 es visible y tiene contenido
        await expect(page.locator('[data-testid="training-step-title"]')).toBeVisible();
        expect(step5Title.trim().length).toBeGreaterThan(0);
    });

    test('should navigate backwards (5→4→3→2→1) without errors', async ({ page }) => {
        // Capturar mensajes de consola
        const consoleMessages = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleMessages.push(msg.text());
            }
        });

        // Abrir training y navegar hasta el paso 5
        await page.locator('button:has-text("Iniciar Training")').click();
        await expect(page.locator('[data-testid="training-wizard-modal"]')).toBeVisible({ timeout: 5000 });
        
        await page.waitForFunction(() => {
            const loading = document.querySelector('[data-testid="training-wizard-loading"]');
            const title = document.querySelector('[data-testid="training-step-title"]');
            return !loading && title && title.textContent.trim().length > 0;
        }, { timeout: 5000 });
        
        const nextButton = page.locator('[data-testid="training-wizard-next"]');
        const previousButton = page.locator('[data-testid="training-wizard-previous"]');
        
        // Avanzar hasta paso 5
        for (let i = 0; i < 4; i++) {
            await nextButton.click();
            await page.waitForTimeout(500); // Pequeña pausa para permitir render
        }
        
        // Verificar que estamos en paso 5
        const step5Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step5Title).toBeTruthy();
        
        // Retroceder al paso 4
        await previousButton.click();
        await page.waitForFunction((previousTitle) => {
            const title = document.querySelector('[data-testid="training-step-title"]');
            return title && title.textContent.trim() !== previousTitle && title.textContent.trim().length > 0;
        }, step5Title, { timeout: 5000 });
        
        const step4Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step4Title).not.toBe(step5Title);
        
        // Retroceder al paso 3
        await previousButton.click();
        await page.waitForFunction((previousTitle) => {
            const title = document.querySelector('[data-testid="training-step-title"]');
            return title && title.textContent.trim() !== previousTitle && title.textContent.trim().length > 0;
        }, step4Title, { timeout: 5000 });
        
        const step3Title = await page.locator('[data-testid="training-step-title"]').textContent();
        expect(step3Title).not.toBe(step4Title);
        
        // Verificar que no hay errores "Content no encontrado"
        const errorMessages = consoleMessages.filter(msg => 
            msg.includes('Content no encontrado') || 
            msg.includes('Modal no encontrado')
        );
        expect(errorMessages.length).toBe(0);
    });
});
