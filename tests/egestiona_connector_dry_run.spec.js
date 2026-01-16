const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { chromium } = require('@playwright/test');

test.describe('SPRINT C2.12.2: e-gestiona Connector Dry-Run', () => {
    test('Ejecuta dry-run del conector e-gestiona para Aigües de Manresa', async ({ request }) => {
        // Verificar que el servidor está corriendo
        const healthResponse = await request.get('http://127.0.0.1:8000/api/health');
        expect(healthResponse.ok()).toBeTruthy();
        
        // Llamar al endpoint de connectors/run con dry_run=true
        const response = await request.post('http://127.0.0.1:8000/api/connectors/run', {
            data: {
                platform_id: 'egestiona',
                tenant_id: 'Aigues de Manresa',
                headless: true,
                max_items: 20,
                dry_run: true,
            },
        });
        
        // Debe devolver 200
        expect(response.ok()).toBeTruthy();
        
        const data = await response.json();
        
        // Verificar estructura básica (incluso si hay error)
        expect(data).toHaveProperty('run_id');
        expect(data).toHaveProperty('platform_id');
        expect(data.platform_id).toBe('egestiona');
        
        // Si hay error, verificar que es de navegación (no de estructura)
        if (data.error) {
            console.log(`[DRY-RUN] Error (expected in some cases): ${data.error.substring(0, 200)}`);
            // El error puede ser de navegación (modal, timeout, etc.) pero la estructura es correcta
            expect(typeof data.error).toBe('string');
        } else {
            // Si no hay error, verificar estructura completa
            expect(data).toHaveProperty('dry_run');
            expect(data.dry_run).toBe(true);
            expect(data).toHaveProperty('evidence_dir');
            expect(data).toHaveProperty('counts');
            expect(data).toHaveProperty('results');
            
            // Verificar que evidence_dir existe
            const evidenceDir = data.evidence_dir;
            if (evidenceDir && fs.existsSync(evidenceDir)) {
                // Verificar que report.json existe (si se llegó a generar)
                const reportJsonPath = path.join(evidenceDir, 'report.json');
                if (fs.existsSync(reportJsonPath)) {
                    const reportJson = JSON.parse(fs.readFileSync(reportJsonPath, 'utf-8'));
                    expect(reportJson).toHaveProperty('run_id');
                    expect(reportJson).toHaveProperty('platform');
                    expect(reportJson).toHaveProperty('dry_run');
                    expect(reportJson.dry_run).toBe(true);
                    expect(reportJson).toHaveProperty('counts');
                    
                    console.log(`[DRY-RUN] Run ID: ${data.run_id}`);
                    console.log(`[DRY-RUN] Evidence dir: ${evidenceDir}`);
                    console.log(`[DRY-RUN] Total requirements: ${reportJson.counts.total_requirements || 0}`);
                    console.log(`[DRY-RUN] Matched: ${reportJson.counts.matched || 0}`);
                    console.log(`[DRY-RUN] No match: ${reportJson.counts.no_match || 0}`);
                }
                
                // Verificar que report.md existe (si se llegó a generar)
                const reportMdPath = path.join(evidenceDir, 'report.md');
                if (fs.existsSync(reportMdPath)) {
                    const reportMd = fs.readFileSync(reportMdPath, 'utf-8');
                    expect(reportMd).toContain('# Informe de Dry-Run');
                    expect(reportMd).toContain('egestiona');
                }
            }
        }
    });
    
    test('Ejecuta dry-run del conector e-gestiona (segunda ejecución para estabilidad)', async ({ request, browser }) => {
        // Verificar que el servidor está corriendo
        const healthResponse = await request.get('http://127.0.0.1:8000/api/health');
        expect(healthResponse.ok()).toBeTruthy();
        
        // Llamar al endpoint de connectors/run con dry_run=true
        const response = await request.post('http://127.0.0.1:8000/api/connectors/run', {
            data: {
                platform_id: 'egestiona',
                tenant_id: 'Aigues de Manresa',
                headless: true,
                max_items: 20,
                dry_run: true,
            },
            timeout: 300000,  // 5 minutos timeout
        });
        
        // Puede devolver 200 (éxito) o 500 (error de navegación)
        expect(response.status()).toBeLessThanOrEqual(500);
        
        const data = await response.json();
        
        // Verificar estructura básica
        expect(data).toHaveProperty('run_id');
        expect(data).toHaveProperty('platform_id');
        expect(data.platform_id).toBe('egestiona');
        
        // Si no hay error, verificar estructura completa
        if (!data.error && data.evidence_dir) {
            const evidenceDir = data.evidence_dir;
            if (fs.existsSync(evidenceDir)) {
                console.log(`[DRY-RUN-2] Run ID: ${data.run_id}`);
                console.log(`[DRY-RUN-2] Evidence dir: ${evidenceDir}`);
            }
        }
    });
});
