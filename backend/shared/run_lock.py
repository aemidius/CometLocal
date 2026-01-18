"""
SPRINT C2.29: Lock por contexto para evitar ejecuciones concurrentes.

Implementa lock de filesystem:
- data/tenants/<tenant_id>/locks/run.lock
- Si existe y no está stale: bloquear nueva ejecución
- Si stale (> 2h): permitir override y loggear
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from backend.config import DATA_DIR
from backend.shared.tenant_paths import tenant_root


STALE_THRESHOLD_HOURS = 2


class RunLock:
    """Lock de filesystem para runs por contexto."""
    
    def __init__(self, base_dir: Path, tenant_id: str):
        """
        Inicializa el lock manager.
        
        Args:
            base_dir: Directorio base (DATA_DIR)
            tenant_id: ID del tenant (derivado del contexto)
        """
        self.base_dir = Path(base_dir)
        self.tenant_id = tenant_id
        self.locks_dir = tenant_root(base_dir, tenant_id) / "locks"
        self.lock_file = self.locks_dir / "run.lock"
    
    def acquire(self, run_id: str) -> tuple[bool, Optional[str]]:
        """
        Intenta adquirir el lock.
        
        Args:
            run_id: ID del run que intenta adquirir el lock
        
        Returns:
            (success, error_message)
            - success=True si se adquirió el lock
            - success=False si está bloqueado (error_message explica por qué)
        """
        # Crear directorio de locks si no existe
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        
        # Verificar si existe lock
        if not self.lock_file.exists():
            # No hay lock: crear uno nuevo
            self._write_lock(run_id)
            return (True, None)
        
        # Hay lock: verificar si está stale
        lock_data = self._read_lock()
        if not lock_data:
            # Lock corrupto: sobrescribir
            self._write_lock(run_id)
            return (True, None)
        
        locked_at = lock_data.get("locked_at")
        if not locked_at:
            # Lock sin timestamp: considerar stale
            self._write_lock(run_id)
            return (True, None)
        
        try:
            locked_at_dt = datetime.fromisoformat(locked_at)
            age = datetime.now() - locked_at_dt
            
            if age > timedelta(hours=STALE_THRESHOLD_HOURS):
                # Lock stale: permitir override
                print(f"[RunLock] WARNING: Stale lock detected (age: {age.total_seconds()/3600:.1f}h), overriding")
                self._write_lock(run_id)
                return (True, None)
            else:
                # Lock activo: bloquear
                locked_run_id = lock_data.get("run_id", "unknown")
                return (False, f"Run en ejecución: {locked_run_id} (iniciado hace {age.total_seconds()/60:.1f} minutos)")
        
        except (ValueError, TypeError) as e:
            # Error parseando timestamp: considerar stale
            print(f"[RunLock] WARNING: Error parsing lock timestamp: {e}, overriding")
            self._write_lock(run_id)
            return (True, None)
    
    def release(self, run_id: str) -> None:
        """
        Libera el lock.
        
        Args:
            run_id: ID del run que libera el lock
        """
        if not self.lock_file.exists():
            return
        
        lock_data = self._read_lock()
        if lock_data and lock_data.get("run_id") == run_id:
            # Solo liberar si es nuestro lock
            try:
                self.lock_file.unlink()
            except Exception as e:
                print(f"[RunLock] WARNING: Error releasing lock: {e}")
    
    def _write_lock(self, run_id: str) -> None:
        """Escribe el archivo de lock."""
        lock_data = {
            "run_id": run_id,
            "locked_at": datetime.now().isoformat(),
            "tenant_id": self.tenant_id,
        }
        with open(self.lock_file, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, indent=2)
    
    def _read_lock(self) -> Optional[dict]:
        """Lee el archivo de lock."""
        try:
            with open(self.lock_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RunLock] WARNING: Error reading lock: {e}")
            return None
