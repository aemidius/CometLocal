"""
H7 — UI mínima operativa para Runs (sin LLM)

Este módulo expone un router FastAPI para:
- listar runs (runs/<run_id>/)
- ver detalle de un run (timeline + errores + evidencias)
- servir archivos dentro del run_dir (con protección anti path-traversal)
- ejecutar un run demo offline (file://) usando ExecutorRuntimeH4

Nota: La UI es HTML server-side mínima (sin build). No añade autenticación (local only).
"""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from backend.executor.runtime_h4 import ExecutorRuntimeH4
from backend.shared.executor_contracts_v1 import (
    EvidenceManifestV1,
    ExecutionModeV1,
    TraceEventTypeV1,
    TraceEventV1,
)
from backend.shared.executor_contracts_v1 import (
    ActionCriticalityV1,
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    ErrorSeverityV1,
    TargetKindV1,
    TargetV1,
)


DEFAULT_MAX_TEXT_BYTES = 2 * 1024 * 1024  # 2MB (html_full / json / trace)
DEFAULT_MAX_TRACE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class RunIndexItem:
    run_id: str
    started_at: Optional[str]
    finished_at: Optional[str]
    status: str
    mode: Optional[str]
    last_error: Optional[str]


@dataclass(frozen=True)
class ParsedRun:
    run_id: str
    started_at: Optional[str]
    finished_at: Optional[str]
    duration_ms: Optional[int]
    status: str
    mode: Optional[str]
    last_error: Optional[str]
    errors: List[Dict[str, Any]]
    policy_halts: List[Dict[str, Any]]
    timeline_by_step: Dict[str, List[Dict[str, Any]]]
    evidence_items: List[Dict[str, Any]]
    redaction_report: Optional[Dict[str, int]]
    counters: Dict[str, Any]


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_join(run_dir: Path, rel_path: str) -> Path:
    """
    Asegura que rel_path:
    - no es absoluto
    - no contiene drive letters (Windows) ni ".."
    - resuelve dentro de run_dir
    """
    if not rel_path or rel_path.strip() == "":
        raise HTTPException(status_code=400, detail="Missing path")

    # Bloquear URLs / esquemas y paths absolutos
    if re.match(r"^[a-zA-Z]+://", rel_path):
        raise HTTPException(status_code=400, detail="Invalid path")
    p = Path(rel_path)
    if p.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid path")
    # Bloquear drive letters tipo C:\...
    if re.match(r"^[a-zA-Z]:", rel_path):
        raise HTTPException(status_code=400, detail="Invalid path")
    # Normalizar y resolver
    candidate = (run_dir / p).resolve()
    run_resolved = run_dir.resolve()
    try:
        candidate.relative_to(run_resolved)
    except Exception:
        raise HTTPException(status_code=403, detail="Path traversal blocked")
    return candidate


def _read_text_limited(path: Path, max_bytes: int) -> Tuple[str, bool]:
    data = path.read_bytes()
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace"), False
    truncated = data[:max_bytes]
    return truncated.decode("utf-8", errors="replace"), True


