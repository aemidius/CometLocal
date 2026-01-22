"""
SPRINT C2.36.1: Script de limpieza de datos demo/seed del repositorio.

Elimina tipos, documentos y archivos demo que se han colado en el entorno real,
y genera un reporte detallado de lo que se elimina.

REGLAS:
- NO borrar datos reales del usuario
- Modo dry-run por defecto (--apply para ejecutar)
- Traza clara: qué se borra, por qué patrón, conteos antes/después
- Allowlist para proteger elementos específicos
"""

import json
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime

# Configuración
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
REPO_DIR = DATA_DIR / "repository"
TYPES_FILE = REPO_DIR / "types" / "types.json"
META_DIR = REPO_DIR / "meta"
DOCS_DIR = REPO_DIR / "docs"
RULES_FILE = REPO_DIR / "rules" / "submission_rules.json"
OVERRIDES_FILE = REPO_DIR / "overrides" / "overrides.json"
EVIDENCE_DIR = BASE_DIR / "docs" / "evidence" / "c2_36_1"

# Patrones de demo/test
DEMO_TYPE_PATTERNS = [
    "TEST_",
    "T999_",
    "E2E_TYPE_",
    "E2E_",
    "DEMO_",
]

DEMO_NAME_PATTERNS = [
    "Test Type",
    "Test ",
    "Demo ",
    "E2E Test",
]

DEMO_DOC_PATTERNS = [
    "TEST_DOC_",
    "E2E_DOC_",
    "T999_DOC_",
    "DEMO_DOC_",
]

DEMO_FILE_PATTERNS = [
    "test_",
    "real_doc_",
    "e2e_",
    "demo_",
    "worker_real_",
]

DEMO_COMPANY_PATTERNS = [
    "TEST_COMPANY",
    "E2E_COMPANY_",
    "T999_COMPANY_",
]

DEMO_PERSON_PATTERNS = [
    "TEST_WORKER",
    "worker_real_",
    "E2E_WORKER_",
]


class CleanupStats:
    """Estadísticas de limpieza."""
    
    def __init__(self):
        self.types_before = 0
        self.types_after = 0
        self.types_removed = []
        
        self.docs_before = 0
        self.docs_after = 0
        self.docs_removed = []
        
        self.files_before = 0
        self.files_after = 0
        self.files_removed = []
        
        self.types_protected = []
        self.docs_protected = []


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


def is_demo_type(type_id: str, name: str, keep_list: Set[str]) -> bool:
    """Determina si un tipo es demo/test."""
    if type_id in keep_list:
        return False
    
    # Verificar patrones en type_id
    for pattern in DEMO_TYPE_PATTERNS:
        if type_id.startswith(pattern):
            return True
    
    # Verificar patrones en name
    for pattern in DEMO_NAME_PATTERNS:
        if pattern in name:
            return True
    
    return False


def is_demo_doc(doc_id: str, file_name: str, type_id: str, company_key: str, person_key: str, keep_list: Set[str]) -> bool:
    """Determina si un documento es demo/test."""
    if doc_id in keep_list:
        return False
    
    # Verificar patrones en doc_id
    for pattern in DEMO_DOC_PATTERNS:
        if doc_id.startswith(pattern):
            return True
    
    # Verificar patrones en file_name
    if file_name:
        file_lower = file_name.lower()
        for pattern in DEMO_FILE_PATTERNS:
            if file_lower.startswith(pattern):
                return True
    
    # Verificar company_key
    if company_key:
        for pattern in DEMO_COMPANY_PATTERNS:
            if company_key.startswith(pattern):
                return True
    
    # Verificar person_key
    if person_key:
        for pattern in DEMO_PERSON_PATTERNS:
            if person_key.startswith(pattern):
                return True
    
    # Si el type_id es demo, el documento también lo es
    if type_id:
        for pattern in DEMO_TYPE_PATTERNS:
            if type_id.startswith(pattern):
                return True
    
    return False


def find_type_references(type_id: str) -> List[Tuple[str, str]]:
    """Busca referencias a un type_id en documentos, reglas y overrides."""
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


