import pytest

from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    EvidenceItemV1,
    EvidenceManifestV1,
    EvidencePolicyV1,
    ExecutorErrorV1,
    ErrorStageV1,
    ERROR_CODES_V1,
    EvidenceKindV1,
    RedactionPolicyV1,
    TraceEventTypeV1,
    TraceEventV1,
    TargetKindV1,
    TargetV1,
    compute_state_signature_v1,
)


def test_error_code_catalog_is_non_empty_and_stable():
    # sanity: evita catálogo vacío por accidente
    assert isinstance(ERROR_CODES_V1, set)
    assert len(ERROR_CODES_V1) > 10
    # canónicos (Block 4)
    assert "TARGET_NOT_FOUND" in ERROR_CODES_V1
    assert "INVALID_ACTIONSPEC" in ERROR_CODES_V1
    # compat extendido (no debe desaparecer)
    assert "POST_ASSERT_FAILED" in ERROR_CODES_V1
    assert "POLICY_MAX_STEPS_REACHED" in ERROR_CODES_V1


def test_executor_error_rejects_unknown_code():
    with pytest.raises(ValueError):
        ExecutorErrorV1(
            error_code="UNKNOWN_CODE_X",
            stage=ErrorStageV1.execution,
            message="boom",
            retryable=False,
        )


def test_action_spec_supports_assert_as_first_class_action():
    spec = ActionSpecV1(
        action_id="a1",
        kind=ActionKindV1.assert_,
        target=None,
        preconditions=[
            ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "portal"})
        ],
        postconditions=[],
        assertions=[
            ConditionV1(kind=ConditionKindV1.element_text_contains, args={"text": "OK"})
        ],
    )
    assert spec.kind == ActionKindV1.assert_
    assert len(spec.assertions) == 1


def test_action_spec_requires_pre_and_postconditions_for_non_noop():
    with pytest.raises(ValueError):
        ActionSpecV1(
            action_id="a2",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector="#btn"),
            preconditions=[],
            postconditions=[ConditionV1(kind=ConditionKindV1.toast_contains, args={"text": "Done"})],
        )

    with pytest.raises(ValueError):
        ActionSpecV1(
            action_id="a3",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector="#btn"),
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#btn"}})],
            postconditions=[],
        )


def test_trace_event_roundtrip_model_dump():
    sig = compute_state_signature_v1(
        url="https://example.com",
        title="Example",
        key_elements={"anchors": [{"text": "Home", "href": "/"}]},
        visible_text="Hello world",
        screenshot_hash="deadbeef",
    )

    spec = ActionSpecV1(
        action_id="a4",
        kind=ActionKindV1.navigate,
        target=TargetV1(type=TargetKindV1.url, url="https://example.com/login"),
        preconditions=[ConditionV1(kind=ConditionKindV1.host_in_allowlist, args={"allowlist": ["example.com"]})],
        postconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "/login"})],
    )

    ev = TraceEventV1(
        run_id="r1",
        seq=1,
        event_type=TraceEventTypeV1.action_started,
        step_id="step_000",
        step_index=0,
        state_signature_before=sig,
        action_spec=spec,
    )

    dumped = ev.model_dump()
    reloaded = TraceEventV1.model_validate(dumped)
    assert reloaded.run_id == "r1"
    assert reloaded.event_type == TraceEventTypeV1.action_started
    assert reloaded.action_spec is not None
    assert reloaded.action_spec.kind == ActionKindV1.navigate


def test_trace_event_has_required_contract_fields():
    ev = TraceEventV1(
        run_id="r2",
        seq=1,
        event_type=TraceEventTypeV1.run_started,
        step_id=None,
        state_signature_before=None,
        state_signature_after=None,
    )
    dumped = ev.model_dump()
    assert "run_id" in dumped
    assert "seq" in dumped
    assert "ts_utc" in dumped
    assert "event_type" in dumped
    assert "step_id" in dumped
    assert "state_signature_before" in dumped
    assert "state_signature_after" in dumped


