const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('SPRINT C2.12.6: Headful Run Persistente (E2E)', () => {
    const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'egestiona_headful_run');
    
    test.beforeAll(() => {
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
    });

    test('Validar error missing_storage_state al iniciar run headful', async () => {
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

        // Intentar iniciar run headful (debe fallar por falta de storage_state)
        const startResponse = await fetch(`${BACKEND_URL}/runs/egestiona/start_headful_run`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-USE-REAL-UPLOADER': '1',
            },
            body: JSON.stringify({
                plan_id: planId,
                confirm_token: confirmToken,
            }),
        });

        const result = await startResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('missing_storage_state');
        expect(result.message).toContain('No hay sesión guardada');
    });

    test('Validar error headful_run_not_found al ejecutar acción sin run activo', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Intentar ejecutar acción sin run activo
        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_action_headful`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-USE-REAL-UPLOADER': '1',
            },
            body: JSON.stringify({
                run_id: 'nonexistent_run_id',
                confirm_token: 'fake_token',
                allowlist_type_ids: ['T_FIX_OK'],
                max_uploads: 1,
                min_confidence: 0.80,
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('headful_run_not_found');
        expect(result.message).toContain('no está activo');
    });

    test('Validar error real_uploader_not_requested al ejecutar acción sin header', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Intentar ejecutar acción sin header X-USE-REAL-UPLOADER
        const executeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/execute_action_headful`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // NO incluir X-USE-REAL-UPLOADER
            },
            body: JSON.stringify({
                run_id: 'test_run',
                confirm_token: 'fake_token',
                allowlist_type_ids: ['T_FIX_OK'],
                max_uploads: 1,
                min_confidence: 0.80,
            }),
        });

        const result = await executeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('real_uploader_not_requested');
    });

    test('Validar error al cerrar run inexistente', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Intentar cerrar run que no existe
        const closeResponse = await fetch(`${BACKEND_URL}/runs/egestiona/close_headful_run`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                run_id: 'nonexistent_run_id',
            }),
        });

        const result = await closeResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('headful_run_not_found');
    });

    test('Validar endpoint de status de run headful', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Intentar obtener status de run inexistente
        const statusResponse = await fetch(`${BACKEND_URL}/runs/egestiona/headful_run_status?run_id=nonexistent_run_id`);
        
        const result = await statusResponse.json();
        expect(result.status).toBe('error');
        expect(result.error_code).toBe('headful_run_not_found');
    });
});
