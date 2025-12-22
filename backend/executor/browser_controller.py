"""
H2 — BrowserController (Playwright encapsulado) + observation real

Diseño:
- No usa LLM.
- No escribe trace.jsonl: devuelve datos para que el runtime emita eventos.
- Target resolution determinista siguiendo TargetV1 (mapping v1).
- Observation real: DomSnapshotV1 + StateSignatureV1 + EvidenceItemV1[] (dom_snapshot_partial + screenshot_hash).
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.shared.executor_contracts_v1 import (
    DomSnapshotV1,
    EvidenceItemV1,
    EvidenceKindV1,
    ExecutorErrorV1,
    ErrorStageV1,
    ErrorSeverityV1,
    StateSignatureV1,
    TargetKindV1,
    TargetV1,
    VisibleAnchorV1,
    VisibleButtonV1,
    VisibleInputV1,
    compute_state_signature_v1,
)

from backend.executor.redaction_v1 import RedactorV1

def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _ensure_windows_proactor_policy_for_playwright() -> None:
    """
    FIX Windows: Playwright sync puede llamar a create_subprocess_exec desde threads/endpoints.
    En algunos entornos Windows, el loop policy por defecto puede provocar NotImplementedError.

    Decisión solicitada: forzar WindowsProactorEventLoopPolicy (idempotente).
    """
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            # Si no está disponible por versión/entorno, no rompemos.
            pass


@dataclass(frozen=True)
class ExecutionProfileV1:
    """
    Perfil mínimo para BrowserController H2 (centraliza timeouts).
    """

    navigation_timeout_ms: int = 15000
    action_timeout_ms: int = 5000
    observation_text_max_len: int = 3000
    max_visible_items: int = 60


class ExecutorTypedException(Exception):
    """
    Excepción con error tipado canónico (v1).
    """

    def __init__(self, error: ExecutorErrorV1):
        super().__init__(error.message)
        self.error = error


class BrowserController:
    def __init__(self, profile: Optional[ExecutionProfileV1] = None):
        self.profile = profile or ExecutionProfileV1()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    @property
    def page(self):
        return self._page

    def start(
        self,
        *,
        headless: bool = True,
        viewport: Optional[Dict[str, int]] = None,
        user_data_dir: Optional[str] = None,
    ) -> None:
        """
        Arranca Playwright (sync) y crea context + page.
        """
        _ensure_windows_proactor_policy_for_playwright()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError("Playwright sync_api not available") from e

        if self._playwright is not None:
            return

        self._playwright = sync_playwright().start()

        if user_data_dir:
            # persistent context
            ctx = self._playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                viewport=viewport or {"width": 1280, "height": 720},
            )
            self._context = ctx
            self._browser = None
            pages = ctx.pages
            self._page = pages[0] if pages else ctx.new_page()
        else:
            self._browser = self._playwright.chromium.launch(headless=headless)
            self._context = self._browser.new_context(viewport=viewport or {"width": 1280, "height": 720})
            self._page = self._context.new_page()

    def close(self) -> None:
        """
        Cierra page/context/browser/playwright.
        """
        try:
            if self._context is not None:
                self._context.close()
        finally:
            self._context = None
            self._page = None

        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            self._browser = None

        try:
            if self._playwright is not None:
                self._playwright.stop()
        finally:
            self._playwright = None

    def navigate(self, url: str, timeout_ms: Optional[int] = None) -> Dict[str, Any]:
        """
        Navega y devuelve info básica (final_url + status si disponible).
        """
        if not self._page:
            raise RuntimeError("BrowserController not started")

        to_ms = timeout_ms or self.profile.navigation_timeout_ms

        try:
            resp = self._page.goto(url, wait_until="networkidle", timeout=to_ms)
            status = None
            try:
                status = resp.status if resp is not None else None
            except Exception:
                status = None
            return {"final_url": self._page.url, "status": status}
        except Exception as e:
            # map to NAVIGATION_TIMEOUT conservador si es timeout
            msg = str(e).lower()
            code = "NAVIGATION_TIMEOUT" if "timeout" in msg else "EXEC_NAVIGATION_FAILED"
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code=code,
                    stage=ErrorStageV1.execution,
                    severity=ErrorSeverityV1.error,
                    message=f"navigation failed: {url}",
                    retryable=False,
                    cause=repr(e),
                    details={"url": url, "timeout_ms": to_ms},
                )
            )

    def locate(self, target: TargetV1):
        """
        Resuelve TargetV1 a Locator (Playwright). No valida count (eso lo hace el executor via precondiciones).

        Nota: TargetV1.type=url no se soporta aquí (v1). Usar navigate().
        """
        if not self._page:
            raise RuntimeError("BrowserController not started")

        if target.type == TargetKindV1.url:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="INVALID_ACTIONSPEC",
                    stage=ErrorStageV1.proposal_validation,
                    severity=ErrorSeverityV1.error,
                    message="locate() does not accept url targets; use navigate()",
                    retryable=False,
                    details={"target_type": "url"},
                )
            )

        page = self._page

        # Base targets
        if target.type == TargetKindV1.testid:
            return page.get_by_test_id(target.testid)
        if target.type == TargetKindV1.role:
            exact = bool(target.exact) if target.exact is not None else True
            return page.get_by_role(target.role, name=target.name, exact=exact)
        if target.type == TargetKindV1.label:
            exact = bool(target.exact) if target.exact is not None else True
            return page.get_by_label(target.text, exact=exact)
        if target.type == TargetKindV1.text:
            exact = bool(target.exact) if target.exact is not None else True
            return page.get_by_text(target.text, exact=exact)
        if target.type == TargetKindV1.css:
            return page.locator(target.selector)
        if target.type == TargetKindV1.xpath:
            # Playwright sync: locator("xpath=...")
            return page.locator(f"xpath={target.selector}")

        # Composition
        if target.type == TargetKindV1.frame:
            fl = page.frame_locator(target.selector)
            inner = target.inner_target
            # inner_target se resuelve en el contexto del frame locator usando locator(...)
            # Implementación conservadora: map inner_target a selector string cuando sea css/xpath; para otros usamos get_by_* sobre frame locator via locator(":scope") no existe.
            # Default conservador v1: soportar inner_target css/xpath/text/role/label/testid usando fl.locator y fl.get_by_*
            if inner is None:
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="INVALID_ACTIONSPEC",
                        stage=ErrorStageV1.proposal_validation,
                        severity=ErrorSeverityV1.error,
                        message="frame target missing inner_target",
                        retryable=False,
                    )
                )
            if inner.type == TargetKindV1.testid:
                return fl.get_by_test_id(inner.testid)
            if inner.type == TargetKindV1.role:
                exact = bool(inner.exact) if inner.exact is not None else True
                return fl.get_by_role(inner.role, name=inner.name, exact=exact)
            if inner.type == TargetKindV1.label:
                exact = bool(inner.exact) if inner.exact is not None else True
                return fl.get_by_label(inner.text, exact=exact)
            if inner.type == TargetKindV1.text:
                exact = bool(inner.exact) if inner.exact is not None else True
                return fl.get_by_text(inner.text, exact=exact)
            if inner.type == TargetKindV1.css:
                return fl.locator(inner.selector)
            if inner.type == TargetKindV1.xpath:
                return fl.locator(f"xpath={inner.selector}")
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="INVALID_ACTIONSPEC",
                    stage=ErrorStageV1.proposal_validation,
                    severity=ErrorSeverityV1.error,
                    message="unsupported inner_target type for frame in v1",
                    retryable=False,
                    details={"inner_type": inner.type.value},
                )
            )

        if target.type == TargetKindV1.nth:
            base = target.base_target
            if base is None:
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="INVALID_ACTIONSPEC",
                        stage=ErrorStageV1.proposal_validation,
                        severity=ErrorSeverityV1.error,
                        message="nth target missing base_target",
                        retryable=False,
                    )
                )
            loc = self.locate(base)
            return loc.nth(int(target.index))

        raise ExecutorTypedException(
            ExecutorErrorV1(
                error_code="INVALID_ACTIONSPEC",
                stage=ErrorStageV1.proposal_validation,
                severity=ErrorSeverityV1.error,
                message="unsupported target type",
                retryable=False,
                details={"target_type": target.type.value},
            )
        )

    def locate_unique(self, target: TargetV1, *, timeout_ms: Optional[int] = None):
        """
        Resuelve locator y aplica U1/U2 en ejecución: count==1.
        """
        if not self._page:
            raise RuntimeError("BrowserController not started")

        loc = self.locate(target)
        to_ms = timeout_ms or self.profile.action_timeout_ms

        try:
            # Espera corta para que el elemento exista/sea observable en DOM
            loc.first.wait_for(timeout=to_ms, state="attached")
        except Exception:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="TARGET_NOT_FOUND",
                    stage=ErrorStageV1.precondition,
                    severity=ErrorSeverityV1.error,
                    message="target not found",
                    retryable=False,
                    details={"target": target.model_dump(), "timeout_ms": to_ms},
                )
            )

        try:
            count = loc.count()
        except Exception:
            count = None

        if count == 0:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="TARGET_NOT_FOUND",
                    stage=ErrorStageV1.precondition,
                    severity=ErrorSeverityV1.error,
                    message="target not found",
                    retryable=False,
                    details={"target": target.model_dump(), "count_observed": 0},
                )
            )
        if count != 1:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="TARGET_NOT_UNIQUE",
                    stage=ErrorStageV1.precondition,
                    severity=ErrorSeverityV1.error,
                    message=f"target not unique (count={count})",
                    retryable=False,
                    details={"target": target.model_dump(), "count_observed": count},
                )
            )

        return loc.first

    def capture_observation(
        self,
        *,
        step_id: str,
        evidence_dir: Path,
        phase: str = "before",
        redactor: Optional[RedactorV1] = None,
    ) -> Tuple[DomSnapshotV1, StateSignatureV1, List[EvidenceItemV1]]:
        """
        Captura:
        - DomSnapshotV1 real (parcial)
        - StateSignatureV1 real (incluye screenshot_hash)
        - EvidenceItemV1[] (dom_snapshot_partial + screenshot_hash)

        No guarda screenshot por defecto; solo crea `.sha256`.
        """
        if not self._page:
            raise RuntimeError("BrowserController not started")

        evidence_dir.mkdir(parents=True, exist_ok=True)
        dom_dir = evidence_dir / "dom"
        shots_dir = evidence_dir / "shots"
        dom_dir.mkdir(parents=True, exist_ok=True)
        shots_dir.mkdir(parents=True, exist_ok=True)

        page = self._page

        url = page.url or ""
        try:
            title = page.title()
        except Exception:
            title = ""

        # Extract visible elements determinísticamente (sin heurísticas creativas)
        extracted: Dict[str, Any] = page.evaluate(
            """(maxItems) => {
              const isVisible = (el) => {
                try {
                  const style = window.getComputedStyle(el);
                  if (!style) return false;
                  if (style.visibility === 'hidden' || style.display === 'none') return false;
                  const r = el.getClientRects();
                  return r && r.length > 0;
                } catch (e) { return false; }
              };
              const norm = (s) => (s || '').toString().replace(/\\s+/g,' ').trim();
              const pickAttrs = (el) => {
                const keys = ['id','name','type','role','aria-label','placeholder','value','href'];
                const out = {};
                for (const k of keys) {
                  const v = el.getAttribute && el.getAttribute(k);
                  if (v) out[k] = norm(v);
                }
                return out;
              };
              const anchors = [];
              const inputs = [];
              const buttons = [];

              for (const a of Array.from(document.querySelectorAll('a'))) {
                if (!isVisible(a)) continue;
                anchors.push({
                  text: norm(a.innerText || a.textContent || ''),
                  href: norm(a.getAttribute('href') || ''),
                  attrs: pickAttrs(a),
                  selector: a.id ? ('#' + a.id) : null,
                });
                if (anchors.length >= maxItems) break;
              }

              for (const i of Array.from(document.querySelectorAll('input, textarea, select'))) {
                if (!isVisible(i)) continue;
                const tag = (i.tagName || '').toLowerCase();
                const id = i.getAttribute('id');
                const name = i.getAttribute('name');
                const type = i.getAttribute('type') || (tag === 'textarea' ? 'textarea' : tag);
                // value se considera sensible: no exportamos valor real
                inputs.push({
                  selector: id ? ('#' + id) : (name ? (tag + '[name=\"' + name + '\"]') : tag),
                  input_type: norm(type),
                  name: name ? norm(name) : null,
                  label: null,
                  value_redacted: null,
                  attrs: pickAttrs(i),
                });
                if (inputs.length >= maxItems) break;
              }

              for (const b of Array.from(document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"], input[type=\"button\"]'))) {
                if (!isVisible(b)) continue;
                buttons.push({
                  text: norm(b.innerText || b.value || b.textContent || ''),
                  attrs: pickAttrs(b),
                  selector: b.id ? ('#' + b.id) : null,
                });
                if (buttons.length >= maxItems) break;
              }

              return { anchors, inputs, buttons, visible_text: norm(document.body ? (document.body.innerText || '') : '') };
            }""",
            self.profile.max_visible_items,
        )

        anchors = [
            VisibleAnchorV1(
                text=a.get("text", "") or "",
                href=a.get("href", "") or "",
                selector=a.get("selector"),
                attrs={k: str(v) for k, v in (a.get("attrs") or {}).items()},
            )
            for a in (extracted.get("anchors") or [])
        ]
        inputs = [
            VisibleInputV1(
                selector=str(i.get("selector") or ""),
                input_type=str(i.get("input_type") or "text"),
                name=i.get("name"),
                label=i.get("label"),
                value_redacted=i.get("value_redacted"),
                attrs={k: str(v) for k, v in (i.get("attrs") or {}).items()},
            )
            for i in (extracted.get("inputs") or [])
            if i.get("selector")
        ]
        buttons = [
            VisibleButtonV1(
                text=b.get("text", "") or "",
                selector=b.get("selector"),
                attrs={k: str(v) for k, v in (b.get("attrs") or {}).items()},
            )
            for b in (extracted.get("buttons") or [])
        ]

        # Redaction (in-memory) antes de persistir
        if redactor and redactor.enabled:
            for a in anchors:
                a.text = redactor.redact_text(a.text)
                a.href = redactor.redact_text(a.href)
                a.attrs = {k: redactor.redact_text(v) for k, v in (a.attrs or {}).items()}
            for i in inputs:
                i.selector = redactor.redact_text(i.selector)
                if i.name:
                    i.name = redactor.redact_text(i.name)
                if i.label:
                    i.label = redactor.redact_text(i.label)
                i.attrs = {k: redactor.redact_text(v) for k, v in (i.attrs or {}).items()}
                # value siempre redacted
                if "value" in (i.attrs or {}):
                    i.attrs["value"] = "***"
            for b in buttons:
                b.text = redactor.redact_text(b.text)
                b.attrs = {k: redactor.redact_text(v) for k, v in (b.attrs or {}).items()}

        dom_snapshot = DomSnapshotV1(
            url=url,
            title=title,
            targets=[],
            visible_anchors=anchors,
            visible_inputs=inputs,
            visible_buttons=buttons,
            truncated=False,
            metadata={"source": "playwright"},
        )

        dom_rel = Path(f"evidence/dom/{step_id}_{phase}.json")
        dom_path = dom_dir / f"{step_id}_{phase}.json"
        dom_path.write_text(json.dumps(dom_snapshot.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

        # screenshot bytes -> hash (no guardamos imagen por defecto)
        try:
            shot_bytes = page.screenshot(full_page=True)
        except Exception as e:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="EVIDENCE_SCREENSHOT_FAILED",
                    stage=ErrorStageV1.evidence,
                    severity=ErrorSeverityV1.error,
                    message="failed to capture screenshot bytes",
                    retryable=False,
                    cause=repr(e),
                )
            )

        import hashlib

        shot_hash_hex = hashlib.sha256(shot_bytes).hexdigest()
        screenshot_hash = f"sha256:{shot_hash_hex}"

        # guardar solo .sha256
        shot_hash_rel = Path(f"evidence/shots/{step_id}_{phase}.sha256")
        shot_hash_path = shots_dir / f"{step_id}_{phase}.sha256"
        shot_hash_path.write_text(screenshot_hash + "\n", encoding="utf-8")

        visible_text = (extracted.get("visible_text") or "")[: self.profile.observation_text_max_len]
        key_elements: Dict[str, Any] = {
            "anchors": [{"t": a.text, "h": a.href} for a in anchors[:50]],
            "inputs": [{"s": i.selector, "t": i.input_type, "n": i.name} for i in inputs[:50]],
            "buttons": [{"t": b.text} for b in buttons[:50]],
        }

        state_sig = compute_state_signature_v1(
            url=url,
            title=title,
            key_elements=key_elements,
            visible_text=visible_text,
            screenshot_hash=screenshot_hash,
            visible_text_max_len=self.profile.observation_text_max_len,
        )

        items = [
            EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id=step_id,
                relative_path=dom_rel.as_posix(),
                sha256=_sha256_bytes(dom_path.read_bytes()),
                size_bytes=dom_path.stat().st_size,
                mime_type="application/json",
                redacted=False,
            ),
            EvidenceItemV1(
                kind=EvidenceKindV1.screenshot_hash,
                step_id=step_id,
                relative_path=shot_hash_rel.as_posix(),
                sha256=_sha256_bytes(shot_hash_path.read_bytes()),
                size_bytes=shot_hash_path.stat().st_size,
                mime_type="text/plain",
                redacted=False,
            ),
        ]

        return dom_snapshot, state_sig, items

    def capture_html_full(self, *, step_id: str, evidence_dir: Path, phase: str = "after", redactor: Optional[RedactorV1] = None) -> EvidenceItemV1:
        """
        Captura HTML completo (page.content) y lo persiste. Usar solo en fallo/acción crítica (policy).
        """
        if not self._page:
            raise RuntimeError("BrowserController not started")
        html_dir = evidence_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        rel = Path(f"evidence/html/{step_id}_{phase}.html")
        path = html_dir / f"{step_id}_{phase}.html"
        try:
            html = self._page.content()
        except Exception as e:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="EVIDENCE_HTML_CAPTURE_FAILED",
                    stage=ErrorStageV1.evidence,
                    severity=ErrorSeverityV1.error,
                    message="failed to capture html_full",
                    retryable=False,
                    cause=repr(e),
                )
            )
        if redactor and redactor.enabled:
            html = redactor.redact_html(html)
        path.write_text(html, encoding="utf-8")
        return EvidenceItemV1(
            kind=EvidenceKindV1.html_full,
            step_id=step_id,
            relative_path=rel.as_posix(),
            sha256=_sha256_bytes(path.read_bytes()),
            size_bytes=path.stat().st_size,
            mime_type="text/html",
            redacted=False,
        )

    def capture_screenshot_file(self, *, step_id: str, evidence_dir: Path, phase: str = "after") -> EvidenceItemV1:
        """
        Captura screenshot PNG a disco (solo fallo/acción crítica).
        """
        if not self._page:
            raise RuntimeError("BrowserController not started")
        shots_dir = evidence_dir / "shots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        rel = Path(f"evidence/shots/{step_id}_{phase}.png")
        path = shots_dir / f"{step_id}_{phase}.png"
        try:
            self._page.screenshot(path=str(path), full_page=True)
        except Exception as e:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="EVIDENCE_SCREENSHOT_FAILED",
                    stage=ErrorStageV1.evidence,
                    severity=ErrorSeverityV1.error,
                    message="failed to capture screenshot file",
                    retryable=False,
                    cause=repr(e),
                )
            )
        return EvidenceItemV1(
            kind=EvidenceKindV1.screenshot,
            step_id=step_id,
            relative_path=rel.as_posix(),
            sha256=_sha256_bytes(path.read_bytes()),
            size_bytes=path.stat().st_size,
            mime_type="image/png",
            redacted=False,
        )


