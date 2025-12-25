import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")


def test_platforms_selector_spec_accepts_dict_and_string():
    from backend.shared.platforms_v1 import PlatformsV1, SelectorSpecV1

    raw = {
        "schema_version": "v1",
        "platforms": [
            {
                "key": "egestiona",
                "base_url": "https://coordinate.egestiona.es/login?origen=subcontrata",
                "login_fields": {
                    "requires_client": True,
                    "client_code_selector": {"kind": "css", "value": "input[name='ClientName']"},
                    "username_selector": "input[name='Username']",
                    "password_selector": {"kind": "css", "value": "input[name='Password']"},
                    "submit_selector": "button[type='submit']",
                },
                "coordinations": [
                    {
                        "label": "Kern",
                        "client_code": "GRUPO_INDUKERN",
                        "username": "F63161988",
                        "password_ref": "pw:egestiona:kern",
                        "post_login_selector": {"kind": "css", "value": "nav, aside"},
                    }
                ],
            }
        ],
    }

    p = PlatformsV1.model_validate(raw)
    plat = p.platforms[0]
    assert isinstance(plat.login_fields.client_code_selector, SelectorSpecV1)
    assert plat.login_fields.client_code_selector.value == "input[name='ClientName']"
    assert isinstance(plat.login_fields.username_selector, SelectorSpecV1)
    assert plat.login_fields.username_selector.kind == "css"
    assert plat.login_fields.username_selector.value == "input[name='Username']"
    assert isinstance(plat.coordinations[0].post_login_selector, SelectorSpecV1)

    dumped = p.model_dump(mode="json")
    assert isinstance(dumped["platforms"][0]["login_fields"]["client_code_selector"], dict)
    assert dumped["platforms"][0]["login_fields"]["client_code_selector"]["kind"] == "css"


def test_egestiona_flow_builds_wait_for_with_visible_any_and_not_visible(monkeypatch, tmp_path: Path):
    """
    No ejecuta Playwright: monkeypatch del runtime para capturar acciones.
    """
    from backend.repository.data_bootstrap_v1 import ensure_data_layout
    from backend.adapters.egestiona import flows as f

    base = tmp_path / "data"
    ensure_data_layout(base_dir=base)

    platforms_path = base / "refs" / "platforms.json"
    secrets_path = base / "refs" / "secrets.json"

    platforms_payload = {
        "schema_version": "v1",
        "platforms": [
            {
                "key": "egestiona",
                "base_url": "https://coordinate.egestiona.es/login?origen=subcontrata",
                "login_fields": {
                    "requires_client": True,
                    "client_code_selector": {"kind": "css", "value": "input[name='ClientName']"},
                    "username_selector": {"kind": "css", "value": "input[name='Username']"},
                    "password_selector": {"kind": "css", "value": "input[name='Password']"},
                    "submit_selector": {"kind": "css", "value": "button[type='submit']"},
                },
                "coordinations": [
                    {
                        "label": "Kern",
                        "client_code": "GRUPO_INDUKERN",
                        "username": "F63161988",
                        "password_ref": "pw:egestiona:kern",
                        "post_login_selector": {"kind": "css", "value": "a[href*='logout'], nav, aside"},
                    }
                ],
            }
        ],
    }
    platforms_path.write_text(json.dumps(platforms_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    secrets_path.write_text(json.dumps({"schema_version": "v1", "secrets": {"pw:egestiona:kern": "SECRET"}}, ensure_ascii=False, indent=2), encoding="utf-8")

    captured = {"actions": None, "url": None}

    class DummyRt:
        def __init__(self, *args, **kwargs):
            pass

        def run_actions(self, *, url: str, actions, headless: bool = True):
            captured["url"] = url
            captured["actions"] = actions
            run_dir = base / "runs" / "r_dummy"
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir

    monkeypatch.setattr(f, "ExecutorRuntimeH4", DummyRt, raising=True)

    run_id = f.run_login_and_snapshot(base_dir=base, platform="egestiona", coordination="Kern", headless=True, execution_mode="training")
    assert run_id == "r_dummy"
    assert captured["actions"] is not None

    # Debe existir wait_for post-login con condiciones robustas:
    wait = next(a for a in captured["actions"] if a.action_id == "eg_wait_post_login")
    kinds = [c.kind.value for c in wait.postconditions]
    assert "element_visible_any" in kinds
    assert "element_not_visible" in kinds


