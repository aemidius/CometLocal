"""
H1 — ExecutorRuntime Skeleton (sin Playwright)

Genera artefactos reales en disco para un run:
- runs/<run_id>/
  - trace.jsonl (run_started, observation_captured, run_finished)
  - evidence_manifest.json
  - evidence/dom/step_000_before.json (dom_snapshot_partial stub)
  - evidence/shots/step_000_before.sha256 (hash de screenshot)

No ejecuta Playwright. La observación es un stub controlado pero válido a nivel de schema.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.shared.executor_contracts_v1 import (
    DomSnapshotV1,
    EvidenceItemV1,
    EvidenceKindV1,
    EvidenceManifestV1,
    EvidencePolicyV1,
    RedactionPolicyV1,
    TraceEventTypeV1,
    TraceEventV1,
    compute_state_signature_v1,
)

from backend.executor.browser_controller import BrowserController, ExecutionProfileV1, ExecutorTypedException


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 128), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ExecutionProfileBasicV1:
    """
    Perfil mínimo para H1 (no depende de agent_runner).
    """

    name: str = "balanced"
    hard_cap_steps: int = 60
    retries_per_action: int = 2
    recovery_max: int = 3
    same_state_revisits: int = 2
    backoff_ms: List[int] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.backoff_ms is None:
            object.__setattr__(self, "backoff_ms", [300, 1000, 2000])


@dataclass
class PolicyStateBasicV1:
    """
    Estado de policy mínimo para H1.
    """

    steps_taken: int = 0
    same_state_revisit_count: int = 1


class ExecutorRuntimeSkeletonH1:
    def __init__(
        self,
        runs_root: str | Path = "runs",
        execution_mode: str = "dry_run",
        domain_allowlist: Optional[List[str]] = None,
        profile: Optional[ExecutionProfileBasicV1] = None,
    ):
        self.runs_root = Path(runs_root)
        self.execution_mode = execution_mode
        self.domain_allowlist = domain_allowlist or []
        self.profile = profile or ExecutionProfileBasicV1()

    def run_stub(self, *, goal: str = "stub_goal") -> Path:
        """
        Crea un run stub y devuelve el path del directorio del run.
        """
        run_id = f"r_{uuid.uuid4().hex}"
        run_dir = self.runs_root / run_id
        evidence_dir = run_dir / "evidence"
        dom_dir = evidence_dir / "dom"
        shots_dir = evidence_dir / "shots"

        dom_dir.mkdir(parents=True, exist_ok=True)
        shots_dir.mkdir(parents=True, exist_ok=True)

        policy_state = PolicyStateBasicV1()

        # Stub observation
        url = "https://stub.local/"
        title = "Stub Page"
        visible_text = "stub observation"
        key_elements: Dict[str, Any] = {"anchors": [], "inputs": []}

        # screenshot hash determinista (sin imagen)
        screenshot_hash = "sha256:" + _sha256_bytes(b"")

        state_sig = compute_state_signature_v1(
            url=url,
            title=title,
            key_elements=key_elements,
            visible_text=visible_text,
            screenshot_hash=screenshot_hash,
        )

        # Evidence: dom_snapshot_partial (before)
        dom_snapshot = DomSnapshotV1(
            url=url,
            title=title,
            targets=[],
            visible_anchors=[],
            visible_inputs=[],
            truncated=False,
            metadata={"stub": True},
        )

        dom_before_rel = Path("evidence/dom/step_000_before.json")
        dom_before_path = run_dir / dom_before_rel
        dom_before_path.write_text(
            json.dumps(dom_snapshot.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Evidence: screenshot hash file
        shot_hash_rel = Path("evidence/shots/step_000_before.sha256")
        shot_hash_path = run_dir / shot_hash_rel
        shot_hash_path.write_text(state_sig.screenshot_hash + "\n", encoding="utf-8")

        # evidence manifest (mínimo)
        items = [
            EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id="step_000",
                relative_path=dom_before_rel.as_posix(),
                sha256=_sha256_file(dom_before_path),
                size_bytes=dom_before_path.stat().st_size,
                mime_type="application/json",
                redacted=False,
            ),
            EvidenceItemV1(
                kind=EvidenceKindV1.screenshot_hash,
                step_id="step_000",
                relative_path=shot_hash_rel.as_posix(),
                sha256=_sha256_file(shot_hash_path),
                size_bytes=shot_hash_path.stat().st_size,
                mime_type="text/plain",
                redacted=False,
            ),
        ]

        manifest = EvidenceManifestV1(
            run_id=run_id,
            policy=EvidencePolicyV1(
                always=[EvidenceKindV1.dom_snapshot_partial],
                on_failure_or_critical=[EvidenceKindV1.html_full, EvidenceKindV1.screenshot],
            ),
            redaction=RedactionPolicyV1(enabled=False, rules=[]),
            items=items,
            metadata={"goal": goal, "stub": True},
        )

        manifest_path = run_dir / "evidence_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # trace.jsonl (mínimo)
        trace_path = run_dir / "trace.jsonl"
        events = [
            TraceEventV1(
                run_id=run_id,
                seq=1,
                event_type=TraceEventTypeV1.run_started,
                step_id=None,
                state_signature_before=None,
                state_signature_after=None,
                metadata={
                    "goal": goal,
                    "execution_mode": self.execution_mode,
                    "domain_allowlist": self.domain_allowlist,
                    "execution_profile": asdict(self.profile),
                },
            ),
            TraceEventV1(
                run_id=run_id,
                seq=2,
                event_type=TraceEventTypeV1.observation_captured,
                step_id="step_000",
                state_signature_before=state_sig,
                state_signature_after=None,
                metadata={
                    "policy": {
                        "steps_taken": policy_state.steps_taken,
                        "hard_cap_steps": self.profile.hard_cap_steps,
                        "same_state_revisit_count": policy_state.same_state_revisit_count,
                        "same_state_revisit_threshold": self.profile.same_state_revisits,
                    }
                },
            ),
            TraceEventV1(
                run_id=run_id,
                seq=3,
                event_type=TraceEventTypeV1.run_finished,
                step_id=None,
                state_signature_before=None,
                state_signature_after=state_sig,
                metadata={"status": "success", "manifest": "evidence_manifest.json"},
            ),
        ]

        with open(trace_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev.model_dump(), ensure_ascii=False) + "\n")
            f.flush()

        return run_dir

    def run(
        self,
        *,
        url: Optional[str] = None,
        goal: str = "stub_goal",
        use_playwright: bool = False,
        headless: bool = True,
    ) -> Path:
        """
        Modo opcional Playwright:
        - Si use_playwright=True y url!=None: abre browser, navega, captura observation real y cierra.
        - Si no: usa stub (H1).
        """
        if not use_playwright or not url:
            return self.run_stub(goal=goal)

        run_id = f"r_{uuid.uuid4().hex}"
        run_dir = self.runs_root / run_id
        evidence_dir = run_dir / "evidence"
        (evidence_dir / "dom").mkdir(parents=True, exist_ok=True)
        (evidence_dir / "shots").mkdir(parents=True, exist_ok=True)

        policy_state = PolicyStateBasicV1()

        # Playwright controller (encapsulado)
        ctrl = BrowserController(profile=ExecutionProfileV1())
        try:
            ctrl.start(headless=headless)
            nav = ctrl.navigate(url, timeout_ms=self.profile.backoff_ms[-1] * 10 if self.profile.backoff_ms else None)
            dom_snapshot, state_sig, evidence_items = ctrl.capture_observation(step_id="step_000", evidence_dir=evidence_dir)
        except ExecutorTypedException as te:
            # En skeleton: re-lanzamos tipado (runtime real lo convertirá en error_raised + run_finished)
            raise
        finally:
            try:
                ctrl.close()
            except Exception:
                pass

        # evidence manifest
        manifest = EvidenceManifestV1(
            run_id=run_id,
            policy=EvidencePolicyV1(
                always=[EvidenceKindV1.dom_snapshot_partial],
                on_failure_or_critical=[EvidenceKindV1.html_full, EvidenceKindV1.screenshot],
            ),
            redaction=RedactionPolicyV1(enabled=False, rules=[]),
            items=evidence_items,
            metadata={"goal": goal, "stub": False, "final_url": nav.get("final_url")},
        )
        (run_dir / "evidence_manifest.json").write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # trace mínimo
        trace_path = run_dir / "trace.jsonl"
        events = [
            TraceEventV1(
                run_id=run_id,
                seq=1,
                event_type=TraceEventTypeV1.run_started,
                step_id=None,
                state_signature_before=None,
                state_signature_after=None,
                metadata={
                    "goal": goal,
                    "execution_mode": self.execution_mode,
                    "domain_allowlist": self.domain_allowlist,
                    "execution_profile": asdict(self.profile),
                    "playwright": True,
                },
            ),
            TraceEventV1(
                run_id=run_id,
                seq=2,
                event_type=TraceEventTypeV1.observation_captured,
                step_id="step_000",
                state_signature_before=state_sig,
                state_signature_after=None,
                metadata={
                    "policy": {
                        "steps_taken": policy_state.steps_taken,
                        "hard_cap_steps": self.profile.hard_cap_steps,
                        "same_state_revisit_count": policy_state.same_state_revisit_count,
                        "same_state_revisit_threshold": self.profile.same_state_revisits,
                    }
                },
            ),
            TraceEventV1(
                run_id=run_id,
                seq=3,
                event_type=TraceEventTypeV1.run_finished,
                step_id=None,
                state_signature_before=None,
                state_signature_after=state_sig,
                metadata={"status": "success", "manifest": "evidence_manifest.json"},
            ),
        ]

        with open(trace_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev.model_dump(), ensure_ascii=False) + "\n")
            f.flush()

        return run_dir


