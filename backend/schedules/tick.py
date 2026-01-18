"""
SPRINT C2.30: CLI para ejecutar tick de schedules.

Uso:
    python -m backend.schedules.tick --all-tenants
    python -m backend.schedules.tick --tenant <tenant_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Añadir raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.shared.schedule_tick import execute_schedule_tick
from backend.shared.tenant_paths import tenants_root
from backend.config import DATA_DIR


def main():
    parser = argparse.ArgumentParser(description="Ejecuta tick de schedules")
    parser.add_argument(
        "--all-tenants",
        action="store_true",
        help="Ejecutar tick para todos los tenants"
    )
    parser.add_argument(
        "--tenant",
        type=str,
        help="Ejecutar tick para un tenant específico"
    )
    
    args = parser.parse_args()
    
    if args.all_tenants:
        # Buscar todos los tenants
        tenants_dir = tenants_root(DATA_DIR)
        if not tenants_dir.exists():
            print("No tenants found")
            return
        
        tenant_dirs = [d for d in tenants_dir.iterdir() if d.is_dir()]
        
        for tenant_dir in tenant_dirs:
            tenant_id = tenant_dir.name
            print(f"\n[Tick] Processing tenant: {tenant_id}")
            try:
                results = execute_schedule_tick(tenant_id, dry_run_mode=False)
                print(f"  Checked: {results['checked']}")
                print(f"  Executed: {results['executed']}")
                print(f"  Skipped (locked): {results['skipped_locked']}")
                print(f"  Skipped (not due): {results['skipped_not_due']}")
                if results['errors']:
                    print(f"  Errors: {len(results['errors'])}")
                    for error in results['errors']:
                        print(f"    - {error['schedule_id']}: {error['error']}")
            except Exception as e:
                print(f"  ERROR: {e}")
    
    elif args.tenant:
        print(f"[Tick] Processing tenant: {args.tenant}")
        try:
            results = execute_schedule_tick(args.tenant, dry_run_mode=False)
            print(f"Checked: {results['checked']}")
            print(f"Executed: {results['executed']}")
            print(f"Skipped (locked): {results['skipped_locked']}")
            print(f"Skipped (not due): {results['skipped_not_due']}")
            if results['errors']:
                print(f"Errors: {len(results['errors'])}")
                for error in results['errors']:
                    print(f"  - {error['schedule_id']}: {error['error']}")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
