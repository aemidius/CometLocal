"""
Script CLI para limpiar datos demo del repositorio.

Uso:
    python -m backend.tools.cleanup_demo_data

Elimina de forma segura:
- Documentos con type_id que empieza con "demo_"
- Documentos con doc_id que empieza con "demo_"
- Documentos con file_name_original que contiene "(Demo)"
- Tipos de documentos con type_id que empieza con "demo_"
- Sujetos demo_worker_*, TEST_*, worker123 (patrones conocidos)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Añadir el root del proyecto al path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import DATA_DIR
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.demo_dataset import (
    DEMO_OWN_COMPANY_KEY,
    DEMO_PLATFORM_KEY,
    DEMO_COORDINATED_COMPANY_KEY,
)


def is_demo_document(doc) -> bool:
    """
    Detecta si un documento es demo de forma conservadora.
    
    Patrones demo:
    - doc_id empieza con "demo_"
    - type_id empieza con "demo_"
    - file_name_original contiene "(Demo)"
    - subject_id es demo_worker_*, TEST_*, worker123
    """
    # Verificar doc_id
    doc_id = doc.doc_id if hasattr(doc, 'doc_id') else getattr(doc, 'id', '')
    if doc_id.startswith('demo_'):
        return True
    
    # Verificar type_id
    type_id = getattr(doc, 'type_id', '')
    if type_id.startswith('demo_'):
        return True
    
    # Verificar file_name_original
    file_name = getattr(doc, 'file_name_original', '') or getattr(doc, 'file_name', '') or ''
    if '(Demo)' in file_name or '(demo)' in file_name:
        return True
    
    # Verificar subject_id (person_key o company_key)
    person_key = getattr(doc, 'person_key', '') or ''
    company_key = getattr(doc, 'company_key', '') or ''
    
    # Patrones conocidos de sujetos demo
    demo_subject_patterns = [
        'demo_worker_',
        'TEST_',
        'worker123',
        'demo_',
    ]
    
    for pattern in demo_subject_patterns:
        if person_key.startswith(pattern) or company_key.startswith(pattern):
            return True
    
    return False


def is_demo_type(type_obj) -> bool:
    """Detecta si un tipo de documento es demo."""
    type_id = getattr(type_obj, 'type_id', '')
    if type_id.startswith('demo_'):
        return True
    
    name = getattr(type_obj, 'name', '')
    if '(Demo)' in name or '(demo)' in name:
        return True
    
    return False


def cleanup_demo_data(dry_run: bool = False) -> dict:
    """
    Limpia datos demo del repositorio.
    
    Args:
        dry_run: Si es True, solo muestra qué se eliminaría sin borrar.
    
    Returns:
        Dict con resumen de lo eliminado.
    """
    results = {
        'docs_deleted': 0,
        'types_deleted': 0,
        'docs_paths': [],
        'types_paths': [],
        'errors': [],
    }
    
    try:
        # Inicializar stores
        repo_store = DocumentRepositoryStoreV1(base_dir=DATA_DIR)
        
        # 1. Eliminar documentos demo
        all_docs = repo_store.list_documents()
        demo_docs = [doc for doc in all_docs if is_demo_document(doc)]
        
        print(f"[Cleanup] Encontrados {len(demo_docs)} documentos demo de {len(all_docs)} totales")
        
        for doc in demo_docs:
            doc_id = doc.doc_id if hasattr(doc, 'doc_id') else getattr(doc, 'id', '')
            try:
                if not dry_run:
                    repo_store.delete_document(doc_id)
                    results['docs_deleted'] += 1
                    results['docs_paths'].append(doc_id)
                    print(f"  ✓ Eliminado documento: {doc_id}")
                else:
                    results['docs_deleted'] += 1
                    results['docs_paths'].append(doc_id)
                    print(f"  [DRY RUN] Se eliminaría documento: {doc_id}")
            except Exception as e:
                error_msg = f"Error eliminando documento {doc_id}: {e}"
                results['errors'].append(error_msg)
                print(f"  ✗ {error_msg}")
        
        # 2. Eliminar tipos demo
        all_types = repo_store.list_types()
        demo_types = [t for t in all_types if is_demo_type(t)]
        
        print(f"\n[Cleanup] Encontrados {len(demo_types)} tipos demo de {len(all_types)} totales")
        
        for type_obj in demo_types:
            type_id = getattr(type_obj, 'type_id', '')
            try:
                if not dry_run:
                    repo_store.delete_type(type_id)
                    results['types_deleted'] += 1
                    results['types_paths'].append(type_id)
                    print(f"  ✓ Eliminado tipo: {type_id}")
                else:
                    results['types_deleted'] += 1
                    results['types_paths'].append(type_id)
                    print(f"  [DRY RUN] Se eliminaría tipo: {type_id}")
            except Exception as e:
                error_msg = f"Error eliminando tipo {type_id}: {e}"
                results['errors'].append(error_msg)
                print(f"  ✗ {error_msg}")
        
        # 3. Limpiar org.json y platforms.json (solo si son completamente demo)
        # Esto es más conservador: solo eliminamos si TODAS las entradas son demo
        config_store = ConfigStoreV1(base_dir=DATA_DIR)
        
        # Verificar org
        org = config_store.load_org()
        if org and org.tax_id == DEMO_OWN_COMPANY_KEY:
            print(f"\n[Cleanup] Advertencia: Org demo encontrado ({org.tax_id})")
            print("  [NOTA] No se elimina org.json automáticamente por seguridad")
            print("  [NOTA] Si es necesario, elimínalo manualmente")
        
        # Verificar platforms
        platforms = config_store.load_platforms()
        demo_platforms = [p for p in platforms.platforms if p.key == DEMO_PLATFORM_KEY]
        if demo_platforms:
            print(f"\n[Cleanup] Advertencia: {len(demo_platforms)} plataforma(s) demo encontrada(s)")
            print("  [NOTA] No se eliminan plataformas automáticamente por seguridad")
            print("  [NOTA] Si es necesario, elimínalas manualmente desde la UI")
        
    except Exception as e:
        error_msg = f"Error general en cleanup: {e}"
        results['errors'].append(error_msg)
        print(f"\n✗ {error_msg}")
        import traceback
        traceback.print_exc()
    
    return results


def main():
    """Punto de entrada CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Limpia datos demo del repositorio'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Solo muestra qué se eliminaría sin borrar realmente'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("LIMPIEZA DE DATOS DEMO")
    print("=" * 60)
    
    if args.dry_run:
        print("\n[DRY RUN] Modo simulación - no se eliminará nada\n")
    else:
        print("\n⚠️  ADVERTENCIA: Se eliminarán datos demo permanentemente")
        response = input("¿Continuar? (s/N): ")
        if response.lower() != 's':
            print("Cancelado.")
            return
    
    results = cleanup_demo_data(dry_run=args.dry_run)
    
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Documentos eliminados: {results['docs_deleted']}")
    print(f"Tipos eliminados: {results['types_deleted']}")
    
    if results['errors']:
        print(f"\nErrores: {len(results['errors'])}")
        for error in results['errors']:
            print(f"  - {error}")
    
    if args.dry_run:
        print("\n[DRY RUN] Ejecuta sin --dry-run para aplicar los cambios")
    else:
        print("\n✓ Limpieza completada")


if __name__ == '__main__':
    main()
