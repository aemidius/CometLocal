from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.shared.org_v1 import OrgV1
from backend.shared.people_v1 import PeopleV1
from backend.shared.platforms_v1 import PlatformsV1


def _atomic_write_json(path: Path, payload: dict) -> None:
    """
    Escribe JSON de forma atómica:
    - escribe a <file>.tmp
    - valida que el tmp contiene JSON parseable
    - replace() sobre el original

    Si la validación falla, NO toca el original.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Validar JSON antes de reemplazar
    try:
        json.loads(tmp.read_text(encoding="utf-8"))
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError(f"Atomic write aborted: invalid JSON for {path.name}")
    tmp.replace(path)


class ConfigStoreV1:
    """
    Store local (JSON) para org/people/platforms (sin DB).
    """

    def __init__(self, *, base_dir: str | Path = "data"):
        self.base_dir = ensure_data_layout(base_dir=base_dir)
        self.refs_dir = (Path(self.base_dir) / "refs").resolve()

    def _read_json(self, name: str) -> dict:
        p = self.refs_dir / name
        if not p.exists():
            ensure_data_layout(base_dir=self.base_dir)
        return json.loads(p.read_text(encoding="utf-8"))

    def _write_json(self, name: str, payload: dict) -> None:
        p = self.refs_dir / name
        _atomic_write_json(p, payload)

    def load_org(self) -> OrgV1:
        raw = self._read_json("org.json")
        org = raw.get("org") if isinstance(raw, dict) else {}
        if isinstance(org, dict):
            org = {**org, "schema_version": "v1"}
        return OrgV1.model_validate(org)

    def save_org(self, org: OrgV1) -> None:
        self._write_json("org.json", {"schema_version": "v1", "org": org.model_dump(mode="json", exclude={"schema_version"})})

    def load_people(self) -> PeopleV1:
        raw = self._read_json("people.json")
        people = raw.get("people") if isinstance(raw, dict) else []
        return PeopleV1.model_validate({"schema_version": "v1", "people": people or []})

    def save_people(self, people: PeopleV1) -> None:
        # HOTFIX: Asegurar que own_company_key se persiste explícitamente
        # model_dump(mode="json") ya incluye own_company_key, pero lo verificamos explícitamente
        serialized_people = []
        for p in people.people:
            person_dict = p.model_dump(mode="json")
            # Asegurar que own_company_key está presente en el dict serializado
            # (model_dump ya lo incluye, pero esto es un guardrail explícito)
            person_dict["own_company_key"] = p.own_company_key
            serialized_people.append(person_dict)
        self._write_json("people.json", {"schema_version": "v1", "people": serialized_people})

    def load_platforms(self) -> PlatformsV1:
        raw = self._read_json("platforms.json")
        platforms = raw.get("platforms") if isinstance(raw, dict) else []
        return PlatformsV1.model_validate({"schema_version": "v1", "platforms": platforms or []})

    def save_platforms(self, platforms: PlatformsV1) -> None:
        # Persistir con aliases para soportar keys "client_input/user_input/pass_input/submit_btn/post_login_check"
        self._write_json(
            "platforms.json",
            {"schema_version": "v1", "platforms": [p.model_dump(mode="json", by_alias=True) for p in platforms.platforms]},
        )


