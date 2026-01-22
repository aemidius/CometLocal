/**
 * SPRINT C2.35.10.1: Script para verificar que el JavaScript en repository_v3.html es válido.
 * 
 * Detecta SyntaxError antes de que llegue al navegador.
 */

const fs = require('fs');
const path = require('path');

const HTML_FILE = path.join(__dirname, '..', 'frontend', 'repository_v3.html');

console.log('[check_frontend_syntax] Verificando sintaxis de JavaScript en repository_v3.html...');

try {
    const htmlContent = fs.readFileSync(HTML_FILE, 'utf-8');
    
    // Extraer el contenido del script principal (el más grande, que suele ser el inline)
    // Buscar desde <script> hasta </script> de forma más robusta
    let scriptContent = '';
    const scriptStartMatch = htmlContent.match(/<script[^>]*>/i);
    const scriptEndMatch = htmlContent.match(/<\/script>/i);
    
    if (scriptStartMatch && scriptEndMatch) {
        const startIndex = scriptStartMatch.index + scriptStartMatch[0].length;
        const endIndex = scriptEndMatch.index;
        scriptContent = htmlContent.substring(startIndex, endIndex);
    } else {
        // Fallback: buscar todos los bloques script
        const scriptMatches = htmlContent.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
        if (scriptMatches && scriptMatches.length > 0) {
            // Tomar el script más grande (normalmente el principal)
            scriptMatches.forEach((scriptTag) => {
                const contentMatch = scriptTag.match(/<script[^>]*>([\s\S]*?)<\/script>/i);
                if (contentMatch && contentMatch[1] && contentMatch[1].length > scriptContent.length) {
                    scriptContent = contentMatch[1];
                }
            });
        }
    }
    
    if (!scriptContent || scriptContent.trim().length === 0) {
        console.error('[check_frontend_syntax] No se encontró contenido JavaScript en el HTML');
        process.exit(1);
    }
    
    console.log(`[check_frontend_syntax] Contenido JavaScript encontrado: ${scriptContent.length} caracteres`);
    
    let errorsFound = false;
    
    try {
        // Intentar parsear el JavaScript completo
        // Usar new Function para detectar SyntaxError sin ejecutar
        new Function(scriptContent);
        console.log('[check_frontend_syntax] ✅ Sintaxis JavaScript válida');
    } catch (err) {
        if (err instanceof SyntaxError) {
            console.error('[check_frontend_syntax] ❌ SyntaxError detectado');
            console.error(`[check_frontend_syntax] Mensaje: ${err.message}`);
            
            // Intentar extraer número de línea si está disponible
            if (err.stack) {
                const lineMatch = err.stack.match(/at.*:(\d+):(\d+)/);
                if (lineMatch) {
                    console.error(`[check_frontend_syntax] Línea aproximada: ${lineMatch[1]}, columna: ${lineMatch[2]}`);
                }
            }
            
            // Mostrar un fragmento del código problemático alrededor del error
            const lines = scriptContent.split('\n');
            if (lines.length > 0) {
                // Intentar encontrar la línea problemática
                const errorLineMatch = err.message.match(/line (\d+)/i) || err.message.match(/:(\d+):/);
                if (errorLineMatch) {
                    const errorLineNum = parseInt(errorLineMatch[1]) - 1;
                    const startLine = Math.max(0, errorLineNum - 5);
                    const endLine = Math.min(lines.length, errorLineNum + 5);
                    const problematicLines = lines.slice(startLine, endLine);
                    console.error(`[check_frontend_syntax] Líneas alrededor del error (${startLine + 1}-${endLine}):`);
                    problematicLines.forEach((line, idx) => {
                        const lineNum = startLine + idx + 1;
                        const marker = lineNum === errorLineNum + 1 ? '>>> ' : '    ';
                        console.error(`${marker}${lineNum}: ${line}`);
                    });
                } else {
                    // Mostrar las últimas líneas si no se puede determinar la línea exacta
                    const problematicLines = lines.slice(Math.max(0, lines.length - 20));
                    console.error(`[check_frontend_syntax] Últimas 20 líneas del script:`);
                    problematicLines.forEach((line, idx) => {
                        const lineNum = lines.length - problematicLines.length + idx + 1;
                        console.error(`    ${lineNum}: ${line}`);
                    });
                }
            }
            
            errorsFound = true;
        } else {
            // Otro tipo de error (no SyntaxError), puede ser por dependencias faltantes
            // No fallar en este caso, solo loguear
            console.warn(`[check_frontend_syntax] Error no relacionado con sintaxis: ${err.message}`);
        }
    }
    
    if (errorsFound) {
        console.error('[check_frontend_syntax] ❌ Se detectaron errores de sintaxis en el JavaScript');
        process.exit(1);
    }
    
    console.log('[check_frontend_syntax] ✅ Sintaxis JavaScript válida');
    process.exit(0);
    
} catch (err) {
    console.error('[check_frontend_syntax] Error al leer o procesar el archivo:', err.message);
    process.exit(1);
}
