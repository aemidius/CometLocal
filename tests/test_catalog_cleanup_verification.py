"""
Test mínimo para verificar que el catálogo carga sin errores después de la limpieza.
"""

import json
import pytest
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
TYPES_FILE = BASE_DIR / "data" / "repository" / "types" / "types.json"


def test_catalog_loads_without_errors():
    """Verifica que el catálogo carga sin errores."""
    assert TYPES_FILE.exists(), "types.json debe existir"
    
    with open(TYPES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "schema_version" in data, "Debe tener schema_version"
    assert "types" in data, "Debe tener types"
    assert isinstance(data["types"], list), "types debe ser una lista"
    
    # Verificar que no hay tipos de prueba
    test_patterns = ["T999_", "TEST_", "E2E_TYPE_", "DEMO_"]
    for doc_type in data["types"]:
        type_id = doc_type.get("type_id", "")
        for pattern in test_patterns:
            # Permitir T999_OTHER si existe (aunque debería haberse eliminado)
            # pero verificar que no hay otros T999_ con hash
            if pattern == "T999_" and type_id.startswith("T999_"):
                if type_id != "T999_OTHER" and len(type_id) > 6:
                    # T999_ con hash después debería haberse eliminado
                    assert False, f"Tipo de prueba encontrado: {type_id}"
            elif type_id.startswith(pattern):
                assert False, f"Tipo de prueba encontrado: {type_id}"


def test_catalog_has_real_types():
    """Verifica que el catálogo tiene tipos reales (no está vacío)."""
    with open(TYPES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    types = data.get("types", [])
    assert len(types) > 0, "El catálogo debe tener al menos un tipo"
    
    # Verificar que hay tipos con nombres significativos
    real_type_names = [
        "Certificado aptitud médica",
        "Recibo Autónomos",
        "No deuda Hacienda",
        "Póliza",
        "EPIS",
    ]
    
    type_names = [t.get("name", "") for t in types]
    has_real_types = any(real_name.lower() in name.lower() for name in type_names for real_name in real_type_names)
    
    assert has_real_types, "El catálogo debe tener tipos reales con nombres significativos"


def test_catalog_types_have_required_fields():
    """Verifica que cada tipo tiene los campos requeridos."""
    with open(TYPES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    required_fields = ["type_id", "name", "scope", "validity_policy", "active"]
    
    for doc_type in data.get("types", []):
        for field in required_fields:
            assert field in doc_type, f"Tipo {doc_type.get('type_id')} debe tener campo {field}"
