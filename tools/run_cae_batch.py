#!/usr/bin/env python3
"""
Script CLI para ejecutar batch CAE desde línea de comandos.

v3.1.0: Permite probar modo batch CAE fácilmente sin tocar el frontend.
"""

import json
import sys
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def load_cae_request(file_path: str) -> Dict[str, Any]:
    """Carga un CAEBatchRequest desde un archivo JSON."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cae_response(response: Dict[str, Any], output_dir: str = "runs") -> str:
    """Guarda un CAEBatchResponse en un archivo JSON."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_path / f"cae_{timestamp}.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)
    
    return str(filename)


def run_cae_batch(
    request_file: str,
    api_url: str = "http://127.0.0.1:8000",
    output_dir: str = "runs",
) -> None:
    """
    Ejecuta un batch CAE desde un archivo JSON.
    
    Args:
        request_file: Ruta al archivo JSON con CAEBatchRequest
        api_url: URL base de la API (por defecto localhost:8000)
        output_dir: Directorio donde guardar el resultado
    """
    print(f"[cae-batch-cli] Loading request from: {request_file}")
    
    try:
        request_data = load_cae_request(request_file)
    except Exception as e:
        print(f"[cae-batch-cli] Error loading request file: {e}", file=sys.stderr)
        sys.exit(1)
    
    endpoint = f"{api_url}/agent/cae/batch"
    print(f"[cae-batch-cli] Sending request to: {endpoint}")
    print(f"[cae-batch-cli] Platform: {request_data.get('platform', 'N/A')}")
    print(f"[cae-batch-cli] Company: {request_data.get('company_name', 'N/A')}")
    print(f"[cae-batch-cli] Workers: {len(request_data.get('workers', []))}")
    
    try:
        response = requests.post(
            endpoint,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=3600,  # 1 hora de timeout para batches largos
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Mostrar resumen
        summary = result.get("summary", {})
        print("\n[cae-batch-cli] Batch execution completed:")
        print(f"  Total workers: {summary.get('total_workers', 0)}")
        print(f"  Success: {summary.get('success_count', 0)}")
        print(f"  Failures: {summary.get('failure_count', 0)}")
        print(f"  Workers with errors: {summary.get('workers_with_errors', 0)}")
        print(f"  Workers with missing docs: {summary.get('workers_with_missing_docs', 0)}")
        
        # Guardar resultado
        output_file = save_cae_response(result, output_dir)
        print(f"\n[cae-batch-cli] Result saved to: {output_file}")
        
    except requests.exceptions.RequestException as e:
        print(f"[cae-batch-cli] Error calling API: {e}", file=sys.stderr)
        if hasattr(e, "response") and e.response is not None:
            print(f"[cae-batch-cli] Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[cae-batch-cli] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_cae_batch.py <request_file.json> [api_url] [output_dir]")
        print("\nExample:")
        print('  python run_cae_batch.py examples/cae_batch_request.json')
        sys.exit(1)
    
    request_file = sys.argv[1]
    api_url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "runs"
    
    run_cae_batch(request_file, api_url, output_dir)





















