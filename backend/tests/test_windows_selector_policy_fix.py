import pytest


def test_windows_selector_policy_is_applied(monkeypatch):
    import backend.executor.browser_controller as bc

    called = {"count": 0}

    def fake_set_policy(_policy):
        called["count"] += 1

    # Simular Windows sin tocar Playwright
    monkeypatch.setattr(bc.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(bc.asyncio, "set_event_loop_policy", fake_set_policy, raising=True)
    monkeypatch.setattr(bc.asyncio, "WindowsProactorEventLoopPolicy", lambda: object(), raising=True)

    bc._ensure_windows_proactor_policy_for_playwright()
    assert called["count"] == 1


