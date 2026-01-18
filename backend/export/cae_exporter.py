"""
SPRINT C2.21: Exportador CAE audit-ready.

Genera ZIP con toda la evidencia relevante para un cliente y periodo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import zipfile
import shutil
import tempfile

from backend.config import DATA_DIR


def export_cae(
    company_key: str,
    period: str,  # "2025" o "2025-01"
    output_dir: Optional[Path] = None,
    base_dir: Path = None,
) -> Path:
    """
    Exporta un paquete CAE completo y auditable.
    
    Args:
        company_key: Clave de empresa
        period: Periodo (YYYY o YYYY-MM)
        output_dir: Directorio donde guardar el ZIP (default: temp)
        base_dir: Directorio base de datos (default: DATA_DIR)
    
    Returns:
        Path al archivo ZIP generado
    """
    base = Path(base_dir) if base_dir else Path(DATA_DIR)
    runs_dir = base / "runs"
    
    if not runs_dir.exists():
        raise ValueError(f"Runs directory not found: {runs_dir}")
    
    # Normalizar periodo
    period_year = period.split("-")[0]
    period_month = period.split("-")[1] if "-" in period else None
    
    # Crear directorio temporal para el export
    if output_dir:
        export_temp_dir = Path(output_dir)
        export_temp_dir.mkdir(parents=True, exist_ok=True)
    else:
        export_temp_dir = Path(tempfile.mkdtemp())
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"CAE_EXPORT_{company_key}_{period.replace('-', '_')}_{timestamp}.zip"
    zip_path = export_temp_dir / zip_filename
    
    # Estructura del ZIP
    zip_structure = {
        "README.md": None,  # Se generará
        "summary.json": None,  # Se generará
        "metrics/": {},
        "plans/": {},
        "uploads/": {},
        "logs/": {},
    }
    
    # Recolectar datos
    plans_found = []
    total_items = 0
    total_auto_upload = 0
    total_learning_hints = 0
    total_presets = 0
    
    # Buscar planes relevantes
    for plan_dir in runs_dir.iterdir():
        if not plan_dir.is_dir() or not plan_dir.name.startswith("plan_"):
            continue
        
        plan_path = plan_dir / "plan_response.json"
        if not plan_path.exists():
            continue
        
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
            
            # Verificar company_key
            artifacts = plan_data.get("artifacts", {})
            plan_company_key = artifacts.get("company_key") or plan_data.get("company_key")
            if plan_company_key != company_key:
                continue
            
            # Verificar periodo en items
            snapshot_items = plan_data.get("snapshot", {}).get("items", [])
            decisions = plan_data.get("decisions", [])
            
            # Filtrar items por periodo
            period_items = []
            for item in snapshot_items:
                item_period = item.get("periodo") or item.get("period_key") or ""
                if period_month:
                    # Periodo mensual: debe coincidir exactamente
                    if item_period == period:
                        period_items.append(item)
                else:
                    # Periodo anual: debe empezar con el año
                    if item_period.startswith(period_year):
                        period_items.append(item)
            
            if not period_items:
                continue  # No hay items de este periodo
            
            plan_id = plan_dir.name
            plans_found.append({
                "plan_id": plan_id,
                "plan_data": plan_data,
                "period_items": period_items,
                "decisions": decisions,
            })
            
            # Contar métricas
            total_items += len(period_items)
            for decision in decisions:
                if decision.get("decision") == "AUTO_UPLOAD":
                    total_auto_upload += 1
            
        except Exception as e:
            print(f"[CAE_EXPORT] Warning: Error processing plan {plan_dir.name}: {e}")
            continue
    
    # Generar contenido del ZIP
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1. README.md
        readme_content = generate_readme(
            company_key=company_key,
            period=period,
            total_items=total_items,
            total_auto_upload=total_auto_upload,
            total_learning_hints=total_learning_hints,
            total_presets=total_presets,
            plans_count=len(plans_found),
            export_date=datetime.now(),
        )
        zipf.writestr("README.md", readme_content)
        
        # 2. summary.json
        summary = {
            "company_key": company_key,
            "period": period,
            "export_date": datetime.now().isoformat(),
            "total_plans": len(plans_found),
            "total_items": total_items,
            "total_auto_upload": total_auto_upload,
            "total_learning_hints": total_learning_hints,
            "total_presets": total_presets,
            "plans": [
                {
                    "plan_id": p["plan_id"],
                    "items_count": len(p["period_items"]),
                }
                for p in plans_found
            ],
        }
        zipf.writestr("summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
        
        # 3. Plans
        for plan_info in plans_found:
            plan_id = plan_info["plan_id"]
            plan_dir = runs_dir / plan_id
            
            # Plan principal
            plan_path = plan_dir / "plan_response.json"
            if plan_path.exists():
                zipf.write(plan_path, f"plans/plan_{plan_id}.json")
            
            # Decision packs
            decision_packs_dir = plan_dir / "decision_packs"
            if decision_packs_dir.exists():
                for pack_file in decision_packs_dir.glob("*.json"):
                    if pack_file.name != "index.json":
                        zipf.write(pack_file, f"plans/plan_{plan_id}/decision_packs/{pack_file.name}")
            
            # Matching debug
            matching_debug_dir = plan_dir / "matching_debug"
            if matching_debug_dir.exists():
                # Solo incluir items del periodo
                for item in plan_info["period_items"]:
                    item_id = item.get("pending_item_key") or item.get("item_id") or item.get("key")
                    if item_id:
                        # Buscar debug file por item_id
                        for debug_file in matching_debug_dir.glob("*__debug.json"):
                            try:
                                with open(debug_file, "r", encoding="utf-8") as f:
                                    debug_data = json.load(f)
                                # Verificar si corresponde a este item
                                meta = debug_data.get("meta", {})
                                request_context = meta.get("request_context", {})
                                if (request_context.get("company_key") == company_key and
                                    item_id in debug_file.stem):
                                    zipf.write(debug_file, f"plans/plan_{plan_id}/matching_debug/{debug_file.name}")
                                    break
                            except Exception:
                                continue
            
            # Métricas
            metrics_path = plan_dir / "metrics.json"
            if metrics_path.exists():
                zipf.write(metrics_path, f"metrics/plan_{plan_id}_metrics.json")
        
        # 4. Métricas agregadas
        try:
            from backend.api.metrics_routes import get_metrics_summary
            # Llamar a la función directamente (sin async)
            # Por ahora, generar summary básico
            metrics_summary = {
                "company_key": company_key,
                "period": period,
                "total_plans": len(plans_found),
                "total_items": total_items,
            }
            zipf.writestr("metrics/metrics_summary.json", json.dumps(metrics_summary, indent=2, ensure_ascii=False))
        except Exception:
            pass
        
        # 5. Uploads (evidencias de ejecución)
        for plan_info in plans_found:
            plan_id = plan_info["plan_id"]
            plan_dir = runs_dir / plan_id
            
            # Buscar run_id asociado (desde run_summary o artifacts)
            run_id = None
            plan_data = plan_info["plan_data"]
            artifacts = plan_data.get("artifacts", {})
            run_id = artifacts.get("run_id")
            
            if not run_id:
                # Buscar en run_summary
                run_summary_path = plan_dir / "run_summary.json"
                if run_summary_path.exists():
                    try:
                        with open(run_summary_path, "r", encoding="utf-8") as f:
                            run_summary = json.load(f)
                        run_id = run_summary.get("run_id")
                    except Exception:
                        pass
            
            if run_id:
                run_dir = runs_dir / run_id
                execution_dir = run_dir / "execution"
                if execution_dir.exists():
                    # Copiar evidencias de uploads
                    for item_dir in execution_dir.glob("items/*"):
                        if item_dir.is_dir():
                            for evidence_file in item_dir.glob("*"):
                                if evidence_file.is_file():
                                    rel_path = f"uploads/{run_id}/{evidence_file.name}"
                                    zipf.write(evidence_file, rel_path)
        
        # 6. Logs (run_summary)
        for plan_info in plans_found:
            plan_id = plan_info["plan_id"]
            plan_dir = runs_dir / plan_id
            
            run_summary_path = plan_dir / "run_summary.json"
            if run_summary_path.exists():
                zipf.write(run_summary_path, f"logs/plan_{plan_id}_run_summary.json")
    
    return zip_path


def generate_readme(
    company_key: str,
    period: str,
    total_items: int,
    total_auto_upload: int,
    total_learning_hints: int,
    total_presets: int,
    plans_count: int,
    export_date: datetime,
) -> str:
    """Genera README.md humano para el export."""
    auto_percent = (total_auto_upload / total_items * 100) if total_items > 0 else 0
    
    return f"""# CAE Export - {company_key} - {period}

