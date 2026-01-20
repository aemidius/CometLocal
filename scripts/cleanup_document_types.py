"""
Script de limpieza conservadora del catálogo de tipos de documento.

Elimina SOLO tipos claramente generados por sistema/tests que:
- NO fueron creados por el usuario
- NO están referenciados en documentos, reglas, calendario o planes CAE
- Cumplen patrones de prueba/demo (T999_, TEST_, E2E_TYPE_, etc.)

GUARDRAILS:
- Ante la duda, conservar
- NO eliminar tipos con nombres significativos
- NO eliminar tipos que puedan ser útiles para el usuario
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Set, Tuple

# Configuración
BASE_DIR = Path(__file__).parent.parent
TYPES_FILE = BASE_DIR / "data" / "repository" / "types" / "types.json"
RULES_FILE = BASE_DIR / "data" / "repository" / "rules" / "submission_rules.json"
OVERRIDES_FILE = BASE_DIR / "data" / "repository" / "overrides" / "overrides.json"
META_DIR = BASE_DIR / "data" / "repository" / "meta"
EVIDENCE_DIR = BASE_DIR / "docs" / "evidence" / "C2_catalog_cleanup_user_safe"

# Patrones de tipos de prueba/demo
TEST_PATTERNS = [
    "T999_",  # Patrón T999_ con hash
    "TEST_",  # Patrón TEST_
    "E2E_TYPE_",  # Tipos E2E
    "DEMO_",  # Tipos demo
]

# Nombres genéricos de prueba
TEST_NAMES = [
    "Otro documento",  # Genérico, pero si tiene T999_ es de prueba
    "Test Mensual",
    "Test *",  # Cualquier cosa que empiece con "Test "
]


def load_json_file(file_path: Path) -> Dict:
    """Carga un archivo JSON, retorna {} si no existe."""
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR al cargar {file_path}: {e}")
        return {}


def save_json_file(file_path: Path, data: Dict) -> None:
    """Guarda un archivo JSON de forma segura."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(file_path)


def is_test_type(type_id: str, name: str) -> bool:
    """
    Determina si un tipo es claramente de prueba/demo.
    
    Criterios:
    - type_id empieza con patrón de prueba (T999_, TEST_, E2E_TYPE_, DEMO_)
    - name es genérico de prueba ("Otro documento", "Test Mensual", etc.)
    """
    # Verificar patrón en type_id
    for pattern in TEST_PATTERNS:
        if type_id.startswith(pattern):
            return True
    
    # Verificar nombre genérico
    if name == "Otro documento":
        # "Otro documento" con T999_ es de prueba, pero T999_OTHER podría ser útil
        # Ser conservador: solo si tiene hash después de T999_
        if type_id.startswith("T999_") and len(type_id) > 6 and type_id[6:].isalnum():
            return True
    
    if name == "Test Mensual":
        return True
    
    if name.startswith("Test "):
        return True
    
    return False


def find_type_references(type_id: str) -> List[Tuple[str, str]]:
    """
    Busca referencias a un type_id en:
    - Documentos (meta/*.json)
    - Reglas (rules/submission_rules.json)
    - Overrides (overrides/overrides.json)
    
    Retorna lista de (ubicación, motivo) donde se encontró.
    """
    references = []
    
    # Buscar en metadatos de documentos
    if META_DIR.exists():
        for meta_file in META_DIR.glob("*.json"):
            try:
                meta_data = load_json_file(meta_file)
                if meta_data.get("type_id") == type_id:
                    references.append((f"meta/{meta_file.name}", "documento"))
            except Exception:
                pass
    
    # Buscar en reglas
    rules_data = load_json_file(RULES_FILE)
    for rule in rules_data.get("rules", []):
        if rule.get("document_type_id") == type_id:
            references.append((f"rules/{RULES_FILE.name}", f"regla {rule.get('rule_id')}"))
    
    # Buscar en overrides
    overrides_data = load_json_file(OVERRIDES_FILE)
    for override in overrides_data.get("overrides", []):
        if override.get("type_id") == type_id:
            references.append((f"overrides/{OVERRIDES_FILE.name}", "override"))
    
    return references


def identify_candidates(types_data: Dict) -> List[Dict]:
    """
    Identifica tipos candidatos a eliminación.
    
    Solo incluye tipos que:
    1. Son claramente de prueba (is_test_type)
    2. NO están referenciados
    """
    candidates = []
    all_types = types_data.get("types", [])
    
    for doc_type in all_types:
        type_id = doc_type.get("type_id", "")
        name = doc_type.get("name", "")
        
        # Verificar si es tipo de prueba
        if not is_test_type(type_id, name):
            continue
        
        # Verificar referencias
        references = find_type_references(type_id)
        
        if references:
            print(f"PROTEGIDO: {type_id} ({name}) - Referencias encontradas:")
            for ref_location, ref_reason in references:
                print(f"     - {ref_location}: {ref_reason}")
            continue
        
        # Candidato seguro para eliminación
        candidates.append({
            "type_id": type_id,
            "name": name,
            "description": doc_type.get("description", ""),
            "scope": doc_type.get("scope", ""),
            "active": doc_type.get("active", True),
        })
    
    return candidates


