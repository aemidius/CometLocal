from fastapi import APIRouter, HTTPException

from ..shared.models import SimulationScenario, SimulationScenarioList
from .simulator import list_scenarios, load_scenario

router = APIRouter(
    prefix="/simulation",
    tags=["simulation"],
)


@router.get("/scenarios", response_model=SimulationScenarioList)
async def get_simulation_scenarios() -> SimulationScenarioList:
    """
    Devuelve la lista de escenarios de simulación disponibles.
    Esta API es usada por la futura Training UI para descubrir escenarios.
    """
    scenarios = list_scenarios()
    return SimulationScenarioList(scenarios=scenarios)


@router.get("/scenarios/{scenario_id}", response_model=SimulationScenario)
async def get_simulation_scenario(scenario_id: str) -> SimulationScenario:
    """
    Devuelve los metadatos de un escenario concreto.
    No ejecuta nada, solo describe la configuración del escenario.
    """
    scenario = load_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Simulation scenario not found")
    return scenario












