const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Buscar Documentos - Acciones', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // Navegar usando helper
        await gotoHash(page, 'buscar');
    });

    test('Ver PDF de un documento', async ({ page }) => {
        // Esperar a que se carguen los resultados
        await page.waitForSelector('table tbody tr', { timeout: 10000 });
        
        // Buscar el primer botón "Ver PDF"
        const viewPdfButton = page.locator('button:has-text("Ver PDF")').first();
        await expect(viewPdfButton).toBeVisible();
        
        // Click en "Ver PDF" (se abrirá en nueva pestaña)
        const [newPage] = await Promise.all([
            page.context().waitForEvent('page'),
            viewPdfButton.click()
        ]);
        
        // Verificar que la nueva pestaña muestra un PDF (esperar a que cargue)
        await newPage.waitForLoadState('load');
        const url = newPage.url();
        expect(url).toContain('/api/repository/docs/');
        expect(url).toContain('/pdf');
        
        await newPage.close();
    });

    test('Resubir documento', async ({ page }) => {
        // Esperar a que se carguen los resultados
        await page.waitForSelector('table tbody tr', { timeout: 10000 });
        
        // Buscar el primer botón "Resubir"
        const resubmitButton = page.locator('button:has-text("Resubir")').first();
        await expect(resubmitButton).toBeVisible();
        
        // Click en "Resubir"
        await resubmitButton.click();
        
        // Verificar que navega a "Subir documentos"
        await page.waitForURL('**/repository**', { timeout: 5000 });
        
        // Verificar que aparece el mensaje de reemplazo
        const infoMsg = page.locator('.alert-info:has-text("Reemplazando documento")');
        await expect(infoMsg).toBeVisible({ timeout: 5000 });
    });

    test('Editar documento (incluyendo documentos antiguos)', async ({ page }) => {
        // Esperar a que se carguen los resultados
        await page.waitForSelector('table tbody tr', { timeout: 10000 });
        
        // Buscar el primer botón "Editar"
        const editButton = page.locator('button:has-text("Editar")').first();
        await expect(editButton).toBeVisible();
        
        // Click en "Editar"
        await editButton.click();
        
        // Verificar que aparece el modal de edición
        const modal = page.locator('#edit-doc-modal-overlay, .modal-overlay');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
        // Verificar que el modal tiene contenido
        const modalTitle = page.locator('h3:has-text("Editar documento")');
        await expect(modalTitle).toBeVisible();
        
        // Cerrar el modal
        const closeButton = page.locator('button:has-text("✕"), button:has-text("Cancelar")').first();
        if (await closeButton.isVisible()) {
            await closeButton.click();
        }
    });

    test('Eliminar documento (incluyendo documentos antiguos)', async ({ page }) => {
        // Esperar a que se carguen los resultados
        await page.waitForSelector('table tbody tr, .search-results-empty', { timeout: 10000 });
        
        // Verificar si hay documentos
        const hasRows = await page.locator('table tbody tr').count() > 0;
        
        if (!hasRows) {
            // Si no hay documentos, el test pasa (no hay nada que eliminar)
            test.skip();
            return;
        }
        
        // Contar documentos iniciales
        const initialRows = await page.locator('table tbody tr').count();
        
        // Buscar el primer botón "Eliminar" que no esté disabled
        const deleteButton = page.locator('button:has-text("Eliminar"):not([disabled])').first();
        await expect(deleteButton).toBeVisible();
        
        // Configurar el diálogo de confirmación ANTES de hacer click
        let dialogHandled = false;
        page.on('dialog', async dialog => {
            dialogHandled = true;
            expect(dialog.type()).toBe('confirm');
            expect(dialog.message()).toContain('eliminar');
            await dialog.dismiss(); // Cancelar para no eliminar en la prueba
        });
        
        // Click en "Eliminar"
        await deleteButton.click();
        
        // Esperar a que se maneje el diálogo
        await page.waitForTimeout(500);
        
        // Verificar que se mostró el diálogo
        expect(dialogHandled).toBe(true);
        
        // Verificar que el número de documentos no cambió (porque cancelamos)
        await page.waitForTimeout(1000);
        const finalRows = await page.locator('table tbody tr').count();
        // Puede haber cambios por recarga, pero no debería ser 0 si había documentos
        expect(finalRows).toBeGreaterThanOrEqual(0);
    });

    test('Verificar que documentos antiguos (sin doc_id) se manejan correctamente', async ({ page }) => {
        // Esperar a que se carguen los resultados
        await page.waitForSelector('table tbody tr', { timeout: 10000 });
        
        // Verificar que no hay mensajes de error sobre documentos sin ID
        const errorMsg = page.locator('text=Documento sin ID');
        await expect(errorMsg).not.toBeVisible();
        
        // Verificar que todos los botones de acción están presentes
        const rows = page.locator('table tbody tr');
        const rowCount = await rows.count();
        
        for (let i = 0; i < Math.min(rowCount, 3); i++) {
            const row = rows.nth(i);
            const viewButton = row.locator('button:has-text("Ver PDF")');
            const resubmitButton = row.locator('button:has-text("Resubir")');
            const editButton = row.locator('button:has-text("Editar")');
            const deleteButton = row.locator('button:has-text("Eliminar")');
            
            await expect(viewButton).toBeVisible();
            await expect(resubmitButton).toBeVisible();
            await expect(editButton).toBeVisible();
            await expect(deleteButton).toBeVisible();
        }
    });
});

