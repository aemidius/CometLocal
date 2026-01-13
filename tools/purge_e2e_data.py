#!/usr/bin/env python3
"""
SPRINT C2.10.1: Script de purga de datos E2E

Elimina documentos y tipos de documento cuyo ID empiece por "E2E_".
Solo funciona en entorno dev/local (verifica E2E_SEED_ENABLED o entorno local).

Uso:
    python tools/purge_e2e_data.py [--dry-run] [--verbose]

Ejemplos:
    python tools/purge_e2e_data.py --dry-run  # Simular sin borrar
    python tools/purge_e2e_data.py --verbose   # Mostrar detalles
"""

import sys
import os
from pathlib import Path
from typing import List, Dict

# Añadir raíz del proyecto al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1


def is_dev_environment() -> bool:
    """Verifica que estamos en entorno dev/local."""
    # Permitir si E2E_SEED_ENABLED está activado (entorno de tests)
    if os.getenv("E2E_SEED_ENABLED") == "1":
        return True
    
    # Permitir si estamos en desarrollo local (sin producción)
    # Por seguridad, requerir variable explícita o estar en localhost
    if os.getenv("ENVIRONMENT") in ("dev", "development", "local"):
        return True
    
    # Por defecto, solo permitir si hay variable explícita
    return False


def purge_e2e_data(dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
    """
    Purga datos E2E del repositorio.
    
    Returns:
        Dict con contadores: {'types_deleted': int, 'docs_deleted': int, 'errors': int}
    """
    if not is_dev_environment():
        print("ERROR: Este script solo puede ejecutarse en entorno dev/local.")
        print("       Establece E2E_SEED_ENABLED=1 o ENVIRONMENT=dev")
        sys.exit(1)
    
    store = DocumentRepositoryStoreV1()
    stats = {
        'types_deleted': 0,
        'docs_deleted': 0,
        'errors': 0
    }
    
    # 1. Listar todos los tipos
    all_types = store.list_types(include_inactive=True)
    e2e_types = [t for t in all_types if t.type_id.startswith("E2E_")]
    
    if verbose:
        print(f"[INFO] Encontrados {len(e2e_types)} tipos E2E de {len(all_types)} totales")
    
    # 2. Para cada tipo E2E, eliminar documentos y luego el tipo
    for doc_type in e2e_types:
        type_id = doc_type.type_id
        if verbose:
            print(f"[INFO] Procesando tipo: {type_id}")
        
        try:
            # Listar documentos de este tipo
            docs = store.list_documents(type_id=type_id)
            e2e_docs = [d for d in docs if d.doc_id.startswith("E2E_")]
            
            if verbose and e2e_docs:
                print(f"  [INFO] Encontrados {len(e2e_docs)} documentos E2E para tipo {type_id}")
            
            # Eliminar documentos E2E
            for doc in e2e_docs:
                doc_id = doc.doc_id
                if not dry_run:
                    try:
                        # Verificar que no esté submitted (delete_document lo verifica)
                        if doc.status == "submitted":
                            if verbose:
                                print(f"  [WARN] Saltando documento {doc_id} (status=submitted)")
                            stats['errors'] += 1
                            continue
                        
                        store.delete_document(doc_id)
                        stats['docs_deleted'] += 1
                        if verbose:
                            print(f"  [OK] Eliminado documento: {doc_id}")
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"  [ERROR] Error eliminando documento {doc_id}: {e}")
                else:
                    stats['docs_deleted'] += 1
                    if verbose:
                        print(f"  [DRY-RUN] Eliminaría documento: {doc_id}")
            
            # Eliminar tipo (solo si no hay más documentos o todos eran E2E)
            remaining_docs = [d for d in docs if not d.doc_id.startswith("E2E_")]
            if remaining_docs:
                if verbose:
                    print(f"  [WARN] Tipo {type_id} tiene {len(remaining_docs)} documentos no-E2E, no se elimina")
            else:
                if not dry_run:
                    try:
                        store.delete_type(type_id)
                        stats['types_deleted'] += 1
                        if verbose:
                            print(f"  [OK] Eliminado tipo: {type_id}")
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"  [ERROR] Error eliminando tipo {type_id}: {e}")
                else:
                    stats['types_deleted'] += 1
                    if verbose:
                        print(f"  [DRY-RUN] Eliminaría tipo: {type_id}")
        
        except Exception as e:
            stats['errors'] += 1
            print(f"[ERROR] Error procesando tipo {type_id}: {e}")
    
    # 3. También buscar documentos E2E huérfanos (sin tipo E2E asociado)
    all_docs = store.list_documents()
    orphan_e2e_docs = [
        d for d in all_docs 
        if d.doc_id.startswith("E2E_") and not any(t.type_id == d.type_id and t.type_id.startswith("E2E_") for t in e2e_types)
    ]
    
    if orphan_e2e_docs:
        if verbose:
            print(f"[INFO] Encontrados {len(orphan_e2e_docs)} documentos E2E huérfanos")
        
        for doc in orphan_e2e_docs:
            doc_id = doc.doc_id
            if not dry_run:
                try:
                    if doc.status == "submitted":
                        if verbose:
                            print(f"  [WARN] Saltando documento huérfano {doc_id} (status=submitted)")
                        stats['errors'] += 1
                        continue
                    
                    store.delete_document(doc_id)
                    stats['docs_deleted'] += 1
                    if verbose:
                        print(f"  [OK] Eliminado documento huérfano: {doc_id}")
                except Exception as e:
                    stats['errors'] += 1
                    print(f"  [ERROR] Error eliminando documento huérfano {doc_id}: {e}")
            else:
                stats['docs_deleted'] += 1
                if verbose:
                    print(f"  [DRY-RUN] Eliminaría documento huérfano: {doc_id}")
    
    return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Purga datos E2E del repositorio documental"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular sin borrar realmente'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Mostrar detalles de la operación'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("SPRINT C2.10.1: Purga de datos E2E")
    print("=" * 60)
    
    if args.dry_run:
        print("[MODO DRY-RUN] No se borrará nada realmente")
    
    if not is_dev_environment():
        print("\nERROR: Este script solo puede ejecutarse en entorno dev/local.")
        print("       Establece E2E_SEED_ENABLED=1 o ENVIRONMENT=dev")
        sys.exit(1)
    
    print("\nIniciando purga...")
    stats = purge_e2e_data(dry_run=args.dry_run, verbose=args.verbose)
    
    print("\n" + "=" * 60)
    print("RESUMEN:")
    print("=" * 60)
    print(f"Tipos eliminados: {stats['types_deleted']}")
    print(f"Documentos eliminados: {stats['docs_deleted']}")
    if stats['errors'] > 0:
        print(f"Errores: {stats['errors']}")
    print("=" * 60)
    
    if args.dry_run:
        print("\n[MODO DRY-RUN] Ejecuta sin --dry-run para aplicar los cambios")


if __name__ == "__main__":
    main()
