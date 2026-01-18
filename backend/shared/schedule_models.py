"""
SPRINT C2.30: Modelos para scheduling de runs por contexto humano.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class ScheduleV1(BaseModel):
    """Schedule para ejecutar runs automáticamente."""
    schedule_id: str
    enabled: bool
    plan_id: str
    dry_run: bool = False
    cadence: Literal["daily", "weekly"]
    at_time: str  # "HH:MM" en formato 24h
    weekday: Optional[int] = None  # 0-6 (0=lunes, 6=domingo), solo si weekly
    # SPRINT C2.30: Contexto humano guardado en schedule
    own_company_key: str
    platform_key: str
    coordinated_company_key: str
    created_at: datetime
    updated_at: datetime
    last_run_id: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None  # success|error|blocked|partial_success


class ScheduleStore:
    """Store para schedules por tenant."""
    
    def __init__(self, base_dir, tenant_id: str):
        """
        Inicializa el store.
        
        Args:
            base_dir: Directorio base (DATA_DIR)
            tenant_id: ID del tenant
        """
        from pathlib import Path
        from backend.shared.tenant_paths import tenant_root
        
        self.base_dir = Path(base_dir)
        self.tenant_id = tenant_id
        self.tenant_dir = tenant_root(base_dir, tenant_id)
        self.schedules_dir = self.tenant_dir / "schedules"
        self.schedules_file = self.schedules_dir / "schedules.json"
    
    def list_schedules(self) -> list[ScheduleV1]:
        """Lista todos los schedules del tenant."""
        if not self.schedules_file.exists():
            return []
        
        import json
        try:
            with open(self.schedules_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                schedules = []
                for sched_dict in data.get("schedules", []):
                    try:
                        # Convertir timestamps ISO a datetime
                        if "created_at" in sched_dict:
                            sched_dict["created_at"] = datetime.fromisoformat(sched_dict["created_at"])
                        if "updated_at" in sched_dict:
                            sched_dict["updated_at"] = datetime.fromisoformat(sched_dict["updated_at"])
                        if "last_run_at" in sched_dict and sched_dict["last_run_at"]:
                            sched_dict["last_run_at"] = datetime.fromisoformat(sched_dict["last_run_at"])
                        schedules.append(ScheduleV1(**sched_dict))
                    except Exception as e:
                        print(f"[ScheduleStore] Error parsing schedule: {e}")
                        continue
                return schedules
        except Exception as e:
            print(f"[ScheduleStore] Error loading schedules: {e}")
            return []
    
    def save_schedule(self, schedule: ScheduleV1) -> None:
        """Guarda o actualiza un schedule."""
        schedules = self.list_schedules()
        
        # Buscar si existe
        existing_idx = None
        for idx, sched in enumerate(schedules):
            if sched.schedule_id == schedule.schedule_id:
                existing_idx = idx
                break
        
        if existing_idx is not None:
            schedules[existing_idx] = schedule
        else:
            schedules.append(schedule)
        
        self._save_all(schedules)
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Elimina un schedule."""
        schedules = self.list_schedules()
        original_count = len(schedules)
        schedules = [s for s in schedules if s.schedule_id != schedule_id]
        
        if len(schedules) < original_count:
            self._save_all(schedules)
            return True
        return False
    
    def _save_all(self, schedules: list[ScheduleV1]) -> None:
        """Guarda todos los schedules."""
        self.schedules_dir.mkdir(parents=True, exist_ok=True)
        
        import json
        data = {
            "schedules": [s.model_dump(mode="json", exclude_none=True) for s in schedules],
            "updated_at": datetime.now().isoformat(),
        }
        
        with open(self.schedules_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
