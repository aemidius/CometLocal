"""
H8.D — Test eGestiona post-login selector definitivo
"""
import json
from pathlib import Path

import pytest

# No requiere fastapi, solo runtime


def test_egestiona_login_success_when_post_login_selector_visible(monkeypatch, tmp_path: Path):
    """
    Offline (sin Playwright):
    - Flow eGestiona con execution_mode="deterministic"
    - Cuando el selector post-login (nav a[href*='Inicio']) es visible → status="success"
    """
    pytest.importorskip("fastapi")
    from backend.adapters.egestiona.flows import run_login_and_snapshot
    from backend.adapters.egestiona.profile import EgestionaProfileV1
    from backend.executor import runtime_h4 as rtmod
    from backend.executor.action_compiler_v1 import ConditionEvaluation
    from backend.shared.executor_contracts_v1 import (
        ConditionKindV1,
        EvidenceItemV1,
        EvidenceKindV1,
        StateSignatureV1,
        TraceEventTypeV1,
    )

    class DummyCtrl:
        def __init__(self, *args, **kwargs):
            self.page = None

        def start(self, headless: bool = True):
            return None

        def navigate(self, url: str, timeout_ms: int = 0):
            return None

        def close(self):
            return None

        def capture_observation(self, step_id: str, evidence_dir, phase: str = "before", redactor=None):
            sig = StateSignatureV1(
                url_hash="u" * 64,
                title_hash="h" * 64,
                key_elements_hash="k" * 64,
                visible_text_hash="t" * 64,
                screenshot_hash="s" * 64,
            )
            item = EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id=step_id,
                relative_path=f"evidence/dom/{step_id}.json",
                sha256="0" * 64,
                size_bytes=0,
            )
            return ({}, sig, [item])

        def capture_html_full(self, *args, **kwargs):
            raise RuntimeError("not needed")

        def capture_screenshot_file(self, *args, **kwargs):
            raise RuntimeError("not needed")

    monkeypatch.setattr(rtmod, "BrowserController", DummyCtrl, raising=True)

    # evaluate_conditions: el selector post-login (nav a[href*='Inicio']) es visible
    post_login_selector = EgestionaProfileV1().POST_LOGIN_SELECTOR

    def fake_eval(conditions, controller, profile, policy, timeout_ms=None):
        out = []
        for c in conditions:
            if c.kind == ConditionKindV1.element_visible:
                tgt = (c.args or {}).get("target") or {}
                sel = (tgt.get("selector") or "") if isinstance(tgt, dict) else ""
                # Si es el selector post-login definitivo, devolver True (visible)
                if post_login_selector in sel or "Inicio" in sel:
                    out.append(ConditionEvaluation(c, True, {}))
                    continue
            # Resto: ok
            out.append(ConditionEvaluation(c, True, {}))
        return out

    monkeypatch.setattr(rtmod, "evaluate_conditions", fake_eval, raising=True)
    monkeypatch.setattr(rtmod, "execute_action_only", lambda *a, **k: {"ok": True, "metadata": {}}, raising=True)
    monkeypatch.setattr(rtmod, "validate_runtime", lambda *a, **k: None, raising=True)

    # Mock ConfigStore y SecretsStore
    from backend.repository.config_store_v1 import ConfigStoreV1
    from backend.repository.secrets_store_v1 import SecretsStoreV1
    from backend.repository.data_bootstrap_v1 import ensure_data_layout
    from backend.shared.platforms_v1 import PlatformsV1, PlatformV1, LoginFieldsV1, CoordinationV1, SelectorSpecV1

    base = ensure_data_layout(base_dir=tmp_path / "data")
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    # Crear platform config mínima
    platforms = PlatformsV1(
        platforms=[
            PlatformV1(
                key="egestiona",
                base_url="https://coordinate.egestiona.es",
                login_fields=LoginFieldsV1(
                    requires_client=True,
                    client_code_selector=SelectorSpecV1(kind="css", value="input[name='ClientName']"),
                    username_selector=SelectorSpecV1(kind="css", value="input[name='Username']"),
                    password_selector=SelectorSpecV1(kind="css", value="input[name='Password']"),
                    submit_selector=SelectorSpecV1(kind="css", value="button[type='submit']"),
                ),
                coordinations=[
                    CoordinationV1(
                        label="Kern",
                        client_code="GRUPO_INDUKERN",
                        username="F63161988",
                        password_ref="egestiona_kern_password",
                    )
                ],
            )
        ]
    )
    store.save_platforms(platforms)
    secrets.set_secret("egestiona_kern_password", "test_password")

    try:
        run_id = run_login_and_snapshot(
            base_dir=tmp_path / "data",
            platform="egestiona",
            coordination="Kern",
            headless=True,
            execution_mode="deterministic",
            fail_fast=False,
        )
        run_dir = tmp_path / "data" / "runs" / run_id
        trace_path = run_dir / "trace.jsonl"
        lines = [json.loads(x) for x in trace_path.read_text(encoding="utf-8").splitlines() if x.strip()]

        # Verificar status final: success
        finished = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_finished.value]
        assert finished, "missing run_finished"
        status = finished[-1]["metadata"]["status"]
        assert status == "success", f"login should succeed when post-login selector is visible, got: {status}"
    except Exception as e:
        pytest.fail(f"login flow should succeed when post-login selector is visible, got exception: {e}")


