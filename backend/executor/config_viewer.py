"""
H7.8 — UI mínima de Config (sin DB)

Router FastAPI para editar:
- org.json
- people.json
- platforms.json
- secrets.json (solo refs; valores redacted)

Incluye botón para lanzar un run de "probar login" (navegación) y redirigir a /runs/<run_id>.
"""

from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.executor.runtime_h4 import ExecutorRuntimeH4
from backend.executor.threaded_runtime import run_actions_threaded
from starlette.concurrency import run_in_threadpool
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    ErrorSeverityV1,
    ErrorStageV1,
    EvidenceItemV1,
    EvidenceKindV1,
    EvidenceManifestV1,
    EvidencePolicyV1,
    ExecutorErrorV1,
    ExecutionModeV1,
    RedactionPolicyV1,
    TraceEventTypeV1,
    TraceEventV1,
    TargetKindV1,
    TargetV1,
)
from backend.shared.org_v1 import OrgV1
from backend.shared.people_v1 import PeopleV1, PersonV1
from backend.shared.platforms_v1 import CoordinationV1, LoginFieldsV1, PlatformV1, PlatformsV1


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
    .row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; flex: 1; min-width: 260px; }}
    .btn {{ display: inline-block; padding: 8px 10px; border: 1px solid #999; border-radius: 6px; background: #fff; cursor: pointer; }}
    .btn:hover {{ background: #f8f8f8; }}
    input[type=text], input[type=password] {{ width: 100%; padding: 6px; box-sizing: border-box; }}
    details {{ border: 1px solid #eee; border-radius: 8px; padding: 8px; }}
  </style>
</head>
<body>
  <div class="row" style="align-items:center; justify-content:space-between;">
    <div>
      <div class="muted">CometLocal</div>
      <h2 style="margin: 6px 0 0 0;">{html.escape(title)}</h2>
    </div>
    <div style="display:flex; gap:8px;">
      <a class="btn" href="/runs">Runs</a>
      <a class="btn" href="/config">Config</a>
    </div>
  </div>
  <hr/>
  {body_html}
</body>
</html>"""


def _get_indices(form: Dict[str, str], prefix: str) -> List[int]:
    out = set()
    for k in form.keys():
        if k.startswith(prefix):
            try:
                out.add(int(k.split("__", 1)[1]))
            except Exception:
                continue
    return sorted(out)


def _pick_platform_and_coord(platforms: PlatformsV1, coord_label: str) -> Tuple[Optional[PlatformV1], Optional[CoordinationV1]]:
    """
    Selecciona la plataforma eGestiona (preferente) y la coordinación por label.
    NO valida login_fields; se usa para snapshot sin credenciales.
    """
    if not platforms.platforms:
        return None, None
    plat = next((p for p in platforms.platforms if p.key == "egestiona"), None)
    if plat is None:
        plat = next((p for p in platforms.platforms if "egestiona" in (p.key or "").lower()), None)
    if plat is None:
        plat = platforms.platforms[0]
    coord = next((c for c in (plat.coordinations or []) if (c.label or "") == coord_label), None)
    return plat, coord


def _create_stub_run_dir(*, base_dir: Path, message: str, details: Optional[Dict[str, str]] = None) -> str:
    """
    Crea un run_dir mínimo (trace + manifest) para diagnosticar problemas de config,
    sin ejecutar Playwright. Útil para cumplir "SIEMPRE crea run".
    """
    run_id = f"r_{uuid.uuid4().hex}"
    runs_root = (Path(base_dir) / "runs").resolve()
    run_dir = runs_root / run_id
    evidence_dir = run_dir / "evidence"
    (evidence_dir / "dom").mkdir(parents=True, exist_ok=True)
    (evidence_dir / "shots").mkdir(parents=True, exist_ok=True)
    (evidence_dir / "html").mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()
    trace_path = run_dir / "trace.jsonl"

    def _write_event(ev: TraceEventV1) -> None:
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev.model_dump(mode="json"), ensure_ascii=False) + "\n")

    _write_event(
        TraceEventV1(
            run_id=run_id,
            seq=1,
            event_type=TraceEventTypeV1.run_started,
            step_id=None,
            ts_utc=ts,
            metadata={"execution_mode": ExecutionModeV1.training.value, "note": "stub run (no Playwright)"},
        )
    )

    err = ExecutorErrorV1(
        error_code="INVALID_CONFIG",
        stage=ErrorStageV1.proposal_validation,
        severity=ErrorSeverityV1.error,
        message=message,
        retryable=False,
        details=details or {},
    )
    _write_event(
        TraceEventV1(
            run_id=run_id,
            seq=2,
            event_type=TraceEventTypeV1.error_raised,
            step_id=None,
            ts_utc=ts,
            error=err,
            metadata={"status": "failed"},
        )
    )
    _write_event(
        TraceEventV1(
            run_id=run_id,
            seq=3,
            event_type=TraceEventTypeV1.run_finished,
            step_id=None,
            ts_utc=ts,
            metadata={"status": "failed"},
        )
    )

    manifest = EvidenceManifestV1(
        run_id=run_id,
        policy=EvidencePolicyV1(always=[EvidenceKindV1.dom_snapshot_partial], on_failure_or_critical=[EvidenceKindV1.html_full, EvidenceKindV1.screenshot]),
        redaction=RedactionPolicyV1(enabled=True, rules=["emails", "phone", "dni", "tokens"], mode=ExecutionModeV1.training),
        items=[
            EvidenceItemV1(kind=EvidenceKindV1.dom_snapshot_partial, step_id="none", relative_path="evidence/dom/none.json", sha256="0" * 64, size_bytes=0)
        ],
        redaction_report=None,
        metadata={"execution_mode": ExecutionModeV1.training.value, "note": "stub run (no Playwright)"},
    )
    (run_dir / "evidence_manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return run_id


def create_config_viewer_router(*, base_dir: Path) -> APIRouter:
    router = APIRouter(tags=["config"])
    base_dir = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base_dir)
    secrets = SecretsStoreV1(base_dir=base_dir)

    @router.get("/config", response_class=HTMLResponse)
    def config_home():
        refs_dir = (Path(base_dir) / "refs").resolve()
        body = f"""
<div class="row">
  <div class="card">
    <div class="muted">base_dir</div>
    <div><code>{html.escape(str(Path(base_dir).resolve()))}</code></div>
    <div class="muted" style="margin-top:8px;">refs_dir</div>
    <div><code>{html.escape(str(refs_dir))}</code></div>
  </div>
</div>
<h3>Secciones</h3>
<ul>
  <li><a href="/config/org">Org</a></li>
  <li><a href="/config/people">People</a></li>
  <li><a href="/config/platforms">Platforms</a></li>
  <li><a href="/config/secrets">Secrets</a></li>
</ul>
"""
        return HTMLResponse(_page("Config", body))

    @router.get("/config/_debug_dump_paths")
    def debug_dump_paths():
        refs_dir = (Path(base_dir) / "refs").resolve()
        return {
            "base_dir": str(Path(base_dir).resolve()),
            "refs_dir": str(refs_dir),
            "org": str((refs_dir / "org.json").resolve()),
            "people": str((refs_dir / "people.json").resolve()),
            "platforms": str((refs_dir / "platforms.json").resolve()),
            "secrets": str((refs_dir / "secrets.json").resolve()),
        }

    @router.get("/config/org", response_class=HTMLResponse)
    def get_org():
        org = store.load_org()
        body = f"""
<form method="post">
  <div class="card">
    <div><b>legal_name</b></div>
    <input type="text" name="legal_name" value="{html.escape(org.legal_name)}"/>
    <div style="margin-top:8px;"><b>tax_id</b></div>
    <input type="text" name="tax_id" value="{html.escape(org.tax_id)}"/>
    <div style="margin-top:8px;"><b>org_type</b></div>
    <input type="text" name="org_type" value="{html.escape(org.org_type)}"/>
    <div style="margin-top:8px;"><b>notes</b></div>
    <input type="text" name="notes" value="{html.escape(org.notes)}"/>
    <div style="margin-top:12px;">
      <button class="btn" type="submit">Guardar</button>
    </div>
  </div>
</form>
"""
        return HTMLResponse(_page("Config — Org", body))

    @router.post("/config/org")
    async def post_org(request: Request):
        form = dict(await request.form())
        org = OrgV1(legal_name=str(form.get("legal_name") or ""), tax_id=str(form.get("tax_id") or ""), org_type=str(form.get("org_type") or "SCCL"), notes=str(form.get("notes") or ""))
        store.save_org(org)
        return RedirectResponse(url="/config/org", status_code=303)

    @router.get("/config/people", response_class=HTMLResponse)
    def get_people():
        people = store.load_people()
        rows = []
        for i, p in enumerate(people.people):
            rows.append(
                "<tr>"
                f"<td><input type='text' name='worker_id__{i}' value='{html.escape(p.worker_id)}'/></td>"
                f"<td><input type='text' name='full_name__{i}' value='{html.escape(p.full_name)}'/></td>"
                f"<td><input type='text' name='tax_id__{i}' value='{html.escape(p.tax_id)}'/></td>"
                f"<td><input type='text' name='role__{i}' value='{html.escape(p.role)}'/></td>"
                f"<td><input type='text' name='relation_type__{i}' value='{html.escape(p.relation_type)}'/></td>"
                "</tr>"
            )
        # una fila extra vacía para añadir
        j = len(people.people)
        rows.append(
            "<tr>"
            f"<td><input type='text' name='worker_id__{j}' value=''/></td>"
            f"<td><input type='text' name='full_name__{j}' value=''/></td>"
            f"<td><input type='text' name='tax_id__{j}' value=''/></td>"
            f"<td><input type='text' name='role__{j}' value=''/></td>"
            f"<td><input type='text' name='relation_type__{j}' value=''/></td>"
            "</tr>"
        )

        body = f"""
<form method="post">
  <div class="card">
    <table>
      <thead><tr><th>worker_id</th><th>full_name</th><th>tax_id</th><th>role</th><th>relation_type</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <div style="margin-top:12px;">
      <button class="btn" type="submit">Guardar</button>
    </div>
    <div class="muted" style="margin-top:8px;">Deja worker_id vacío para no guardar esa fila.</div>
  </div>
</form>
"""
        return HTMLResponse(_page("Config — People", body))

    @router.post("/config/people")
    async def post_people(request: Request):
        form = {k: str(v) for k, v in (await request.form()).items()}
        idxs = _get_indices(form, "worker_id__")
        out: List[PersonV1] = []
        for i in idxs:
            worker_id = (form.get(f"worker_id__{i}") or "").strip()
            if not worker_id:
                continue
            out.append(
                PersonV1(
                    worker_id=worker_id,
                    full_name=(form.get(f"full_name__{i}") or "").strip(),
                    tax_id=(form.get(f"tax_id__{i}") or "").strip(),
                    role=(form.get(f"role__{i}") or "").strip(),
                    relation_type=(form.get(f"relation_type__{i}") or "").strip(),
                )
            )
        store.save_people(PeopleV1(people=out))
        return RedirectResponse(url="/config/people", status_code=303)

    @router.get("/config/platforms", response_class=HTMLResponse)
    def get_platforms():
        platforms = store.load_platforms()
        sections: List[str] = []
        for pi, p in enumerate(platforms.platforms):
            coord_rows = []
            for ci, c in enumerate(p.coordinations):
                coord_rows.append(
                    "<tr>"
                    f"<td><input type='text' name='coord_label__{pi}__{ci}' value='{html.escape(c.label)}'/></td>"
                    f"<td><input type='text' name='coord_client_code__{pi}__{ci}' value='{html.escape(c.client_code)}'/></td>"
                    f"<td><input type='text' name='coord_username__{pi}__{ci}' value='{html.escape(c.username)}'/></td>"
                    f"<td><input type='text' name='coord_password_ref__{pi}__{ci}' value='{html.escape(c.password_ref)}'/></td>"
                    f"<td><input type='text' name='coord_url_override__{pi}__{ci}' value='{html.escape(c.url_override or '')}'/></td>"
                    f"<td><input type='text' name='coord_post_login_selector__{pi}__{ci}' value='{html.escape(c.post_login_selector or '')}'/></td>"
                    "</tr>"
                )
            # fila extra
            cj = len(p.coordinations)
            coord_rows.append(
                "<tr>"
                f"<td><input type='text' name='coord_label__{pi}__{cj}' value=''/></td>"
                f"<td><input type='text' name='coord_client_code__{pi}__{cj}' value=''/></td>"
                f"<td><input type='text' name='coord_username__{pi}__{cj}' value=''/></td>"
                f"<td><input type='text' name='coord_password_ref__{pi}__{cj}' value=''/></td>"
                f"<td><input type='text' name='coord_url_override__{pi}__{cj}' value=''/></td>"
                f"<td><input type='text' name='coord_post_login_selector__{pi}__{cj}' value=''/></td>"
                "</tr>"
            )

            sections.append(
                f"""
<details open>
  <summary><b>{html.escape(p.key)}</b> <span class="muted">{html.escape(p.base_url)}</span></summary>
  <div class="row" style="margin-top:10px;">
    <div class="card">
      <div><b>key</b></div><input type="text" name="platform_key__{pi}" value="{html.escape(p.key)}"/>
      <div style="margin-top:8px;"><b>base_url</b></div><input type="text" name="platform_base_url__{pi}" value="{html.escape(p.base_url)}"/>
      <div style="margin-top:8px;"><b>login.requires_client</b></div><input type="text" name="platform_requires_client__{pi}" value="{html.escape(str(bool(p.login_fields.requires_client)))}"/>
      <div style="margin-top:8px;"><b>login.client_code_selector</b></div><input type="text" name="platform_client_code_selector__{pi}" value="{html.escape(p.login_fields.client_code_selector or '')}"/>
      <div style="margin-top:8px;"><b>login.username_selector</b></div><input type="text" name="platform_username_selector__{pi}" value="{html.escape(p.login_fields.username_selector or '')}"/>
      <div style="margin-top:8px;"><b>login.password_selector</b></div><input type="text" name="platform_password_selector__{pi}" value="{html.escape(p.login_fields.password_selector or '')}"/>
      <div style="margin-top:8px;"><b>login.submit_selector</b></div><input type="text" name="platform_submit_selector__{pi}" value="{html.escape(p.login_fields.submit_selector or '')}"/>
    </div>
  </div>
  <div class="card" style="margin-top:10px;">
    <div><b>coordinations</b></div>
    <table>
      <thead><tr><th>label</th><th>client_code</th><th>username</th><th>password_ref</th><th>url_override</th><th>post_login_selector</th></tr></thead>
      <tbody>{''.join(coord_rows)}</tbody>
    </table>
    <div class="muted" style="margin-top:6px;">Deja label vacío para no guardar esa coordinación.</div>
  </div>
</details>
"""
            )

        # plataforma extra en blanco
        pi = len(platforms.platforms)
        sections.append(
            f"""
<details>
  <summary><b>(Añadir plataforma)</b></summary>
  <div class="row" style="margin-top:10px;">
    <div class="card">
      <div><b>key</b></div><input type="text" name="platform_key__{pi}" value=""/>
      <div style="margin-top:8px;"><b>base_url</b></div><input type="text" name="platform_base_url__{pi}" value=""/>
      <div style="margin-top:8px;"><b>login.requires_client</b></div><input type="text" name="platform_requires_client__{pi}" value="true"/>
      <div style="margin-top:8px;"><b>login.client_code_selector</b></div><input type="text" name="platform_client_code_selector__{pi}" value=""/>
      <div style="margin-top:8px;"><b>login.username_selector</b></div><input type="text" name="platform_username_selector__{pi}" value=""/>
      <div style="margin-top:8px;"><b>login.password_selector</b></div><input type="text" name="platform_password_selector__{pi}" value=""/>
      <div style="margin-top:8px;"><b>login.submit_selector</b></div><input type="text" name="platform_submit_selector__{pi}" value=""/>
    </div>
  </div>
  <div class="card" style="margin-top:10px;">
    <div><b>coordinations</b></div>
    <table>
      <thead><tr><th>label</th><th>client_code</th><th>username</th><th>password_ref</th><th>url_override</th><th>post_login_selector</th></tr></thead>
      <tbody>
        <tr>
          <td><input type='text' name='coord_label__{pi}__0' value=''/></td>
          <td><input type='text' name='coord_client_code__{pi}__0' value=''/></td>
          <td><input type='text' name='coord_username__{pi}__0' value=''/></td>
          <td><input type='text' name='coord_password_ref__{pi}__0' value=''/></td>
          <td><input type='text' name='coord_url_override__{pi}__0' value=''/></td>
          <td><input type='text' name='coord_post_login_selector__{pi}__0' value=''/></td>
        </tr>
      </tbody>
    </table>
  </div>
</details>
"""
        )

        body = f"""
<form method="post">
  <div class="card">
    <div style="display:flex; gap:8px; align-items:center; justify-content:space-between;">
      <div class="muted">Editar plataformas/coordinaciones</div>
      <div style="display:flex; gap:8px;">
        <button class="btn" type="submit">Guardar</button>
      </div>
    </div>
  </div>
  <div style="margin-top:12px;">{''.join(sections)}</div>
</form>

<form method="post" action="/config/platforms/test_login" style="margin-top:14px;">
  <div class="card">
    <div><b>Probar login eGestiona (Kern)</b></div>
    <div class="muted">Lanza un run de login REAL usando platform.key=<code>egestiona</code> y coordinación <code>Kern</code>. Requiere <code>post_login_selector</code>.</div>
    <div style="margin-top:10px; display:flex; gap:12px; align-items:center;">
      <label><input type="checkbox" name="headless" checked/> headless</label>
      <button class="btn" type="submit">Probar login</button>
    </div>
  </div>
</form>

<form method="post" action="/config/platforms/egestiona/snapshot_login" style="margin-top:10px;">
  <div class="card">
    <div><b>Snapshot login eGestiona (sin credenciales)</b></div>
    <div class="muted">Crea un run SIEMPRE y captura <code>html_full</code>, <code>screenshot</code> y <code>dom_snapshot_partial</code> para extraer selectors reales del formulario.</div>
    <input type="hidden" name="coord" value="Kern"/>
    <div style="margin-top:10px; display:flex; gap:12px; align-items:center;">
      <label><input type="checkbox" name="headless" checked/> headless</label>
      <button class="btn" type="submit">Snapshot login</button>
    </div>
  </div>
</form>
"""
        return HTMLResponse(_page("Config — Platforms", body))

    @router.post("/config/platforms")
    async def post_platforms(request: Request):
        form = {k: str(v) for k, v in (await request.form()).items()}
        # platforms by index
        p_idxs = _get_indices(form, "platform_key__")
        platforms_out: List[PlatformV1] = []
        for pi in p_idxs:
            key = (form.get(f"platform_key__{pi}") or "").strip()
            base_url = (form.get(f"platform_base_url__{pi}") or "").strip()
            if not key or not base_url:
                continue
            requires_client_raw = (form.get(f"platform_requires_client__{pi}") or "true").strip().lower()
            requires_client = requires_client_raw in ("1", "true", "yes", "y", "on")
            login = LoginFieldsV1(
                requires_client=requires_client,
                client_code_selector=(form.get(f"platform_client_code_selector__{pi}") or "").strip() or None,
                username_selector=(form.get(f"platform_username_selector__{pi}") or "").strip() or None,
                password_selector=(form.get(f"platform_password_selector__{pi}") or "").strip() or None,
                submit_selector=(form.get(f"platform_submit_selector__{pi}") or "").strip() or None,
            )

            # coordinations scan
            coords: List[CoordinationV1] = []
            for k in list(form.keys()):
                if not k.startswith(f"coord_label__{pi}__"):
                    continue
                try:
                    ci = int(k.split("__")[2])
                except Exception:
                    continue
                label = (form.get(f"coord_label__{pi}__{ci}") or "").strip()
                if not label:
                    continue
                coords.append(
                    CoordinationV1(
                        label=label,
                        client_code=(form.get(f"coord_client_code__{pi}__{ci}") or "").strip(),
                        username=(form.get(f"coord_username__{pi}__{ci}") or "").strip(),
                        password_ref=(form.get(f"coord_password_ref__{pi}__{ci}") or "").strip(),
                        url_override=(form.get(f"coord_url_override__{pi}__{ci}") or "").strip() or None,
                        post_login_selector=(form.get(f"coord_post_login_selector__{pi}__{ci}") or "").strip() or None,
                    )
                )
            coords.sort(key=lambda x: x.label)
            platforms_out.append(PlatformV1(key=key, base_url=base_url, login_fields=login, coordinations=coords))

        platforms_out.sort(key=lambda x: x.key)
        store.save_platforms(PlatformsV1(platforms=platforms_out))
        return RedirectResponse(url="/config/platforms", status_code=303)

    @router.post("/config/platforms/test_login")
    async def test_login(request: Request):
        form = dict(await request.form())
        headless = form.get("headless") == "on"
        platforms = store.load_platforms()
        if not platforms.platforms:
            raise HTTPException(status_code=400, detail="No platforms configured")

        # eGestiona (Kern): usar flow oficial determinista (login real)
        try:
            from backend.adapters.egestiona.flows import run_login_and_snapshot
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"egestiona adapter not available: {e}")

        # Requisito: post_login_selector debe estar definido en la coordinación.
        try:
            run_id = await run_in_threadpool(
                lambda: run_login_and_snapshot(
                    base_dir=Path(base_dir),
                    platform="egestiona",
                    coordination="Kern",
                    headless=headless,
                    execution_mode="training",
                )
            )
        except ValueError as e:
            msg = str(e)
            if "post_login_selector" in msg:
                raise HTTPException(status_code=400, detail="Define post_login_selector")
            raise HTTPException(status_code=400, detail=msg)

        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

    @router.post("/config/platforms/egestiona/snapshot_login")
    async def snapshot_login(request: Request):
        """
        H8.A1: Snapshot del login para extraer selectors (sin credenciales).
        - No requiere login_fields selectors.
        - Siempre crea run_dir (si falta URL/config, crea stub run con error).
        """
        form = dict(await request.form())
        coord_label = str(form.get("coord") or "Kern").strip() or "Kern"
        headless = form.get("headless") == "on"

        platforms = store.load_platforms()
        plat, coord = _pick_platform_and_coord(platforms, coord_label)

        url = None
        if plat is not None:
            url = (coord.url_override if coord and coord.url_override else None) or (plat.base_url or None)

        def _run() -> str:
            if not url:
                return _create_stub_run_dir(
                    base_dir=Path(base_dir),
                    message="No base_url/url_override configured for eGestiona snapshot_login",
                    details={"coord": coord_label, "platform_key": (plat.key if plat else ""), "hint": "Configura platforms.json (base_url) o coord.url_override"},
                )

            rt = ExecutorRuntimeH4(
                runs_root=Path(base_dir) / "runs",
                project_root=Path(base_dir).parent,
                data_root=Path(base_dir).name,
                execution_mode=ExecutionModeV1.training,
                secrets_store=SecretsStoreV1(base_dir=base_dir),
            )
            actions = [
                ActionSpecV1(
                    action_id="eg_snapshot_login_navigate",
                    kind=ActionKindV1.navigate,
                    target=TargetV1(type=TargetKindV1.url, url=str(url)),
                    input={},
                    preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
                    postconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
                    timeout_ms=30000,
                    tags=["egestiona", "snapshot_login"],
                )
            ]
            run_dir = rt.run_actions(url="about:blank", actions=actions, headless=headless)
            return run_dir.name

        run_id = await run_in_threadpool(_run)
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

    @router.get("/config/secrets", response_class=HTMLResponse)
    def get_secrets():
        refs = secrets.list_refs()
        rows = []
        keys = sorted(refs.keys())
        for k in keys:
            rows.append(
                "<tr>"
                f"<td><code>{html.escape(k)}</code></td>"
                f"<td><code>***</code></td>"
                f"<td><input type='password' name='value__{html.escape(k)}' value='' placeholder='nuevo valor'/></td>"
                "</tr>"
            )
        # fila para nuevo ref
        rows.append(
            "<tr>"
            "<td><input type='text' name='new_ref' value='' placeholder='password_ref'/></td>"
            "<td class='muted'>(nuevo)</td>"
            "<td><input type='password' name='new_value' value='' placeholder='valor'/></td>"
            "</tr>"
        )
        body = f"""
<form method="post">
  <div class="card">
    <table>
      <thead><tr><th>password_ref</th><th>stored</th><th>set (no se muestra en claro)</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <div style="margin-top:12px;">
      <button class="btn" type="submit">Guardar</button>
    </div>
  </div>
</form>
"""
        return HTMLResponse(_page("Config — Secrets", body))

    @router.post("/config/secrets")
    async def post_secrets(request: Request):
        form = {k: str(v) for k, v in (await request.form()).items()}
        # actualizaciones existentes
        for k, v in form.items():
            if not k.startswith("value__"):
                continue
            ref = k.split("__", 1)[1]
            if v.strip():
                secrets.set_secret(ref, v.strip())
        # nuevo
        new_ref = (form.get("new_ref") or "").strip()
        new_value = (form.get("new_value") or "").strip()
        if new_ref and new_value:
            secrets.set_secret(new_ref, new_value)
        return RedirectResponse(url="/config/secrets", status_code=303)

    return router


