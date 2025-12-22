from pathlib import Path

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


