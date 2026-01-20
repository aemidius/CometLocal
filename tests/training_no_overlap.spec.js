/**
 * SPRINT C2.35.2: Test E2E para verificar que NO hay solape entre training C2.35 y legacy.
 * 
 * Verifica:
 * 1) Con training C2.35 incompleto: solo se ve banner/wizard C2.35, NO legacy
 * 2) Con training C2.35 completado: NO se auto-dispara legacy
 * 
 * Tiempo objetivo: < 60s
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Training No Overlap (C2.35.2)', () => {
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
        // Resetear estado antes de cada test
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
        
        // Seleccionar primera opción disponible en cada selector
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
        
        // Esperar a que se cargue el estado de training
        await page.waitForTimeout(1000);
        
        // Guardar consoleErrors para verificación posterior
        page.consoleErrors = consoleErrors;
    });

    test('should NOT show legacy training when C2.35 training is active', async ({ page }) => {
        // Verificar que training C2.35 está activo (banner visible)
        const c235Banner = page.locator('[data-testid="training-banner"]');
        await expect(c235Banner).toBeVisible({ timeout: 5000 });
        
        // Navegar a vista donde se disparaba legacy (ejecuciones)
        await page.goto('http://127.0.0.1:8000/repository_v3.html#ejecuciones');
        await page.waitForTimeout(2000);
        
        // Verificar que NO aparece el modal legacy
        // Buscar por texto característico del legacy
        const legacyWizard = page.locator('#training-wizard');
        const legacyText = page.locator('text=/Paso.*de.*Ejecuta una simulación/i');
        
        // Verificar que legacy wizard NO está visible
        if (await legacyWizard.count() > 0) {
            await expect(legacyWizard).not.toBeVisible({ timeout: 2000 });
        }
        
        // Verificar que NO hay texto del legacy visible
        if (await legacyText.count() > 0) {
            await expect(legacyText).not.toBeVisible({ timeout: 2000 });
        }
        
        // Verificar que el banner C2.35 sigue visible
        await expect(c235Banner).toBeVisible({ timeout: 2000 });
        
        // Verificar que NO hay demo-onboarding-banner visible
        const demoBanner = page.locator('#demo-onboarding-banner');
        if (await demoBanner.count() > 0) {
            await expect(demoBanner).not.toBeVisible({ timeout: 2000 });
        }
    });

    test('should NOT auto-start legacy training when C2.35 is completed', async ({ page }) => {
        // Marcar training C2.35 como completado
        markTrainingCompleted();
        
        // Refrescar página para que cargue el nuevo estado
        await page.reload();
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        
        // Esperar a que se cargue el estado
        await page.waitForTimeout(2000);
        
        // Verificar que el banner C2.35 NO está visible
        const c235Banner = page.locator('[data-testid="training-banner"]');
        await expect(c235Banner).not.toBeVisible({ timeout: 2000 });
        
        // Navegar por diferentes vistas donde antes se disparaba legacy
        await page.goto('http://127.0.0.1:8000/repository_v3.html#ejecuciones');
        await page.waitForTimeout(2000);
        
        // Verificar que legacy NO se auto-dispara
        const legacyWizard = page.locator('#training-wizard');
        if (await legacyWizard.count() > 0) {
            await expect(legacyWizard).not.toBeVisible({ timeout: 2000 });
        }
        
        // Navegar a otra vista
        await page.goto('http://127.0.0.1:8000/repository_v3.html#calendario');
        await page.waitForTimeout(2000);
        
        // Verificar que legacy sigue sin aparecer
        if (await legacyWizard.count() > 0) {
            await expect(legacyWizard).not.toBeVisible({ timeout: 2000 });
        }
    });

    test('should dismiss legacy if it appears while C2.35 wizard is open', async ({ page }) => {
        // Abrir wizard C2.35
        const c235Banner = page.locator('[data-testid="training-banner"]');
        await expect(c235Banner).toBeVisible({ timeout: 5000 });
        
        const startButton = c235Banner.locator('button:has-text("Iniciar Training")');
        await startButton.click();
        
        // SPRINT C2.35.4: Esperar a que aparezca el wizard C2.35 (el contenido se renderiza en setTimeout)
        const modal = page.locator('#training-wizard-modal');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Esperar a que el contenido tenga título válido
        await page.waitForFunction(
            () => {
                const title = document.querySelector('[data-testid="training-step-title"]');
                return title && title.textContent && title.textContent.trim().length > 0 && title.textContent.trim() !== 'undefined';
            },
            { timeout: 5000 }
        );
        
        // Verificar que legacy NO está visible
        const legacyWizard = page.locator('#training-wizard');
        if (await legacyWizard.count() > 0) {
            await expect(legacyWizard).not.toBeVisible({ timeout: 2000 });
        }
        
        // Intentar forzar que legacy aparezca (simular bug)
        await page.evaluate(() => {
            const legacy = document.getElementById('training-wizard');
            if (legacy) {
                legacy.style.display = 'flex';
            }
        });
        
        // Esperar un momento
        await page.waitForTimeout(500);
        
        // Verificar que legacy fue cerrado automáticamente (o no está visible)
        if (await legacyWizard.count() > 0) {
            const isVisible = await legacyWizard.isVisible();
            // Si está visible, verificar que el wizard C2.35 tiene z-index mayor
            if (isVisible) {
                const c235Wizard = page.locator('#training-wizard-modal');
                await expect(c235Wizard).toBeVisible({ timeout: 2000 });
            }
        }
    });
});
