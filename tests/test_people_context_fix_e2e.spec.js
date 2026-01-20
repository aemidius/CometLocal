/**
 * FIX: Test E2E para verificar que Config → Trabajadores (/config/people) funciona correctamente.
 * 
 * Este test verifica:
 * 1. GET /config/people siempre carga (nunca 500)
 * 2. POST /config/people guarda own_company_key correctamente cuando hay contexto
 * 3. La UI muestra errores de guardrail como 400 con mensaje claro, nunca 500
 * 4. Persistencia: own_company_key se mantiene tras recargar
 * 
 * Requisitos del fix:
 * - Abrir repository_v3.html#configuracion?section=people
 * - Seleccionar contexto humano en header (empresa propia + plataforma + empresa coordinada)
 * - Cambiar workers a la empresa propia seleccionada
 * - Guardar y verificar persistencia
 * - Fail si hay errores JS en consola
 */

import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

test.describe('FIX: /config/people GET 500 + context headers + persist own_company_key', () => {
    test.beforeEach(async ({ page }) => {
        // Capturar errores de JavaScript
        const jsErrors = [];
        page.on('pageerror', error => {
            jsErrors.push(error.message);
        });
        
        page.on('console', msg => {
            if (msg.type() === 'error') {
                jsErrors.push(`Console error: ${msg.text()}`);
            }
        });
        
        // Guardar referencia a errores para verificación posterior
        page.jsErrors = jsErrors;
        
        // Desactivar training wizard
        await page.addInitScript(() => {
            localStorage.setItem('trainingCompleted', 'true');
        });
    });
    
    test('should complete full flow: context selection → workers assignment → save → verify persistence', async ({ page }) => {
        // 1. Abrir repository_v3.html#configuracion?section=people
        await page.goto('http://127.0.0.1:8000/repository_v3.html#configuracion?section=people');
        
        // Esperar a que la app esté lista
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        await page.waitForTimeout(1000);
        
        // 2. Seleccionar contexto humano en el header
        const ownCompanySelect = page.locator('[data-testid="ctx-own-company"], #ctx-own-company');
        const platformSelect = page.locator('[data-testid="ctx-platform"], #ctx-platform');
        const coordinatedSelect = page.locator('[data-testid="ctx-coordinated-company"], #ctx-coordinated-company');
        
        // Esperar a que los selectores estén cargados
        await ownCompanySelect.waitFor({ timeout: 5000, state: 'attached' });
        await platformSelect.waitFor({ timeout: 5000, state: 'attached' });
        await coordinatedSelect.waitFor({ timeout: 5000, state: 'attached' });
        
        // Seleccionar Empresa propia = Tedelab (o la primera disponible)
        const ownCompanyOptions = await ownCompanySelect.locator('option').all();
        let selectedOwnCompany = null;
        if (ownCompanyOptions.length > 1) {
            // Buscar "Tedelab" primero, si no existe usar la primera disponible
            for (let i = 1; i < ownCompanyOptions.length; i++) {
                const text = await ownCompanyOptions[i].textContent();
                const value = await ownCompanyOptions[i].getAttribute('value');
                if (text && text.toLowerCase().includes('tedelab')) {
                    selectedOwnCompany = value;
                    await ownCompanySelect.selectOption(value);
                    break;
                }
            }
            if (!selectedOwnCompany && ownCompanyOptions.length > 1) {
                selectedOwnCompany = await ownCompanyOptions[1].getAttribute('value');
                await ownCompanySelect.selectOption(selectedOwnCompany);
            }
        }
        await page.waitForTimeout(300);
        
        // Seleccionar Plataforma = Egestiona (o primera disponible)
        const platformOptions = await platformSelect.locator('option').all();
        let selectedPlatform = null;
        if (platformOptions.length > 1) {
            // Buscar "egestiona" primero
            for (let i = 1; i < platformOptions.length; i++) {
                const text = await platformOptions[i].textContent();
                const value = await platformOptions[i].getAttribute('value');
                if (text && text.toLowerCase().includes('egestiona')) {
                    selectedPlatform = value;
                    await platformSelect.selectOption(value);
                    break;
                }
            }
            if (!selectedPlatform && platformOptions.length > 1) {
                selectedPlatform = await platformOptions[1].getAttribute('value');
                await platformSelect.selectOption(selectedPlatform);
            }
        }
        await page.waitForTimeout(500); // Esperar a que se carguen empresas coordinadas
        
        // Seleccionar Empresa coordinada = Aigües de Manresa (o primera disponible)
        const coordinatedOptions = await coordinatedSelect.locator('option').all();
        let selectedCoordinated = null;
        if (coordinatedOptions.length > 1) {
            // Buscar "Aigües de Manresa" primero
            for (let i = 1; i < coordinatedOptions.length; i++) {
                const text = await coordinatedOptions[i].textContent();
                const value = await coordinatedOptions[i].getAttribute('value');
                if (text && text.toLowerCase().includes('manresa') || text && text.toLowerCase().includes('aigües')) {
                    selectedCoordinated = value;
                    await coordinatedSelect.selectOption(value);
                    break;
                }
            }
            if (!selectedCoordinated && coordinatedOptions.length > 1) {
                selectedCoordinated = await coordinatedOptions[1].getAttribute('value');
                await coordinatedSelect.selectOption(selectedCoordinated);
            }
        }
        await page.waitForTimeout(300);
        
        // Verificar que el contexto está seleccionado
        const badge = page.locator('[data-testid="ctx-badge"], .ctx-badge');
        const badgeText = await badge.textContent();
        expect(badgeText).not.toBe('Sin contexto');
        
        // 3. Esperar a que el iframe de Config People esté cargado
        // El iframe puede estar en un contenedor específico
        await page.waitForTimeout(2000); // Dar tiempo al iframe para cargar
        
        // Buscar el iframe (puede estar en diferentes ubicaciones)
        let iframe = null;
        try {
            iframe = page.frameLocator('iframe[src*="/config/people"]');
            await iframe.locator('form#people-form').waitFor({ timeout: 5000, state: 'attached' });
        } catch (e) {
            // Si no hay iframe, puede que esté integrado directamente
            // Intentar buscar el formulario directamente
            await page.waitForSelector('form#people-form', { timeout: 5000 });
        }
        
        // 4. Cambiar ambos workers a la empresa propia seleccionada
        // Buscar todos los selects de own_company_key en el iframe o en la página
        let companySelects;
        if (iframe) {
            companySelects = await iframe.locator('select[name^="own_company_key__"]').all();
        } else {
            companySelects = await page.locator('select[name^="own_company_key__"]').all();
        }
        
        // Filtrar solo los que tienen un worker_id asociado (no la fila vacía)
        const workerSelects = [];
        for (const select of companySelects) {
            const name = await select.getAttribute('name');
            const match = name.match(/own_company_key__(\d+)/);
            if (match) {
                const index = parseInt(match[1]);
                // Verificar que hay un worker_id para este índice
                let workerInput;
                if (iframe) {
                    workerInput = iframe.locator(`input[name="worker_id__${index}"]`);
                } else {
                    workerInput = page.locator(`input[name="worker_id__${index}"]`);
                }
                const workerId = await workerInput.inputValue();
                if (workerId && workerId.trim() !== '') {
                    workerSelects.push({ select, index, workerId: workerId.trim() });
                }
            }
        }
        
        // Si no hay workers, crear uno para probar
        if (workerSelects.length === 0) {
            // Buscar la fila vacía y llenarla
            let emptyWorkerInput;
            if (iframe) {
                emptyWorkerInput = iframe.locator('input[name^="worker_id__"]').first();
            } else {
                emptyWorkerInput = page.locator('input[name^="worker_id__"]').first();
            }
            
            const emptyName = await emptyWorkerInput.getAttribute('name');
            const emptyMatch = emptyName.match(/worker_id__(\d+)/);
            if (emptyMatch) {
                const emptyIndex = parseInt(emptyMatch[1]);
                await emptyWorkerInput.fill('test_worker_1');
                
                // Llenar otros campos mínimos
                if (iframe) {
                    await iframe.locator(`input[name="full_name__${emptyIndex}"]`).fill('Test Worker 1');
                    await iframe.locator(`select[name="own_company_key__${emptyIndex}"]`).selectOption(selectedOwnCompany || 'unassigned');
                } else {
                    await page.locator(`input[name="full_name__${emptyIndex}"]`).fill('Test Worker 1');
                    await page.locator(`select[name="own_company_key__${emptyIndex}"]`).selectOption(selectedOwnCompany || 'unassigned');
                }
                
                workerSelects.push({
                    select: iframe ? iframe.locator(`select[name="own_company_key__${emptyIndex}"]`) : page.locator(`select[name="own_company_key__${emptyIndex}"]`),
                    index: emptyIndex,
                    workerId: 'test_worker_1'
                });
            }
        }
        
        // Cambiar los primeros 2 workers (o todos si hay menos) a la empresa propia seleccionada
        const workersToChange = workerSelects.slice(0, 2);
        for (const { select, workerId } of workersToChange) {
            if (selectedOwnCompany) {
                await select.selectOption(selectedOwnCompany);
            }
        }
        
        // 5. Click Guardar
        let saveButton;
        if (iframe) {
            saveButton = iframe.locator('button[type="submit"], button#people-save-btn');
        } else {
            saveButton = page.locator('button[type="submit"], button#people-save-btn');
        }
        
        await expect(saveButton).toBeVisible();
        
        // Interceptar respuesta para verificar que no hay errores
        let responseError = null;
        let responseStatus = null;
        page.on('response', response => {
            if (response.url().includes('/config/people') && response.request().method() === 'POST') {
                responseStatus = response.status();
                if (response.status() >= 400) {
                    responseError = `HTTP ${response.status()}: ${response.statusText()}`;
                }
            }
        });
        
        // Hacer click en Guardar
        await saveButton.click();
        
        // Esperar a que se procese el POST
        await page.waitForTimeout(3000);
        
        // Verificar que no hubo errores 500
        if (responseStatus === 500) {
            throw new Error(`POST /config/people devolvió 500: ${responseError}`);
        }
        
        // Si hay error 400, debe ser por falta de contexto (esperado si no se seleccionó contexto)
        if (responseStatus === 400 && responseError) {
            // Verificar que el mensaje de error es claro
            const errorDiv = iframe ? iframe.locator('#people-form-error') : page.locator('#people-form-error');
            const errorVisible = await errorDiv.isVisible().catch(() => false);
            if (errorVisible) {
                const errorText = await errorDiv.textContent();
                expect(errorText).toContain('Selecciona Empresa propia');
            }
        }
        
        // 6. Reabrir "Trabajadores" (recargar la página)
        await page.reload();
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        await page.waitForTimeout(2000);
        
        // Esperar a que el iframe se recargue
        if (iframe) {
            await iframe.locator('form#people-form').waitFor({ timeout: 10000, state: 'attached' });
        } else {
            await page.waitForSelector('form#people-form', { timeout: 10000 });
        }
        await page.waitForTimeout(1000);
        
        // 7. Verificar que los selects por fila mantienen la selección (no vuelve a "Sin asignar")
        for (const { select, workerId } of workersToChange) {
            if (selectedOwnCompany) {
                const currentValue = await select.inputValue();
                expect(currentValue).toBe(selectedOwnCompany);
            }
        }
        
        // 8. Verificar que no hay errores JS en consola
        const jsErrors = page.jsErrors || [];
        if (jsErrors.length > 0) {
            // Filtrar errores conocidos/no críticos si es necesario
            const criticalErrors = jsErrors.filter(err => {
                // Filtrar errores conocidos que no son críticos
                return !err.includes('favicon') && !err.includes('chrome-extension');
            });
            
            if (criticalErrors.length > 0) {
                throw new Error(`Errores de JavaScript detectados: ${criticalErrors.join(', ')}`);
            }
        }
        
        // 9. Capturar screenshot como evidencia
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'c2_fix_people_context');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
        
        const screenshotPath = path.join(evidenceDir, 'people_config_after_save.png');
        await page.screenshot({ path: screenshotPath, fullPage: true });
        
        // Verificar que el JSON contiene own_company_key
        const peopleJsonPath = path.join(__dirname, '..', 'data', 'refs', 'people.json');
        if (fs.existsSync(peopleJsonPath)) {
            const peopleData = JSON.parse(fs.readFileSync(peopleJsonPath, 'utf-8'));
            for (const { workerId } of workersToChange) {
                const workerData = peopleData.people.find((p) => p.worker_id === workerId);
                if (workerData) {
                    expect(workerData).toHaveProperty('own_company_key');
                    if (selectedOwnCompany) {
                        expect(workerData.own_company_key).toBe(selectedOwnCompany);
                    }
                }
            }
        }
    });
    
    test('should show 400 error (not 500) when POST without context', async ({ page }) => {
        // Navegar directamente a /config/people (sin contexto)
        await page.goto('http://127.0.0.1:8000/config/people');
        
        // Esperar a que el formulario esté cargado
        await page.waitForSelector('form#people-form', { timeout: 10000 });
        await page.waitForTimeout(1000);
        
        // Verificar que GET devuelve 200 (no 500)
        const response = await page.goto('http://127.0.0.1:8000/config/people');
        expect(response.status()).toBe(200);
        
        // Intentar guardar sin contexto
        const saveButton = page.locator('button[type="submit"], button#people-save-btn');
        await expect(saveButton).toBeVisible();
        
        // Interceptar respuesta POST
        let responseStatus = null;
        let responseError = null;
        page.on('response', response => {
            if (response.url().includes('/config/people') && response.request().method() === 'POST') {
                responseStatus = response.status();
                if (response.status() >= 400) {
                    responseError = `HTTP ${response.status()}: ${response.statusText()}`;
                }
            }
        });
        
        await saveButton.click();
        await page.waitForTimeout(2000);
        
        // Debe devolver 400 (no 500)
        expect(responseStatus).toBe(400);
        
        // Verificar que aparece el mensaje de error en la UI
        const errorDiv = page.locator('#people-form-error');
        await expect(errorDiv).toBeVisible({ timeout: 3000 });
        const errorText = await errorDiv.textContent();
        expect(errorText).toContain('Selecciona Empresa propia');
    });
});
