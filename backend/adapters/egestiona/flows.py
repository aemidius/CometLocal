from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from backend.adapters.egestiona.profile import EgestionaProfileV1
from backend.adapters.egestiona.targets import build_targets_from_selectors

# Selector post-login robusto: verificar que salimos de login (no usar texto específico)
POST_LOGIN_SELECTOR_DEFAULT = None  # No usar selector de texto, verificar navegación
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
from backend.repository.document_repository_v1 import DocumentRepositoryV1
from backend.shared.file_ref_v1 import build_shared_ref


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
    if plat is None:
        # backward-compat: aceptar "egestiona_*"
        plat = next((p for p in platforms.platforms if str(p.key or "").lower().startswith(str(platform).lower())), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if coord is None:
        coord = next((c for c in plat.coordinations if str(c.label or "").lower() == str(coordination).lower()), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    def _looks_like_selector(v: str) -> bool:
        vv = (v or "").strip()
        if not vv:
            return False
        # Playwright text selector
        if vv.startswith("text=") or vv.startswith("text=\"") or vv.startswith("text='"):
            return True
        # CSS-ish / xpath-ish cues
        return any(tok in vv for tok in ("[", "]", "#", ".", "=", ":", "//"))

    # Post-login check: usar verificación robusta de que salimos de la página de login
    if not coord.post_login_selector:
        # No usar selector específico, verificar navegación en las postcondiciones
        coord.post_login_selector = None

    # URL: override > platform.base_url > default
    url = coord.url_override or plat.base_url or EgestionaProfileV1().default_base_url

    # FIX H8.A2+: si faltan selectors, autocompletar defaults estables y (opcional) persistir.
    autofilled = False
    lf = plat.login_fields
    if lf.client_code_selector is None:
        lf.client_code_selector = SelectorSpecV1(kind="css", value='input[name="ClientName"]')
        autofilled = True
    if lf.username_selector is None:
        lf.username_selector = SelectorSpecV1(kind="css", value='input[name="Username"]')
        autofilled = True
    if lf.password_selector is None:
        lf.password_selector = SelectorSpecV1(kind="css", value='input[name="Password"]')
        autofilled = True
    if lf.submit_selector is None:
        lf.submit_selector = SelectorSpecV1(kind="css", value='button[type="submit"]')
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

    # Resolver credenciales (NO 500; error claro si falta secret requerido)
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    password_val = secrets.get_secret(password_ref)
    if password_val is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="eg_fill_client",
                kind=ActionKindV1.fill,
                target=targets.client_code,
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": targets.client_code.model_dump(), "value": client_val},
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
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.username.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": targets.username.model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
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
            input={"secret_ref": password_ref},
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

    # Último paso (determinista): esperar que el login termine y naveguemos fuera de la página de login.
    # IMPORTANTE: este es el paso final; si se cumple, el runtime termina success y no evalúa policies después.
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_post_login_check",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                # Verificar que salimos de la página de login (postcondición crítica)
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
                # Verificar que el formulario de login desapareció
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical, description="Login form must be gone"),
                # Verificar que el botón submit desapareció
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.critical, description="Submit button must be gone"),
            ],
            timeout_ms=30000,  # Más tiempo para esperar la navegación post-login
            criticality="critical",
        )
    )

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


