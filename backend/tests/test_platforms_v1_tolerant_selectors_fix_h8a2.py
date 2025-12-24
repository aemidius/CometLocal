import pytest


def test_normalize_selector_accepts_targetv1_dict_shape():
    from backend.shared.platforms_v1 import PlatformsV1

    raw = {
        "schema_version": "v1",
        "platforms": [
            {
                "key": "egestiona",
                "base_url": "https://coordinate.egestiona.es/login?origen=subcontrata",
                "login_fields": {
                    "client_code_selector": {"type": "css", "selector": "input[name='ClientName']"},
                    "username_selector": {"type": "css", "selector": "input[name='Username']"},
                    "password_selector": {"type": "css", "selector": "input[name='Password']"},
                    "submit_selector": {"type": "css", "selector": "button[type='submit']"},
                },
                "coordinations": [
                    {
                        "label": "Kern",
                        "post_login_selector": {"type": "css", "selector": "nav, aside"},
                    }
                ],
            }
        ],
    }

    p = PlatformsV1.model_validate(raw)
    lf = p.platforms[0].login_fields
    assert lf.client_code_selector is not None
    assert lf.client_code_selector.kind == "css"
    assert "ClientName" in lf.client_code_selector.value
    assert p.platforms[0].coordinations[0].post_login_selector is not None


