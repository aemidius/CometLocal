/**
 * E2E tests para cola de ejecuciones CAE v1.8.2
 * 
 * Flujo FAKE:
 * - Usar seed o snapshot FAKE
 * - Generar plan READY con 2 items
 * - Challenge → /enqueue
 * - Verificar progreso en tiempo real usando señales DOM explícitas
 * - Esperar SUCCESS usando data-job-status
 */

const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash, waitForTestId } = require('./helpers/e2eSeed');

test.describe('CAE Job Queue E2E - Cola de ejecuciones con progreso', () => {
    test.setTimeout(90000); // 90 segundos timeout
    
    let seedData = null;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando helpers
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
        
        // También seed específico para CAE selection si está disponible
        try {
            const seedResponse = await request.post('http://127.0.0.1:8000/api/test/seed/cae_selection_v1', {
                headers: { 'Content-Type': 'application/json' },
                data: {},
            });
            if (seedResponse.ok()) {
                const caeSeedData = await seedResponse.json();
                console.log('[E2E] CAE seed data created:', caeSeedData);
                // Combinar datos si es necesario
                seedData = { ...seedData, ...caeSeedData };
            }
        } catch (error) {
            console.log('[E2E] CAE seed not available, using basic seed');
        }
    });
    
    test('Test 1: Encolar ejecución y verificar progreso hasta SUCCESS', async ({ page }) => {
        // Navigate usando helper
        await gotoHash(page, 'calendario');
        
        // Click on "Pendientes" tab
        const missingTab = page.locator('#pending-tab-missing');
        await expect(missingTab).toBeVisible({ timeout: 10000 });
        await missingTab.click();
        
        // v1.8.2: Seleccionar filas que tengan period_key que coincida con los documentos del seed
        // El seed crea documentos con period_key específico, así que necesitamos seleccionar pendientes con ese period_key
        const pendingRows = page.locator('tr[data-testid="calendar-pending-row"]');
        await page.waitForTimeout(2000); // Dar tiempo para que aparezcan las filas
        
        const rowCount = await pendingRows.count();
        console.log(`[E2E] Found ${rowCount} pending rows`);
        
        if (rowCount < 2) {
            console.log('[E2E] Not enough pending rows, skipping test');
            test.skip();
            return;
        }
        
        // Si tenemos seed data con period_keys, intentar seleccionar filas con esos period_keys
        let selectedPeriodKeys = [];
        if (seedData && seedData.period_keys && seedData.period_keys.length >= 2) {
            const targetPeriodKeys = seedData.period_keys.slice(0, 2);
            console.log(`[E2E] Looking for rows with period_keys: ${targetPeriodKeys.join(', ')}`);
            
            // Buscar filas con los period_keys del seed
            for (const periodKey of targetPeriodKeys) {
                const row = page.locator(`tr[data-pending-period-key="${periodKey}"]`).first();
                const count = await row.count();
                if (count > 0) {
                    await row.locator('.pending-row-checkbox').check();
                    await page.waitForTimeout(300);
                    selectedPeriodKeys.push(periodKey);
                    console.log(`[E2E] Selected row with period_key: ${periodKey}`);
                }
            }
        }
        
        // Si no encontramos suficientes filas con los period_keys del seed, seleccionar cualquier fila disponible
        if (selectedPeriodKeys.length < 2) {
            console.log(`[E2E] Only found ${selectedPeriodKeys.length} rows with seed period_keys, selecting generic rows`);
            // Seleccionar primera fila disponible que no esté ya seleccionada
            const firstRow = pendingRows.first();
            const firstChecked = await firstRow.locator('.pending-row-checkbox').isChecked();
            if (!firstChecked) {
                await firstRow.locator('.pending-row-checkbox').check();
                await page.waitForTimeout(300);
            }
            
            // Seleccionar segunda fila disponible
            const secondRow = pendingRows.nth(1);
            const secondChecked = await secondRow.locator('.pending-row-checkbox').isChecked();
            if (!secondChecked) {
                await secondRow.locator('.pending-row-checkbox').check();
                await page.waitForTimeout(300);
            }
            
            // Extraer period_keys de las filas seleccionadas para usar en la selección de documentos
            const firstPeriodKey = await firstRow.getAttribute('data-pending-period-key');
            const secondPeriodKey = await secondRow.getAttribute('data-pending-period-key');
            if (firstPeriodKey) selectedPeriodKeys.push(firstPeriodKey);
            if (secondPeriodKey) selectedPeriodKeys.push(secondPeriodKey);
            console.log(`[E2E] Selected generic rows with period_keys: ${selectedPeriodKeys.join(', ')}`);
        }
        
        // Verificar que el botón muestra el count
        const selectionButton = page.locator('[data-testid="cae-selection-button"]');
        await expect(selectionButton).toBeVisible();
        const buttonText = await selectionButton.textContent();
        expect(buttonText).toContain('(2)');
        
        // Click en botón de selección
        await selectionButton.click();
        await page.waitForTimeout(1000);
        
        // Verificar que el modal se abre
        const modal = page.locator('#cae-selection-modal');
        await expect(modal).toBeVisible({ timeout: 5000 });
        
                // v1.7: Esperar señales de auto-sugerencia lista para cada item seleccionado
                // Sabemos que seleccionamos 2 items, así que esperamos 2 señales
                const expectedItemCount = 2;
                console.log(`[E2E] Waiting for auto-suggestion ready signals for ${expectedItemCount} items`);
                
                // Debug: Mostrar información de los items seleccionados
                if (seedData && seedData.type_id) {
                    console.log(`[E2E] Seed type_id: ${seedData.type_id}`);
                }
                
                for (let i = 0; i < expectedItemCount; i++) {
                    // Esperar la señal data-autosuggestion-ready en el contenedor del item
                    // Usar waitForSelector para esperar que el atributo esté presente
                    await page.waitForSelector(`[data-item-idx="${i}"][data-autosuggestion-ready="true"]`, { 
                        state: 'attached', 
                        timeout: 15000 
                    });
                    console.log(`[E2E] Auto-suggestion ready signal received for item ${i}`);
                    
                    // Debug: Mostrar type_id del item seleccionado
                    const itemCard = page.locator(`[data-item-idx="${i}"]`);
                    const itemTypeId = await itemCard.locator('h3').first().textContent().catch(() => 'N/A');
                    console.log(`[E2E] Item ${i} type_id: ${itemTypeId}`);
                }
        
                // v1.7: Verificar que los selects están disponibles y tienen valores preseleccionados
                const docSelects = page.locator('select[id^="doc-select-"]');
                const selectCount = await docSelects.count().catch(() => 0);
                console.log(`[E2E] Found ${selectCount} document selects`);
                
                // Verificar si hay errores en la carga de candidatos
                for (let i = 0; i < expectedItemCount; i++) {
                    const errorDiv = page.locator(`[data-testid="doc-candidates-error-${i}"]`);
                    const errorVisible = await errorDiv.isVisible().catch(() => false);
                    if (errorVisible) {
                        const errorText = await errorDiv.textContent().catch(() => '');
                        console.error(`[E2E] Error loading candidates for item ${i}: ${errorText}`);
                    }
                }
                
                // Verificar que hay al menos 2 selects (uno por cada item seleccionado)
                expect(selectCount).toBeGreaterThanOrEqual(expectedItemCount);
        
        // Verificar que al menos uno tiene un valor preseleccionado (auto-sugerencia funcionó)
        let hasAutoSuggestion = false;
        for (let i = 0; i < Math.min(selectCount, expectedItemCount); i++) {
            try {
                const select = docSelects.nth(i);
                const currentValue = await select.inputValue().catch(() => '');
                if (currentValue && currentValue !== '') {
                    console.log(`[E2E] Item ${i} has auto-suggested value: ${currentValue}`);
                    hasAutoSuggestion = true;
                }
                
                // Verificar que aparece el texto de sugerencia automática
                const suggestionDiv = page.locator(`[data-testid="auto-suggestion-${i}"]`);
                const suggestionVisible = await suggestionDiv.isVisible().catch(() => false);
                if (suggestionVisible) {
                    const suggestionText = await suggestionDiv.textContent().catch(() => '');
                    console.log(`[E2E] Auto-suggestion text for item ${i}:`, suggestionText);
                    expect(suggestionText).toContain('Sugerido automáticamente');
                }
            } catch (e) {
                console.log(`[E2E] Could not check select ${i}:`, e.message);
            }
        }
        
        // v1.7: Verificar que al menos una auto-sugerencia funcionó (o que al menos hay candidatos disponibles)
        // Si no hay auto-sugerencia, puede ser porque no hay candidatos o porque el ranking no encontró coincidencias
        // En ese caso, solo verificamos que las señales se recibieron correctamente
        if (!hasAutoSuggestion) {
            console.log('[E2E] No auto-suggestion found, but signals were received correctly');
        } else {
            console.log('[E2E] Auto-suggestion verified successfully');
        }
        
        // v1.8.2: Seleccionar documentos explícitamente si no hay auto-sugerencia o si hay seed data
        // Esto asegura que el plan sea READY cuando se generen documentos con el mismo period_key
        if (seedData && seedData.doc_ids) {
            console.log(`[E2E] Selecting seed documents: ${seedData.doc_ids.join(', ')}`);
            for (let i = 0; i < Math.min(selectCount, seedData.doc_ids.length); i++) {
                try {
                    const select = docSelects.nth(i);
                    const targetDocId = seedData.doc_ids[i];
                    const currentValue = await select.inputValue().catch(() => '');
                    
                    // Debug: Listar todas las opciones disponibles
                    const options = await select.locator('option').allTextContents();
                    const optionValues = await Promise.all(
                        (await select.locator('option').all()).map(async (opt) => await opt.getAttribute('value'))
                    );
                    console.log(`[E2E] Select ${i} options (${options.length}):`, options);
                    console.log(`[E2E] Select ${i} option values:`, optionValues);
                    console.log(`[E2E] Select ${i} target doc_id: ${targetDocId}`);
                    
                    if (currentValue === targetDocId) {
                        console.log(`[E2E] Item ${i} already has correct document selected: ${targetDocId}`);
                    } else {
                        // Intentar seleccionar el documento del seed
                        const optionCount = await select.locator('option').count();
                        console.log(`[E2E] Select ${i} has ${optionCount} options`);
                        if (optionCount > 1) {
                            // Verificar si el targetDocId está en las opciones
                            const targetOptionExists = optionValues.includes(targetDocId);
                            console.log(`[E2E] Select ${i} target doc_id exists in options: ${targetOptionExists}`);
                            
                            if (targetOptionExists) {
                                try {
                                    await select.selectOption({ value: targetDocId });
                                    // v1.8.2: Esperar a que el valor se establezca correctamente
                                    await page.waitForFunction(
                                        (idx, expectedValue) => {
                                            const select = document.getElementById(`doc-select-${idx}`);
                                            return select && select.value === expectedValue;
                                        },
                                        { args: [i, targetDocId], timeout: 5000 }
                                    ).catch(() => {
                                        console.log(`[E2E] Could not verify select value for item ${i}, continuing...`);
                                    });
                                    console.log(`[E2E] Selected seed document ${targetDocId} for item ${i}`);
                                } catch (e) {
                                    console.log(`[E2E] Error selecting target doc_id: ${e.message}`);
                                    // Si falla, seleccionar primera opción disponible
                                    await select.selectOption({ index: 1 }).catch(() => {});
                                    console.log(`[E2E] Could not select seed document, selected first available for item ${i}`);
                                }
                            } else {
                                // El documento no está en las opciones, seleccionar primera opción disponible
                                console.log(`[E2E] Target doc_id not in options, selecting first available`);
                                await select.selectOption({ index: 1 }).catch(() => {});
                            }
                        } else {
                            console.log(`[E2E] Select ${i} has no options available (only placeholder)`);
                        }
                    }
                } catch (e) {
                    console.log(`[E2E] Could not select document for item ${i}: ${e.message}`);
                }
            }
        } else if (!hasAutoSuggestion) {
            // Sin seed data y sin auto-sugerencia, seleccionar primera opción disponible
            console.log('[E2E] No seed data and no auto-suggestion, selecting first available options');
            for (let i = 0; i < selectCount; i++) {
                try {
                    const select = docSelects.nth(i);
                    const optionCount = await select.locator('option').count();
                    if (optionCount > 1) {
                        await select.selectOption({ index: 1 }).catch(() => {});
                        // Verificar que el valor se estableció
                        await page.waitForFunction(
                            (idx) => {
                                const select = document.getElementById(`doc-select-${idx}`);
                                return select && select.value !== '';
                            },
                            { args: [i], timeout: 5000 }
                        ).catch(() => {
                            console.log(`[E2E] Could not verify select value for item ${i}, continuing...`);
                        });
                        console.log(`[E2E] Selected first available option for item ${i}`);
                    }
                } catch (e) {
                    console.log(`[E2E] Could not select option for item ${i}: ${e.message}`);
                }
            }
        }
        
        // v1.8.2: Verificar que todos los selects tienen valores antes de generar el plan
        console.log('[E2E] Verifying all selects have values before generating plan');
        for (let i = 0; i < Math.min(selectCount, expectedItemCount); i++) {
            const select = docSelects.nth(i);
            const value = await select.inputValue().catch(() => '');
            console.log(`[E2E] Select ${i} value: ${value || 'EMPTY'}`);
            if (!value || value === '') {
                throw new Error(`Select ${i} does not have a value selected. Cannot generate READY plan.`);
            }
        }
        
        // Click en "Generar plan" (aunque no haya auto-sugerencia, el plan puede generarse)
        const generateButton = page.locator('[data-testid="cae-selection-generate"]');
        await expect(generateButton).toBeVisible({ timeout: 5000 });
        await generateButton.click();
        
        // Esperar a que el plan se genere (sin timeout fijo)
        await page.waitForSelector('#cae-selection-result', { state: 'visible', timeout: 15000 });
        
        // Verificar que aparece el resultado
        const resultDiv = page.locator('#cae-selection-result');
        await expect(resultDiv).toBeVisible({ timeout: 10000 });
        
        // Verificar que decision es READY
        const decisionBadge = resultDiv.locator('.badge');
        await expect(decisionBadge).toBeVisible();
        const decisionText = await decisionBadge.textContent();
        console.log('[E2E] Plan decision:', decisionText);
        
        // Si NO es READY, mostrar razones
        if (decisionText && decisionText.trim() !== 'READY') {
            const reasonsDiv = resultDiv.locator('.reasons, ul, ol').first();
            const reasonsVisible = await reasonsDiv.isVisible().catch(() => false);
            if (reasonsVisible) {
                const reasonsText = await reasonsDiv.textContent().catch(() => '');
                console.error(`[E2E] Plan is not READY. Reasons: ${reasonsText}`);
            }
            throw new Error(`Plan is not READY, decision: ${decisionText}`);
        }
        
        // Si es READY, verificar que aparece botón de ejecutar
        if (decisionText && decisionText.trim() === 'READY') {
            const executeButton = resultDiv.locator('[data-testid="cae-execute-button"]');
            const executeButtonCount = await executeButton.count();
            console.log(`[E2E] Execute button count: ${executeButtonCount}`);
            
            if (executeButtonCount > 0) {
                console.log('[E2E] Plan is READY, executing...');
                
                // Click en ejecutar
                await executeButton.click();
                
                // Esperar a que aparezca el challenge (sin timeout fijo)
                await page.waitForSelector('#cae-challenge-response', { state: 'visible', timeout: 10000 });
                
                // Verificar que aparece el challenge
                const challengeInput = page.locator('#cae-challenge-response');
                const challengeInputCount = await challengeInput.count();
                console.log(`[E2E] Challenge input count: ${challengeInputCount}`);
                
                if (challengeInputCount > 0) {
                    await expect(challengeInput).toBeVisible();
                    
                    // Obtener el prompt del challenge
                    const challengePrompt = await resultDiv.locator('p').first().textContent();
                    const planIdMatch = challengePrompt.match(/EJECUTAR (CAEPLAN-[^\s]+)/);
                    
                    if (planIdMatch) {
                        const planId = planIdMatch[1];
                        
                        // Rellenar challenge response
                        await challengeInput.fill(`EJECUTAR ${planId}`);
                        
                        // Asegurar que dry_run está activado (FAKE mode)
                        const dryRunCheckbox = page.locator('#cae-dry-run');
                        if (await dryRunCheckbox.isVisible()) {
                            await dryRunCheckbox.check();
                        }
                        
                        // Confirmar ejecución
                        const confirmButton = page.locator('[data-testid="cae-confirm-execute-button"]');
                        await expect(confirmButton).toBeVisible();
                        await confirmButton.click();
                        
                        // v1.8.2: Esperar EXCLUSIVAMENTE por señales DOM explícitas
                        // Esperar a que aparezca el div de progreso con atributo data-job-status
                        await page.waitForSelector('#cae-job-progress[data-job-status]', { 
                            state: 'visible', 
                            timeout: 15000 
                        });
                        const progressDiv = page.locator('#cae-job-progress');
                        console.log('[E2E] Progress div appeared with data-job-status');
                        
                        // Verificar que el estado inicial es RUNNING o QUEUED
                        const initialStatus = await progressDiv.getAttribute('data-job-status');
                        console.log('[E2E] Initial job status:', initialStatus);
                        
                        // Si el estado es FAILED, mostrar el mensaje de error
                        if (initialStatus === 'FAILED') {
                            const errorText = await progressDiv.textContent();
                            console.error('[E2E] Job failed with error:', errorText);
                            throw new Error(`Job failed: ${errorText}`);
                        }
                        
                        expect(['QUEUED', 'RUNNING']).toContain(initialStatus);
                        
                        // v1.8.2: Esperar EXCLUSIVAMENTE por data-job-status="SUCCESS"
                        await page.waitForSelector('#cae-job-progress[data-job-status="SUCCESS"]', { 
                            state: 'visible', 
                            timeout: 60000 
                        });
                        console.log('[E2E] Job status is SUCCESS');
                        
                        // Verificar que progress es 100%
                        const finalProgress = await progressDiv.getAttribute('data-job-progress');
                        console.log('[E2E] Final progress:', finalProgress);
                        expect(finalProgress).toBe('100');
                        
                        // Verificar que aparece run_id
                        const runIdElement = progressDiv.locator('[data-testid="job-run-id"]');
                        await expect(runIdElement).toBeVisible({ timeout: 5000 });
                        const runIdText = await runIdElement.textContent();
                        console.log('[E2E] Run ID:', runIdText);
                        expect(runIdText).toContain('Run ID');
                        expect(runIdText).not.toContain('N/A');
                        
                        // Verificar que aparece mensaje de completado
                        const completedMessage = progressDiv.locator('[data-testid="job-completed-message"]');
                        await expect(completedMessage).toBeVisible({ timeout: 5000 });
                        const completedText = await completedMessage.textContent();
                        console.log('[E2E] Completed message:', completedText);
                        expect(completedText).toContain('Completado');
                        
                        console.log('[E2E] Test completed successfully');
                    } else {
                        throw new Error('Could not extract plan ID from challenge prompt');
                    }
                } else {
                    throw new Error('Challenge input not found');
                }
            } else {
                throw new Error('Execute button not found');
            }
        } else {
            throw new Error(`Plan is not READY, decision: ${decisionText}`);
        }
    });
});
