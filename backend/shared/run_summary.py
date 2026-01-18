"""
SPRINT C2.29: Modelo de RunSummary para runs audit-ready.

Cada run genera una carpeta con:
- input.json (plan/preset/decision pack)
- result.json (resultado de ejecución)
- summary.md (humano)
- summary.json (máquina)
- evidence/ (si hay)
- export/ (si hay)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel


class RunContextV1(BaseModel):
    """Contexto humano de un run."""
    own_company_key: str
    own_company_name: Optional[str] = None
    platform_key: str
    platform_name: Optional[str] = None
    coordinated_company_key: str
    coordinated_company_name: Optional[str] = None


class RunSummaryV1(BaseModel):
    """Resumen de un run para auditoría."""
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: Literal["success", "error", "blocked", "partial_success", "canceled"]
    context: RunContextV1
    plan_id: Optional[str] = None
    preset_id: Optional[str] = None
    decision_pack_id: Optional[str] = None
    dry_run: bool = False
    steps_executed: List[str] = []
    counters: Dict[str, int] = {
        "docs_processed": 0,
        "uploads_attempted": 0,
        "uploads_ok": 0,
        "uploads_failed": 0,
    }
    artifacts: Dict[str, str] = {}  # paths relativos desde run_dir
    error: Optional[str] = None
    run_dir_rel: str  # ruta relativa desde data/<context>/runs/


def create_run_dir(
    base_dir: Path,
    tenant_id: str,
    run_id: str,
) -> Path:
    """
    Crea el directorio de un run con estructura audit-ready.
    
    Estructura:
    data/tenants/<tenant_id>/runs/<YYYYMMDD_HHMMSS>__<run_id>/
    
    Args:
        base_dir: Directorio base (DATA_DIR)
        tenant_id: ID del tenant (derivado del contexto)
        run_id: ID único del run
    
    Returns:
        Path al directorio del run
    """
    from backend.shared.tenant_paths import tenant_runs_root
    
    runs_root = tenant_runs_root(base_dir, tenant_id)
    runs_root.mkdir(parents=True, exist_ok=True)
    
    # Formato: YYYYMMDD_HHMMSS__<run_id>
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir_name = f"{timestamp}__{run_id}"
    run_dir = runs_root / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Crear subdirectorios
    (run_dir / "evidence").mkdir(exist_ok=True)
    (run_dir / "export").mkdir(exist_ok=True)
    
    return run_dir


def save_run_summary(
    run_dir: Path,
    summary: RunSummaryV1,
    input_data: Optional[Dict[str, Any]] = None,
    result_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Guarda el summary y archivos relacionados en el run_dir.
    
    Args:
        run_dir: Directorio del run
        summary: RunSummaryV1 a guardar
        input_data: Datos de input (plan/preset/pack) para input.json
        result_data: Datos de resultado para result.json
    """
    # Guardar summary.json
    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        import json
        json.dump(summary.model_dump(mode="json", exclude_none=True), f, indent=2, ensure_ascii=False, default=str)
    
    # Guardar summary.md (humano)
    summary_md_path = run_dir / "summary.md"
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write(generate_summary_md(summary))
    
    # Guardar input.json si hay
    if input_data:
        input_path = run_dir / "input.json"
        with open(input_path, "w", encoding="utf-8") as f:
            import json
            json.dump(input_data, f, indent=2, ensure_ascii=False, default=str)
    
    # Guardar result.json si hay
    if result_data:
        result_path = run_dir / "result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            import json
            json.dump(result_data, f, indent=2, ensure_ascii=False, default=str)


def generate_summary_md(summary: RunSummaryV1) -> str:
    """Genera el summary.md legible por humanos."""
    lines = []
    lines.append(f"# Run Summary: {summary.run_id}")
    lines.append("")
    lines.append(f"**Estado:** {summary.status.upper()}")
    lines.append(f"**Iniciado:** {summary.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if summary.finished_at:
        duration = summary.finished_at - summary.started_at
        lines.append(f"**Finalizado:** {summary.finished_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Duración:** {duration.total_seconds():.1f} segundos")
    lines.append("")
    
    lines.append("## Contexto")
    lines.append(f"- **Empresa propia:** {summary.context.own_company_name or summary.context.own_company_key}")
    lines.append(f"- **Plataforma:** {summary.context.platform_name or summary.context.platform_key}")
    lines.append(f"- **Empresa coordinada:** {summary.context.coordinated_company_name or summary.context.coordinated_company_key}")
    lines.append("")
    
    if summary.plan_id:
        lines.append(f"**Plan ID:** {summary.plan_id}")
    if summary.preset_id:
        lines.append(f"**Preset ID:** {summary.preset_id}")
    if summary.decision_pack_id:
        lines.append(f"**Decision Pack ID:** {summary.decision_pack_id}")
    if summary.dry_run:
        lines.append("**Modo:** DRY-RUN (simulación)")
    lines.append("")
    
    lines.append("## Contadores")
    for key, value in summary.counters.items():
        lines.append(f"- **{key}:** {value}")
    lines.append("")
    
    if summary.steps_executed:
        lines.append("## Pasos Ejecutados")
        for step in summary.steps_executed:
            lines.append(f"- {step}")
        lines.append("")
    
    if summary.artifacts:
        lines.append("## Artefactos")
        for name, path in summary.artifacts.items():
            lines.append(f"- **{name}:** `{path}`")
        lines.append("")
    
    if summary.error:
        lines.append("## Error")
        lines.append(f"```")
        lines.append(summary.error)
        lines.append("```")
        lines.append("")
    
    return "\n".join(lines)


def list_run_summaries(
    limit: int = 50,
    platform: Optional[str] = None,
    tenant_id: str = "default",
) -> List[Dict[str, Any]]:
    """
    Lista summaries de runs recientes.
    
    SPRINT C2.16: Función legacy para compatibilidad con runs_summary_routes.
    SPRINT C2.29: Adaptada para usar estructura de directorios nueva.
    
    Args:
        limit: Límite de resultados
        platform: Filtrar por plataforma (opcional)
        tenant_id: ID del tenant
    
    Returns:
        Lista de diccionarios con información de runs
    """
    from backend.shared.tenant_paths import tenant_runs_root
    from backend.config import DATA_DIR
    import json
    
    runs_root = tenant_runs_root(DATA_DIR, tenant_id)
    
    if not runs_root.exists():
        return []
    
    # Buscar directorios de runs
    run_dirs = sorted(runs_root.glob("*__*"), key=lambda p: p.name, reverse=True)
    
    summaries = []
    for run_dir in run_dirs[:limit]:
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
            
            # Filtrar por plataforma si se especifica
            if platform:
                context = summary_data.get("context", {})
                if context.get("platform_key") != platform:
                    continue
            
            # Convertir a formato legacy si es necesario
            summaries.append(summary_data)
        
        except Exception as e:
            print(f"[list_run_summaries] Error loading {summary_path}: {e}")
            continue
    
    return summaries
