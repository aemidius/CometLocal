/**
 * SPRINT C2.9.23: Script para parsear y encontrar errores de sintaxis en repository_v3.html
 * Extrae el script inline y lo compila para detectar errores de parse
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'frontend', 'repository_v3.html');

console.log(`[PARSE] Leyendo ${htmlPath}...`);

const htmlContent = fs.readFileSync(htmlPath, 'utf8');

// Extraer todos los scripts inline (sin src)
const scriptRegex = /<script(?![^>]*\ssrc=)([^>]*)>([\s\S]*?)<\/script>/gi;
const scripts = [];
let match;

while ((match = scriptRegex.exec(htmlContent)) !== null) {
    const scriptContent = match[2];
    const scriptAttrs = match[1];
    
    // Solo procesar scripts que no sean externos
    if (!scriptAttrs.includes('src=')) {
        scripts.push({
            content: scriptContent,
            startIndex: match.index,
            fullMatch: match[0]
        });
    }
}

console.log(`[PARSE] Encontrados ${scripts.length} scripts inline`);

// Procesar cada script
for (let i = 0; i < scripts.length; i++) {
    const script = scripts[i];
    console.log(`\n[PARSE] Procesando script ${i + 1}/${scripts.length}...`);
    console.log(`[PARSE] Longitud: ${script.content.length} caracteres`);
    
    try {
        // Intentar compilar con vm.Script
        const scriptObj = new vm.Script(script.content, {
            filename: 'repository_v3.html',
            displayErrors: true
        });
        
        console.log(`[PARSE] ✅ Script ${i + 1} compilado correctamente (sin errores de sintaxis)`);
        
    } catch (error) {
        console.error(`\n[PARSE] ❌ ERROR en script ${i + 1}:`);
        console.error(`[PARSE] Error name: ${error.name}`);
        console.error(`[PARSE] Error message: ${error.message}`);
        
        if (error.stack) {
            console.error(`[PARSE] Stack:\n${error.stack}`);
        }
        
        // Intentar extraer línea y columna del error
        let errorLine = null;
        let errorCol = null;
        
        // Buscar en el mensaje
        const lineMatch = error.message.match(/line (\d+)/i) || error.message.match(/:(\d+):/);
        const colMatch = error.message.match(/column (\d+)/i) || error.message.match(/:(\d+):(\d+)/);
        
        if (lineMatch) {
            errorLine = parseInt(lineMatch[1]);
        }
        if (colMatch && colMatch.length > 2) {
            errorCol = parseInt(colMatch[2]);
        } else if (colMatch) {
            errorCol = parseInt(colMatch[1]);
        }
        
        // Buscar en el stack
        if (!errorLine && error.stack) {
            const stackLineMatch = error.stack.match(/repository_v3\.html:(\d+):(\d+)/);
            if (stackLineMatch) {
                errorLine = parseInt(stackLineMatch[1]);
                errorCol = parseInt(stackLineMatch[2]);
            }
        }
        
        if (errorLine) {
            console.error(`[PARSE] Línea del error: ${errorLine}`);
        }
        if (errorCol) {
            console.error(`[PARSE] Columna del error: ${errorCol}`);
        }
        
        // Mostrar contexto alrededor del error
        if (errorLine) {
            const lines = script.content.split('\n');
            const startLine = Math.max(0, errorLine - 15);
            const endLine = Math.min(lines.length - 1, errorLine + 15);
            
            console.error(`\n[PARSE] Contexto alrededor de la línea ${errorLine} (líneas ${startLine + 1}-${endLine + 1}):`);
            console.error('─'.repeat(80));
            
            for (let lineNum = startLine; lineNum <= endLine; lineNum++) {
                const line = lines[lineNum];
                const marker = lineNum === errorLine - 1 ? ' >>> ' : '     ';
                console.error(`${marker}${String(lineNum + 1).padStart(4, ' ')} | ${line}`);
            }
            
            console.error('─'.repeat(80));
        } else {
            // Si no tenemos línea exacta, mostrar las primeras líneas del script
            console.error(`\n[PARSE] Primeras 30 líneas del script:`);
            const lines = script.content.split('\n').slice(0, 30);
            lines.forEach((line, idx) => {
                console.error(`     ${String(idx + 1).padStart(4, ' ')} | ${line}`);
            });
        }
        
        // Salir con error
        process.exit(1);
    }
}

console.log(`\n[PARSE] ✅ Todos los scripts compilados correctamente (sin errores de sintaxis)`);
console.log(`[PARSE] OK`);
