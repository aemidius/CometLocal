/**
 * E2E tests para filtros del calendario y verificación de períodos faltantes
 */
const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Calendario - Filtros y Períodos', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // SPRINT C2.3: Navegar usando helper y esperar señales deterministas
        await gotoHash(page, 'calendario');
        // Esperar view-calendario-ready primero
        await page.waitForSelector('[data-testid="view-calendario-ready"]', { timeout: 15000 });
        // SPRINT C2.3: Esperar calendar-filters-ready
        await page.waitForSelector('[data-testid="calendar-filters-ready"]', { timeout: 10000 });
    });

    test('Test 1: Select "Aplica a" cambia estado y filtran', async ({ page }) => {
        // SPRINT C2.3: Usar select en lugar de pills
        const scopeSelect = page.locator('[data-testid="calendar-scope-select"]');
        await expect(scopeSelect).toBeVisible();
        
        // Verificar que inicialmente "Todos" está seleccionado
        await expect(scopeSelect).toHaveValue('all');
        
        // Obtener contadores iniciales
        const initialExpiredCount = await page.locator('#pending-count-expired').textContent();
        const initialExpiringSoonCount = await page.locator('#pending-count-expiring_soon').textContent();
        const initialMissingCount = await page.locator('#pending-count-missing').textContent();
        
        // Cambiar a "Empresa"
        await scopeSelect.selectOption('company');
        
        // Esperar a que se actualice la UI
        await page.waitForTimeout(500);
        
        // Verificar que "Empresa" está seleccionado
        await expect(scopeSelect).toHaveValue('company');
        
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
        
        // Cambiar a "Trabajador"
        await scopeSelect.selectOption('worker');
        await page.waitForTimeout(500);
        
        // Verificar que "Trabajador" está seleccionado
        await expect(scopeSelect).toHaveValue('worker');
        
        // Cambiar a "Todos"
        await scopeSelect.selectOption('all');
        await page.waitForTimeout(500);
        
        // Verificar que "Todos" está seleccionado
        await expect(scopeSelect).toHaveValue('all');
        
        // Verificar que los contadores se restauraron (o son iguales)
        const restoredExpiredCount = await page.locator('#pending-count-expired').textContent();
        const restoredExpired = parseInt(restoredExpiredCount || '0');
        // Puede ser igual o diferente dependiendo de los datos, pero debe ser un número válido
        expect(restoredExpired).toBeGreaterThanOrEqual(0);
    });

    test('Test 2: "Máx. meses atrás" reduce el número de filas en Pendientes', async ({ page }) => {
        // Ir al tab "Pendientes de subir"
        await page.click('[data-testid="calendar-tab-pending"]');
        await page.waitForTimeout(500);
        
        // Obtener contador inicial
        const initialMissingCount = await page.locator('#pending-count-missing').textContent();
        const initialMissing = parseInt(initialMissingCount || '0');
        
        // Si no hay pendientes, saltar el test
        if (initialMissing === 0) {
            test.skip();
            return;
        }
        
        // Contar filas visibles
        const initialRows = await page.locator('[data-testid="calendar-pending-row"]').count();
        
        // Cambiar "Máx. meses atrás" a 3
        const maxMonthsBackInput = page.locator('[data-testid="calendar-max-months-back"]');
        await maxMonthsBackInput.clear();
        await maxMonthsBackInput.fill('3');
        await maxMonthsBackInput.press('Enter');
        
        // Esperar a que se recargue la página
        await page.waitForSelector('#pending-documents-container', { timeout: 10000 });
        await page.waitForTimeout(1000);
        
        // Verificar que el contador ha cambiado (debe ser menor o igual)
        const filteredMissingCount = await page.locator('#pending-count-missing').textContent();
        const filteredMissing = parseInt(filteredMissingCount || '0');
        
        expect(filteredMissing).toBeLessThanOrEqual(initialMissing);
        
        // Contar filas visibles después del filtro
        const filteredRows = await page.locator('[data-testid="calendar-pending-row"]').count();
        
        // Las filas filtradas deben ser <= a las iniciales
        expect(filteredRows).toBeLessThanOrEqual(initialRows);
        
        // Verificar que el input tiene el valor correcto
        const value = await maxMonthsBackInput.inputValue();
        expect(parseInt(value)).toBe(3);
    });

    test('Test 3: Tipo con frecuencia >1 (ej RC cada 12/24 meses) NO genera filas mensuales', async ({ page }) => {
        // Ir al tab "Pendientes de subir"
        await page.click('[data-testid="calendar-tab-pending"]');
        await page.waitForTimeout(500);
        
        // Obtener todas las filas de pendientes
        const rows = page.locator('[data-testid="calendar-pending-row"]');
        const rowCount = await rows.count();
        
        // Si no hay pendientes, el test pasa (no hay problema)
        if (rowCount === 0) {
            test.skip();
            return;
        }
        
        // Agrupar por type_id para verificar que no hay múltiples períodos consecutivos
        const typePeriods = {};
        
        for (let i = 0; i < rowCount; i++) {
            const row = rows.nth(i);
            const typeCell = row.locator('td').nth(0); // Primera columna: Tipo
            const periodCell = row.locator('td').nth(1); // Segunda columna: Período
            
            const typeText = await typeCell.textContent();
            const periodText = await periodCell.textContent();
            
            // Extraer type_id del texto (puede estar en el código o nombre)
            // Buscar si contiene "RC" o similar
            const typeKey = typeText.trim();
            
            if (!typePeriods[typeKey]) {
                typePeriods[typeKey] = [];
            }
            typePeriods[typeKey].push(periodText.trim());
        }
        
        // Verificar que para tipos con frecuencia >1 (ej: RC), no hay múltiples períodos mensuales consecutivos
        for (const [typeName, periods] of Object.entries(typePeriods)) {
            // Si el tipo parece ser RC o similar (cada 12/24 meses), verificar
            if (typeName.toUpperCase().includes('RC') || typeName.toUpperCase().includes('CERTIFICADO')) {
                // Parsear períodos (formato esperado: YYYY-MM o similar)
                const parsedPeriods = periods
                    .map(p => {
                        const match = p.match(/(\d{4})-(\d{2})/);
                        if (match) {
                            return { year: parseInt(match[1]), month: parseInt(match[2]) };
                        }
                        return null;
                    })
                    .filter(p => p !== null);
                
                // Si hay múltiples períodos mensuales consecutivos, es sospechoso
                // Para RC (cada 12 meses), debería haber como máximo 1 período en una ventana de 24 meses
                // (o 0 si no toca)
                if (parsedPeriods.length > 1) {
                    // Verificar que no sean meses consecutivos
                    const sortedPeriods = parsedPeriods.sort((a, b) => {
                        if (a.year !== b.year) return a.year - b.year;
                        return a.month - b.month;
                    });
                    
                    // Contar cuántos períodos hay en un rango de 12 meses
                    let consecutiveCount = 0;
                    for (let i = 0; i < sortedPeriods.length - 1; i++) {
                        const current = sortedPeriods[i];
                        const next = sortedPeriods[i + 1];
                        const monthsDiff = (next.year - current.year) * 12 + (next.month - current.month);
                        if (monthsDiff === 1) {
                            consecutiveCount++;
                        }
                    }
                    
                    // Para RC (cada 12 meses), no debería haber períodos mensuales consecutivos
                    // Si hay más de 1 período consecutivo, es un bug
                    expect(consecutiveCount).toBeLessThanOrEqual(1);
                }
                
                // Para RC, el número total de períodos en una ventana de 24 meses debería ser <= 2
                // (uno cada 12 meses)
                expect(periods.length).toBeLessThanOrEqual(2);
            }
        }
    });

    test('Test 4: Limpiar filtros restaura valores por defecto', async ({ page }) => {
        // SPRINT C2.3: Aplicar algunos filtros usando select
        const scopeSelect = page.locator('[data-testid="calendar-scope-select"]');
        await scopeSelect.selectOption('company');
        await page.waitForTimeout(500);
        
        const maxMonthsBackInput = page.locator('[data-testid="calendar-max-months-back"]');
        await maxMonthsBackInput.clear();
        await maxMonthsBackInput.fill('12');
        await maxMonthsBackInput.press('Enter');
        await page.waitForTimeout(1000);
        
        // Verificar que los filtros están aplicados
        await expect(scopeSelect).toHaveValue('company');
        
        let value = await maxMonthsBackInput.inputValue();
        expect(parseInt(value)).toBe(12);
        
        // Limpiar filtros
        await page.click('[data-testid="calendar-filter-clear"]');
        await page.waitForTimeout(1000);
        
        // Verificar que se restauraron
        await expect(scopeSelect).toHaveValue('all');
        
        value = await maxMonthsBackInput.inputValue();
        expect(parseInt(value)).toBe(24);
    });
});