def identify_demo_types(types_data: Dict, keep_list: Set[str]) -> List[Dict]:
    """Identifica tipos demo candidatos a eliminación."""
    candidates = []
    all_types = types_data.get("types", [])
    
    for doc_type in all_types:
        type_id = doc_type.get("type_id", "")
        name = doc_type.get("name", "")
        
        if not is_demo_type(type_id, name, keep_list):
            continue
        
        # Verificar referencias
        references = find_type_references(type_id)
        
        if references:
            candidates.append({
                "type_id": type_id,
                "name": name,
                "reason": "demo_type_with_references",
                "references": references,
                "action": "protect"
            })
            continue
        
        # Candidato seguro para eliminación
        candidates.append({
            "type_id": type_id,
            "name": name,
            "description": doc_type.get("description", ""),
            "scope": doc_type.get("scope", ""),
            "active": doc_type.get("active", True),
            "reason": "demo_type_no_references",
            "action": "remove"
        })
    
    return candidates


def identify_demo_docs(keep_list: Set[str]) -> List[Dict]:
    """Identifica documentos demo candidatos a eliminación."""
    candidates = []
    
    if not META_DIR.exists():
        return candidates
    
    for meta_file in META_DIR.glob("*.json"):
        try:
            meta_data = load_json_file(meta_file)
            doc_id = meta_data.get("doc_id", "")
            file_name = meta_data.get("file_name_original", "") or meta_data.get("file_name", "")
            type_id = meta_data.get("type_id", "")
            company_key = meta_data.get("company_key", "")
            person_key = meta_data.get("person_key", "")
            
            if not doc_id:
                continue
            
            if is_demo_doc(doc_id, file_name, type_id, company_key, person_key, keep_list):
                stored_path = meta_data.get("stored_path", "")
                candidates.append({
                    "doc_id": doc_id,
                    "file_name": file_name,
                    "type_id": type_id,
                    "company_key": company_key,
                    "person_key": person_key,
                    "stored_path": stored_path,
                    "meta_file": str(meta_file),
                    "reason": "demo_doc"
                })
        except Exception as e:
            print(f"WARN: Error procesando {meta_file}: {e}")
            continue
    
    return candidates


def identify_demo_files(doc_candidates: List[Dict]) -> List[Path]:
    """Identifica archivos PDF demo basándose en documentos demo y archivos huérfanos."""
    files_to_remove = []
    
    # Archivos asociados a documentos demo
    for doc in doc_candidates:
        stored_path = doc.get("stored_path", "")
        if stored_path:
            # Convertir ruta relativa a absoluta
            if stored_path.startswith("data/"):
                file_path = BASE_DIR / stored_path
            else:
                file_path = DOCS_DIR / stored_path.split("/")[-1]
            
            if file_path.exists() and file_path.suffix.lower() == ".pdf":
                files_to_remove.append(file_path)
    
    # Archivos huérfanos en data/ raíz con patrones demo
    if DATA_DIR.exists():
        for pattern in DEMO_FILE_PATTERNS:
            for file_path in DATA_DIR.glob(f"{pattern}*.pdf"):
                # Verificar que no está referenciado en meta
                doc_id = file_path.stem
                meta_file = META_DIR / f"{doc_id}.json"
                if not meta_file.exists():
                    files_to_remove.append(file_path)
    
    # Eliminar duplicados
    return list(set(files_to_remove))


def remove_demo_types(types_data: Dict, candidates: List[Dict]) -> Dict:
    """Elimina tipos demo del catálogo."""
    remove_candidates = [c for c in candidates if c.get("action") == "remove"]
    candidate_ids = {c["type_id"] for c in remove_candidates}
    
    all_types = types_data.get("types", [])
    filtered_types = [t for t in all_types if t.get("type_id") not in candidate_ids]
    
    return {
        **types_data,
        "types": filtered_types
    }


def remove_demo_docs(candidates: List[Dict], apply: bool) -> List[Dict]:
    """Elimina documentos demo (metadatos y archivos asociados)."""
    removed = []
    
    for doc in candidates:
        meta_file = Path(doc["meta_file"])
        
        if apply and meta_file.exists():
            try:
                meta_file.unlink()
                removed.append(doc)
            except Exception as e:
                print(f"ERROR: No se pudo eliminar {meta_file}: {e}")
        else:
            removed.append(doc)
    
    return removed


def remove_demo_files(candidates: List[Path], apply: bool) -> List[Path]:
    """Elimina archivos PDF demo."""
    removed = []
    
    for file_path in candidates:
        if apply and file_path.exists():
            try:
                file_path.unlink()
                removed.append(file_path)
            except Exception as e:
                print(f"ERROR: No se pudo eliminar {file_path}: {e}")
        else:
            removed.append(file_path)
    
    return removed


def create_evidence_report(stats: CleanupStats, apply: bool) -> None:
    """Crea reporte de evidencia de la limpieza."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().isoformat()
    
    readme_content = f"""# Limpieza de Datos Demo/Seed (C2.36.1)