def test_evidence_manifest_schema_roundtrip():
    manifest = EvidenceManifestV1(
        run_id="r3",
        policy=EvidencePolicyV1(
            always=[EvidenceKindV1.dom_snapshot_partial],
            on_failure_or_critical=[EvidenceKindV1.html_full, EvidenceKindV1.screenshot],
        ),
        redaction=RedactionPolicyV1(enabled=True, rules=["emails", "dni"]),
        items=[
            EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id="step_000",
                relative_path="evidence/dom/step_000_before.json",
                sha256="a" * 64,
                size_bytes=123,
                mime_type="application/json",
                redacted=True,
            )
        ],
    )
    dumped = manifest.model_dump()
    reloaded = EvidenceManifestV1.model_validate(dumped)
    assert reloaded.run_id == "r3"
    assert reloaded.policy.always[0] == EvidenceKindV1.dom_snapshot_partial


def test_evidence_manifest_requires_non_empty_items():
    with pytest.raises(ValueError):
        EvidenceManifestV1(
            run_id="r4",
            policy=EvidencePolicyV1(
                always=[EvidenceKindV1.dom_snapshot_partial],
                on_failure_or_critical=[EvidenceKindV1.html_full],
            ),
            items=[],
        )


def test_state_signature_hashing_is_deterministic():
    s1 = compute_state_signature_v1(
        url="https://example.com",
        title="Example",
        key_elements={"a": 1, "b": 2},
        visible_text="Hello   world",
        screenshot_hash="abc",
    )
    s2 = compute_state_signature_v1(
        url="https://example.com",
        title="Example",
        key_elements={"b": 2, "a": 1},  # orden distinto, debe hashear igual
        visible_text="Hello world",  # espacios normalizados
        screenshot_hash="abc",
    )
    assert s1.url_hash == s2.url_hash
    assert s1.title_hash == s2.title_hash
    assert s1.key_elements_hash == s2.key_elements_hash
    assert s1.visible_text_hash == s2.visible_text_hash
    assert s1.screenshot_hash == s2.screenshot_hash


def test_action_spec_complete_click_requires_count_equals_1_and_strong_post_if_critical():
    # click critical: exige element_count_equals==1 en pre y postcondición fuerte (U1, U5)
    spec = ActionSpecV1(
        action_id="a_click_crit",
        kind=ActionKindV1.click,
        criticality="critical",
        target=TargetV1(type=TargetKindV1.role, role="button", name="Enviar", exact=True),
        preconditions=[
            ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "role", "role": "button", "name": "Enviar", "exact": True}, "count": 1}),
            ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": {"type": "role", "role": "button", "name": "Enviar", "exact": True}}),
            ConditionV1(kind=ConditionKindV1.no_blocking_overlay, args={}),
        ],
        postconditions=[
            ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "/done"}, severity="critical"),
        ],
        timeout_ms=8000,
    )
    assert spec.kind == ActionKindV1.click


def test_error_raised_event_with_canonical_code():
    sig = compute_state_signature_v1(
        url="https://example.com",
        title="Example",
        key_elements={"a": 1},
        visible_text="x",
        screenshot_hash="abc",
    )
    err = ExecutorErrorV1(
        error_code="TARGET_NOT_FOUND",
        stage=ErrorStageV1.precondition,
        message="target not found",
        retryable=False,
        details={"count_observed": 0},
    )
    ev = TraceEventV1(
        run_id="r5",
        seq=1,
        event_type=TraceEventTypeV1.error_raised,
        step_id="step_000",
        state_signature_before=sig,
        error=err,
    )
    assert ev.error is not None
    assert ev.error.error_code == "TARGET_NOT_FOUND"


def test_run_trace_minimal_sequence_validates():
    # run_started -> observation_captured -> run_finished
    sig = compute_state_signature_v1(
        url="https://example.com",
        title="Example",
        key_elements={"anchors": []},
        visible_text="hello",
        screenshot_hash="abc",
    )
    ev1 = TraceEventV1(run_id="r6", seq=1, event_type=TraceEventTypeV1.run_started, step_id=None)
    ev2 = TraceEventV1(run_id="r6", seq=2, event_type=TraceEventTypeV1.observation_captured, step_id="step_000", state_signature_before=sig)
    ev3 = TraceEventV1(run_id="r6", seq=3, event_type=TraceEventTypeV1.run_finished, step_id=None, state_signature_after=sig)
    assert ev1.event_type == TraceEventTypeV1.run_started
    assert ev2.state_signature_before is not None
    assert ev3.state_signature_after is not None


