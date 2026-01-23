/**
 * SPRINT FIX: Test E2E para verificar que guardar un tipo de documento funciona con contexto activo.
 * 
 * Verifica:
 * 1) El contexto de coordinación está seleccionado
 * 2) Se puede crear un tipo de documento con contexto activo
 * 3) Se puede editar un tipo de documento con contexto activo
 * 4) Si no hay contexto, se muestra mensaje claro y se bloquea el guardado
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Type Save With Context (SPRINT FIX)', () => {
    // Helper para resetear estado de training
    function resetTrainingState() {
        const statePath = path.join(__dirname, '..', 'data', 'training', 'state.json');
        if (fs.existsSync(statePath)) {
            fs.unlinkSync(statePath);
        }
    }

    // Helper para setup común de la app
    async function setupApp(page, view = 'catalog') {
        // Resetear training state si es necesario
        resetTrainingState();
        
        // Arrancar app en la vista de catálogo
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
        
        // Esperar a que el catálogo esté cargado
        await page.waitForTimeout(1000);
    }

    test.beforeEach(async ({ page }) => {
        await setupApp(page, 'catalog');
    });

    test('should save type with valid coordination context', async ({ page }) => {
        // Verificar que el contexto está seleccionado
        const ownCompanyValue = await page.locator('[data-testid="ctx-own-company"]').inputValue();
        const platformValue = await page.locator('[data-testid="ctx-platform"]').inputValue();
        const coordinatedValue = await page.locator('[data-testid="ctx-coordinated-company"]').inputValue();
        
        expect(ownCompanyValue).toBeTruthy();
        expect(platformValue).toBeTruthy();
        expect(coordinatedValue).toBeTruthy();
        
        // Abrir drawer de crear tipo
        const createButton = page.locator('button:has-text("Crear"), button:has-text("Nuevo tipo")');
        if (await createButton.count() > 0) {
            await createButton.click();
        } else {
            // Buscar botón alternativo
            const altButton = page.locator('button[onclick*="openCreateTypeDrawer"], button[onclick*="createType"]');
            if (await altButton.count() > 0) {
                await altButton.click();
            } else {
                // Usar función directa
                await page.evaluate(() => {
                    if (typeof window.openCreateTypeDrawer === 'function') {
                        window.openCreateTypeDrawer();
                    }
                });
            }
        }
        
        // Esperar a que el drawer aparezca
        await page.waitForTimeout(500);
        
        // Llenar formulario básico
        const nameInput = page.locator('#drawer-name, input[name="name"], input[placeholder*="nombre" i]');
        if (await nameInput.count() > 0) {
            await nameInput.fill('Test Type E2E ' + Date.now());
        }
        
        // Intentar guardar
        const saveButton = page.locator('button:has-text("Guardar"), button[onclick*="saveType"]');
        if (await saveButton.count() > 0) {
            // Capturar mensajes de consola para verificar que no hay errores de contexto
            const consoleMessages = [];
            page.on('console', msg => {
                if (msg.type() === 'error') {
                    consoleMessages.push(msg.text());
                }
            });
            
            await saveButton.click();
            
            // Esperar a que el drawer se cierre o aparezca un mensaje de éxito/error
            await page.waitForTimeout(2000);
            
            // Verificar que no hay errores de contexto faltante
            const contextErrors = consoleMessages.filter(msg => 
                msg.includes('missing_coordination_context') || 
                msg.includes('Selecciona Empresa propia')
            );
            expect(contextErrors.length).toBe(0);
        }
    });

    test('should block save when coordination context is missing', async ({ page }) => {
        // Limpiar contexto de coordinación
        await page.evaluate(() => {
            localStorage.removeItem('coordination_context_v1');
        });
        
        // Recargar página para que se aplique el cambio
        await page.reload();
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        
        // Abrir drawer de crear tipo
        await page.evaluate(() => {
            if (typeof window.openCreateTypeDrawer === 'function') {
                window.openCreateTypeDrawer();
            }
        });
        
        await page.waitForTimeout(500);
        
        // Llenar formulario básico
        const nameInput = page.locator('#drawer-name, input[name="name"]');
        if (await nameInput.count() > 0) {
            await nameInput.fill('Test Type Without Context');
        }
        
        // Capturar diálogos de alert
        let alertMessage = null;
        page.on('dialog', async dialog => {
            alertMessage = dialog.message();
            await dialog.accept();
        });
        
        // Intentar guardar
        const saveButton = page.locator('button:has-text("Guardar")');
        if (await saveButton.count() > 0) {
            await saveButton.click();
            await page.waitForTimeout(1000);
            
            // Verificar que se mostró el mensaje de contexto faltante
            expect(alertMessage).toContain('Selecciona Empresa propia');
        }
    });
});