def run_upload_document_cae(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    file_path: str | Path,
    headless: bool = True,
    execution_mode: str = "production",
    fail_fast: bool = False,
) -> str:
    """
    Ejecuta flujo completo: login + navegación a CAE + upload de documento + validación.
    Devuelve run_id.
    
    Args:
        file_path: Ruta local al archivo a subir (se registrará en el repositorio si no existe)
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)
    
    # Registrar documento si no existe
    repo = DocumentRepositoryV1(project_root=Path(base).parent, data_root="data")
    file_path_obj = Path(file_path).resolve()
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Construir file_ref esperado
    company_id = "demo"
    namespace = "samples"
    name = file_path_obj.stem
    file_ref = f"doc:company:{company_id}:company_docs:{namespace}:{name}"
    
    # Intentar registrar documento (si ya existe, validar que el archivo es el mismo)
    try:
        # Verificar si ya existe
        try:
            entry = repo.validate(file_ref)
            # Si existe y es válido, usar ese file_ref
        except (FileNotFoundError, ValueError):
            # No existe o no es válido, registrar nuevo
            file_ref = repo.register(
                path=file_path_obj,
                metadata={
                    "company_id": company_id,
                    "doc_type": "test_document",
                    "namespace": namespace,
                    "name": name,
                    "tags": ["egestiona_upload_test"],
                },
            )
    except Exception as e:
        raise ValueError(f"Failed to register/validate document: {e}")

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if plat is None:
        plat = next((p for p in platforms.platforms if str(p.key or "").lower().startswith(str(platform).lower())), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if coord is None:
        coord = next((c for c in plat.coordinations if str(c.label or "").lower() == str(coordination).lower()), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    def _looks_like_selector(v: str) -> bool:
        vv = (v or "").strip()
        if not vv:
            return False
        if vv.startswith("text=") or vv.startswith("text=\"") or vv.startswith("text='"):
            return True
        return any(tok in vv for tok in ("[", "]", "#", ".", "=", ":", "//"))

    if (not coord.post_login_selector) or (coord.post_login_selector and not _looks_like_selector(coord.post_login_selector.value)):
        coord.post_login_selector = SelectorSpecV1(kind="css", value=POST_LOGIN_SELECTOR_DEFAULT)
        store.save_platforms(platforms)

    url = coord.url_override or plat.base_url or EgestionaProfileV1().default_base_url

    autofilled = False
    lf = plat.login_fields
    if lf.client_code_selector is None:
        lf.client_code_selector = SelectorSpecV1(kind="css", value='input[name="ClientName"]')
        autofilled = True
    if lf.username_selector is None:
        lf.username_selector = SelectorSpecV1(kind="css", value='input[name="Username"]')
        autofilled = True
    if lf.password_selector is None:
        lf.password_selector = SelectorSpecV1(kind="css", value='input[name="Password"]')
        autofilled = True
    if lf.submit_selector is None:
        lf.submit_selector = SelectorSpecV1(kind="css", value='button[type="submit"]')
        autofilled = True

    if autofilled:
        store.save_platforms(platforms)

    targets = build_targets_from_selectors(
        client_code_selector=plat.login_fields.client_code_selector,
        username_selector=plat.login_fields.username_selector,
        password_selector=plat.login_fields.password_selector,
        submit_selector=plat.login_fields.submit_selector,
        post_login_selector=coord.post_login_selector,
    )

    # Resolver credenciales
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Navegación inicial
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

    # 2. Login
    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="eg_fill_client",
                kind=ActionKindV1.fill,
                target=targets.client_code,
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": targets.client_code.model_dump(), "value": client_val},
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
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.username.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": targets.username.model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="eg_fill_pass",
            kind=ActionKindV1.fill,
            target=targets.password,
            input={"secret_ref": password_ref},
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

    # 3. Esperar post-login
    # Nota: Agregamos url_matches como postcondición fuerte para cumplir U5
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_post_login_check",
            kind=ActionKindV1.wait_for,
            target=targets.post_login,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.post_login.model_dump()}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical, description="Login form must be gone"),
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",
        )
    )

    # 4. Navegación a CAE - usar selectores robustos basados en texto/roles
    # Estrategia: buscar enlaces o botones que contengan "CAE", "Documentación", "Subir", etc.
    # Usaremos selectores de texto como fallback robusto
    cae_link_target = TargetV1(
        type=TargetKindV1.text,
        text="CAE",
        exact=True,
        normalize_ws=True,
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_nav_cae",
            kind=ActionKindV1.click,
            target=cae_link_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": cae_link_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": cae_link_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 5. Esperar a que cargue la página de CAE/upload
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_cae_page",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # 6. Localizar input file - estrategia múltiple: input[type="file"], botones con texto "Subir"/"Seleccionar", etc.
    # Prioridad: input[type="file"] visible > botón con aria-label/role > texto "Subir"/"Seleccionar"
    file_input_target = TargetV1(
        type=TargetKindV1.css,
        selector='input[type="file"]',
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_upload_file",
            kind=ActionKindV1.upload,
            target=file_input_target,
            input={"file_ref": file_ref},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": file_input_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": file_input_target.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.upload_completed, args={}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=30000,
            criticality="critical",
        )
    )

    # 7. Buscar y hacer click en botón "Subir"/"Enviar"/"Guardar" si existe
    # Estrategia: buscar botones con texto que contenga "Subir", "Enviar", "Guardar", "Cargar"
    submit_upload_target = TargetV1(
        type=TargetKindV1.text,
        text="Subir",
        exact=True,
        normalize_ws=True,
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_click_submit_upload",
            kind=ActionKindV1.click,
            target=submit_upload_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": submit_upload_target.model_dump()}, severity=ErrorSeverityV1.warning),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": submit_upload_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 8. Esperar confirmación - buscar mensajes de éxito, toasts, o cambios en la UI
    # Estrategia: buscar texto que indique éxito: "Cargado", "Correcto", "Éxito", "Documento subido", etc.
    # Nota: Hacemos esta acción menos crítica (normal) porque la confirmación puede variar en la UI real
    confirmation_target = TargetV1(
        type=TargetKindV1.text,
        text="Cargado",
        exact=True,
        normalize_ws=True,
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_confirmation",
            kind=ActionKindV1.wait_for,
            target=confirmation_target,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": confirmation_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=20000,
            criticality="normal",
        )
    )

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


@router.post("/runs/egestiona/upload_document")
async def egestiona_upload_document(coord: str = "Kern", file_path: str = "data/samples/dummy.pdf"):
    """
    Ejecuta flujo completo: login + navegación a CAE + upload de documento + validación.
    
    Args:
        coord: Coordinación (default: "Kern")
        file_path: Ruta al archivo a subir (default: "data/samples/dummy.pdf")
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_upload_document_cae(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                file_path=file_path,
                headless=True,
                execution_mode="production",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


