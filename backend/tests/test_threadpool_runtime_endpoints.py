import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pathlib import Path


def test_config_test_login_uses_threadpool(monkeypatch, tmp_path: Path):
    # Arrange: config mínima con una plataforma
    from backend.executor.config_viewer import create_config_viewer_router
    from backend.repository.config_store_v1 import ConfigStoreV1
    from backend.shared.platforms_v1 import PlatformsV1, PlatformV1

    base = tmp_path / "data"
    store = ConfigStoreV1(base_dir=base)
    store.save_platforms(PlatformsV1(platforms=[PlatformV1(key="egestiona_kern", base_url="https://example.invalid")]))

    # Spy threadpool
    import backend.executor.threaded_runtime as tr

    called = {"tp": 0, "run": 0}

    async def fake_run_in_threadpool(fn):
        called["tp"] += 1
        return fn()

    monkeypatch.setattr(tr, "run_in_threadpool", fake_run_in_threadpool, raising=True)

    # Patch run_actions para no tocar Playwright
    import backend.executor.config_viewer as cv

    def fake_run_actions(self, **kwargs):
        called["run"] += 1
        return (tmp_path / "data" / "runs" / "r_fake")

    monkeypatch.setattr(cv.ExecutorRuntimeH4, "run_actions", fake_run_actions, raising=True)

    app = FastAPI()
    app.include_router(create_config_viewer_router(base_dir=base))
    client = TestClient(app)

    # Act
    resp = client.post("/config/platforms/test_login", allow_redirects=False)

    # Assert
    assert resp.status_code in (302, 303)
    assert called["tp"] == 1
    assert called["run"] == 1


def test_runs_demo_uses_threadpool(monkeypatch, tmp_path: Path):
    from backend.executor.runs_viewer import create_runs_viewer_router
    import backend.executor.threaded_runtime as tr
    import backend.executor.runs_viewer as rv

    called = {"tp": 0, "run": 0}

    async def fake_run_in_threadpool(fn):
        called["tp"] += 1
        return fn()

    monkeypatch.setattr(tr, "run_in_threadpool", fake_run_in_threadpool, raising=True)

    def fake_run_actions(self, **kwargs):
        called["run"] += 1
        return (tmp_path / "data" / "runs" / "r_demo")

    monkeypatch.setattr(rv.ExecutorRuntimeH4, "run_actions", fake_run_actions, raising=True)

    app = FastAPI()
    app.include_router(create_runs_viewer_router(runs_root=tmp_path / "data" / "runs"))
    client = TestClient(app)

    resp = client.post("/runs/demo")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "r_demo"
    assert called["tp"] == 1
    assert called["run"] == 1




