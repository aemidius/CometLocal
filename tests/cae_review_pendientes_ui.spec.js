const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.2d: Revisar Pendientes CAE (UI)', () => {
    test('Abre modal, selecciona filtros y ejecuta revisión READ-ONLY', async ({ page }) => {
        // Crear directorio de evidencias
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'cae_review_ui');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }

        // 1) Abrir Dashboard (ruta /home según app.py)
        await page.goto('http://127.0.0.1:8000/home');
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000); // Dar tiempo para que cargue JavaScript

        // 2) Abrir modal "Revisar Pendientes CAE (Avanzado)"
        // Buscar el botón con múltiples estrategias
        let openModalBtn = page.locator('button:has-text("📋 Revisar Pendientes CAE")');
        let count = await openModalBtn.count();
        if (count === 0) {
            // Intentar sin emoji
            openModalBtn = page.locator('button:has-text("Revisar Pendientes CAE")');
            count = await openModalBtn.count();
        }
        if (count === 0) {
            // Intentar buscar por onclick
            openModalBtn = page.locator('button[onclick*="openPendingReviewModal"]');
            count = await openModalBtn.count();
        }
        expect(count).toBeGreaterThan(0);
        await openModalBtn.first().click();
        await page.waitForTimeout(1000);
        
        // Verificar que el modal está abierto
        const modal = page.locator('[data-testid="cae-review-modal"]');
        await expect(modal).toBeVisible();
        
        // Screenshot del modal abierto
        await page.screenshot({ path: path.join(evidenceDir, '00_modal_opened.png'), fullPage: true });

        // 3) Seleccionar plataforma "egestiona"
        // Usar JavaScript para activar el dropdown y seleccionar
        await page.evaluate(() => {
            const input = document.getElementById('filter-platform');
            if (input) {
                input.value = 'egestiona';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                // Activar dropdown
                const dropdown = document.getElementById('filter-platform-dropdown');
                if (dropdown) {
                    dropdown.style.display = 'block';
                    // Buscar opción egestiona y hacer click
                    const options = dropdown.querySelectorAll('div[onclick]');
                    for (const opt of options) {
                        if (opt.textContent && opt.textContent.toLowerCase().includes('egestiona')) {
                            opt.click();
                            break;
                        }
                    }
                }
            }
        });
        await page.waitForTimeout(1000);

        // 4) Seleccionar ámbito "Trabajador"
        const scopeWorker = page.locator('[data-testid="cae-review-scope-worker"]');
        await scopeWorker.click();
        await page.waitForTimeout(500);

        // 5) Seleccionar trabajador (buscar "Emilio Roldán" o el primero disponible)
        // Usar JavaScript para seleccionar trabajador
        await page.evaluate(() => {
            const input = document.getElementById('filter-worker');
            if (input) {
                input.value = 'Emilio';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                // Activar dropdown
                const dropdown = document.getElementById('filter-worker-dropdown');
                if (dropdown) {
                    dropdown.style.display = 'block';
                    // Buscar opción con Emilio y hacer click
                    const options = dropdown.querySelectorAll('div[onclick]');
                    for (const opt of options) {
                        if (opt.textContent && opt.textContent.toLowerCase().includes('emilio')) {
                            opt.click();
                            break;
                        }
                    }
                }
            }
        });
        await page.waitForTimeout(1000);

        // Screenshot del modal con filtros seleccionados
        await page.screenshot({ path: path.join(evidenceDir, '01_modal_filled.png'), fullPage: true });

        // 6) Click botón "Revisar ahora (READ-ONLY)" usando data-testid
        const runBtn = page.locator('[data-testid="cae-review-run-btn"]');
        await expect(runBtn).toBeVisible();
        
        // Hacer click y esperar a que cambie el texto o aparezca resultado
        await runBtn.click();
        
        // Esperar a que el botón cambie o aparezca resultado (hasta 120 segundos)
        await page.waitForTimeout(3000); // Dar tiempo inicial para que empiece
        
        // Esperar a que aparezca summary o items (o error)
        const summary = page.locator('[data-testid="cae-review-summary"]');
        const items = page.locator('[data-testid="cae-review-items"]');
        const error = page.locator('[data-testid="cae-review-error"]');
        
        // Esperar hasta 120 segundos para que termine la ejecución
        let found = false;
        for (let i = 0; i < 60; i++) {
            const summaryVisible = await summary.isVisible().catch(() => false);
            const itemsVisible = await items.isVisible().catch(() => false);
            const errorVisible = await error.isVisible().catch(() => false);
            const btnText = await runBtn.textContent().catch(() => '');
            
            // Si el botón ya no dice "Ejecutando", probablemente terminó
            if (!btnText.includes('Ejecutando') && (summaryVisible || itemsVisible || errorVisible)) {
                found = true;
                break;
            }
            
            await page.waitForTimeout(2000);
        }

        // Screenshot del resultado
        await page.screenshot({ path: path.join(evidenceDir, '02_report.png'), fullPage: true });

        // 8) Asserts
        // El modal sigue abierto
        await expect(modal).toBeVisible();

        // Verificar que summary o error es visible
        const summaryVisible = await summary.isVisible().catch(() => false);
        const itemsVisible = await items.isVisible().catch(() => false);
        const errorVisible = await error.isVisible().catch(() => false);
        
        expect(summaryVisible || itemsVisible || errorVisible).toBeTruthy();

        if (errorVisible) {
            // Si hay error, verificar que tiene mensaje
            const errorText = await error.textContent();
            expect(errorText).toBeTruthy();
            expect(errorText.length).toBeGreaterThan(0);
            
            // Screenshot de error
            await page.screenshot({ path: path.join(evidenceDir, '99_error.png'), fullPage: true });
        } else {
            // Si no hay error, verificar que summary o items están presentes
            if (summaryVisible) {
                const summaryText = await summary.textContent();
                expect(summaryText).toBeTruthy();
                console.log(`[CAE_REVIEW] Summary: ${summaryText}`);
            }
            
            if (itemsVisible) {
                const itemsText = await items.textContent();
                expect(itemsText).toBeTruthy();
                // Puede ser "0 pendientes encontrados" o una tabla
                console.log(`[CAE_REVIEW] Items container: ${itemsText.substring(0, 200)}`);
            }
        }

        console.log(`[CAE_REVIEW] Evidence guardado en: ${evidenceDir}`);
    });
});
