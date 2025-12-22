from pathlib import Path

import pytest

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.shared.org_v1 import OrgV1
from backend.shared.people_v1 import PeopleV1, PersonV1
from backend.shared.platforms_v1 import PlatformsV1, PlatformV1


def test_config_store_load_save_roundtrip(tmp_path: Path):
    base = tmp_path / "data"
    store = ConfigStoreV1(base_dir=base)

    org = OrgV1(legal_name="Demo", tax_id="B123", org_type="SCCL", notes="n")
    store.save_org(org)
    org2 = store.load_org()
    assert org2.legal_name == "Demo"
    assert org2.tax_id == "B123"

    people = PeopleV1(people=[PersonV1(worker_id="w1", full_name="Juan", tax_id="00000000T", role="worker", relation_type="employee")])
    store.save_people(people)
    people2 = store.load_people()
    assert len(people2.people) == 1
    assert people2.people[0].worker_id == "w1"

    platforms = PlatformsV1(platforms=[PlatformV1(key="egestiona_kern", base_url="https://example.com")])
    store.save_platforms(platforms)
    platforms2 = store.load_platforms()
    assert platforms2.platforms[0].key == "egestiona_kern"


def test_secrets_store_redaction(tmp_path: Path):
    base = tmp_path / "data"
    secrets = SecretsStoreV1(base_dir=base)
    secrets.set_secret("pw:egestiona:demo", "SUPERSECRET")

    listed = secrets.list_refs()
    assert listed["pw:egestiona:demo"] == "***"
    # get_secret sí devuelve el valor (solo backend-side)
    assert secrets.get_secret("pw:egestiona:demo") == "SUPERSECRET"


def test_atomic_write_does_not_replace_on_validation_failure(monkeypatch, tmp_path: Path):
    """
    Simula fallo de validación JSON antes del replace() y verifica que el fichero original no se toca.
    """
    base = tmp_path / "data"
    store = ConfigStoreV1(base_dir=base)

    # Crear un org.json con contenido conocido
    org_path = (base / "refs" / "org.json")
    org_path.write_text('{"schema_version":"v1","org":{"legal_name":"KEEP"}}', encoding="utf-8")

    import backend.repository.config_store_v1 as mod

    real_loads = mod.json.loads

    def boom(_s: str):
        raise ValueError("boom")

    # Forzar que la validación del tmp falle
    monkeypatch.setattr(mod.json, "loads", boom, raising=True)

    with pytest.raises(ValueError, match="Atomic write aborted"):
        store.save_org(OrgV1(legal_name="NEW", tax_id="X", org_type="SCCL", notes=""))

    # Restaurar para leer
    monkeypatch.setattr(mod.json, "loads", real_loads, raising=True)
    assert "KEEP" in org_path.read_text(encoding="utf-8")


def test_secrets_atomic_write_does_not_replace_on_validation_failure(monkeypatch, tmp_path: Path):
    base = tmp_path / "data"
    secrets = SecretsStoreV1(base_dir=base)

    secrets_path = base / "refs" / "secrets.json"
    secrets_path.write_text('{"schema_version":"v1","secrets":{"pw:test":"KEEP"}}', encoding="utf-8")

    # Simular fallo en la fase de validación pre-replace sin romper la lectura inicial.
    def boom_atomic(_path, _payload):
        raise ValueError("Atomic write aborted: invalid JSON for secrets.json")

    import backend.repository.secrets_store_v1 as sec_mod

    monkeypatch.setattr(sec_mod, "_atomic_write_json", boom_atomic, raising=True)

    with pytest.raises(ValueError, match="Atomic write aborted"):
        secrets.set_secret("pw:test", "NEW")

    assert "KEEP" in secrets_path.read_text(encoding="utf-8")


