"""
CometLocal v1.0 — Executor Contracts (schemas only)

Este módulo define únicamente **schemas/contratos** (Pydantic) para:
- Trace (eventos JSONL)
- Evidence refs + DOM snapshot (parcial/total)
- State signatures
- ActionSpec (incluye `assert` como acción de primera clase)
- Error codes / errores tipificados

No ejecuta Playwright ni cambia el API público existente.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


SCHEMA_VERSION_V1 = "v1"


class ErrorStageV1(str, Enum):
    proposal_validation = "proposal_validation"
    precondition = "precondition"
    execution = "execution"
    postcondition = "postcondition"
    policy = "policy"
    evidence = "evidence"


class ErrorSeverityV1(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


ERROR_CODES_V1: set[str] = {
    # PROPOSAL_*
    "PROPOSAL_SCHEMA_INVALID",
    "PROPOSAL_UNSUPPORTED_ACTION",
    "PROPOSAL_OUT_OF_SCOPE",
    "PROPOSAL_UNSAFE",
    # PRE_*
    "PRE_STATE_MISMATCH",
    "PRE_URL_NOT_ALLOWED",
    "PRE_TARGET_NOT_FOUND",
    "PRE_TARGET_NOT_VISIBLE",
    "PRE_TARGET_NOT_ENABLED",
    "PRE_AMBIGUOUS_TARGET",
    # EXEC_*
    "EXEC_TIMEOUT",
    "EXEC_NAVIGATION_FAILED",
    "EXEC_CLICK_FAILED",
    "EXEC_FILL_FAILED",
    "EXEC_SELECT_FAILED",
    "EXEC_UPLOAD_FAILED",
    "EXEC_DOWNLOAD_TRIGGERED",
    "EXEC_JS_EVALUATION_FAILED",
    "EXEC_BROWSER_DISCONNECTED",
    # POST_*
    "POST_NO_EFFECT",
    "POST_CONTRACT_MISMATCH",
    "POST_CONTRACT_VIOLATION",
    "POST_ASSERT_FAILED",
    # POLICY_*
    "POLICY_MAX_STEPS_REACHED",
    "POLICY_RETRY_LIMIT_REACHED",
    "POLICY_RECOVERY_LIMIT_REACHED",
    "POLICY_SAME_STATE_REVISIT",
    "POLICY_STOP_REQUESTED",
    # EVIDENCE_*
    "EVIDENCE_DOM_SNAPSHOT_FAILED",
    "EVIDENCE_HTML_CAPTURE_FAILED",
    "EVIDENCE_SCREENSHOT_FAILED",
    "EVIDENCE_PERSIST_FAILED",
    # SECURITY_*
    "SECURITY_BLOCKED_CRITICAL_ACTION",
    "SECURITY_BLOCKED_DOMAIN_ESCAPE",
    # EXTERNAL_*
    "EXTERNAL_CAPTCHA_DETECTED",
    "EXTERNAL_SSO_INTERSTITIAL",
    "EXTERNAL_2FA_REQUIRED",
    "EXTERNAL_MODAL_BLOCKING",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_text(s: Optional[str], *, max_len: int = 3000) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(r"\s+", " ", s).strip()
    if max_len > 0 and len(s) > max_len:
        s = s[:max_len]
    return s


def sha256_text(s: Optional[str], *, max_len: int = 3000) -> str:
    norm = _normalize_text(s, max_len=max_len)
    return _sha256_bytes(norm.encode("utf-8"))


class ExecutorErrorV1(BaseModel):
    schema_version: Literal["v1"] = Field(default=SCHEMA_VERSION_V1)

    error_code: str
    stage: ErrorStageV1
    severity: ErrorSeverityV1 = ErrorSeverityV1.error

    message: str
    retryable: bool = False

    debug_message: Optional[str] = None
    cause: Optional[str] = None  # repr(exc) si aplica
    details: Dict[str, Any] = Field(default_factory=dict)

    created_at: str = Field(default_factory=_now_iso)

    @field_validator("error_code")
    @classmethod
    def _validate_error_code(cls, v: str) -> str:
        if v not in ERROR_CODES_V1:
            raise ValueError(f"Unknown error_code={v!r} (not in ERROR_CODES_V1)")
        return v


class EvidenceKindV1(str, Enum):
    dom_snapshot_partial = "dom_snapshot_partial"
    html_full = "html_full"
    screenshot_hash = "screenshot_hash"
    screenshot = "screenshot"
    console_log = "console_log"
    network_har = "network_har"
    trace_ref = "trace_ref"


class EvidenceRefV1(BaseModel):
    kind: EvidenceKindV1
    uri: str  # path relativo o URI lógico
    sha256: Optional[str] = None
    mime_type: Optional[str] = None
    redacted: Optional[bool] = None
    size_bytes: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VisibleAnchorV1(BaseModel):
    text: str = ""
    href: str = ""
    selector: Optional[str] = None
    attrs: Dict[str, str] = Field(default_factory=dict)


class VisibleInputV1(BaseModel):
    selector: str
    input_type: str = "text"
    name: Optional[str] = None
    label: Optional[str] = None
    value_redacted: Optional[str] = None
    attrs: Dict[str, str] = Field(default_factory=dict)


class DomNodeSnapshotV1(BaseModel):
    """
    Snapshot acotado del subárbol DOM relevante para un target.
    Debe poder serializarse sin HTML completo.
    """

    selector: Optional[str] = None
    tag: Optional[str] = None
    text: Optional[str] = None
    attrs: Dict[str, str] = Field(default_factory=dict)
    children: List["DomNodeSnapshotV1"] = Field(default_factory=list)


DomNodeSnapshotV1.model_rebuild()


class DomTargetSnapshotV1(BaseModel):
    """
    Snapshot de un target y su contexto (ancestros + siblings + subárbol).
    """

    target_selector: Optional[str] = None
    target_text: Optional[str] = None
    context: DomNodeSnapshotV1


class DomSnapshotV1(BaseModel):
    schema_version: Literal["v1"] = Field(default=SCHEMA_VERSION_V1)

    url: str
    title: str
    captured_at: str = Field(default_factory=_now_iso)

    targets: List[DomTargetSnapshotV1] = Field(default_factory=list)
    visible_anchors: List[VisibleAnchorV1] = Field(default_factory=list)
    visible_inputs: List[VisibleInputV1] = Field(default_factory=list)

    truncated: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StateSignatureV1(BaseModel):
    """
    Firma estable del estado observado.

    v1: hash(url + title + elementos clave + texto visible acotado) + hash de screenshot.
    """

    schema_version: Literal["v1"] = Field(default=SCHEMA_VERSION_V1)
    algorithm_version: Literal["v1"] = "v1"

    url_hash: str
    title_hash: str
    key_elements_hash: str
    visible_text_hash: str
    screenshot_hash: str

    # opcional (no imprescindible para auditoría; útil para debug)
    url: Optional[str] = None

    created_at: str = Field(default_factory=_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def compute_state_signature_v1(
    *,
    url: str,
    title: str,
    key_elements: Any,
    visible_text: str,
    screenshot_hash: str,
    visible_text_max_len: int = 3000,
) -> StateSignatureV1:
    """
    Helper determinista para construir StateSignatureV1 dado material ya extraído.

    Nota: este helper NO extrae DOM ni toma screenshots; solo hashea entradas.
    """
    key_elements_json = json.dumps(key_elements, ensure_ascii=False, sort_keys=True, default=str)
    return StateSignatureV1(
        url_hash=sha256_text(url, max_len=4096),
        title_hash=sha256_text(title, max_len=512),
        key_elements_hash=_sha256_bytes(_normalize_text(key_elements_json, max_len=20000).encode("utf-8")),
        visible_text_hash=sha256_text(visible_text, max_len=visible_text_max_len),
        screenshot_hash=str(screenshot_hash or ""),
        url=url,
    )


class TargetKindV1(str, Enum):
    selector = "selector"
    text = "text"
    role = "role"
    coordinates = "coordinates"
    url = "url"


class TargetV1(BaseModel):
    type: TargetKindV1

    selector: Optional[str] = None
    text: Optional[str] = None
    role: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    url: Optional[str] = None

    @model_validator(mode="after")
    def _validate_target_shape(self) -> "TargetV1":
        t = self.type
        if t == TargetKindV1.selector and not self.selector:
            raise ValueError("TargetV1.type=selector requires selector")
        if t == TargetKindV1.text and not self.text:
            raise ValueError("TargetV1.type=text requires text")
        if t == TargetKindV1.role and not self.role:
            raise ValueError("TargetV1.type=role requires role")
        if t == TargetKindV1.coordinates and (self.x is None or self.y is None):
            raise ValueError("TargetV1.type=coordinates requires x and y")
        if t == TargetKindV1.url and not self.url:
            raise ValueError("TargetV1.type=url requires url")
        return self


class ConditionKindV1(str, Enum):
    # URL / navegación
    url_equals = "url_equals"
    url_contains = "url_contains"
    url_in_allowlist = "url_in_allowlist"
    # DOM
    selector_visible = "selector_visible"
    selector_enabled = "selector_enabled"
    text_present = "text_present"
    # Formularios
    field_equals = "field_equals"
    # Visual
    visual_contract_match = "visual_contract_match"


class ConditionV1(BaseModel):
    kind: ConditionKindV1
    args: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    severity: ErrorSeverityV1 = ErrorSeverityV1.error


class ActionKindV1(str, Enum):
    navigate = "navigate"
    click = "click"
    fill = "fill"
    select = "select"
    upload = "upload"
    wait_for = "wait_for"
    assert_ = "assert"  # palabra reservada
    noop = "noop"


class ActionCriticalityV1(str, Enum):
    normal = "normal"
    critical = "critical"


class ActionSpecV1(BaseModel):
    schema_version: Literal["v1"] = Field(default=SCHEMA_VERSION_V1)

    action_id: str = Field(..., description="Identificador estable de acción dentro del run")
    kind: ActionKindV1
    target: Optional[TargetV1] = None

    preconditions: List[ConditionV1] = Field(default_factory=list)
    postconditions: List[ConditionV1] = Field(default_factory=list)

    timeout_ms: Optional[int] = None
    criticality: ActionCriticalityV1 = ActionCriticalityV1.normal
    tags: List[str] = Field(default_factory=list)

    # Para assert como acción de primera clase:
    assertions: List[ConditionV1] = Field(default_factory=list)

    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_action(self) -> "ActionSpecV1":
        if self.kind == ActionKindV1.assert_:
            if not self.assertions and not self.postconditions:
                raise ValueError("ActionSpec(kind=assert) requires assertions or postconditions")
        else:
            if self.target is None and self.kind not in (ActionKindV1.noop,):
                raise ValueError(f"ActionSpec(kind={self.kind.value}) requires target")
        if not self.preconditions:
            raise ValueError("ActionSpec requires at least one precondition (v1 invariant)")
        if not self.postconditions and self.kind != ActionKindV1.noop:
            # assert puede usar assertions en lugar de postconditions; wait_for puede usar postcond también.
            if self.kind != ActionKindV1.assert_:
                raise ValueError("ActionSpec requires at least one postcondition (v1 invariant)")
        return self


class ActionStatusV1(str, Enum):
    success = "success"
    failed = "failed"
    skipped_by_policy = "skipped_by_policy"


class ActionResultV1(BaseModel):
    schema_version: Literal["v1"] = Field(default=SCHEMA_VERSION_V1)
    status: ActionStatusV1
    error: Optional[ExecutorErrorV1] = None

    state_before: Optional[StateSignatureV1] = None
    state_after: Optional[StateSignatureV1] = None

    evidence_refs: List[EvidenceRefV1] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TraceEventTypeV1(str, Enum):
    run_started = "run_started"
    proposal_received = "proposal_received"
    proposal_rejected = "proposal_rejected"
    proposal_accepted = "proposal_accepted"
    action_started = "action_started"
    preconditions_checked = "preconditions_checked"
    action_executed = "action_executed"
    postconditions_checked = "postconditions_checked"
    action_finished = "action_finished"
    retry_scheduled = "retry_scheduled"
    backoff_applied = "backoff_applied"
    recovery_started = "recovery_started"
    recovery_finished = "recovery_finished"
    policy_halt = "policy_halt"
    run_finished = "run_finished"


class TraceEventV1(BaseModel):
    schema_version: Literal["v1"] = Field(default=SCHEMA_VERSION_V1)

    run_id: str
    seq: int
    ts: str = Field(default_factory=_now_iso)
    event_type: TraceEventTypeV1

    step_index: int = 0
    sub_goal_index: Optional[int] = None

    state_before: Optional[StateSignatureV1] = None
    state_after: Optional[StateSignatureV1] = None

    action_spec: Optional[ActionSpecV1] = None
    result: Optional[ActionResultV1] = None
    error: Optional[ExecutorErrorV1] = None

    evidence_refs: List[EvidenceRefV1] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


