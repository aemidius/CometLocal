import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pathlib import Path

from backend.executor.config_viewer import create_config_viewer_router
from backend.repository.secrets_store_v1 import SecretsStoreV1


def test_config_secrets_page_does_not_leak_secret(tmp_path: Path):
    base = tmp_path / "data"
    secrets = SecretsStoreV1(base_dir=base)
    secrets.set_secret("pw:test", "TOPSECRET")

    app = FastAPI()
    app.include_router(create_config_viewer_router(base_dir=base))
    client = TestClient(app)

    r = client.get("/config/secrets")
    assert r.status_code == 200
    assert "TOPSECRET" not in r.text
    assert "***" in r.text





