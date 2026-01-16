const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.5: Execute Plan Headful (E2E)', () => {
    const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_execute_headful');
    
    test.beforeAll(() => {
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
    });
    test('Validar error missing_storage_state cuando no existe storage_state.json', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Generar plan con FIXTURE (no genera storage_state real)
        const buildResponse = await fetch(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=B12345678&limit=5&only_target=false&fixture=1`, {
            method: 'POST',
            headers: {
                'X-CAE-PLAN-FIXTURE': '1',
            },
        });

        expect(buildResponse.ok).toBeTruthy();
        const buildResult = await buildResponse.json();
        const planId = buildResult.plan_id || buildResult.run_id;
        const confirmToken = buildResult.confirm_token;

        // Intentar ejecutar con header X-USE-REAL-UPLOADER (debe fallar por falta de storage_state)
        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_plan_headful`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-USE-REAL-UPLOADER': '1',
            },
            body: JSON.stringify({
                plan_id: planId,
                confirm_token: confirmToken,
                allowlist_type_ids: ["T_FIX_OK"],
                max_uploads: 1,
                min_confidence: 0.80,
                use_fake_uploader: false,
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('missing_storage_state');
        expect(result.message).toContain('No hay sesión guardada');
    });

    test('Validar guardrail: sin header X-USE-REAL-UPLOADER', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Generar plan con FIXTURE
        const buildResponse = await fetch(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=B12345678&limit=5&only_target=false&fixture=1`, {
            method: 'POST',
            headers: {
                'X-CAE-PLAN-FIXTURE': '1',
            },
        });

        const buildResult = await buildResponse.json();
        const planId = buildResult.plan_id || buildResult.run_id;
        const confirmToken = buildResult.confirm_token;

        // Intentar ejecutar SIN header (debe fallar)
        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_plan_headful`, {
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
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('real_uploader_not_requested');
        
        // Guardar evidencia
        const evidenceFile = path.join(evidenceDir, 'missing_header_response.json');
        fs.writeFileSync(evidenceFile, JSON.stringify({
            request: {
                plan_id: planId,
                confirm_token: confirmToken,
                allowlist_type_ids: ["T_FIX_OK"],
                max_uploads: 1,
                min_confidence: 0.80,
            },
            response: result,
        }, null, 2));
    });
});
