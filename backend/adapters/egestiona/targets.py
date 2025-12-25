from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.shared.executor_contracts_v1 import TargetKindV1, TargetV1
from backend.shared.platforms_v1 import SelectorSpecV1


@dataclass(frozen=True)
class EgestionaLoginTargetsV1:
    client_code: TargetV1
    username: TargetV1
    password: TargetV1
    submit: TargetV1
    post_login: TargetV1


def _spec_to_target(spec: SelectorSpecV1) -> TargetV1:
    if spec.kind == "css":
        return TargetV1(type=TargetKindV1.css, selector=spec.value)
    if spec.kind == "xpath":
        return TargetV1(type=TargetKindV1.xpath, selector=spec.value)
    raise ValueError(f"Unsupported selector kind: {spec.kind}")


def build_targets_from_selectors(
    *,
    client_code_selector: Optional[SelectorSpecV1],
    username_selector: Optional[SelectorSpecV1],
    password_selector: Optional[SelectorSpecV1],
    submit_selector: Optional[SelectorSpecV1],
    post_login_selector: Optional[SelectorSpecV1],
) -> EgestionaLoginTargetsV1:
    if not (client_code_selector and username_selector and password_selector and submit_selector and post_login_selector):
        raise ValueError("Missing required selectors for eGestiona login flow")
    return EgestionaLoginTargetsV1(
        client_code=_spec_to_target(client_code_selector),
        username=_spec_to_target(username_selector),
        password=_spec_to_target(password_selector),
        submit=_spec_to_target(submit_selector),
        post_login=_spec_to_target(post_login_selector),
    )


