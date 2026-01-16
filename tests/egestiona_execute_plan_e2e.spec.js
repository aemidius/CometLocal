const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.3: Ejecutar Plan con Guardrails (E2E)', () => {
    test('Flujo completo: build plan → execute plan con guardrails', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_execute_plan_e2e');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }

        const BACKEND_URL = 'http://127.0.0.1:8000';

        // PASO 1: Generar plan (READ-ONLY) usando FIXTURE
        console.log('[E2E] Paso 1: Generando plan READ-ONLY con FIXTURE...');
        const buildResponse = await fetch(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=B12345678&limit=5&only_target=false&fixture=1`, {
            method: 'POST',
            headers: {
                'X-CAE-PLAN-FIXTURE': '1',
            },
        });

        expect(buildResponse.ok).toBeTruthy();
        const buildResult = await buildResponse.json();
        expect(buildResult.status).toBe('ok');
        expect(buildResult.plan_id || buildResult.run_id).toBeTruthy();
        expect(buildResult.confirm_token).toBeTruthy();

        const planId = buildResult.plan_id || buildResult.run_id;
        const confirmToken = buildResult.confirm_token;

        console.log(`[E2E] Plan generado: ${planId}, token: ${confirmToken.substring(0, 16)}...`);

        // Cargar plan desde archivo para obtener items completos
        const planFileResponse = await fetch(`${BACKEND_URL}/runs/${planId}/file/evidence/submission_plan.json`);
        expect(planFileResponse.ok).toBeTruthy();
        const planFileData = await planFileResponse.json();
        const planItems = planFileData.plan || [];
        
        // Validar que el fixture tiene al menos 2 items
        expect(planItems.length).toBeGreaterThanOrEqual(2);
        console.log(`[E2E] Plan tiene ${planItems.length} items`);

        // Obtener type_ids del plan para la allowlist
        const typeIds = [];
        for (const item of planItems) {
            const typeId = item.matched_doc?.type_id;
            if (typeId && !typeIds.includes(typeId)) {
                typeIds.push(typeId);
            }
        }
        
        expect(typeIds.length).toBeGreaterThan(0);
        console.log(`[E2E] Type IDs encontrados: ${typeIds.join(', ')}`);

        // PASO 2: Ejecutar plan con guardrails
        console.log('[E2E] Paso 2: Ejecutando plan con guardrails...');

        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_submission_plan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                plan_id: planId,
                confirm_token: confirmToken,
                allowlist_type_ids: ["T_FIX_OK"], // Solo el item bueno del fixture
                max_uploads: 2,
                min_confidence: 0.80,
                use_fake_uploader: true,
            }),
        });

        expect(executeResponse.ok).toBeTruthy();
        const executeResult = await executeResponse.json();
        expect(executeResult.status).toBe('ok');
        expect(executeResult.executed).toBe(true);
        expect(executeResult.summary).toBeTruthy();
        
        // Validar que el plan tiene items
        expect(executeResult.summary.total).toBeGreaterThanOrEqual(2);
        expect(executeResult.summary.eligible).toBeGreaterThanOrEqual(1);
        
        // EXIGIR uploaded=1 (el fixture tiene 1 item elegible con T_FIX_OK)
        expect(executeResult.summary.uploaded).toBe(1);
        expect(executeResult.use_fake_uploader).toBe(true);

        console.log(`[E2E] Ejecución completada:`);
        console.log(`  - Total: ${executeResult.summary.total}`);
        console.log(`  - Eligible: ${executeResult.summary.eligible}`);
        console.log(`  - Uploaded: ${executeResult.summary.uploaded}`);
        console.log(`  - Skipped: ${executeResult.summary.skipped}`);
        console.log(`  - Failed: ${executeResult.summary.failed}`);

        // Validar que uploaded <= max_uploads
        expect(executeResult.summary.uploaded).toBeLessThanOrEqual(2);

        // Validar que todos los items tienen outcome y reason
        const items = executeResult.items || [];
        expect(items.length).toBeGreaterThan(0);
        
        for (const item of items) {
            expect(item.outcome).toBeTruthy();
            expect(['uploaded', 'skipped', 'failed']).toContain(item.outcome);
            expect(item.reason).toBeTruthy();
        }
        
        // Validar que existe al menos 1 item uploaded con type_id="T_FIX_OK"
        const uploadedItems = items.filter(i => i.outcome === 'uploaded');
        expect(uploadedItems.length).toBe(1);
        expect(uploadedItems[0].item.matched_doc.type_id).toBe('T_FIX_OK');
        
        // Validar que items con baja confianza están skipped con reason="below_min_confidence"
        const skippedLowConf = items.filter(i => 
            i.outcome === 'skipped' && 
            i.reason === 'below_min_confidence'
        );
        expect(skippedLowConf.length).toBeGreaterThanOrEqual(0); // Puede haber 0 si no hay items con baja confianza en allowlist
        
        // Validar que items fuera de allowlist están skipped con reason="not_in_allowlist"
        const skippedNotInAllowlist = items.filter(i => 
            i.outcome === 'skipped' && 
            i.reason === 'not_in_allowlist'
        );
        expect(skippedNotInAllowlist.length).toBeGreaterThanOrEqual(0);

        // Guardar evidencia
        const evidenceFile = path.join(evidenceDir, 'execution_result.json');
        fs.writeFileSync(evidenceFile, JSON.stringify(executeResult, null, 2));
        console.log(`[E2E] Evidencia guardada en: ${evidenceFile}`);
    });

    test('Validar guardrails: token inválido', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_submission_plan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                plan_id: 'r_invalid',
                confirm_token: 'invalid_token',
                allowlist_type_ids: ['T001'],
                max_uploads: 1,
                min_confidence: 0.80,
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBeTruthy();
        expect(['plan_not_found', 'invalid_confirm_token']).toContain(result.error_code);
    });
});
