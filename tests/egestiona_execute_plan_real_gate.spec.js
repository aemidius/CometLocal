const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.4: Real Upload Gate (E2E)', () => {
    test('Validar que sin header X-USE-REAL-UPLOADER se usa FakeUploader', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_real_gate_e2e');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }

        const BACKEND_URL = 'http://127.0.0.1:8000';

        // PASO 1: Generar plan con FIXTURE
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

        // Cargar plan desde archivo
        const planFileResponse = await fetch(`${BACKEND_URL}/runs/${planId}/file/evidence/submission_plan.json`);
        expect(planFileResponse.ok).toBeTruthy();
        const planFileData = await planFileResponse.json();
        const planItems = planFileData.plan || [];
        expect(planItems.length).toBeGreaterThanOrEqual(2);

        // PASO 2: Ejecutar SIN header X-USE-REAL-UPLOADER (debe usar FakeUploader)
        console.log('[E2E] Paso 2: Ejecutando plan SIN header X-USE-REAL-UPLOADER (debe usar FakeUploader)...');

        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_submission_plan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // NO incluir X-USE-REAL-UPLOADER
            },
            body: JSON.stringify({
                plan_id: planId,
                confirm_token: confirmToken,
                allowlist_type_ids: ["T_FIX_OK"],
                max_uploads: 1,
                min_confidence: 0.80,
                use_fake_uploader: true,
            }),
        });

        expect(executeResponse.ok).toBeTruthy();
        const executeResult = await executeResponse.json();
        expect(executeResult.status).toBe('ok');
        expect(executeResult.executed).toBe(true);
        expect(executeResult.uploader_type).toBe('fake');
        expect(executeResult.use_fake_uploader).toBe(true);
        expect(executeResult.summary.uploaded).toBe(1);

        console.log(`[E2E] Ejecución completada con FakeUploader:`);
        console.log(`  - Uploader type: ${executeResult.uploader_type}`);
        console.log(`  - Uploaded: ${executeResult.summary.uploaded}`);

        // Guardar evidencia
        const evidenceFile = path.join(evidenceDir, 'fake_upload_result.json');
        fs.writeFileSync(evidenceFile, JSON.stringify(executeResult, null, 2));
        console.log(`[E2E] Evidencia guardada en: ${evidenceFile}`);
    });

    test('Validar guardrail: max_uploads != 1 con header X-USE-REAL-UPLOADER', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Generar plan fixture
        const buildResponse = await fetch(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=B12345678&limit=5&only_target=false&fixture=1`, {
            method: 'POST',
            headers: {
                'X-CAE-PLAN-FIXTURE': '1',
            },
        });

        const buildResult = await buildResponse.json();
        const planId = buildResult.plan_id || buildResult.run_id;
        const confirmToken = buildResult.confirm_token;

        // Intentar ejecutar con max_uploads=2 (debe fallar)
        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_submission_plan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-USE-REAL-UPLOADER': '1',
            },
            body: JSON.stringify({
                plan_id: planId,
                confirm_token: confirmToken,
                allowlist_type_ids: ["T_FIX_OK"],
                max_uploads: 2, // Violación: debe ser 1
                min_confidence: 0.80,
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('REAL_UPLOAD_GUARDRAIL_VIOLATION');
        expect(result.message).toContain('max_uploads debe ser 1');
    });

    test('Validar guardrail: len(allowlist_type_ids) != 1 con header X-USE-REAL-UPLOADER', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Generar plan fixture
        const buildResponse = await fetch(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=B12345678&limit=5&only_target=false&fixture=1`, {
            method: 'POST',
            headers: {
                'X-CAE-PLAN-FIXTURE': '1',
            },
        });

        const buildResult = await buildResponse.json();
        const planId = buildResult.plan_id || buildResult.run_id;
        const confirmToken = buildResult.confirm_token;

        // Intentar ejecutar con 2 tipos (debe fallar)
        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_submission_plan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-USE-REAL-UPLOADER': '1',
            },
            body: JSON.stringify({
                plan_id: planId,
                confirm_token: confirmToken,
                allowlist_type_ids: ["T_FIX_OK", "T_FIX_LOW"], // Violación: debe ser 1
                max_uploads: 1,
                min_confidence: 0.80,
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('REAL_UPLOAD_GUARDRAIL_VIOLATION');
        expect(result.message).toContain('allowlist_type_ids debe tener exactamente 1 tipo');
    });
});
