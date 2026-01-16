"""
Ejecutar dry-run directamente para generar evidencia real.
"""
import os
import asyncio
import sys

# Configurar E2E_SEED_ENABLED
os.environ["E2E_SEED_ENABLED"] = "1"

from backend.connectors.runner import run_connector
# Importar conector para registrarlo
import backend.connectors.egestiona  # noqa: F401

async def main():
    print("=" * 60)
    print("EJECUTANDO DRY-RUN E-GESTIONA (Aigues de Manresa)")
    print("=" * 60)
    
    result = await run_connector(
        platform_id="egestiona",
        tenant_id="Aigues de Manresa",
        headless=False,  # HEADED para ver el navegador
        max_items=20,
        dry_run=True,
    )
    
    print("\n" + "=" * 60)
    print("RESULTADO:")
    print("=" * 60)
    print(f"Run ID: {result.get('run_id')}")
    print(f"Platform: {result.get('platform_id')}")
    print(f"Tenant: {result.get('tenant_id')}")
    print(f"Dry-Run: {result.get('dry_run')}")
    print(f"Evidence Dir: {result.get('evidence_dir')}")
    print(f"\nCounts:")
    counts = result.get('counts', {})
    print(f"  - Total requirements: {counts.get('total_requirements', 0)}")
    print(f"  - Matched: {counts.get('matched', 0)}")
    print(f"  - Uploaded: {counts.get('uploaded', 0)}")
    print(f"  - Failed: {counts.get('failed', 0)}")
    print(f"  - Skipped: {counts.get('skipped', 0)}")
    
    if 'error' in result:
        print(f"\nERROR: {result['error']}")
        sys.exit(1)
    
    evidence_dir = result.get('evidence_dir')
    if evidence_dir:
        print(f"\nEvidence generado en: {evidence_dir}")
        import pathlib
        evidence_path = pathlib.Path(evidence_dir)
        if (evidence_path / "report.json").exists():
            print("✓ report.json existe")
        if (evidence_path / "report.md").exists():
            print("✓ report.md existe")
    
    print("\n" + "=" * 60)
    print("CONFIRMACIÓN DRY-RUN:")
    print("=" * 60)
    print(f"uploaded = {counts.get('uploaded', 0)} (debe ser 0)")
    if counts.get('uploaded', 0) == 0:
        print("✓ CONFIRMADO: No se subió ningún documento (dry-run funcionando)")
    else:
        print("✗ ERROR: Se subieron documentos en dry-run!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