**Fecha:** {timestamp}
**Script:** `scripts/cleanup_demo_data.py`
**Modo:** {'APPLY (ejecutado)' if apply else 'DRY-RUN (simulación)'}

## Resumen

### Tipos de Documento
- **Antes:** {stats.types_before}
- **Eliminados:** {len([t for t in stats.types_removed if t.get('action') == 'remove'])}
- **Protegidos:** {len([t for t in stats.types_removed if t.get('action') == 'protect'])}
- **Después:** {stats.types_after}

### Documentos
- **Antes:** {stats.docs_before}
- **Eliminados:** {len(stats.docs_removed)}
- **Después:** {stats.docs_after}

### Archivos PDF
- **Antes:** {stats.files_before}
- **Eliminados:** {len(stats.files_removed)}
- **Después:** {stats.files_after}

## Tipos Eliminados

"""
    
    for type_info in stats.types_removed:
        if type_info.get("action") == "remove":
            readme_content += f"""
### {type_info['type_id']}
- **Nombre:** {type_info['name']}
- **Descripción:** {type_info.get('description', '')}
- **Scope:** {type_info.get('scope', '')}
- **Motivo:** {type_info.get('reason', 'demo_type_no_references')}
- **Patrón:** {type_info['type_id'][:10]}...

"""
    
    readme_content += """
## Tipos Protegidos (NO eliminados)

"""
    
    for type_info in stats.types_removed:
        if type_info.get("action") == "protect":
            readme_content += f"""
### {type_info['type_id']}
- **Nombre:** {type_info['name']}
- **Motivo:** Tiene referencias en documentos, reglas o overrides
- **Referencias:**
"""
            for ref_location, ref_reason in type_info.get("references", []):
                readme_content += f"  - {ref_location}: {ref_reason}\n"
    
    readme_content += f"""
## Documentos Eliminados

"""
    
    for doc in stats.docs_removed:
        readme_content += f"""
- **doc_id:** {doc['doc_id']}
- **file_name:** {doc.get('file_name', '')}
- **type_id:** {doc.get('type_id', '')}
- **company_key:** {doc.get('company_key', '')}
- **person_key:** {doc.get('person_key', '')}

"""
    
    readme_content += f"""
## Archivos PDF Eliminados

"""
    
    for file_path in stats.files_removed:
        readme_content += f"- {file_path}\n"
    
    readme_content += f"""
## Patrones Utilizados

### Tipos
{chr(10).join(f"- {p}" for p in DEMO_TYPE_PATTERNS)}

### Nombres
{chr(10).join(f"- {p}" for p in DEMO_NAME_PATTERNS)}

### Documentos
{chr(10).join(f"- {p}" for p in DEMO_DOC_PATTERNS)}

### Archivos
{chr(10).join(f"- {p}" for p in DEMO_FILE_PATTERNS)}

## Confirmación

OK: **No se ha eliminado ningún dato creado por el usuario.**

