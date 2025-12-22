import pytest

pytest.importorskip("fastapi")

def test_egestiona_flow_fails_without_platform_config(tmp_path):
    from backend.repository.data_bootstrap_v1 import ensure_data_layout
    from backend.adapters.egestiona.flows import run_login_and_snapshot

    base = tmp_path / "data"
    ensure_data_layout(base_dir=base)

    # Sin platforms configuradas -> error determinista
    with pytest.raises(ValueError, match="platform not found"):
        run_login_and_snapshot(base_dir=base, platform="egestiona", coordination="Kern", headless=True)


