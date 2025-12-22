from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.config_store_v1 import _atomic_write_json


class SecretsStoreV1:
    """
    Store local (JSON) para secretos.
    - secrets.json contiene refs -> secret_value
    - La UI nunca debe devolver valores en claro.
    """

    def __init__(self, *, base_dir: str | Path = "data"):
        self.base_dir = ensure_data_layout(base_dir=base_dir)
        self.refs_dir = (Path(self.base_dir) / "refs").resolve()
        self.path = self.refs_dir / "secrets.json"

    def _read(self) -> dict:
        if not self.path.exists():
            ensure_data_layout(base_dir=self.base_dir)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        _atomic_write_json(self.path, payload)

    def list_refs(self) -> Dict[str, str]:
        raw = self._read()
        secrets = raw.get("secrets") if isinstance(raw, dict) else {}
        if not isinstance(secrets, dict):
            secrets = {}
        # Nunca devolver valores reales
        return {k: "***" for k in secrets.keys()}

    def get_secret(self, password_ref: str) -> Optional[str]:
        raw = self._read()
        secrets = raw.get("secrets") if isinstance(raw, dict) else {}
        if not isinstance(secrets, dict):
            return None
        v = secrets.get(password_ref)
        return str(v) if v is not None else None

    def set_secret(self, password_ref: str, value: str) -> None:
        raw = self._read()
        secrets = raw.get("secrets") if isinstance(raw, dict) else {}
        if not isinstance(secrets, dict):
            secrets = {}
        secrets[str(password_ref)] = str(value)
        self._write({"schema_version": "v1", "secrets": secrets})


