"""
Script de migración para añadir period_key a documentos existentes.

Ejecutar: python scripts/migrate_period_keys.py [--dry-run]
"""

import sys
from pathlib import Path

# Añadir raíz del proyecto al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.period_migration_v1 import PeriodMigrationV1


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate period_key for existing documents")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes, just report")
    args = parser.parse_args()
    
    print("=" * 60)
    print("PERIOD KEY MIGRATION")
    print("=" * 60)
    print()
    
    store = DocumentRepositoryStoreV1()
    migrator = PeriodMigrationV1(store)
    
    if args.dry_run:
        print("[DRY RUN] No changes will be saved")
        print()
    
    stats = migrator.migrate_all(dry_run=args.dry_run)
    
    print("=" * 60)
    print("MIGRATION STATISTICS")
    print("=" * 60)
    print(f"Total documents: {stats['total']}")
    print(f"Migrated: {stats['migrated']}")
    print(f"Already has period_key: {stats['already_has_period']}")
    print(f"Not periodic: {stats['not_periodic']}")
    print(f"Needs period (could not infer): {stats['needs_period']}")
    print(f"Errors: {stats['errors']}")
    print()
    
    if stats['needs_period'] > 0:
        print(f"⚠️  {stats['needs_period']} documents need manual period_key assignment")
        print("   These documents are periodic but period_key could not be inferred.")
        print("   They have been marked with needs_period=True")
        print()


if __name__ == "__main__":
    main()