def _iter_trace_events(trace_path: Path, max_bytes: int = DEFAULT_MAX_TRACE_BYTES) -> Iterable[Tuple[Optional[TraceEventV1], Dict[str, Any]]]:
    """
    Itera eventos del trace.
    - Si el trace es grande, lee los últimos max_bytes (puede truncar al empezar en mitad de línea).
    - Devuelve (event_tipado|None, raw_dict).
    """
    if not trace_path.exists():
        return []

    size = trace_path.stat().st_size
    raw_bytes = trace_path.read_bytes() if size <= max_bytes else _tail_bytes(trace_path, max_bytes)
    text = raw_bytes.decode("utf-8", errors="replace")
    # Si es tail, saltar la primera línea parcial
    lines = text.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]

    out: List[Tuple[Optional[TraceEventV1], Dict[str, Any]]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except Exception:
            continue
        try:
            ev = TraceEventV1.model_validate(raw)
            out.append((ev, raw))
        except Exception:
            out.append((None, raw))
    return out


def _tail_bytes(path: Path, max_bytes: int) -> bytes:
    with open(path, "rb") as f:
        try:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            return f.read()
        except Exception:
            return path.read_bytes()


def _load_manifest(run_dir: Path) -> Optional[EvidenceManifestV1]:
    p = run_dir / "evidence_manifest.json"
    if not p.exists():
        return None
    try:
        return EvidenceManifestV1.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_run(run_dir: Path) -> ParsedRun:
    run_id = run_dir.name
    trace_path = run_dir / "trace.jsonl"
    events = list(_iter_trace_events(trace_path))
    manifest = _load_manifest(run_dir)

    started_at = None
    finished_at = None
    status = "unknown"
    mode = None
    last_error = None

    errors: List[Dict[str, Any]] = []
    policy_halts: List[Dict[str, Any]] = []
    timeline_by_step: Dict[str, List[Dict[str, Any]]] = {}

    retry_count = 0
    recovery_count = 0
    same_state_revisits_max: Optional[int] = None

    for ev, raw in events:
        et = (ev.event_type.value if ev else raw.get("event_type")) if raw else None
        step_id = (ev.step_id if ev else raw.get("step_id")) or "none"
        ts = (ev.ts_utc if ev else raw.get("ts_utc")) if raw else None

        if et == TraceEventTypeV1.run_started.value:
            started_at = ts
            mode = (raw.get("metadata") or {}).get("execution_mode") or mode
        if et == TraceEventTypeV1.run_finished.value:
            finished_at = ts
            status = (raw.get("metadata") or {}).get("status") or status
        if et == TraceEventTypeV1.error_raised.value:
            err = raw.get("error") or {}
            errors.append({"ts_utc": ts, "step_id": step_id, "error_code": err.get("error_code"), "stage": err.get("stage"), "message": err.get("message")})
            last_error = err.get("error_code") or last_error
        if et == TraceEventTypeV1.policy_halt.value:
            err = raw.get("error") or {}
            policy_halts.append({"ts_utc": ts, "step_id": step_id, "error_code": err.get("error_code"), "message": err.get("message")})
            last_error = err.get("error_code") or last_error
        if et == TraceEventTypeV1.retry_scheduled.value:
            retry_count += 1
        if et == TraceEventTypeV1.recovery_started.value:
            recovery_count += 1
        if et == TraceEventTypeV1.observation_captured.value:
            pol = ((raw.get("metadata") or {}).get("policy") or {})
            ss = pol.get("same_state_revisit_count")
            if isinstance(ss, int):
                same_state_revisits_max = max(same_state_revisits_max or 0, ss)

        if step_id not in timeline_by_step:
            timeline_by_step[step_id] = []
        if et in {
            TraceEventTypeV1.action_compiled.value,
            TraceEventTypeV1.action_started.value,
            TraceEventTypeV1.preconditions_checked.value,
            TraceEventTypeV1.action_executed.value,
            TraceEventTypeV1.postconditions_checked.value,
            TraceEventTypeV1.assert_checked.value,
            TraceEventTypeV1.error_raised.value,
            TraceEventTypeV1.recovery_started.value,
            TraceEventTypeV1.recovery_finished.value,
            TraceEventTypeV1.policy_halt.value,
            TraceEventTypeV1.evidence_captured.value,
            TraceEventTypeV1.observation_captured.value,
        }:
            timeline_by_step[step_id].append(
                {
                    "ts_utc": ts,
                    "event_type": et,
                    "metadata": raw.get("metadata") or {},
                    "error": raw.get("error"),
                    "evidence_refs": raw.get("evidence_refs") or [],
                    "action_id": (raw.get("action_spec") or {}).get("action_id") if isinstance(raw.get("action_spec"), dict) else None,
                    "action_kind": (raw.get("action_spec") or {}).get("kind") if isinstance(raw.get("action_spec"), dict) else None,
                }
            )

    # Ordenar eventos por ts por step_id (best-effort)
    for sid, items in timeline_by_step.items():
        items.sort(key=lambda x: x.get("ts_utc") or "")

    started_dt = _parse_iso(started_at)
    finished_dt = _parse_iso(finished_at)
    duration_ms = int((finished_dt - started_dt).total_seconds() * 1000) if started_dt and finished_dt else None

    evidence_items: List[Dict[str, Any]] = []
    redaction_report = None
    if manifest:
        for it in manifest.items:
            evidence_items.append(
                {
                    "kind": it.kind.value,
                    "relative_path": it.relative_path,
                    "sha256": it.sha256,
                    "size_bytes": it.size_bytes,
                    "redacted": it.redacted,
                    "mime_type": it.mime_type,
                    "step_id": it.step_id,
                }
            )
        redaction_report = manifest.redaction_report
        if not mode:
            mode = (manifest.metadata or {}).get("execution_mode")

    counters = {
        "retries": retry_count,
        "recoveries": recovery_count,
        "same_state_revisits_max": same_state_revisits_max,
    }

    return ParsedRun(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        mode=mode,
        last_error=last_error,
        errors=errors,
        policy_halts=policy_halts,
        timeline_by_step=timeline_by_step,
        evidence_items=evidence_items,
        redaction_report=redaction_report,
        counters=counters,
    )


def list_runs(runs_root: Path) -> List[RunIndexItem]:
    if not runs_root.exists():
        return []
    items: List[RunIndexItem] = []
    for p in runs_root.iterdir():
        if not p.is_dir():
            continue
        trace = p / "trace.jsonl"
        if not trace.exists():
            continue
        parsed = parse_run(p)
        items.append(
            RunIndexItem(
                run_id=parsed.run_id,
                started_at=parsed.started_at,
                finished_at=parsed.finished_at,
                status=parsed.status,
                mode=parsed.mode,
                last_error=parsed.last_error,
            )
        )
    # Orden desc por started_at (string ISO) y fallback por nombre
    items.sort(key=lambda x: (x.started_at or "", x.run_id), reverse=True)
    return items


def _wants_json(request: Request, format: Optional[str]) -> bool:
    if format and format.lower() == "json":
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept.lower()


def _page(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    th {{ background: #f6f6f6; text-align: left; }}
    code {{ background: #f3f3f3; padding: 2px 4px; border-radius: 4px; }}
    .muted {{ color: #666; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eee; }}
    .pill.ok {{ background: #e7f7ee; }}
    .pill.bad {{ background: #fde8e8; }}
    .row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; flex: 1; min-width: 260px; }}
    .timeline li {{ margin-bottom: 6px; }}
    .btn {{ display: inline-block; padding: 8px 10px; border: 1px solid #999; border-radius: 6px; background: #fff; cursor: pointer; }}
    .btn:hover {{ background: #f8f8f8; }}
  </style>
</head>
<body>
  <div class="row" style="align-items:center; justify-content:space-between;">
    <div>
      <div class="muted">CometLocal</div>
      <h2 style="margin: 6px 0 0 0;">{html.escape(title)}</h2>
    </div>
    <div><a class="btn" href="/runs">Runs</a></div>
  </div>
  <hr/>
  {body_html}
</body>
</html>"""


def create_runs_viewer_router(*, runs_root: Path) -> APIRouter:
    router = APIRouter(tags=["runs"])
    runs_root = Path(runs_root)

    @router.get("/runs", response_class=HTMLResponse)
    def runs_index(request: Request, format: Optional[str] = None):
        rows = list_runs(runs_root)
        if _wants_json(request, format):
            return JSONResponse([r.__dict__ for r in rows])

        trs = []
        for r in rows:
            status_pill = "pill ok" if r.status in ("success", "ok") else ("pill" if r.status == "unknown" else "pill bad")
            trs.append(
                "<tr>"
                f"<td><a href=\"/runs/{html.escape(r.run_id)}\"><code>{html.escape(r.run_id)}</code></a></td>"
                f"<td><span class=\"{status_pill}\">{html.escape(r.status)}</span></td>"
                f"<td>{html.escape(r.mode or '')}</td>"
                f"<td class=\"muted\">{html.escape(r.started_at or '')}</td>"
                f"<td class=\"muted\">{html.escape(r.finished_at or '')}</td>"
                f"<td>{html.escape(r.last_error or '')}</td>"
                "</tr>"
            )

        body = f"""
<div class="row">
  <div class="card">
    <div style="display:flex; gap:10px; align-items:center; justify-content:space-between;">
      <div>
        <div class="muted">Carpeta runs</div>
        <div><code>{html.escape(str(runs_root.resolve()))}</code></div>
      </div>
      <form method="post" action="/runs/demo">
        <button class="btn" type="submit">Run demo offline</button>
      </form>
    </div>
  </div>
</div>
<h3>Runs recientes</h3>
<table>
  <thead>
    <tr>
      <th>run_id</th><th>status</th><th>mode</th><th>started_at</th><th>finished_at</th><th>last_error</th>
    </tr>
  </thead>
  <tbody>
    {''.join(trs) if trs else '<tr><td colspan="6" class="muted">No hay runs todavía.</td></tr>'}
  </tbody>
</table>
"""
        return HTMLResponse(_page("Runs", body))

    @router.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(run_id: str, request: Request, format: Optional[str] = None):
        run_dir = runs_root / run_id
        if not run_dir.exists() or not run_dir.is_dir():
            raise HTTPException(status_code=404, detail="Run not found")

        parsed = parse_run(run_dir)
        if _wants_json(request, format):
            return JSONResponse(parsed.__dict__)

        status_pill = "pill ok" if parsed.status in ("success", "ok") else ("pill" if parsed.status == "unknown" else "pill bad")

        # Timeline
        steps = [k for k in parsed.timeline_by_step.keys() if k != "none"]
        steps.sort()
        timeline_html = []
        for sid in steps:
            events = parsed.timeline_by_step.get(sid, [])
            li = []
            for e in events:
                et = html.escape(str(e.get("event_type") or ""))
                ts = html.escape(str(e.get("ts_utc") or ""))
                ak = e.get("action_kind")
                aid = e.get("action_id")
                label = ""
                if ak or aid:
                    label = f" <span class=\"muted\">[{html.escape(str(aid or ''))} {html.escape(str(ak or ''))}]</span>"
                err = e.get("error") or {}
                err_html = ""
                if isinstance(err, dict) and err.get("error_code"):
                    err_html = f" <span class=\"pill bad\">{html.escape(str(err.get('error_code')))}</span>"
                li.append(f"<li><code>{ts}</code> <b>{et}</b>{label}{err_html}</li>")
            timeline_html.append(f"<div class=\"card\"><div><b>step_id</b>: <code>{html.escape(sid)}</code></div><ul class=\"timeline\">{''.join(li) if li else ''}</ul></div>")

        # Evidence links
        ev_links = []
        manifest_rel = "evidence_manifest.json"
        ev_links.append(f"<li><a href=\"/runs/{html.escape(run_id)}/file/{manifest_rel}\"><code>{html.escape(manifest_rel)}</code></a></li>")
        for it in parsed.evidence_items[:300]:
            rp = it.get("relative_path") or ""
            kind = it.get("kind") or ""
            ev_links.append(
                f"<li><span class=\"muted\">{html.escape(kind)}</span> — "
                f"<a href=\"/runs/{html.escape(run_id)}/file/{html.escape(rp)}\"><code>{html.escape(rp)}</code></a>"
                f"</li>"
            )

        redaction_html = "<div class=\"muted\">(sin redaction_report)</div>"
        if parsed.redaction_report:
            rows = "".join(f"<tr><td><code>{html.escape(str(k))}</code></td><td>{html.escape(str(v))}</td></tr>" for k, v in parsed.redaction_report.items())
            redaction_html = f"<table><thead><tr><th>tipo</th><th>count</th></tr></thead><tbody>{rows}</tbody></table>"

        counters_html = "".join(
            f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in (parsed.counters or {}).items()
        )

        body = f"""
<div class="row">
  <div class="card">
    <div><b>run_id</b>: <code>{html.escape(parsed.run_id)}</code></div>
    <div><b>status</b>: <span class="{status_pill}">{html.escape(parsed.status)}</span></div>
    <div><b>mode</b>: {html.escape(parsed.mode or '')}</div>
    <div><b>started_at</b>: <span class="muted">{html.escape(parsed.started_at or '')}</span></div>
    <div><b>finished_at</b>: <span class="muted">{html.escape(parsed.finished_at or '')}</span></div>
    <div><b>duration_ms</b>: <span class="muted">{html.escape(str(parsed.duration_ms or ''))}</span></div>
    <div><b>run folder</b>: <code>{html.escape(str((runs_root / run_id).resolve()))}</code></div>
  </div>
  <div class="card">
    <div><b>Summary</b></div>
    <ul>{counters_html}</ul>
    <div><b>last_error</b>: <code>{html.escape(parsed.last_error or '')}</code></div>
  </div>
</div>

<h3>Timeline</h3>
<div class="row">
  {''.join(timeline_html) if timeline_html else '<div class="muted">No hay eventos por step_id.</div>'}
</div>

<h3>Evidence</h3>
<ul>
  {''.join(ev_links) if ev_links else '<li class="muted">No hay evidencias.</li>'}
</ul>

<h3>Redaction</h3>
{redaction_html}
"""
        return HTMLResponse(_page(f"Run {run_id}", body))

    @router.get("/runs/{run_id}/file/{path:path}")
    def run_file(run_id: str, path: str, download: Optional[int] = None):
        run_dir = runs_root / run_id
        if not run_dir.exists() or not run_dir.is_dir():
            raise HTTPException(status_code=404, detail="Run not found")

        file_path = _safe_join(run_dir, path)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        ext = file_path.suffix.lower()
        is_text = ext in {".html", ".htm", ".json", ".jsonl", ".txt", ".log", ".sha256"}
        if is_text:
            content, truncated = _read_text_limited(file_path, DEFAULT_MAX_TEXT_BYTES)
            if truncated:
                content = content + "\n\n[TRUNCATED] file too large\n"
            media = "text/plain; charset=utf-8"
            if ext in {".html", ".htm"}:
                media = "text/html; charset=utf-8"
            if ext == ".json":
                media = "application/json; charset=utf-8"
            if ext == ".jsonl":
                media = "application/x-ndjson; charset=utf-8"
            return PlainTextResponse(content, media_type=media)

        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
        return FileResponse(path=str(file_path), headers=headers)

    @router.post("/runs/demo")
    def run_demo():
        """
        Ejecuta un run demo offline (file:// HTML local).
        Devuelve run_id.
        """
        demo_html = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>CometLocal Demo Run</title></head>
<body>
  <h1>Demo</h1>
  <label>Email <input data-testid="email" name="email" type="email" value="alice@example.com"/></label>
  <label>Password <input data-testid="password" name="password" type="password" value="SuperSecret123"/></label>
  <button data-testid="submit">Enviar</button>
  <div id="result" role="status" aria-live="polite"></div>
  <script>
    document.querySelector('[data-testid="submit"]').addEventListener('click', () => {
      document.querySelector('#result').textContent = 'OK token=AAAAAAAAAAAAAAAAAAAAAA';
    });
  </script>
</body>
</html>"""

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
            f.write(demo_html)
            demo_path = f.name

        demo_url = Path(demo_path).resolve().as_uri()

        actions: List[ActionSpecV1] = [
            ActionSpecV1(
                action_id="a1_navigate",
                kind=ActionKindV1.navigate,
                target=TargetV1(type=TargetKindV1.url, url=demo_url),
                preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"})],
                postconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "CometLocal Demo Run"})],
            ),
            ActionSpecV1(
                action_id="a2_fill_email",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.testid, testid="email"),
                input={"text": "alice@example.com"},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "testid", "testid": "email"}})],
                postconditions=[ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "testid", "testid": "email"}, "value": "alice@example.com"})],
            ),
            ActionSpecV1(
                action_id="a3_click_submit",
                kind=ActionKindV1.click,
                target=TargetV1(type=TargetKindV1.testid, testid="submit"),
                preconditions=[
                    ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "testid", "testid": "submit"}, "count": 1}),
                    ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": {"type": "testid", "testid": "submit"}}),
                ],
                postconditions=[ConditionV1(kind=ConditionKindV1.toast_contains, args={"text": "OK"}, severity=ErrorSeverityV1.critical)],
                criticality=ActionCriticalityV1.critical,
            ),
        ]

        # Ejecutar en production para demostrar redaction (local-only)
        runtime = ExecutorRuntimeH4(runs_root=runs_root, execution_mode=ExecutionModeV1.production)
        run_dir = runtime.run_actions(url=demo_url, actions=actions, headless=True)
        return JSONResponse({"run_id": run_dir.name})

    return router


