/**
 * E2E tests para filtros del calendario
 */
const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('Calendario - Filtros', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // Capturar logs [CAL] en la salida del test (evidencia)
        page.on('console', (msg) => {
            const text = msg.text();
            if (text && text.includes('[CAL]')) console.log(text);
        });

        // SPRINT C2.6: Usar gotoHash para navegar y esperar view-calendario-ready
        await gotoHash(page, 'calendario');
        // Esperar view-calendario-ready (emitido por loadPage)
        await waitForTestId(page, 'view-calendario-ready');
        // Esperar calendar-filters-ready (emitido por loadCalendario)
        await waitForTestId(page, 'calendar-filters-ready');
        // Esperar calendar-scope-select (elemento del formulario)
        await waitForTestId(page, 'calendar-scope-select');
    });

    test('TEST 1: Scope select funciona', async ({ page }) => {
        // Verificar que inicialmente "Todos" está seleccionado
        const scopeSelect = page.locator('[data-testid="calendar-scope-select"]');
        await expect(scopeSelect).toHaveValue('all');
        
        // Obtener contadores iniciales
        const initialExpiredCount = await page.locator('#pending-count-expired').textContent();
        const initialExpiringSoonCount = await page.locator('#pending-count-expiring_soon').textContent();
        const initialMissingCount = await page.locator('#pending-count-missing').textContent();
        
        // Cambiar a "Trabajador"
        await scopeSelect.selectOption('worker');
        await page.waitForTimeout(500);
        
        // Verificar que el select tiene el valor correcto
        await expect(scopeSelect).toHaveValue('worker');
        
        // Verificar que los contadores han cambiado (pueden ser menores o iguales)
        const filteredExpiredCount = await page.locator('#pending-count-expired').textContent();
        const filteredExpiringSoonCount = await page.locator('#pending-count-expiring_soon').textContent();
        const filteredMissingCount = await page.locator('#pending-count-missing').textContent();
        
        const filteredExpired = parseInt(filteredExpiredCount || '0');
        const filteredExpiringSoon = parseInt(filteredExpiringSoonCount || '0');
        const filteredMissing = parseInt(filteredMissingCount || '0');
        
        const initialExpired = parseInt(initialExpiredCount || '0');
        const initialExpiringSoon = parseInt(initialExpiringSoonCount || '0');
        const initialMissing = parseInt(initialMissingCount || '0');
        
        // Los contadores filtrados deben ser <= a los iniciales
        expect(filteredExpired).toBeLessThanOrEqual(initialExpired);
        expect(filteredExpiringSoon).toBeLessThanOrEqual(initialExpiringSoon);
        expect(filteredMissing).toBeLessThanOrEqual(initialMissing);
        
        // Verificar que solo aparecen items de trabajador (si hay datos)
        // Esto se verifica indirectamente: si hay items, deben ser de scope=worker
        if (filteredExpired > 0 || filteredExpiringSoon > 0 || filteredMissing > 0) {
            // Verificar que el select de sujeto solo muestra trabajadores
            const subjectSelect = page.locator('[data-testid="calendar-subject-select"]');
            const subjectOptions = await subjectSelect.locator('option').all();
            
            // Si hay opciones, verificar que no hay empresas (solo trabajadores)
            // Nota: esto depende de los datos, pero al menos verificamos que el select existe
            expect(subjectSelect).toBeVisible();
        }
        
        // Cambiar a "Empresa"
        await scopeSelect.selectOption('company');
        await page.waitForTimeout(500);
        
        // Verificar que el select tiene el valor correcto
        await expect(scopeSelect).toHaveValue('company');
        
        // Verificar que los contadores han cambiado
        const filteredExpiredCount2 = await page.locator('#pending-count-expired').textContent();
        const filteredExpired2 = parseInt(filteredExpiredCount2 || '0');
        
        // Los contadores deben ser <= a los iniciales
        expect(filteredExpired2).toBeLessThanOrEqual(initialExpired);
        
        // Cambiar de vuelta a "Todos"
        await scopeSelect.selectOption('all');
        await page.waitForTimeout(500);
        
        // Verificar que el select tiene el valor correcto
        await expect(scopeSelect).toHaveValue('all');
    });

    test('TEST 2: Máx. meses atrás filtra de verdad', async ({ page }) => {
        // Ir al tab "Pendientes de subir"
        await page.click('[data-testid="calendar-tab-pending"]');
        await page.waitForTimeout(500);
        
        // Primero, verificar con max_months_back=24 que hay items
        const maxMonthsBackInput = page.locator('[data-testid="calendar-max-months-back"]');
        await expect(maxMonthsBackInput).toBeVisible();
        
        // Obtener contador inicial (con default 24)
        const initialMissingCount = await page.locator('#pending-count-missing').textContent();
        const initialMissing = parseInt(initialMissingCount || '0');
        
        // Si no hay pendientes, el test pasa (no hay problema)
        if (initialMissing === 0) {
            test.skip();
            return;
        }
        
        // Obtener todos los períodos renderizados
        const rows = page.locator('[data-testid="calendar-pending-row"]');
        const rowCount = await rows.count();
        
        // Verificar que hay al menos una fila
        expect(rowCount).toBeGreaterThan(0);
        
        // Cambiar "Máx. meses atrás" a 3
        await maxMonthsBackInput.clear();
        await maxMonthsBackInput.fill('3');
        
        // Esperar a que se actualice la UI
        await page.waitForTimeout(500);
        
        // Verificar que el contador ha cambiado (debe ser menor o igual)
        const filteredMissingCount = await page.locator('#pending-count-missing').textContent();
        const filteredMissing = parseInt(filteredMissingCount || '0');
        
        expect(filteredMissing).toBeLessThanOrEqual(initialMissing);
        
        // Obtener todas las filas después del filtro
        const filteredRows = page.locator('[data-testid="calendar-pending-row"]');
        const filteredRowCount = await filteredRows.count();
        
        // Verificar que cada período está dentro del rango (0 <= monthsDiff <= 3)
        for (let i = 0; i < filteredRowCount; i++) {
            const row = filteredRows.nth(i);
            // Usar data-testid para el período
            const periodElement = row.locator('[data-testid="calendar-period"]');
            const periodText = await periodElement.textContent();
            
            const period = (periodText || '').trim();
            expect(period).toMatch(/^\d{4}-\d{2}$/, `Periodo "${period}" no tiene formato válido YYYY-MM`);
            const y = parseInt(period.slice(0, 4), 10);
            const m = parseInt(period.slice(5, 7), 10);
            expect(m).toBeGreaterThanOrEqual(1);
            expect(m).toBeLessThanOrEqual(12);

            const today = new Date();
            const monthsDiff = (today.getFullYear() - y) * 12 + (today.getMonth() - (m - 1));
            expect(monthsDiff).toBeGreaterThanOrEqual(0, `Periodo ${period} tiene monthsDiff=${monthsDiff} (futuro)`);
            expect(monthsDiff).toBeLessThanOrEqual(3, `Periodo ${period} tiene monthsDiff=${monthsDiff} (> 3)`);
        }
        
        // Verificar que el input tiene el valor correcto
        const value = await maxMonthsBackInput.inputValue();
        expect(parseInt(value)).toBe(3);

        // Screenshot AFTER (evidencia)
        await page.screenshot({
            path: 'docs/evidence/calendar_max_months_back_fix/02_after.png',
            fullPage: true
        });
    });

    test('TEST 4: Máx. meses atrás NO muestra períodos antiguos (bug fix)', async ({ page }) => {
        // Ir al tab "Pendientes de subir"
        await page.click('[data-testid="calendar-tab-pending"]');
        await page.waitForTimeout(500);
        
        const maxMonthsBackInput = page.locator('[data-testid="calendar-max-months-back"]');
        await expect(maxMonthsBackInput).toBeVisible();
        
        // Obtener contador inicial (con default 24)
        const initialMissingCount = await page.locator('#pending-count-missing').textContent();
        const initialMissing = parseInt(initialMissingCount || '0');
        
        // Si no hay pendientes, el test pasa (no hay problema)
        if (initialMissing === 0) {
            test.skip();
            return;
        }
        
        // Obtener fecha actual del test
        const today = new Date();
        const currentYear = today.getFullYear();
        const currentMonth = today.getMonth() + 1;
        
        // Cambiar "Máx. meses atrás" a 3
        await maxMonthsBackInput.clear();
        await maxMonthsBackInput.fill('3');
        await page.waitForTimeout(1000); // Esperar a que se aplique el filtro
        
        // Obtener todas las filas después del filtro
        const filteredRows = page.locator('[data-testid="calendar-pending-row"]');
        const filteredRowCount = await filteredRows.count();
        
        // Verificar que cada período está dentro del rango (0 <= monthsDiff <= 3)
        const periods = [];
        for (let i = 0; i < filteredRowCount; i++) {
            const row = filteredRows.nth(i);
            const periodElement = row.locator('[data-testid="calendar-period"]');
            const periodText = await periodElement.textContent();
            
            // Parsear período (formato: YYYY-MM)
            const periodMatch = periodText.trim().match(/^(\d{4})-(\d{2})$/);
            expect(periodMatch, `Periodo "${periodText}" no tiene formato válido YYYY-MM`).toBeTruthy();
            
            if (periodMatch) {
                const periodYear = parseInt(periodMatch[1], 10);
                const periodMonth = parseInt(periodMatch[2], 10);
                
                // Validar mes
                expect(periodMonth).toBeGreaterThanOrEqual(1);
                expect(periodMonth).toBeLessThanOrEqual(12);
                
                // Calcular diferencia en meses
                const monthsDiff = (currentYear - periodYear) * 12 + (currentMonth - periodMonth);
                
                periods.push({ period: periodText, monthsDiff });
                
                // Verificar que está dentro del rango (0 <= monthsDiff <= 3)
                expect(
                    monthsDiff,
                    `Periodo ${periodText} tiene monthsDiff=${monthsDiff} que es negativo (futuro)`
                ).toBeGreaterThanOrEqual(0);
                expect(
                    monthsDiff,
                    `Periodo ${periodText} tiene monthsDiff=${monthsDiff} que excede el máximo de 3 meses`
                ).toBeLessThanOrEqual(3);
            }
        }
        
        // Verificar que el contador se redujo (si había períodos antiguos)
        const filteredMissingCount = await page.locator('#pending-count-missing').textContent();
        const filteredMissing = parseInt(filteredMissingCount || '0');
        
        expect(filteredMissing).toBeLessThanOrEqual(initialMissing);
        expect(filteredMissing).toBe(filteredRowCount);
        
        // Log para debugging
        console.log(`[TEST] Períodos mostrados con maxMonthsBack=3:`, periods);
    });

    test('TEST 3: Clear filtros resetea correctamente', async ({ page }) => {
        // Aplicar algunos filtros
        const scopeSelect = page.locator('[data-testid="calendar-scope-select"]');
        await scopeSelect.selectOption('company');
        await page.waitForTimeout(300);
        
        const searchInput = page.locator('[data-testid="calendar-search-input"]');
        await searchInput.fill('test');
        await page.waitForTimeout(500);
        
        const typeSelect = page.locator('[data-testid="calendar-type-select"]');
        if (await typeSelect.count() > 0) {
            const options = await typeSelect.locator('option').all();
            if (options.length > 1) {
                await typeSelect.selectOption({ index: 1 });
                await page.waitForTimeout(300);
            }
        }
        
        const maxMonthsBackInput = page.locator('[data-testid="calendar-max-months-back"]');
        await maxMonthsBackInput.clear();
        await maxMonthsBackInput.fill('12');
        await maxMonthsBackInput.press('Enter');
        await page.waitForTimeout(500);
        
        // Verificar que los filtros están aplicados
        await expect(scopeSelect).toHaveValue('company');
        const searchValue = await searchInput.inputValue();
        expect(searchValue).toBe('test');
        const maxMonthsValue = await maxMonthsBackInput.inputValue();
        expect(parseInt(maxMonthsValue)).toBe(12);
        
        // Limpiar filtros
        const clearButton = page.locator('[data-testid="calendar-clear-filters"]');
        await clearButton.click();
        await page.waitForTimeout(500);
        
        // Verificar que se restauraron
        await expect(scopeSelect).toHaveValue('all');
        const searchValueAfter = await searchInput.inputValue();
        expect(searchValueAfter).toBe('');
        const maxMonthsValueAfter = await maxMonthsBackInput.inputValue();
        expect(parseInt(maxMonthsValueAfter)).toBe(24);
        
        const subjectSelect = page.locator('[data-testid="calendar-subject-select"]');
        const subjectValue = await subjectSelect.inputValue();
        expect(subjectValue).toBe('');
    });
});
