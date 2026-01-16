import json
from pathlib import Path
from typing import List, Optional

from ..shared.models import SimulationScenario

# Directorio raíz de escenarios de simulación
SCENARIOS_ROOT = Path(__file__).parent / "scenarios"


def _load_metadata_file(path: Path) -> Optional[SimulationScenario]:
    """
    Carga un fichero metadata.json y lo convierte en SimulationScenario.
    Devuelve None si hay cualquier problema de lectura o validación.
    Errores aquí NUNCA deben romper el backend global.
    """
    if not path.is_file():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Campos mínimos obligatorios
    required = ("id", "name", "description", "entry_path")
    if not all(k in raw for k in required):
        return None

    try:
        scenario = SimulationScenario(
            id=str(raw["id"]),
            name=str(raw["name"]),
            description=str(raw["description"]),
            entry_path=str(raw["entry_path"]),
            version=str(raw["version"]) if "version" in raw and raw["version"] is not None else None,
            tags=list(raw.get("tags", [])) if isinstance(raw.get("tags", []), list) else [],
        )
    except Exception:
        # Nunca propagamos excepciones de validación
        return None

    return scenario


def list_scenarios() -> List[SimulationScenario]:
    """
    Devuelve la lista de escenarios de simulación disponibles.
    Ignora directorios/archivos inválidos de forma silenciosa.
    """
    scenarios: List[SimulationScenario] = []

    if not SCENARIOS_ROOT.exists():
        return scenarios

    for child in SCENARIOS_ROOT.iterdir():
        if not child.is_dir():
            continue

        metadata_path = child / "metadata.json"
        scenario = _load_metadata_file(metadata_path)
        if scenario is not None:
            scenarios.append(scenario)

    # Ordenar por id para tener resultados deterministas
    scenarios.sort(key=lambda s: s.id)
    return scenarios


def load_scenario(scenario_id: str) -> Optional[SimulationScenario]:
    """
    Devuelve un escenario concreto por su id o None si no existe/está corrupto.
    """
    scenario_dir = SCENARIOS_ROOT / scenario_id
    metadata_path = scenario_dir / "metadata.json"
    return _load_metadata_file(metadata_path)





















