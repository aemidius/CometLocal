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
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    _write_json_if_missing(base / "refs" / "documents.json", {"schema_version": "v1", "documents": {}})
    _write_json_if_missing(base / "refs" / "secrets.json", {"schema_version": "v1", "secrets": {}})

    _write_json_if_missing(
        base / "refs" / "org.json",
        {"schema_version": "v1", "org": {"legal_name": "", "tax_id": "", "org_type": "SCCL", "notes": ""}},
    )
    _write_json_if_missing(base / "refs" / "people.json", {"schema_version": "v1", "people": []})
    _write_json_if_missing(base / "refs" / "platforms.json", {"schema_version": "v1", "platforms": []})

    return base


