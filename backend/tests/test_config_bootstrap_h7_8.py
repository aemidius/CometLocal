from pathlib import Path

from backend.repository.data_bootstrap_v1 import ensure_data_layout


def test_ensure_data_layout_creates_dirs_and_files(tmp_path: Path):
    base = tmp_path / "data"
    ensure_data_layout(base_dir=base)

    assert (base / "documents").exists()
    assert (base / "documents" / "_inspections").exists()
    assert (base / "refs").exists()
    assert (base / "tmp" / "uploads").exists()
    assert (base / "runs").exists()

    assert (base / "refs" / "documents.json").exists()
    assert (base / "refs" / "secrets.json").exists()
    assert (base / "refs" / "org.json").exists()
    assert (base / "refs" / "people.json").exists()
    assert (base / "refs" / "platforms.json").exists()




