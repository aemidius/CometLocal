from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from backend.adapters.egestiona.profile import EgestionaProfileV1
from backend.adapters.egestiona.targets import build_targets_from_selectors

# H8.D FIX: Selector post-login definitivo (pantalla inicial post-login)
POST_LOGIN_SELECTOR_DEFAULT = EgestionaProfileV1().POST_LOGIN_SELECTOR
from backend.executor.runtime_h4 import ExecutorRuntimeH4
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    ErrorSeverityV1,
    TargetKindV1,
    TargetV1,
)
from backend.shared.platforms_v1 import SelectorSpecV1


def run_login_and_snapshot(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = True,
    execution_mode: str = "production",
    fail_fast: bool = False,
) -> str:
    """
    Ejecuta login determinista (sin LLM) usando Config Store + Secrets Store.
    Devuelve run_id.
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # H8.B: si no viene en config, usar default estable
    if not coord.post_login_selector:
        coord.post_login_selector = SelectorSpecV1(kind="css", value=POST_LOGIN_SELECTOR_DEFAULT)
        # write-back para dejarlo fijo
        store.save_platforms(platforms)

    # URL: override > platform.base_url > default
    url = coord.url_override or plat.base_url or EgestionaProfileV1().default_base_url

    # FIX H8.A2+: si faltan selectors, autocompletar defaults estables y (opcional) persistir.
    autofilled = False
    lf = plat.login_fields
    if lf.client_code_selector is None:
        lf.client_code_selector = SelectorSpecV1(kind="css", value="input[name='ClientName']")
        autofilled = True
    if lf.username_selector is None:
        lf.username_selector = SelectorSpecV1(kind="css", value="input[name='Username']")
        autofilled = True
    if lf.password_selector is None:
        lf.password_selector = SelectorSpecV1(kind="css", value="input[name='Password']")
        autofilled = True
    if lf.submit_selector is None:
        lf.submit_selector = SelectorSpecV1(kind="css", value="button[type='submit']")
        autofilled = True

    if autofilled:
        # write-back para evitar 400 permanente y dejar config estable
        store.save_platforms(platforms)

    targets = build_targets_from_selectors(
        client_code_selector=plat.login_fields.client_code_selector,
        username_selector=plat.login_fields.username_selector,
        password_selector=plat.login_fields.password_selector,
        submit_selector=plat.login_fields.submit_selector,
        post_login_selector=coord.post_login_selector,
    )

    actions: list[ActionSpecV1] = []

    actions.append(
        ActionSpecV1(
            action_id="eg_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="eg_fill_client",
                kind=ActionKindV1.fill,
                target=targets.client_code,
                input={"text": coord.client_code},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": targets.client_code.model_dump(), "value": coord.client_code},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="eg_fill_user",
            kind=ActionKindV1.fill,
            target=targets.username,
            input={"text": coord.username},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.username.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": targets.username.model_dump(), "value": coord.username}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    # password: secret_ref (no viaja en claro por config; se resuelve en runtime)
    actions.append(
        ActionSpecV1(
            action_id="eg_fill_pass",
            kind=ActionKindV1.fill,
            target=targets.password,
            input={"secret_ref": coord.password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.password.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": targets.password.model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="eg_click_submit",
            kind=ActionKindV1.click,
            target=targets.submit,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": targets.submit.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # Post-login wait: elemento estable (determinista)
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_post_login",
            kind=ActionKindV1.wait_for,
            target=targets.post_login,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                # OR lógico: basta con que exista/sea visible algún elemento post-login (>=1).
                ConditionV1(kind=ConditionKindV1.element_visible_any, args={"target": targets.post_login.model_dump()}, severity=ErrorSeverityV1.critical),
                # Login REAL: el formulario ya no puede estar visible tras submit.
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical, description="Login form must be gone (ClientName not visible)"),
            ],
            timeout_ms=20000,
        )
    )

    # H8.D: post-login condition REAL (estable y fuerte).
    # Debe ser visible un elemento inequívoco del dashboard (nav lateral con "Inicio") para considerar SUCCESS.
    post_login_strict = TargetV1(type=TargetKindV1.css, selector=POST_LOGIN_SELECTOR_DEFAULT)
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_post_login_real",
            kind=ActionKindV1.wait_for,
            target=post_login_strict,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": post_login_strict.model_dump()}, severity=ErrorSeverityV1.critical),
                # U5 strong postcondition (y robustez extra): no seguir en una URL de login.
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",
        )
    )

    # Assert final: no puede terminar success si seguimos en login.
    actions.append(
        ActionSpecV1(
            action_id="eg_assert_not_login",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[],
            assertions=[
                ConditionV1(kind=ConditionKindV1.element_visible_any, args={"target": targets.post_login.model_dump()}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=5000,
        )
    )

    # Asegurar que el password_ref existe (fail fast)
    if coord.password_ref and secrets.get_secret(coord.password_ref) is None:
        raise ValueError(f"password_ref not found in secrets.json: {coord.password_ref}")

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode=execution_mode,
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=fail_fast, execution_mode="deterministic")
    return run_dir.name


router = APIRouter(tags=["egestiona"])


@router.post("/runs/egestiona/login")
async def egestiona_login(coord: str = "Kern"):
    """
    Ejecuta login determinista a eGestiona usando Config Store (platform=egestiona, coordination=<coord>).
    """
    try:
        run_id = await run_in_threadpool(lambda: run_login_and_snapshot(base_dir="data", platform="egestiona", coordination=coord, headless=True, execution_mode="production"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


