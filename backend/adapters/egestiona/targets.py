from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.shared.executor_contracts_v1 import TargetKindV1, TargetV1


@dataclass(frozen=True)
class EgestionaLoginTargetsV1:
    client_code: TargetV1
    username: TargetV1
    password: TargetV1
    submit: TargetV1
    post_login: TargetV1


def build_targets_from_selectors(
    *,
    client_code_selector: Optional[str],
    username_selector: Optional[str],
    password_selector: Optional[str],
    submit_selector: Optional[str],
    post_login_selector: Optional[str],
) -> EgestionaLoginTargetsV1:
    if not (client_code_selector and username_selector and password_selector and submit_selector and post_login_selector):
        raise ValueError("Missing required selectors for eGestiona login flow")
    return EgestionaLoginTargetsV1(
        client_code=TargetV1(type=TargetKindV1.css, selector=client_code_selector),
        username=TargetV1(type=TargetKindV1.css, selector=username_selector),
        password=TargetV1(type=TargetKindV1.css, selector=password_selector),
        submit=TargetV1(type=TargetKindV1.css, selector=submit_selector),
        post_login=TargetV1(type=TargetKindV1.css, selector=post_login_selector),
    )


