"""
Tests unitarios para validar que la construcción de artifacts paths es robusta.

Evita errores de tipo "WindowsPath / NoneType" cuando se intenta hacer join con None.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from backend.shared.path_utils import safe_path_join, as_str
from backend.adapters.egestiona.page_contract_validator import PageContractError


def test_safe_path_join_with_none():
    """Test que safe_path_join devuelve None cuando part es None."""
    base = Path("data")
    result = safe_path_join(base, None)
    assert result is None


def test_safe_path_join_with_empty_string():
    """Test que safe_path_join devuelve None cuando part es string vacío."""
    base = Path("data")
    result = safe_path_join(base, "")
    assert result is None


def test_safe_path_join_with_valid_string():
    """Test que safe_path_join funciona correctamente con string válido."""
    base = Path("data")
    result = safe_path_join(base, "runs")
    assert result == Path("data/runs")
    assert isinstance(result, Path)


def test_safe_path_join_with_path():
    """Test que safe_path_join funciona correctamente con Path."""
    base = Path("data")
    part = Path("runs")
    result = safe_path_join(base, part)
    assert result == Path("data/runs")
    assert isinstance(result, Path)


def test_as_str_with_path():
    """Test que as_str convierte Path a string."""
    p = Path("data/runs/test.json")
    result = as_str(p)
    # En Windows puede usar backslashes, así que solo verificamos que es string y contiene las partes
    assert isinstance(result, str)
    assert "data" in result
    assert "runs" in result
    assert "test.json" in result


def test_as_str_with_none():
    """Test que as_str devuelve None cuando input es None."""
    result = as_str(None)
    assert result is None


def test_as_str_with_string():
    """Test que as_str devuelve string cuando input es string."""
    result = as_str("test")
    assert result == "test"
    assert isinstance(result, str)


def test_page_contract_error_evidence_paths_are_strings():
    """Test que PageContractError con evidence_paths contiene solo strings o None."""
    error = PageContractError(
        error_code="test_error",
        message="Test message",
        details={},
        evidence_paths={
            "screenshot": "runs/test/evidence/screenshot.png",
            "dump": None,
        }
    )
    
    # Verificar que evidence_paths es dict con strings o None
    assert isinstance(error.evidence_paths, dict)
    assert isinstance(error.evidence_paths.get("screenshot"), (str, type(None)))
    assert error.evidence_paths.get("dump") is None or isinstance(error.evidence_paths.get("dump"), str)
    
    # Verificar que no hay Path objects
    for key, value in error.evidence_paths.items():
        assert not isinstance(value, Path), f"evidence_paths['{key}'] es Path, debería ser str o None"


def test_artifacts_construction_with_none_components():
    """Test que la construcción de artifacts no falla con componentes None."""
    # Simular construcción de artifacts como en flows.py
    artifacts = {}
    
    # Simular evidence_paths con None
    evidence_paths = {
        "screenshot": None,
        "dump": "runs/test/dump.txt",
    }
    
    # Convertir a dict limpio (como en flows.py)
    from backend.shared.path_utils import as_str
    evidence_paths_clean = {}
    if evidence_paths:
        for key, value in evidence_paths.items():
            if value is not None:
                evidence_paths_clean[key] = as_str(value)
    
    artifacts["evidence"] = evidence_paths_clean if evidence_paths_clean else None
    
    # Verificar que no hay Path objects
    assert artifacts["evidence"] is not None
    assert isinstance(artifacts["evidence"], dict)
    for key, value in artifacts["evidence"].items():
        assert isinstance(value, str), f"artifacts['evidence']['{key}'] debería ser str, es {type(value)}"
    
    # Verificar que se puede serializar a JSON
    import json
    json_str = json.dumps(artifacts)
    assert "dump" in json_str
    assert "screenshot" not in json_str  # None no se incluye


def test_storage_state_path_construction_safe():
    """Test que la construcción de storage_state_path es segura."""
    from backend.shared.path_utils import safe_path_join, as_str
    
    DATA_DIR = Path("data")
    storage_state_rel = None  # Simular caso donde es None
    
    # Esto no debe fallar
    if storage_state_rel:
        storage_state_abs = safe_path_join(Path(DATA_DIR), storage_state_rel)
        if storage_state_abs:
            result = as_str(storage_state_abs)
        else:
            result = None
    else:
        result = None
    
    assert result is None
    
    # Test con valor válido
    storage_state_rel = "runs/test/storage_state.json"
    storage_state_abs = safe_path_join(Path(DATA_DIR), storage_state_rel)
    assert storage_state_abs is not None
    result = as_str(storage_state_abs)
    assert isinstance(result, str)
    assert "data" in result
    assert "runs" in result


def test_instrumentation_path_construction_safe():
    """Test que la construcción de instrumentation_path es segura."""
    from backend.shared.path_utils import safe_path_join, as_str
    from backend.config import DATA_DIR
    from pathlib import Path
    
    # Simular caso donde run_id existe pero instrumentation.json no
    run_id = "test_run_123"
    instrumentation_path = safe_path_join(Path(DATA_DIR) / "runs" / run_id / "evidence", "instrumentation.json")
    
    # No debe fallar aunque instrumentation_path sea None
    artifacts = {}
    if instrumentation_path and instrumentation_path.exists():
        artifacts["instrumentation_path"] = as_str(instrumentation_path.relative_to(Path(DATA_DIR)))
    else:
        # No incluir si no existe
        pass
    
    # Verificar que artifacts no tiene instrumentation_path si no existe
    assert "instrumentation_path" not in artifacts or isinstance(artifacts.get("instrumentation_path"), (str, type(None)))


def test_artifacts_response_no_path_objects():
    """Test que la respuesta de artifacts no contiene objetos Path."""
    from backend.shared.path_utils import safe_path_join, as_str
    from pathlib import Path
    
    # Simular construcción de artifacts como en flows.py
    artifacts = {}
    
    # Simular storage_state_path
    storage_state_rel = "runs/test/storage_state.json"
    storage_state_abs = safe_path_join(Path("data"), storage_state_rel)
    if storage_state_abs:
        artifacts["storage_state_path"] = as_str(storage_state_abs)
    
    # Verificar que todos los valores son strings o None, no Path
    for key, value in artifacts.items():
        assert isinstance(value, (str, type(None))), f"artifacts['{key}'] es {type(value)}, debería ser str o None"
        assert not isinstance(value, Path), f"artifacts['{key}'] es Path object, debería ser str"
    
    # Verificar que se puede serializar a JSON
    import json
    json_str = json.dumps(artifacts)
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    for key, value in parsed.items():
        assert isinstance(value, (str, type(None))), f"JSON parsed['{key}'] es {type(value)}, debería ser str o None"


def test_relative_to_with_none_base():
    """Test que relative_to no falla cuando el path es None."""
    from backend.shared.path_utils import safe_path_join, as_str
    from pathlib import Path
    
    # Simular caso donde storage_state_path podría ser None
    storage_state_path = None
    base = Path("data")
    
    # Esto no debe fallar
    if storage_state_path and storage_state_path.exists():
        result = as_str(storage_state_path.relative_to(base))
    else:
        result = None
    
    assert result is None
