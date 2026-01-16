/**
 * SPRINT C2.9.24: Script para medir latencia del endpoint /api/repository/docs/pending
 * Determina si es problema de warmup (caso A) o siempre lento (caso B)
 */

const url = 'http://127.0.0.1:8000/api/repository/docs/pending?months_ahead=3&max_months_back=12';

async function measureRequest() {
    const start = Date.now();
    try {
        const response = await fetch(url);
        const text = await response.text();
        const end = Date.now();
        const duration = end - start;
        const jsonSize = text.length;
        
        return {
            status: response.status,
            duration,
            jsonSize,
            ok: response.ok
        };
    } catch (error) {
        const end = Date.now();
        const duration = end - start;
        return {
            status: 0,
            duration,
            jsonSize: 0,
            ok: false,
            error: error.message
        };
    }
}

async function main() {
    console.log('[TIMING] Iniciando medición de latencia del endpoint pending...');
    console.log(`[TIMING] URL: ${url}\n`);
    
    // Esperar un poco para asegurar que el servidor está listo
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Request 1: "cold-ish" (primero tras arrancar)
    console.log('[TIMING] Request 1 (cold-ish)...');
    const result1 = await measureRequest();
    console.log(`[TIMING] Request 1: status=${result1.status}, duration=${result1.duration}ms, size=${result1.jsonSize} bytes`);
    if (result1.error) {
        console.error(`[TIMING] Request 1 ERROR: ${result1.error}`);
    }
    
    // Requests 2-6: "warm" (seguidos)
    const warmResults = [];
    for (let i = 2; i <= 6; i++) {
        console.log(`[TIMING] Request ${i} (warm)...`);
        const result = await measureRequest();
        warmResults.push(result);
        console.log(`[TIMING] Request ${i}: status=${result.status}, duration=${result.duration}ms, size=${result.jsonSize} bytes`);
        if (result.error) {
            console.error(`[TIMING] Request ${i} ERROR: ${result.error}`);
        }
        // Pequeña pausa entre requests para no saturar
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    // Análisis
    console.log('\n[TIMING] ========== ANÁLISIS ==========');
    console.log(`[TIMING] Request 1 (cold): ${result1.duration}ms`);
    
    const warmDurations = warmResults.map(r => r.duration);
    const avgWarm = warmDurations.reduce((a, b) => a + b, 0) / warmDurations.length;
    const minWarm = Math.min(...warmDurations);
    const maxWarm = Math.max(...warmDurations);
    
    console.log(`[TIMING] Requests 2-6 (warm): avg=${avgWarm.toFixed(0)}ms, min=${minWarm}ms, max=${maxWarm}ms`);
    
    // Criterio de decisión
    console.log('\n[TIMING] ========== DIAGNÓSTICO ==========');
    if (result1.duration > 10000 && avgWarm < 2000) {
        console.log('[TIMING] ✅ CASO A (WARMUP): Primer request lento, siguientes rápidos');
        console.log('[TIMING]    Solución: Pre-warm en tests antes de usar el endpoint');
    } else if (result1.duration > 10000 || avgWarm > 10000) {
        console.log('[TIMING] ❌ CASO B (SIEMPRE LENTO): Múltiples requests > 10s');
        console.log('[TIMING]    Solución: Instrumentar backend y optimizar cuello de botella');
    } else {
        console.log('[TIMING] ⚠️  CASO INTERMEDIO: Algunos requests lentos pero no consistentemente > 10s');
        console.log('[TIMING]    Revisar logs del backend para identificar picos ocasionales');
    }
    
    console.log('\n[TIMING] ========== RESUMEN ==========');
    console.log(`[TIMING] Cold request: ${result1.duration}ms`);
    console.log(`[TIMING] Warm requests: ${warmDurations.join(', ')}ms`);
    console.log(`[TIMING] Promedio warm: ${avgWarm.toFixed(0)}ms`);
}

main().catch(error => {
    console.error('[TIMING] Error fatal:', error);
    process.exit(1);
});
