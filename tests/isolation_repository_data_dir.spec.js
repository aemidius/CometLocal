const { test, expect } = require('@playwright/test');

test.describe('SPRINT C2.10.2: Aislamiento de datos E2E', () => {
    test('Verifica que E2E usa directorio aislado (repository_e2e)', async ({ request }) => {
        // Verificar que el servidor está corriendo
        const healthResponse = await request.get('http://127.0.0.1:8000/api/health');
        expect(healthResponse.ok()).toBeTruthy();
        
        // Llamar al endpoint debug para obtener el directorio usado
        const debugResponse = await request.get('http://127.0.0.1:8000/api/repository/debug/data_dir');
        
        // El endpoint debe existir y responder (estamos en modo E2E)
        expect(debugResponse.ok()).toBeTruthy();
        
        const debugData = await debugResponse.json();
        
        // Verificar que contiene información del directorio
        expect(debugData).toHaveProperty('data_dir');
        expect(debugData).toHaveProperty('repository_root');
        expect(debugData).toHaveProperty('repository_data_dir_env');
        
        // Verificar que el directorio usado es el aislado (repository_e2e)
        const dataDir = debugData.data_dir;
        const repoRoot = debugData.repository_root;
        
        // Debe contener "repository_e2e" y NO ser "data/repository" (sin _e2e)
        expect(dataDir).toContain('repository_e2e');
        // Verificar que NO termina en "data/repository" (sin _e2e)
        const normalizedDataDir = dataDir.replace(/\\/g, '/');
        expect(normalizedDataDir).not.toMatch(/data\/repository$/);
        expect(repoRoot).toContain('repository_e2e');
        
        // Verificar que la env var está configurada
        expect(debugData.repository_data_dir_env).toBe('data/repository_e2e');
        
        // Verificar flag is_e2e
        expect(debugData.is_e2e).toBe(true);
        
        console.log(`[ISOLATION] Data dir: ${dataDir}`);
        console.log(`[ISOLATION] Repository root: ${repoRoot}`);
        console.log(`[ISOLATION] Env var: ${debugData.repository_data_dir_env}`);
    });
});
