"""
SPRINT C2.30: Lógica de "tick" para ejecutar schedules.

Determina si un schedule "toca ejecutar ahora" y ejecuta si corresponde.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from backend.shared.schedule_models import ScheduleV1, ScheduleStore
from backend.shared.run_lock import RunLock
from backend.shared.run_summary import RunContextV1
from backend.shared.tenant_context import compute_tenant_from_coordination_context
from backend.config import DATA_DIR


def should_execute_now(schedule: ScheduleV1, now: Optional[datetime] = None) -> bool:
    """
    Determina si un schedule debe ejecutarse ahora.
    
    Args:
        schedule: Schedule a evaluar
        now: Timestamp actual (default: datetime.now())
    
    Returns:
        True si debe ejecutarse ahora, False en caso contrario
    """
    if not schedule.enabled:
        return False
    
    if now is None:
        now = datetime.now()
    
    # Parsear hora objetivo
    try:
        hour, minute = map(int, schedule.at_time.split(":"))
        target_time = time(hour, minute)
    except (ValueError, AttributeError):
        return False
    
    current_time = now.time()
    
    if schedule.cadence == "daily":
        # Daily: ejecutar si la hora coincide y no se ejecutó hoy
        if current_time >= target_time:
            # Verificar si ya se ejecutó hoy
            if schedule.last_run_at:
                last_run_date = schedule.last_run_at.date()
                today = now.date()
                if last_run_date == today:
                    # Ya se ejecutó hoy
                    return False
            # Toca ejecutar hoy
            return True
        return False
    
    elif schedule.cadence == "weekly":
        # Weekly: ejecutar si es el día correcto y la hora coincide
        if schedule.weekday is None:
            return False
        
        # weekday: 0=lunes, 6=domingo
        # datetime.weekday(): 0=lunes, 6=domingo
        if now.weekday() != schedule.weekday:
            return False
        
        # Es el día correcto, verificar hora
        if current_time >= target_time:
            # Verificar si ya se ejecutó esta semana
            if schedule.last_run_at:
                last_run_date = schedule.last_run_at.date()
                today = now.date()
                days_diff = (today - last_run_date).days
                if days_diff < 7:
                    # Ya se ejecutó esta semana
                    return False
            # Toca ejecutar esta semana
            return True
        return False
    
    return False


def execute_schedule_tick(
    tenant_id: str,
    dry_run_mode: bool = False,
) -> dict:
    """
    Ejecuta un "tick" de schedules para un tenant.
    
    Recorre schedules habilitados, determina si tocan ejecutar,
    y ejecuta los que correspondan.
    
    Args:
        tenant_id: ID del tenant
        dry_run_mode: Si True, solo simula sin ejecutar realmente
    
    Returns:
        Dict con resumen de ejecución
    """
    store = ScheduleStore(DATA_DIR, tenant_id)
    schedules = store.list_schedules()
    
    enabled_schedules = [s for s in schedules if s.enabled]
    
    results = {
        "checked": len(enabled_schedules),
        "executed": 0,
        "skipped_locked": 0,
        "skipped_not_due": 0,
        "errors": [],
    }
    
    now = datetime.now()
    
    for schedule in enabled_schedules:
        if not should_execute_now(schedule, now):
            results["skipped_not_due"] += 1
            continue
        
        # Verificar lock
        lock = RunLock(DATA_DIR, tenant_id)
        import uuid
        test_run_id = str(uuid.uuid4())[:8]
        acquired, lock_error = lock.acquire(test_run_id)
        
        if not acquired:
            results["skipped_locked"] += 1
            continue
        
        try:
            if dry_run_mode:
                # Solo simular
                results["executed"] += 1
                results["errors"].append({
                    "schedule_id": schedule.schedule_id,
                    "error": "DRY_RUN_MODE: No ejecutado realmente"
                })
            else:
                # Ejecutar realmente
                # Construir contexto desde schedule
                from backend.api.runs_routes import _execute_schedule_run
                from backend.repository.config_store_v1 import ConfigStoreV1
                from backend.api.coordination_context_routes import CompanyOptionV1
                
                # Obtener nombres desde ConfigStore
                store = ConfigStoreV1(base_dir=DATA_DIR)
                org = store.load_org()
                platforms_data = store.load_platforms()
                
                own_company_name = org.legal_name if org.tax_id == schedule.own_company_key else None
                platform_name = None
                for p in platforms_data.platforms:
                    if p.key == schedule.platform_key:
                        platform_name = p.key.replace("_", " ").title()
                        break
                
                coordinated_company_name = None
                for platform in platforms_data.platforms:
                    if platform.key == schedule.platform_key:
                        for coord in platform.coordinations:
                            if coord.client_code == schedule.coordinated_company_key:
                                coordinated_company_name = coord.label
                                break
                        break
                
                context = RunContextV1(
                    own_company_key=schedule.own_company_key,
                    own_company_name=own_company_name,
                    platform_key=schedule.platform_key,
                    platform_name=platform_name,
                    coordinated_company_key=schedule.coordinated_company_key,
                    coordinated_company_name=coordinated_company_name,
                )
                
                run_result = _execute_schedule_run(
                    schedule=schedule,
                    tenant_id=tenant_id,
                    context=context,
                )
                
                # Actualizar schedule con último run
                schedule.last_run_id = run_result.get("run_id")
                schedule.last_run_at = now
                schedule.last_status = run_result.get("status")
                schedule.updated_at = now
                store.save_schedule(schedule)
                
                results["executed"] += 1
        
        except Exception as e:
            results["errors"].append({
                "schedule_id": schedule.schedule_id,
                "error": str(e)
            })
        
        finally:
            lock.release(test_run_id)
    
    return results
