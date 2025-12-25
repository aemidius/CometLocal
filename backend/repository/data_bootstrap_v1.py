"""
H7.8 — DataBootstrap v1 (sin DB)

Responsabilidad:
- Asegurar que existe la estructura base de `data/`
- Crear archivos de refs con plantillas mínimas si faltan
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _write_json_if_missing(path: Path, payload: Dict[str, Any]) -> None:
    # Guardarraíl: NUNCA sobrescribir ficheros de config existentes.
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _warn_if_damaged_json(path: Path) -> None:
    """
    Si el fichero existe pero está vacío o contiene JSON inválido,
    NO lo sobrescribimos (por requerimiento). Solo avisamos.
    """
    if not path.exists():
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        print(f"[WARN] Config file unreadable (left as-is): {path}")
        return
    if not raw.strip():
        print(f"[WARN] Config file empty (left as-is): {path}")
        return
    try:
        json.loads(raw)
    except Exception:
        print(f"[WARN] Config file has invalid JSON (left as-is): {path}")


def ensure_data_layout(*, base_dir: str | Path = "data") -> Path:
    """
    Crea la estructura base de data/ si falta y devuelve base_dir (Path resuelto).
    """
    base = Path(base_dir).resolve()

    # Dirs
    (base / "documents").mkdir(parents=True, exist_ok=True)
    (base / "documents" / "_inspections").mkdir(parents=True, exist_ok=True)
    (base / "refs").mkdir(parents=True, exist_ok=True)
    (base / "tmp" / "uploads").mkdir(parents=True, exist_ok=True)
    (base / "runs").mkdir(parents=True, exist_ok=True)

    # Files
    documents_p = base / "refs" / "documents.json"
    secrets_p = base / "refs" / "secrets.json"
    org_p = base / "refs" / "org.json"
    people_p = base / "refs" / "people.json"
    platforms_p = base / "refs" / "platforms.json"

    _write_json_if_missing(documents_p, {"schema_version": "v1", "documents": {}})
    _write_json_if_missing(secrets_p, {"schema_version": "v1", "secrets": {}})

    _write_json_if_missing(
        org_p,
        {"schema_version": "v1", "org": {"legal_name": "", "tax_id": "", "org_type": "SCCL", "notes": ""}},
    )
    _write_json_if_missing(people_p, {"schema_version": "v1", "people": []})
    _write_json_if_missing(platforms_p, {"schema_version": "v1", "platforms": []})

    # Si existen pero están vacíos/dañados: avisar, nunca sobrescribir.
    for p in (documents_p, secrets_p, org_p, people_p, platforms_p):
        _warn_if_damaged_json(p)

    return base


