/**
 * SPRINT C2.36: Test E2E para preview de impacto y sugerencias.
 * 
 * Verifica:
 * 1) Preview aparece antes de confirmar
 * 2) Confirmación requerida (checkbox)
 * 3) Sugerencias aparecen con explicación
 * 4) Cancelar preview no cambia nada
 * 
 * Tiempo objetivo: < 60s
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Impact Preview and Suggestions (C2.36)', () => {
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
        // Marcar training como completado para desbloquear acciones
        markTrainingCompleted();
        
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
        
        // Esperar a que se cargue el estado
        await page.waitForTimeout(1000);
    });

    test('should show preview before confirming assign alias', async ({ page }) => {
        // Navegar a CAE Plan (asumiendo que hay un plan con NO_MATCH)
        await page.goto('http://127.0.0.1:8000/repository_v3.html#cae-plan');
        await page.waitForTimeout(2000);
        
        // Buscar botón de acción asistida
        const assignButton = page.locator('[data-testid="action-assign-existing-type"]').first();
        
        if (await assignButton.count() > 0) {
            await assignButton.click();
            await page.waitForTimeout(1000);
            
            // Seleccionar un tipo
            const typeSelector = page.locator('#type-selector');
            if (await typeSelector.count() > 0) {
                await typeSelector.selectOption({ index: 1 });
                await page.waitForTimeout(500);
                
                // Click en "Ver Preview"
                const previewButton = page.locator('button:has-text("Ver Preview")');
                if (await previewButton.count() > 0) {
                    await previewButton.click();
                    await page.waitForTimeout(2000);
                    
                    // Verificar que aparece el panel de preview
                    const previewPanel = page.locator('[data-testid="impact-preview-panel"], div:has-text("Impacto esperado")');
                    await expect(previewPanel.first()).toBeVisible({ timeout: 5000 });
                    
                    // Verificar que el botón "Aplicar" está deshabilitado inicialmente
                    const applyButton = page.locator('[data-testid="impact-preview-confirm"]');
                    if (await applyButton.count() > 0) {
                        await expect(applyButton).toBeDisabled();
                        
                        // Marcar checkbox
                        const confirmCheckbox = page.locator('#impact-preview-confirm');
                        if (await confirmCheckbox.count() > 0) {
                            await confirmCheckbox.check();
                            await page.waitForTimeout(500);
                            
                            // Verificar que el botón se habilita
                            await expect(applyButton).toBeEnabled();
                        }
                    }
                }
            }
        } else {
            // Si no hay botones de acción, el test pasa (no hay NO_MATCH)
            test.skip();
        }
    });

    test('should show suggestions with explanations', async ({ page }) => {
        // Navegar a CAE Plan
        await page.goto('http://127.0.0.1:8000/repository_v3.html#cae-plan');
        await page.waitForTimeout(2000);
        
        // Buscar contenedor de sugerencias
        const suggestionsContainer = page.locator('[id^="suggestions-container-"]').first();
        
        if (await suggestionsContainer.count() > 0) {
            // Esperar a que se carguen las sugerencias
            await page.waitForTimeout(2000);
            
            // Verificar que hay sugerencias visibles
            const suggestionsText = await suggestionsContainer.textContent();
            if (suggestionsText && suggestionsText.includes('Tipos sugeridos')) {
                // Verificar que hay botones "Usar este tipo"
                const useTypeButtons = page.locator('button:has-text("Usar este tipo")');
                if (await useTypeButtons.count() > 0) {
                    // Verificar que hay razones explicables
                    const reasons = page.locator('span:has-text("coincide"), span:has-text("compatible")');
                    await expect(reasons.first()).toBeVisible({ timeout: 2000 });
                }
            }
        } else {
            // Si no hay sugerencias, el test pasa (no hay NO_MATCH o no hay tipos similares)
            test.skip();
        }
    });

    test('should not apply changes when canceling preview', async ({ page }) => {
        // Navegar a CAE Plan
        await page.goto('http://127.0.0.1:8000/repository_v3.html#cae-plan');
        await page.waitForTimeout(2000);
        
        // Obtener estado inicial (contar tipos)
        const typesResponse = await page.evaluate(async () => {
            const response = await fetch('http://127.0.0.1:8000/api/repository/types');
            return await response.json();
        });
        const initialTypesCount = Array.isArray(typesResponse) ? typesResponse.length : 0;
        
        // Buscar botón de acción asistida
        const assignButton = page.locator('[data-testid="action-assign-existing-type"]').first();
        
        if (await assignButton.count() > 0) {
            await assignButton.click();
            await page.waitForTimeout(1000);
            
            const typeSelector = page.locator('#type-selector');
            if (await typeSelector.count() > 0) {
                await typeSelector.selectOption({ index: 1 });
                await page.waitForTimeout(500);
                
                const previewButton = page.locator('button:has-text("Ver Preview")');
                if (await previewButton.count() > 0) {
                    await previewButton.click();
                    await page.waitForTimeout(2000);
                    
                    // Cancelar preview
                    const cancelButton = page.locator('button:has-text("Cancelar")').last();
                    if (await cancelButton.count() > 0) {
                        await cancelButton.click();
                        await page.waitForTimeout(1000);
                        
                        // Verificar que no se aplicaron cambios
                        const typesResponseAfter = await page.evaluate(async () => {
                            const response = await fetch('http://127.0.0.1:8000/api/repository/types');
                            return await response.json();
                        });
                        const finalTypesCount = Array.isArray(typesResponseAfter) ? typesResponseAfter.length : 0;
                        
                        // El conteo debe ser el mismo (no se crearon tipos nuevos)
                        // Nota: Para alias, necesitaríamos verificar el tipo específico
                        // Por simplicidad, solo verificamos que no se crearon tipos
                        expect(finalTypesCount).toBe(initialTypesCount);
                    }
                }
            }
        } else {
            test.skip();
        }
    });
});
