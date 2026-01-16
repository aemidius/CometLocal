"""
Generación de informes de jobs CAE v1.9.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Optional
from backend.cae.job_queue_models_v1 import CAEJobV1
from backend.cae.submission_routes import _get_plan_evidence


def generate_job_report_html(job: CAEJobV1) -> str:
    """
    Genera un informe HTML del job.
    
    Args:
        job: Job a reportar
    
    Returns:
        HTML como string
    """
    # Cargar plan para obtener detalles de items
    plan = _get_plan_evidence(job.plan_id)
    
    # Determinar color de badge según status
    status_colors = {
        "SUCCESS": "#10b981",
        "PARTIAL_SUCCESS": "#f59e0b",
        "FAILED": "#ef4444",
        "BLOCKED": "#f59e0b",
        "CANCELED": "#6b7280",
        "QUEUED": "#3b82f6",
        "RUNNING": "#3b82f6",
    }
    status_color = status_colors.get(job.status, "#6b7280")
    
    # Formatear fechas
    created_at_str = job.created_at.strftime("%Y-%m-%d %H:%M:%S") if job.created_at else "N/A"
    started_at_str = job.started_at.strftime("%Y-%m-%d %H:%M:%S") if job.started_at else "N/A"
    finished_at_str = job.finished_at.strftime("%Y-%m-%d %H:%M:%S") if job.finished_at else "N/A"
    
    # Items del plan
    items_html = ""
    if plan:
        for idx, item in enumerate(plan.items, 1):
            item_status_color = {
                "PLANNED": "#10b981",
                "NEEDS_CONFIRMATION": "#f59e0b",
                "BLOCKED": "#ef4444",
            }.get(item.status, "#6b7280")
            
            items_html += f"""
            <tr>
                <td>{idx}</td>
                <td>{item.type_id}</td>
                <td>{item.period_key or 'N/A'}</td>
                <td>{item.suggested_doc_id or 'N/A'}</td>
                <td><span style="color: {item_status_color};">{item.status}</span></td>
                <td>{item.reason or '-'}</td>
            </tr>
            """
    else:
        items_html = "<tr><td colspan='6'>Plan no disponible</td></tr>"
    
    # Evidencia
    evidence_html = ""
    if job.evidence_path:
        evidence_path = Path(job.evidence_path)
        if evidence_path.exists():
            screenshots_dir = evidence_path / "screenshots"
            if screenshots_dir.exists():
                screenshots = list(screenshots_dir.glob("*.png")) + list(screenshots_dir.glob("*.jpg"))
                if screenshots:
                    evidence_html = "<ul>"
                    for screenshot in sorted(screenshots)[:10]:  # Limitar a 10
                        evidence_html += f"<li>{screenshot.name}</li>"
                    evidence_html += "</ul>"
                else:
                    evidence_html = "<p>No hay screenshots disponibles</p>"
            else:
                evidence_html = f"<p>Ruta de evidencia: {job.evidence_path}</p>"
        else:
            evidence_html = f"<p>Evidencia no encontrada en: {job.evidence_path}</p>"
    else:
        evidence_html = "<p>No hay evidencia disponible</p>"
    
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Informe de Ejecución CAE - {job.job_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f9fafb;
        }}
        .header {{
            background: white;
            padding: 24px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 24px;
        }}
        .header h1 {{
            margin: 0 0 8px 0;
            color: #111827;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 0.875rem;
            font-weight: 600;
            color: white;
            background: {status_color};
        }}
        .section {{
            background: white;
            padding: 24px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 24px;
        }}
        .section h2 {{
            margin-top: 0;
            color: #111827;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }}
        th {{
            background: #f9fafb;
            font-weight: 600;
            color: #374151;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
            margin-top: 16px;
        }}
        .info-item {{
            padding: 12px;
            background: #f9fafb;
            border-radius: 4px;
        }}
        .info-label {{
            font-size: 0.875rem;
            color: #6b7280;
            margin-bottom: 4px;
        }}
        .info-value {{
            font-weight: 600;
            color: #111827;
        }}
        .footer {{
            margin-top: 32px;
            padding: 16px;
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            border-radius: 4px;
            font-size: 0.875rem;
            color: #92400e;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Informe de Ejecución CAE</h1>
        <p style="margin: 8px 0; color: #6b7280;">Job ID: <strong>{job.job_id}</strong></p>
        <p style="margin: 8px 0;">
            <span class="badge">{job.status}</span>
        </p>
    </div>
    
    <div class="section">
        <h2>Información General</h2>
        <div class="info-grid">
            <div class="info-item">
                <div class="info-label">Job ID</div>
                <div class="info-value">{job.job_id}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Plan ID</div>
                <div class="info-value">{job.plan_id}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Creado</div>
                <div class="info-value">{created_at_str}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Iniciado</div>
                <div class="info-value">{started_at_str}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Finalizado</div>
                <div class="info-value">{finished_at_str}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Run ID</div>
                <div class="info-value">{job.run_id or 'N/A'}</div>
            </div>
        </div>
    </div>
    
    <div class="section">
        <h2>Scope</h2>
        <div class="info-grid">
            <div class="info-item">
                <div class="info-label">Plataforma</div>
                <div class="info-value">{job.scope_summary.get('platform_key', 'N/A')}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Empresa</div>
                <div class="info-value">{job.scope_summary.get('company_key', 'N/A')}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Trabajador</div>
                <div class="info-value">{job.scope_summary.get('person_key', 'N/A')}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Modo</div>
                <div class="info-value">{job.scope_summary.get('mode', 'N/A')}</div>
            </div>
        </div>
    </div>
    
    <div class="section">
        <h2>Resultado</h2>
        <div class="info-grid">
            <div class="info-item">
                <div class="info-label">Estado</div>
                <div class="info-value"><span class="badge">{job.status}</span></div>
            </div>
            <div class="info-item">
                <div class="info-label">Progreso</div>
                <div class="info-value">{job.progress.percent}%</div>
            </div>
            <div class="info-item">
                <div class="info-label">Total Items</div>
                <div class="info-value">{job.progress.total_items}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Éxito</div>
                <div class="info-value" style="color: #10b981;">{job.progress.items_success}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Fallos</div>
                <div class="info-value" style="color: #ef4444;">{job.progress.items_failed}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Bloqueados</div>
                <div class="info-value" style="color: #f59e0b;">{job.progress.items_blocked}</div>
            </div>
        </div>
        {f'<div style="margin-top: 16px; padding: 12px; background: #fee2e2; border-radius: 4px; color: #991b1b;"><strong>Error:</strong> {job.error}</div>' if job.error else ''}
    </div>
    
    <div class="section">
        <h2>Items del Plan</h2>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Type ID</th>
                    <th>Período</th>
                    <th>Documento</th>
                    <th>Estado</th>
                    <th>Razón</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h2>Evidencia</h2>
        {evidence_html}
    </div>
    
    {f'<div class="section"><h2>Información de Reintento</h2><p>Este job es un reintento del job: <strong>{job.retry_of}</strong></p></div>' if job.retry_of else ''}
    
    <div class="footer">
        <strong>Nota:</strong> Este informe fue generado automáticamente. Revisión humana requerida antes de considerar la ejecución como definitiva.
    </div>
</body>
</html>
"""
    return html