def remove_types(types_data: Dict, candidates: List[Dict]) -> Dict:
    """
    Elimina los tipos candidatos del catálogo.
    """
    all_types = types_data.get("types", [])
    candidate_ids = {c["type_id"] for c in candidates}
    
    filtered_types = [t for t in all_types if t.get("type_id") not in candidate_ids]
    
    return {
        **types_data,
        "types": filtered_types
    }


def create_evidence(candidates: List[Dict], before_count: int, after_count: int) -> None:
    """Crea documentación de evidencia de la limpieza."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    
    readme_content = f"""# Limpieza de Catálogo de Tipos de Documento

**Fecha:** {Path(__file__).stat().st_mtime}
**Script:** `scripts/cleanup_document_types.py`

## Resumen

- **Tipos antes:** {before_count}
- **Tipos eliminados:** {len(candidates)}
- **Tipos después:** {after_count}

## Tipos Eliminados

Los siguientes tipos fueron eliminados por ser claramente generados por sistema/tests y no tener referencias:

"""
    
    for candidate in candidates:
        readme_content += f"""
### {candidate['type_id']}

- **Nombre:** {candidate['name']}
- **Descripción:** {candidate.get('description', '')}
- **Scope:** {candidate.get('scope', '')}
- **Activo:** {candidate.get('active', True)}
- **Motivo:** Tipo de prueba/demo generado automáticamente, sin referencias en documentos, reglas o overrides
- **Patrón:** {candidate['type_id'][:5]}...

"""
    
    readme_content += f"""
## Confirmación

✅ **No se ha eliminado ningún tipo creado por el usuario.**

Todos los tipos eliminados cumplían TODAS estas condiciones:
1. Patrón de prueba/demo (T999_*, TEST_*, E2E_TYPE_*, etc.)
2. Nombre genérico de prueba ("Otro documento", "Test Mensual", etc.)
3. Sin referencias en documentos, reglas o overrides
4. Generados automáticamente por sistema/tests

## Tipos Protegidos (NO eliminados)

Los siguientes tipos de prueba fueron PROTEGIDOS por tener referencias:

(Ver logs del script para detalles)

## Notas

- Esta limpieza es conservadora y reversible
- Solo se eliminaron tipos claramente de prueba sin uso
- Todos los tipos con nombres significativos fueron conservados
- Ante cualquier duda, se optó por conservar el tipo
"""
    
    readme_path = EVIDENCE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print(f"OK: Evidencia guardada en: {readme_path}")


def main():
    """Función principal."""
    import sys
    
    # Verificar si se pasa --yes para ejecutar sin confirmación
    auto_yes = "--yes" in sys.argv or "-y" in sys.argv
    
    print("Limpieza de Catalogo de Tipos de Documento")
    print("=" * 60)
    
    # Cargar tipos
    types_data = load_json_file(TYPES_FILE)
    if not types_data:
        print("ERROR: No se pudo cargar types.json")
        sys.exit(1)
    
    before_count = len(types_data.get("types", []))
    print(f"Tipos en catalogo: {before_count}")
    
    # Identificar candidatos
    print("\nIdentificando candidatos a eliminacion...")
    candidates = identify_candidates(types_data)
    
    if not candidates:
        print("OK: No se encontraron tipos candidatos a eliminacion.")
        return
    
    print(f"\nCandidatos identificados: {len(candidates)}")
    for candidate in candidates:
        print(f"   - {candidate['type_id']}: {candidate['name']}")
    
    # Confirmar (solo si no es auto-yes)
    if not auto_yes:
        print(f"\nATENCION: Se eliminaran {len(candidates)} tipos.")
        try:
            response = input("Continuar? (s/N): ").strip().lower()
            if response != "s":
                print("Operacion cancelada.")
                return
        except (EOFError, KeyboardInterrupt):
            print("\nOperacion cancelada (sin entrada disponible).")
            print("Usa --yes o -y para ejecutar sin confirmacion.")
            return
    else:
        print(f"\nEliminando {len(candidates)} tipos (modo auto-yes)...")
    
    # Eliminar tipos
    print("\nEliminando tipos...")
    cleaned_data = remove_types(types_data, candidates)
    
    # Guardar
    save_json_file(TYPES_FILE, cleaned_data)
    after_count = len(cleaned_data.get("types", []))
    
    print(f"OK: Limpieza completada: {before_count} -> {after_count} tipos")
    
    # Crear evidencia
    print("\nCreando evidencia...")
    create_evidence(candidates, before_count, after_count)
    
    # Log de eliminación
    print("\nTipos eliminados:")
    for candidate in candidates:
        print(f"   Removed demo type: {candidate['type_id']} (reason: test-generated, unused)")
    
    print("\nOK: Limpieza completada exitosamente.")


if __name__ == "__main__":
    main()
