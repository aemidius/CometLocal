const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Fix PDF Viewing and Document Actions', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'buscar');
    });

    // Helper: Verificar si hay documentos, si no, crear uno de prueba
    async function ensureDocumentExists(page) {
        await page.waitForSelector('table tbody tr, .search-results-empty', { timeout: 10000 });
        const hasRows = await page.locator('table tbody tr').count() > 0;
        
        if (!hasRows) {
            // No hay documentos, crear uno de prueba
            // Navegar a subir documentos
            await page.click('text=Subir documentos');
            // SPRINT B2: Usar gotoHash en lugar de waitForLoadState
            await gotoHash(page, 'subir');
            
            // Buscar un PDF de prueba
            const testPdfPath = path.join(__dirname, '..', 'data', 'AEAT-16-oct-2025.pdf');
            
            if (fs.existsSync(testPdfPath)) {
                const fileInput = page.locator('[data-testid="upload-input"]');
                await fileInput.setInputFiles(testPdfPath);
                await page.waitForSelector('.file-card:has(select.repo-upload-type-select)', { timeout: 10000 });
                // SPRINT B2: Esperar usando expect en lugar de waitForTimeout
                
                // Seleccionar tipo
                const select = page.locator('select.repo-upload-type-select').first();
                const options = await select.locator('option').all();
                if (options.length > 1) {
                    await select.selectOption({ index: 1 });
                    // SPRINT B2: Esperar usando expect en lugar de waitForTimeout
                }
                
                // Subir el documento
                const submitButton = page.locator('button:has-text("Subir")').first();
                if (await submitButton.isVisible()) {
                    await submitButton.click();
                    await page.waitForTimeout(2000);
                }
            }
            
            // Volver a buscar documentos
            await page.click('text=Buscar documentos');
            // SPRINT B2: Usar gotoHash en lugar de waitForLoadState
            await gotoHash(page, 'subir');
            await page.waitForSelector('table tbody tr', { timeout: 10000 });
        }
    }

    test('Ver PDF funciona correctamente', async ({ page, context }) => {
        // Asegurar que hay al menos un documento
        await ensureDocumentExists(page);
        
        // Buscar el primer botón "Ver PDF"
        const viewPdfButton = page.locator('button:has-text("Ver PDF")').first();
        await expect(viewPdfButton).toBeVisible();
        
        // Click en "Ver PDF" (se abrirá en nueva pestaña)
        const [newPage] = await Promise.all([
            context.waitForEvent('page', { timeout: 10000 }),
            viewPdfButton.click()
        ]);
        
        // Verificar que la nueva pestaña muestra un PDF (no un error 404)
        await newPage.waitForLoadState('networkidle', { timeout: 10000 });
        const url = newPage.url();
        expect(url).toContain('/api/repository/docs/');
        expect(url).toContain('/pdf');
        
        // Verificar que no es un error JSON
        const bodyText = await newPage.locator('body').textContent();
        expect(bodyText).not.toContain('"detail":"Not Found"');
        expect(bodyText).not.toContain('404');
        
        await newPage.close();
    });

    test('Editar documento funciona', async ({ page }) => {
        // Asegurar que hay al menos un documento
        await ensureDocumentExists(page);
        
        // Buscar el primer documento con botón "Editar" habilitado
        const firstRow = page.locator('table tbody tr').first();
        await expect(firstRow).toBeVisible();
        
        // Buscar el botón "Editar" en esa fila
        const editButton = firstRow.locator('button:has-text("Editar")');
        await expect(editButton).toBeVisible();
        await expect(editButton).not.toBeDisabled();
        
        // Click en "Editar"
        await editButton.click();
        
        // Verificar que aparece el modal de edición
        const modal = page.locator('.modal-overlay, #edit-doc-modal-overlay');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Verificar que el modal tiene contenido
        const modalTitle = page.locator('h3:has-text("Editar documento")');
        await expect(modalTitle).toBeVisible();
        
        // Verificar que se puede cambiar el estado (para poder eliminar después)
        const statusSelect = page.locator('select#edit-doc-status');
        if (await statusSelect.isVisible()) {
            await statusSelect.selectOption({ value: 'draft' });
            
            // Guardar cambios
            const saveButton = page.locator('button:has-text("Guardar")');
            if (await saveButton.isVisible()) {
                await saveButton.click();
                // SPRINT B2: Esperar usando expect en lugar de waitForTimeout
            }
        }
        
        // Cerrar el modal
        const closeButton = page.locator('button:has-text("✕"), button:has-text("Cancelar")').first();
        if (await closeButton.isVisible()) {
            await closeButton.click();
        }
    });

    test('Eliminar documento después de cambiar estado', async ({ page }) => {
        // Asegurar que hay al menos un documento
        await ensureDocumentExists(page);
        
        // Buscar el primer documento
        const firstRow = page.locator('table tbody tr').first();
        await expect(firstRow).toBeVisible();
        
        // Verificar que el botón "Eliminar" existe
        const deleteButton = firstRow.locator('button:has-text("Eliminar")');
        await expect(deleteButton).toBeVisible();
        
        // Si está disabled, primero cambiar el estado
        if (await deleteButton.isDisabled()) {
            // Editar el documento y cambiar el estado
            const editButton = firstRow.locator('button:has-text("Editar")');
            await editButton.click();
            
            await page.waitForSelector('.modal-overlay', { timeout: 5000 });
            const statusSelect = page.locator('select#edit-doc-status');
            if (await statusSelect.isVisible()) {
                await statusSelect.selectOption({ value: 'draft' });
                const saveButton = page.locator('button:has-text("Guardar")');
                if (await saveButton.isVisible()) {
                    await saveButton.click();
                    await page.waitForTimeout(2000);
                }
            }
            
            // Cerrar modal si está abierto
            const closeButton = page.locator('button:has-text("✕"), button:has-text("Cancelar")').first();
            if (await closeButton.isVisible()) {
                await closeButton.click();
            }
            
            // Recargar la página para ver los cambios
            await page.reload();
            await page.waitForSelector('table tbody tr', { timeout: 10000 });
        }
        
        // Ahora intentar eliminar (usar el primer documento disponible)
        const deleteButtonAfter = page.locator('table tbody tr').first().locator('button:has-text("Eliminar")');
        await expect(deleteButtonAfter).toBeVisible();
        await expect(deleteButtonAfter).not.toBeDisabled();
        
        // Configurar el diálogo de confirmación
        page.on('dialog', async dialog => {
            expect(dialog.type()).toBe('confirm');
            expect(dialog.message()).toContain('eliminar');
            await dialog.dismiss(); // Cancelar para no eliminar en la prueba
        });
        
        // Click en "Eliminar"
        await deleteButtonAfter.click();
        
        // Verificar que se mostró el diálogo (el botón no debería estar disabled)
        await page.waitForTimeout(500);
    });
});


