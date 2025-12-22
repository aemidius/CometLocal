from pathlib import Path

from backend.repository.data_bootstrap_v1 import ensure_data_layout


def test_bootstrap_does_not_overwrite_existing_refs(tmp_path: Path):
    base = tmp_path / "data"
    ensure_data_layout(base_dir=base)

    org_path = base / "refs" / "org.json"
    original = org_path.read_text(encoding="utf-8")

    # Simular edición del usuario
    org_path.write_text('{"schema_version":"v1","org":{"legal_name":"KEEP","tax_id":"X","org_type":"SCCL","notes":""}}', encoding="utf-8")

    ensure_data_layout(base_dir=base)
    assert org_path.read_text(encoding="utf-8").find('"KEEP"') != -1


