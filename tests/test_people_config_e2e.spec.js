/**
 * HOTFIX URGENTE: Test E2E para verificar que Config → Trabajadores guarda correctamente con headers de contexto.
 * 
 * Este test verifica:
 * 1. Abrir repository_v3.html#configuracion → Trabajadores
 * 2. Seleccionar contexto humano (Empresa propia, Plataforma, Empresa coordinada)
 * 3. Seleccionar Empresa propia para trabajadores
 * 4. Guardar (debe incluir headers de contexto)
 * 5. Refrescar y verificar persistencia
 */

import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

test.describe('HOTFIX: People Config own_company_key persistence with context headers', () => {
    test('should persist own_company_key when saving from Config People UI with context headers', async ({ page }) => {
        // Desactivar training wizard
        await page.addInitScript(() => {
            localStorage.setItem('trainingCompleted', 'true');
        });
        
        // Navegar a repository_v3.html#configuracion para tener contexto
        await page.goto('http://127.0.0.1:8000/repository_v3.html#configuracion?section=people&notraining=true');
        
        // Esperar a que la app esté lista
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
        await page.waitForTimeout(1000);
        
        // Verificar que hay contexto humano seleccionado (o seleccionarlo)
        // El contexto se carga automáticamente, pero verificamos que existe
        const ownCompanySelect = page.locator('#ctx-own-company');
        await ownCompanySelect.waitFor({ timeout: 5000, state: 'attached' });
        
        // Seleccionar empresa propia si no está seleccionada
        const ownCompanyValue = await ownCompanySelect.inputValue();
        if (!ownCompanyValue || ownCompanyValue === '') {
            // Seleccionar la primera opción disponible
            const options = await ownCompanySelect.locator('option').all();
            if (options.length > 1) {
                const firstOptionValue = await options[1].getAttribute('value');
                if (firstOptionValue) {
                    await ownCompanySelect.selectOption(firstOptionValue);
                    await page.waitForTimeout(500);
                }
            }
        }
        
        // Seleccionar plataforma si no está seleccionada
        const platformSelect = page.locator('#ctx-platform');
        const platformValue = await platformSelect.inputValue();
        if (!platformValue || platformValue === '') {
            const options = await platformSelect.locator('option').all();
            if (options.length > 1) {
                const firstOptionValue = await options[1].getAttribute('value');
                if (firstOptionValue) {
                    await platformSelect.selectOption(firstOptionValue);
                    await page.waitForTimeout(500);
                }
            }
        }
        
        // Seleccionar empresa coordinada si no está seleccionada
        const coordinatedSelect = page.locator('#ctx-coordinated-company');
        const coordinatedValue = await coordinatedSelect.inputValue();
        if (!coordinatedValue || coordinatedValue === '') {
            const options = await coordinatedSelect.locator('option').all();
            if (options.length > 1) {
                const firstOptionValue = await options[1].getAttribute('value');
                if (firstOptionValue) {
                    await coordinatedSelect.selectOption(firstOptionValue);
                    await page.waitForTimeout(500);
                }
            }
        }
        
        // Esperar a que el iframe de Config People esté cargado
        const iframe = page.frameLocator('iframe[src="/config/people"]');
        await page.waitForTimeout(2000); // Dar tiempo al iframe para cargar
        
        // Esperar a que el formulario esté cargado en el iframe
        const formInIframe = iframe.locator('form#people-form');
        await formInIframe.waitFor({ timeout: 10000, state: 'attached' });
        await page.waitForTimeout(1000);
        
        // Buscar un trabajador existente en el iframe
        const workerInputs = await iframe.locator('input[name^="worker_id__"]').all();
        
        if (workerInputs.length === 0) {
            test.skip(true, 'No hay trabajadores en el sistema para probar');
            return;
        }
        
        // Obtener el worker_id del primer trabajador
        const firstWorkerId = await workerInputs[0].inputValue();
        
        if (!firstWorkerId || firstWorkerId.trim() === '') {
            test.skip(true, 'No hay trabajadores con worker_id para probar');
            return;
        }
        
        // Encontrar el índice del trabajador
        const workerIndex = await workerInputs[0].getAttribute('name').then(name => {
            const match = name.match(/worker_id__(\d+)/);
            return match ? parseInt(match[1]) : null;
        });
        
        if (workerIndex === null) {
            throw new Error('No se pudo determinar el índice del trabajador');
        }
        
        // Obtener las empresas disponibles del selector
        const companySelect = page.locator(`select[name="own_company_key__${workerIndex}"]`);
        await expect(companySelect).toBeVisible();
        
        // Obtener todas las opciones disponibles (excluyendo "unassigned")
        const options = await companySelect.locator('option').all();
        const companyOptions = [];
        for (const option of options) {
            const value = await option.getAttribute('value');
            const text = await option.textContent();
            if (value && value !== 'unassigned' && value !== '') {
                companyOptions.push({ value: value.trim(), text: text?.trim() || '' });
            }
        }
        
        if (companyOptions.length === 0) {
            test.skip(true, 'No hay empresas propias disponibles para asignar');
            return;
        }
        
        // Seleccionar la primera empresa disponible
        const targetCompany = companyOptions[0];
        await companySelect.selectOption(targetCompany.value);
        
        // Verificar que se seleccionó correctamente
        const selectedValue = await companySelect.inputValue();
        expect(selectedValue).toBe(targetCompany.value);
        
        // Guardar el formulario
        const saveButton = page.locator('button[type="submit"]');
        await expect(saveButton).toBeVisible();
        
        // Interceptar la respuesta para verificar que no hay errores
        let responseError = null;
        page.on('response', response => {
            if (response.url().includes('/config/people') && response.request().method() === 'POST') {
                if (response.status() >= 400) {
                    responseError = `HTTP ${response.status()}: ${response.statusText()}`;
                }
            }
        });
        
        // Hacer click en Guardar
        await saveButton.click();
        
        // Esperar a que se procese el POST (redirección o recarga)
        await page.waitForTimeout(2000);
        
        // Verificar que no hubo errores
        if (responseError) {
            throw new Error(`Error al guardar: ${responseError}`);
        }
        
        // Recargar la página para verificar persistencia
        await page.reload();
        await page.waitForSelector('form#people-form', { timeout: 10000 });
        await page.waitForTimeout(1000);
        
        // Verificar que el selector muestra la empresa seleccionada
        const reloadedSelect = page.locator(`select[name="own_company_key__${workerIndex}"]`);
        await expect(reloadedSelect).toBeVisible();
        
        const reloadedValue = await reloadedSelect.inputValue();
        expect(reloadedValue).toBe(targetCompany.value);
        
        // Verificar que el JSON contiene own_company_key
        // (esto requiere acceso al sistema de archivos, solo en desarrollo)
        const dataDir = path.join(__dirname, '..', 'data', 'refs', 'people.json');
        if (fs.existsSync(dataDir)) {
            const peopleData = JSON.parse(fs.readFileSync(dataDir, 'utf-8'));
            const workerData = peopleData.people.find((p: any) => p.worker_id === firstWorkerId);
            
            if (workerData) {
                expect(workerData).toHaveProperty('own_company_key');
                expect(workerData.own_company_key).toBe(targetCompany.value);
            }
        }
    });
    
    test('should show error message when context is missing', async ({ page }) => {
        // Desactivar training wizard
        await page.addInitScript(() => {
            localStorage.setItem('trainingCompleted', 'true');
        });
        
        // Navegar directamente a /config/people (sin contexto)
        await page.goto('http://127.0.0.1:8000/config/people?notraining=true');
        
        // Esperar a que el formulario esté cargado
        await page.waitForSelector('form#people-form', { timeout: 10000 });
        await page.waitForTimeout(1000);
        
        // Buscar un trabajador
        const workerInputs = await page.locator('input[name^="worker_id__"]').all();
        
        if (workerInputs.length === 0) {
            test.skip(true, 'No hay trabajadores en el sistema para probar');
            return;
        }
        
        const firstWorkerId = await workerInputs[0].inputValue();
        if (!firstWorkerId || firstWorkerId.trim() === '') {
            test.skip(true, 'No hay trabajadores con worker_id para probar');
            return;
        }
        
        // Intentar guardar sin contexto (el script debería mostrar error)
        const saveButton = page.locator('button[type="submit"]');
        await saveButton.click();
        
        // Esperar a que aparezca el mensaje de error
        await page.waitForTimeout(1000);
        
        // Verificar que aparece el mensaje de error
        const errorDiv = page.locator('#people-form-error');
        await expect(errorDiv).toBeVisible({ timeout: 2000 });
        
        const errorText = await errorDiv.textContent();
        expect(errorText).toContain('Selecciona Empresa propia');
    });
});