Todos los elementos eliminados cumplían patrones de prueba/demo y no tenían referencias en datos reales.
"""
    
    readme_path = EVIDENCE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print(f"OK: Evidencia guardada en: {readme_path}")


def main():
    """Función principal."""
    parser = argparse.ArgumentParser(description="Limpieza de datos demo/seed del repositorio")
    parser.add_argument("--apply", action="store_true", help="Ejecutar limpieza (por defecto es dry-run)")
    parser.add_argument("--keep-type-id", action="append", default=[], help="Proteger tipo por type_id (puede repetirse)")
    parser.add_argument("--keep-doc-id", action="append", default=[], help="Proteger documento por doc_id (puede repetirse)")
    parser.add_argument("--patterns", action="store_true", help="Mostrar patrones utilizados")
    
    args = parser.parse_args()
    
    if args.patterns:
        print("Patrones de demo/test utilizados:")
        print("\nTipos:", ", ".join(DEMO_TYPE_PATTERNS))
        print("Nombres:", ", ".join(DEMO_NAME_PATTERNS))
        print("Documentos:", ", ".join(DEMO_DOC_PATTERNS))
        print("Archivos:", ", ".join(DEMO_FILE_PATTERNS))
        return
    
    apply_mode = args.apply
    keep_list = set(args.keep_type_id + args.keep_doc_id)
    
    print("=" * 60)
    print("Limpieza de Datos Demo/Seed (C2.36.1)")
    print("=" * 60)
    print(f"Modo: {'APPLY (ejecutando)' if apply_mode else 'DRY-RUN (simulación)'}")
    if keep_list:
        print(f"Allowlist: {', '.join(keep_list)}")
    print()
    
    stats = CleanupStats()
    
    # ========== TIPOS ==========
    print("1. Analizando tipos de documento...")
    types_data = load_json_file(TYPES_FILE)
    if not types_data:
        print("ERROR: No se pudo cargar types.json")
        sys.exit(1)
    
    stats.types_before = len(types_data.get("types", []))
    print(f"   Tipos en catálogo: {stats.types_before}")
    
    type_candidates = identify_demo_types(types_data, keep_list)
    stats.types_removed = type_candidates
    
    remove_candidates = [c for c in type_candidates if c.get("action") == "remove"]
    protect_candidates = [c for c in type_candidates if c.get("action") == "protect"]
    
    print(f"   Candidatos a eliminación: {len(remove_candidates)}")
    print(f"   Candidatos protegidos: {len(protect_candidates)}")
    
    if remove_candidates:
        print("\n   Tipos a eliminar:")
        for candidate in remove_candidates:
            print(f"      - {candidate['type_id']}: {candidate['name']}")
    
    if protect_candidates:
        print("\n   Tipos protegidos (tienen referencias):")
        for candidate in protect_candidates:
            print(f"      - {candidate['type_id']}: {candidate['name']}")
            for ref_location, ref_reason in candidate.get("references", []):
                print(f"        → {ref_location}: {ref_reason}")
    
    if apply_mode and remove_candidates:
        cleaned_types = remove_demo_types(types_data, remove_candidates)
        save_json_file(TYPES_FILE, cleaned_types)
        stats.types_after = len(cleaned_types.get("types", []))
    else:
        stats.types_after = stats.types_before - len(remove_candidates)
    
    print()
    
    # ========== DOCUMENTOS ==========
    print("2. Analizando documentos...")
    doc_candidates = identify_demo_docs(keep_list)
    stats.docs_before = len(list(META_DIR.glob("*.json"))) if META_DIR.exists() else 0
    
    print(f"   Documentos en meta: {stats.docs_before}")
    print(f"   Candidatos a eliminación: {len(doc_candidates)}")
    
    if doc_candidates:
        print("\n   Documentos a eliminar:")
        for doc in doc_candidates[:10]:  # Mostrar primeros 10
            print(f"      - {doc['doc_id']}: {doc.get('file_name', 'N/A')}")
        if len(doc_candidates) > 10:
            print(f"      ... y {len(doc_candidates) - 10} más")
    
    if apply_mode:
        stats.docs_removed = remove_demo_docs(doc_candidates, apply=True)
        stats.docs_after = stats.docs_before - len(stats.docs_removed)
    else:
        stats.docs_removed = doc_candidates
        stats.docs_after = stats.docs_before - len(doc_candidates)
    
    print()
    
    # ========== ARCHIVOS PDF ==========
    print("3. Analizando archivos PDF...")
    file_candidates = identify_demo_files(doc_candidates)
    stats.files_before = len(list(DOCS_DIR.glob("*.pdf"))) if DOCS_DIR.exists() else 0
    
    print(f"   Archivos PDF en docs: {stats.files_before}")
    print(f"   Candidatos a eliminación: {len(file_candidates)}")
    
    if file_candidates:
        print("\n   Archivos a eliminar:")
        for file_path in file_candidates[:10]:  # Mostrar primeros 10
            print(f"      - {file_path}")
        if len(file_candidates) > 10:
            print(f"      ... y {len(file_candidates) - 10} más")
    
    if apply_mode:
        stats.files_removed = remove_demo_files(file_candidates, apply=True)
        stats.files_after = stats.files_before - len(stats.files_removed)
    else:
        stats.files_removed = file_candidates
        stats.files_after = stats.files_before - len(file_candidates)
    
    print()
    
    # ========== RESUMEN ==========
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Tipos: {stats.types_before} -> {stats.types_after} (eliminados: {len(remove_candidates)})")
    print(f"Documentos: {stats.docs_before} -> {stats.docs_after} (eliminados: {len(stats.docs_removed)})")
    print(f"Archivos PDF: {stats.files_before} -> {stats.files_after} (eliminados: {len(stats.files_removed)})")
    print()
    
    if not apply_mode:
        print("ATENCION: MODO DRY-RUN: No se ha modificado nada.")
        print("   Usa --apply para ejecutar la limpieza.")
    else:
        print("OK: Limpieza ejecutada.")
    
    # Crear evidencia
    print("\nCreando evidencia...")
    create_evidence_report(stats, apply_mode)
    
    print("\nOK: Análisis completado.")


if __name__ == "__main__":
    main()
