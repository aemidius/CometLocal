#!/usr/bin/env node
/**
 * SPRINT B2: Guardrail para detectar esperas frágiles en tests E2E.
 * 
 * Este script falla si encuentra:
 * - waitForLoadState('networkidle')
 * - waitForSelector con 'page-ready'
 * - waitForTimeout(
 * 
 * en archivos tests/*.spec.js
 */

const fs = require('fs');
const path = require('path');

const TEST_DIR = path.join(__dirname, '..', 'tests');
const PATTERNS = [
    {
        pattern: /waitForLoadState\(['"]networkidle['"]\)/,
        message: 'waitForLoadState("networkidle") está prohibido. Usa gotoHash() y waitForTestId() en su lugar.'
    },
    {
        pattern: /waitForSelector.*page-ready/,
        message: 'waitForSelector con "page-ready" está prohibido. Usa gotoHash() que espera view-*-ready automáticamente.'
    },
    {
        pattern: /waitForTimeout\(/,
        message: 'waitForTimeout() está prohibido. Usa expect().toBeVisible() o waitForSelector() con data-testid específicos.'
    }
];

function findSpecFiles(dir) {
    const files = [];
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    
    for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            files.push(...findSpecFiles(fullPath));
        } else if (entry.isFile() && entry.name.endsWith('.spec.js')) {
            files.push(fullPath);
        }
    }
    
    return files;
}

function checkFile(filePath) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    const errors = [];
    
    PATTERNS.forEach(({ pattern, message }) => {
        lines.forEach((line, index) => {
            if (pattern.test(line)) {
                errors.push({
                    file: path.relative(process.cwd(), filePath),
                    line: index + 1,
                    match: line.trim(),
                    message
                });
            }
        });
    });
    
    return errors;
}

function main() {
    const specFiles = findSpecFiles(TEST_DIR);
    const allErrors = [];
    
    console.log(`[Guardrail] Revisando ${specFiles.length} archivos spec...\n`);
    
    specFiles.forEach(file => {
        const errors = checkFile(file);
        if (errors.length > 0) {
            allErrors.push(...errors);
        }
    });
    
    if (allErrors.length > 0) {
        console.error('❌ ENCONTRADAS ESPERAS FRÁGILES PROHIBIDAS:\n');
        allErrors.forEach(({ file, line, match, message }) => {
            console.error(`  ${file}:${line}`);
            console.error(`    ${match}`);
            console.error(`    → ${message}\n`);
        });
        console.error(`\nTotal: ${allErrors.length} violación(es) encontrada(s)`);
        process.exit(1);
    } else {
        console.log('✅ No se encontraron esperas frágiles prohibidas.');
        process.exit(0);
    }
}

main();