def test_egestiona_login_fails_when_post_login_selector_not_visible(monkeypatch, tmp_path: Path):
    """
    Offline (sin Playwright):
    - Flow eGestiona con execution_mode="deterministic"
    - Cuando el selector post-login NO es visible → status="failed"
    """
    pytest.importorskip("fastapi")
    from backend.adapters.egestiona.flows import run_login_and_snapshot
    from backend.adapters.egestiona.profile import EgestionaProfileV1
    from backend.executor import runtime_h4 as rtmod
    from backend.executor.action_compiler_v1 import ConditionEvaluation
    from backend.shared.executor_contracts_v1 import (
        ConditionKindV1,
        EvidenceItemV1,
        EvidenceKindV1,
        StateSignatureV1,
        TraceEventTypeV1,
    )

    class DummyCtrl:
        def __init__(self, *args, **kwargs):
            self.page = None

        def start(self, headless: bool = True):
            return None

        def navigate(self, url: str, timeout_ms: int = 0):
            return None

        def close(self):
            return None

        def capture_observation(self, step_id: str, evidence_dir, phase: str = "before", redactor=None):
            sig = StateSignatureV1(
                url_hash="u" * 64,
                title_hash="h" * 64,
                key_elements_hash="k" * 64,
                visible_text_hash="t" * 64,
                screenshot_hash="s" * 64,
            )
            item = EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id=step_id,
                relative_path=f"evidence/dom/{step_id}.json",
                sha256="0" * 64,
                size_bytes=0,
            )
            return ({}, sig, [item])

        def capture_html_full(self, *args, **kwargs):
            raise RuntimeError("not needed")

        def capture_screenshot_file(self, *args, **kwargs):
            raise RuntimeError("not needed")

    monkeypatch.setattr(rtmod, "BrowserController", DummyCtrl, raising=True)

    # evaluate_conditions: el selector post-login NO es visible (falla)
    post_login_selector = EgestionaProfileV1().POST_LOGIN_SELECTOR
    call_count = [0]

    def fake_eval(conditions, controller, profile, policy, timeout_ms=None):
        call_count[0] += 1
        out = []
        for c in conditions:
            if c.kind == ConditionKindV1.element_visible:
                tgt = (c.args or {}).get("target") or {}
                sel = (tgt.get("selector") or "") if isinstance(tgt, dict) else ""
                # Si es el selector post-login definitivo y ya pasamos varios steps, devolver False (no visible)
                if (post_login_selector in sel or "Inicio" in sel) and call_count[0] >= 8:
                    out.append(ConditionEvaluation(c, False, {"actual": "not visible"}))
                    continue
            # Resto: ok
            out.append(ConditionEvaluation(c, True, {}))
        return out

    monkeypatch.setattr(rtmod, "evaluate_conditions", fake_eval, raising=True)
    monkeypatch.setattr(rtmod, "execute_action_only", lambda *a, **k: {"ok": True, "metadata": {}}, raising=True)
    monkeypatch.setattr(rtmod, "validate_runtime", lambda *a, **k: None, raising=True)

    # Mock ConfigStore y SecretsStore
    from backend.repository.config_store_v1 import ConfigStoreV1
    from backend.repository.secrets_store_v1 import SecretsStoreV1
    from backend.repository.data_bootstrap_v1 import ensure_data_layout
    from backend.shared.platforms_v1 import PlatformsV1, PlatformV1, LoginFieldsV1, CoordinationV1, SelectorSpecV1

    base = ensure_data_layout(base_dir=tmp_path / "data")
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    # Crear platform config mínima
    platforms = PlatformsV1(
        platforms=[
            PlatformV1(
                key="egestiona",
                base_url="https://coordinate.egestiona.es",
                login_fields=LoginFieldsV1(
                    requires_client=True,
                    client_code_selector=SelectorSpecV1(kind="css", value="input[name='ClientName']"),
                    username_selector=SelectorSpecV1(kind="css", value="input[name='Username']"),
                    password_selector=SelectorSpecV1(kind="css", value="input[name='Password']"),
                    submit_selector=SelectorSpecV1(kind="css", value="button[type='submit']"),
                ),
                coordinations=[
                    CoordinationV1(
                        label="Kern",
                        client_code="GRUPO_INDUKERN",
                        username="F63161988",
                        password_ref="egestiona_kern_password",
                    )
                ],
            )
        ]
    )
    store.save_platforms(platforms)
    secrets.set_secret("egestiona_kern_password", "test_password")

    run_id = run_login_and_snapshot(
        base_dir=tmp_path / "data",
        platform="egestiona",
        coordination="Kern",
        headless=True,
        execution_mode="deterministic",
        fail_fast=False,
    )
    run_dir = tmp_path / "data" / "runs" / run_id
    trace_path = run_dir / "trace.jsonl"
    lines = [json.loads(x) for x in trace_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    # Verificar status final: failed
    finished = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_finished.value]
    assert finished, "missing run_finished"
    status = finished[-1]["metadata"]["status"]
    assert status == "failed", f"login should fail when post-login selector is not visible, got: {status}"