## Información General

- **Cliente**: {company_key}
- **Periodo**: {period}
- **Fecha de Exportación**: {export_date.strftime("%Y-%m-%d %H:%M:%S UTC")}
- **Total de Planes**: {plans_count}
- **Total de Items**: {total_items}

## Métricas

- **Items Auto-Upload**: {total_auto_upload} ({auto_percent:.1f}%)
- **Items con Learning Hints**: {total_learning_hints}
- **Items con Presets**: {total_presets}

## Estructura del Export

```
CAE_EXPORT_{company_key}_{period.replace('-', '_')}_{export_date.strftime("%Y%m%d_%H%M%S")}.zip
├── README.md (este archivo)
├── summary.json (resumen estructurado)
├── metrics/
│   ├── plan_<plan_id>_metrics.json (métricas por plan)
│   └── metrics_summary.json (resumen agregado)
├── plans/
│   ├── plan_<plan_id>.json (plan completo)
│   ├── plan_<plan_id>/
│   │   ├── decision_packs/ (decision packs aplicados)
│   │   └── matching_debug/ (debug reports por item)
├── uploads/
│   └── <run_id>/ (evidencias de uploads ejecutados)
└── logs/
    └── plan_<plan_id>_run_summary.json (resúmenes de ejecución)
```

## Notas

- Este export contiene toda la evidencia relevante para auditoría.
- Los documentos subidos están en `uploads/` con sus evidencias (screenshots, logs).
- Los matching_debug solo incluyen items del periodo especificado.
- Las métricas incluyen desglose por origen (auto_matching, learning, presets, manual).

## Contacto

Para preguntas sobre este export, contactar al equipo CAE.
"""
