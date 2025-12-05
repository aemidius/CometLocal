from typing import List, Optional, Tuple
import re
from urllib.parse import quote_plus

from openai import AsyncOpenAI

from backend.browser.browser import BrowserController
from backend.shared.models import BrowserAction, BrowserObservation, StepResult, SourceInfo
from backend.planner.simple_planner import SimplePlanner
from backend.planner.llm_planner import LLMPlanner
from backend.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, DEFAULT_IMAGE_SEARCH_URL_TEMPLATE


def _goal_mentions_wikipedia(goal: str) -> bool:
    text = goal.lower()
    return "wikipedia" in text


def _goal_requires_wikipedia(goal: str) -> bool:
    """Returns True if the goal requires Wikipedia context (obligatory)."""
    text = goal.lower()
    return "wikipedia" in text


def _goal_mentions_images(goal: str) -> bool:
    text = goal.lower()
    keywords = ["imagen", "imágenes", "foto", "fotos", "picture", "pictures", "image", "images"]
    return any(keyword in text for keyword in keywords)


def _is_url_in_wikipedia(url: str | None) -> bool:
    if not url:
        return False
    return "wikipedia.org" in url.lower()


def _is_url_in_image_search(url: str | None) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return (
        "ia=images" in url_lower
        or "iax=images" in url_lower
        or ("duckduckgo.com" in url_lower and "/images" in url_lower)
    )


def _extract_wikipedia_entity_from_goal(goal: str) -> Optional[str]:
    """
    Extrae la entidad de Wikipedia del objetivo si sigue un patrón conocido.
    
    Soporta patrones como:
    - "investiga quién fue X"
    - "mira información sobre X"
    - "busca información sobre X"
    - "consulta información sobre X"
    
    Devuelve la entidad extraída (sin "en Wikipedia" si estaba presente) o None.
    """
    goal_lower = goal.lower()
    
    # Patrones para extraer la entidad
    # Usamos grupos de captura para encontrar la posición exacta en el texto original
    patterns = [
        (r"investiga\s+qui[eé]n\s+fue\s+(.+?)(?:\s+en\s+wikipedia)?$", "investiga quién fue "),
        (r"investiga\s+quien\s+fue\s+(.+?)(?:\s+en\s+wikipedia)?$", "investiga quien fue "),
        (r"(?:mira|busca|consulta)\s+informaci[oó]n\s+sobre\s+(.+?)(?:\s+en\s+wikipedia)?$", "información sobre "),
    ]
    
    for pattern, prefix in patterns:
        match = re.search(pattern, goal_lower, re.IGNORECASE)
        if match:
            entity_lower = match.group(1).strip()
            # Eliminar "en wikipedia" si quedó al final
            entity_lower = re.sub(r"\s+en\s+wikipedia\s*$", "", entity_lower, flags=re.IGNORECASE)
            # Limpiar espacios y puntuación final
            entity_lower = entity_lower.strip(" ,;.")
            if entity_lower:
                # Buscar la posición del prefijo en el texto original
                prefix_lower = prefix.lower()
                prefix_pos = goal_lower.find(prefix_lower)
                if prefix_pos != -1:
                    # Calcular la posición donde empieza la entidad
                    entity_start = prefix_pos + len(prefix_lower)
                    # Buscar dónde termina la entidad (hasta "en wikipedia" o fin de línea)
                    entity_end_marker = " en wikipedia"
                    if entity_end_marker in goal_lower[entity_start:]:
                        entity_end = goal_lower.find(entity_end_marker, entity_start)
                    else:
                        entity_end = len(goal)
                    # Extraer la entidad del texto original
                    original_entity = goal[entity_start:entity_end].strip(" ,;.")
                    if original_entity:
                        return original_entity
                # Fallback: devolver en minúsculas si no encontramos la posición
                return entity_lower
    
    return None


def _build_wikipedia_article_url(entity: str) -> str:
    """
    Construye la URL de artículo en la Wikipedia en español para una entidad dada.
    """
    slug = entity.strip().replace(" ", "_")
    # Usa quote_plus para codificar caracteres especiales, pero respeta los guiones bajos
    # Primero reemplazamos espacios por guiones bajos, luego codificamos el resto
    encoded_slug = quote_plus(slug, safe="_")
    return f"https://es.wikipedia.org/wiki/{encoded_slug}"


def _is_url_entity_article(url: Optional[str], entity: str) -> bool:
    """
    Comprueba si la URL actual ya es el artículo de esa entidad en Wikipedia.
    """
    if not url:
        return False
    slug = entity.strip().replace(" ", "_")
    # Normalizar la URL para comparación
    url_lower = url.lower()
    slug_lower = slug.lower()
    # Buscar el patrón /wiki/entidad en la URL
    return f"/wiki/{slug_lower}" in url_lower or f"/wiki/{quote_plus(slug_lower, safe='_')}" in url_lower


async def ensure_context(
    goal: str,
    observation: Optional[BrowserObservation],
    browser: BrowserController,
    focus_entity: Optional[str] = None,
) -> Optional[BrowserAction]:
    """
    Context reorientation layer: ensures the browser is in a reasonable site
    for the current goal before delegating to the LLM planner.
    Returns a BrowserAction if reorientation is needed, None otherwise.
    
    v1.2: Images have priority over Wikipedia to avoid context contamination.
    v1.3: Uses normalized queries with focus_entity fallback.
    v1.4: Always navigates to new context, never reuses old pages even if in same domain.
    """
    # v1.4: Si observation es None, tratamos como contexto desconocido
    current_url = observation.url if observation else None
    
    # PRIORIDAD 1 (v1.2): Image search - tiene prioridad sobre Wikipedia
    # v1.4: Siempre navegar a nueva búsqueda de imágenes, incluso si ya estamos en DuckDuckGo
    if _goal_mentions_images(goal):
        # v1.4: Usar query normalizada con focus_entity
        image_query = _normalize_image_query(goal, fallback_focus=focus_entity)
        image_search_url = DEFAULT_IMAGE_SEARCH_URL_TEMPLATE.format(query=quote_plus(image_query))
        return BrowserAction(type="open_url", args={"url": image_search_url})
    
    # PRIORIDAD 2: Wikipedia con entidad específica
    # Solo aplica si NO menciona imágenes (ya manejado en PRIORIDAD 1)
    # v1.4: Siempre navegar a nueva búsqueda/artículo, incluso si ya estamos en Wikipedia
    if _goal_mentions_wikipedia(goal):
        # v1.4: Usar _get_effective_focus_entity para obtener entidad
        entity = _get_effective_focus_entity(goal, focus_entity)
        
        if entity:
            # v1.4: Siempre construir URL de búsqueda, no reutilizar página anterior
            # Incluso si ya estamos en el artículo de esa entidad, forzamos navegación limpia
            wiki_query = _normalize_wikipedia_query(goal, focus_entity=entity)
            if wiki_query:
                search_param = quote_plus(wiki_query)
                wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
                return BrowserAction(type="open_url", args={"url": wikipedia_search_url})
    
    # PRIORIDAD 3: OBLIGATORY CONTEXT: Wikipedia (sin entidad específica o fallback)
    # v1.4: Solo forzamos búsqueda si tenemos una entidad clara
    if _goal_requires_wikipedia(goal):
        # v1.4: Usar _normalize_wikipedia_query que solo devuelve entidades o None
        wiki_query = _normalize_wikipedia_query(goal, focus_entity=focus_entity)
        
        # Si no hay entidad, NO forzamos búsqueda (dejamos que el agente navegue normalmente)
        if wiki_query is None:
            return None
        
        # v1.4: Siempre construir URL de búsqueda, no reutilizar página anterior
        search_param = quote_plus(wiki_query)
        wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
        return BrowserAction(type="open_url", args={"url": wikipedia_search_url})
    
    # No reorientation needed
    return None


async def _execute_action(action: BrowserAction, browser: BrowserController) -> Optional[str]:
    """
    Executes a BrowserAction on the BrowserController.
    Returns None if successful, or an error message string if it failed.
    """
    try:
        if action.type == "open_url":
            url = action.args.get("url", "")
            if url:
                await browser.goto(url)
        elif action.type == "click_text":
            text = action.args.get("text", "")
            if text:
                await browser.click_by_text(text)
        elif action.type == "fill_input":
            # Use Playwright directly to fill by selector
            selector = action.args.get("selector", "")
            text = action.args.get("text", "")
            if selector and text and browser.page:
                try:
                    locator = browser.page.locator(selector).first
                    await locator.click(timeout=2000)
                    await locator.fill(text)
                except Exception as e:
                    return f"Failed to fill input with selector '{selector}': {str(e)}"
            elif text:
                # Fallback to type_text if no selector
                await browser.type_text(text)
        elif action.type == "press_key":
            key = action.args.get("key", "Enter")
            if key == "Enter":
                await browser.press_enter()
            elif browser.page:
                await browser.page.keyboard.press(key)
        elif action.type == "accept_cookies":
            await browser.accept_cookies()
        elif action.type == "wait":
            # No artificial sleeps, but we can wait for network idle
            if browser.page:
                try:
                    await browser.page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass  # Ignore timeout
        elif action.type == "noop":
            # No operation, just continue
            pass
        else:
            return f"Unknown action type: {action.type}"
        return None
    except Exception as exc:
        return str(exc)


async def run_simple_agent(
    goal: str,
    browser: BrowserController,
    max_steps: int = 5,
) -> List[StepResult]:
    """
    Runs a very simple, synchronous-looking agent loop on top of the
    BrowserController using the SimplePlanner.
    """
    planner = SimplePlanner()
    steps: List[StepResult] = []
    action_history: List[BrowserAction] = []

    for step_index in range(max_steps):
        try:
            # Get observation
            observation = await browser.get_observation()

            # Ask planner for next action (pass action history)
            action = planner.next_action(
                goal=goal,
                observation=observation,
                step_index=step_index,
                action_history=action_history
            )

            # If stop action, add final step and break
            if action.type == "stop":
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=None
                ))
                break

            # Execute the action
            error = await _execute_action(action, browser)

            # If there was an error, add step with error and break
            if error:
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=error
                ))
                break

            # Add action to history (only if it was executed successfully)
            action_history.append(action)

            # Get a new observation after the action
            try:
                observation_after = await browser.get_observation()
            except Exception:
                # If we can't get a new observation, use the previous one
                observation_after = observation

            # Add step result
            steps.append(StepResult(
                observation=observation_after,
                last_action=action,
                error=None
            ))

        except Exception as exc:
            # If we can't even get an observation, create a step with error
            try:
                observation = await browser.get_observation()
            except Exception:
                # Create a minimal observation if we can't get one
                from backend.shared.models import BrowserObservation
                observation = BrowserObservation(
                    url="",
                    title="",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[]
                )
            
            steps.append(StepResult(
                observation=observation,
                last_action=None,
                error=f"Failed to execute step {step_index}: {str(exc)}"
            ))
            break

    return steps


async def run_llm_agent(
    goal: str,
    browser: BrowserController,
    max_steps: int = 8,
    focus_entity: Optional[str] = None,
    reset_context: bool = False,
) -> List[StepResult]:
    """Runs an agent loop on top of BrowserController using the LLMPlanner."""
    planner = LLMPlanner()
    steps: List[StepResult] = []
    
    # v1.4: Calcular focus_entity si no se proporciona
    if focus_entity is None:
        focus_entity = _extract_focus_entity_from_goal(goal)

    for step_idx in range(max_steps):
        try:
            # Get observation
            observation = await browser.get_observation()
            
            # v1.4: Si reset_context es True y es el primer paso, ignorar la observación actual
            # para forzar navegación a nuevo contexto
            if reset_context and step_idx == 0:
                observation = None

            # Context reorientation layer: ensure we're in the right context
            # v1.4: Pasar observation=None si reset_context para forzar navegación
            reorientation_action = await ensure_context(goal, observation, browser, focus_entity=focus_entity)
            if reorientation_action:
                # Execute reorientation action immediately
                error = await _execute_action(reorientation_action, browser)
                if error:
                    # If reorientation failed, add error step and continue anyway
                    steps.append(StepResult(
                        observation=observation,
                        last_action=reorientation_action,
                        error=f"Failed to reorient context: {error}",
                        info={}
                    ))
                else:
                    # Get new observation after reorientation
                    try:
                        observation = await browser.get_observation()
                        steps.append(StepResult(
                            observation=observation,
                            last_action=reorientation_action,
                            error=None,
                            info={}
                        ))
                    except Exception:
                        # If we can't get observation, continue with previous one
                        pass
                
                # IMPORTANT: After reorientation, continue loop without consulting LLMPlanner
                # This ensures we don't skip the reorientation step
                continue

            # Ask planner for next action
            action = await planner.next_action(
                goal=goal,
                observation=observation,
                history=steps
            )

            # BLOCK STOP if obligatory context is not met
            # If goal requires Wikipedia and we're not in Wikipedia, ignore STOP and force reorientation
            if action.type == "stop":
                if _goal_requires_wikipedia(goal) and not _is_url_in_wikipedia(observation.url):
                    # Ignore STOP action - force reorientation instead
                    # v1.3: Pasar focus_entity a ensure_context
                    reorientation_action = await ensure_context(goal, observation, browser, focus_entity=focus_entity)
                    if reorientation_action:
                        # Execute reorientation action
                        error = await _execute_action(reorientation_action, browser)
                        if error:
                            steps.append(StepResult(
                                observation=observation,
                                last_action=reorientation_action,
                                error=f"Failed to reorient context: {error}",
                                info={}
                            ))
                        else:
                            try:
                                observation = await browser.get_observation()
                                steps.append(StepResult(
                                    observation=observation,
                                    last_action=reorientation_action,
                                    error=None,
                                    info={}
                                ))
                            except Exception:
                                pass
                        # Continue loop without accepting STOP
                        continue

            # If stop action (and context is OK), add final step and break
            if action.type == "stop":
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=None,
                    info={}
                ))
                break

            # Execute the action
            try:
                error = await _execute_action(action, browser)
            except Exception as exc:
                # If there was an exception executing the action
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=str(exc),
                    info={}
                ))
                break

            # If there was an error, add step with error and break
            if error:
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=error,
                    info={}
                ))
                break

            # Get a new observation after the action
            try:
                observation_after = await browser.get_observation()
            except Exception:
                # If we can't get a new observation, use the previous one
                observation_after = observation

            # Add step result
            steps.append(StepResult(
                observation=observation_after,
                last_action=action,
                error=None,
                info={}
            ))

        except Exception as exc:
            # If we can't even get an observation, create a step with error
            try:
                observation = await browser.get_observation()
            except Exception:
                # Create a minimal observation if we can't get one
                from backend.shared.models import BrowserObservation
                observation = BrowserObservation(
                    url="",
                    title="",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[]
                )
            
            steps.append(StepResult(
                observation=observation,
                last_action=None,
                error=f"Failed to execute step: {str(exc)}",
                info={}
            ))
            break

    return steps


SYSTEM_PROMPT_ANSWER = (
    "Eres el agente de respuesta de CometLocal.\n"
    "Has navegado por la web con otro componente y ahora recibes:\n"
    "- el objetivo original del usuario,\n"
    "- el contenido textual visible de la última página,\n"
    "- y opcionalmente la URL y el título.\n"
    "Debes responder al usuario en español, de forma clara y resumida,\n"
    "usando SOLO la información disponible en el texto y el objetivo.\n\n"
    "INSTRUCCIONES ESPECÍFICAS:\n"
    "✅ Prioriza Wikipedia para objetivos tipo 'quién fue X' o 'información sobre X'.\n"
    "✅ Prioriza búsqueda de imágenes cuando el objetivo lo indique explícitamente.\n"
    "❌ No rechaces responder solo porque haya ruido en el histórico.\n"
    "✅ Explica explícitamente qué fuente estás usando.\n"
    "✅ Usa lo mejor disponible incluso si no es perfecto.\n"
    "❌ Solo di 'no encontré información' si realmente no hay fuentes útiles.\n\n"
    "IMPORTANTE: No debes bloquear la respuesta por la presencia de páginas menos relevantes.\n"
    "Debes centrarte únicamente en las fuentes pertinentes al objetivo actual.\n\n"
    "Si la URL indica que estás en una página de resultados de imágenes "
    "(por ejemplo, contiene 'ia=images' o 'iax=images' o es una búsqueda de imágenes),\n"
    "explica que has encontrado resultados de imágenes relacionados con el objetivo, "
    "y describe brevemente qué tipo de imágenes se muestran basándote en el texto visible.\n"
    "Si la página no es relevante o no hay información útil, explícalo."
)


def _decompose_goal(goal: str) -> List[str]:
    """
    Descomposición muy simple de un objetivo en sub-objetivos ordenados.

    Regla v1:
    - Si no detecta conectores, devuelve [goal] tal cual.
    - Si detecta un conector tipo "y luego", "y después", "y despues",
      parte el objetivo en dos.
    - Si el objetivo original menciona "wikipedia" y alguna parte no la
      menciona, se añade " en Wikipedia" a esa parte.
    - Limpia espacios y signos de puntuación sobrantes en los extremos.
    """
    text = " ".join(goal.strip().split())
    lower = text.lower()

    # Conectores simples v1 (se puede ampliar en el futuro)
    connectors = [
        " y luego ",
        " y después ",
        " y despues ",
        ", luego ",
        "; luego ",
        ", después ",
        ", despues ",
    ]

    # Buscar el primer conector que encaje
    split_index = -1
    split_len = 0
    for c in connectors:
        idx = lower.find(c)
        if idx != -1:
            split_index = idx
            split_len = len(c)
            break

    if split_index == -1:
        # No hay conector reconocible → un solo objetivo
        return [text] if text else []

    before = text[:split_index].strip(" ,;.")
    after = text[split_index + split_len :].strip(" ,;.")

    parts = [p for p in [before, after] if p]

    if not parts:
        return [text] if text else []

    # Propagar contexto de Wikipedia:
    # Si el objetivo global menciona "wikipedia" y una parte no lo menciona,
    # añade " en Wikipedia" a esa parte.
    # EXCEPCIÓN v1.2: NO propagar "en Wikipedia" a sub-goals que mencionen imágenes
    if "wikipedia" in lower:
        new_parts: List[str] = []
        for p in parts:
            if "wikipedia" not in p.lower():
                # v1.2: Si el sub-goal menciona imágenes, NO añadir "en Wikipedia"
                if not _goal_mentions_images(p):
                    p = p + " en Wikipedia"
            new_parts.append(p)
        parts = new_parts

    return parts


def decompose_goal(goal: str) -> List[str]:
    """
    Divide un objetivo en sub-objetivos secuenciales usando conectores simples.
    Devuelve una lista ordenada de strings, uno por cada sub-objetivo.
    """
    # Conectores que indican secuencia
    connectors = [
        " y luego ",
        " luego ",
        " después ",
        " y después ",
        " and then ",
    ]
    
    # Buscar el primer conector que aparezca
    goal_lower = goal.lower()
    found_connector = None
    found_index = -1
    
    for connector in connectors:
        index = goal_lower.find(connector)
        if index != -1 and (found_index == -1 or index < found_index):
            found_connector = connector
            found_index = index
    
    # Si no hay conector, devolver el goal original
    if found_connector is None:
        return [goal.strip()]
    
    # Dividir por el conector encontrado
    parts = goal.split(found_connector, 1)
    first_part = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    
    # Si hay más partes, descomponer recursivamente
    if rest:
        sub_goals = [first_part] + decompose_goal(rest)
    else:
        sub_goals = [first_part]
    
    # Filtrar partes vacías y devolver
    return [sg for sg in sub_goals if sg]


def normalize_subgoal(sub_goal: str) -> str:
    """
    Normaliza un sub-objetivo humano a una forma más útil para navegación.
    
    Elimina verbos y frases guía comunes al principio del texto,
    preservando el contenido esencial y la mención a Wikipedia si existe.
    """
    # Trabajar sobre una copia
    result = sub_goal.strip()
    if not result:
        return sub_goal
    
    # Verificar si contiene "wikipedia" (para preservarlo después)
    original_lower = sub_goal.lower()
    has_wikipedia = "wikipedia" in original_lower
    
    # Prefijos a eliminar (en orden de más específico a menos específico)
    prefixes = [
        "investiga quién fue ",
        "investigar quién fue ",
        "investiga ",
        "investigar ",
        "quién fue ",
        "mira información sobre ",
        "mira ",
        "buscar información sobre ",
        "busca información sobre ",
        "buscar ",
        "busca ",
        "consulta ",
        "averigua ",
        "infórmate sobre ",
    ]
    
    # Intentar eliminar prefijos
    lower_result = result.lower()
    for prefix in prefixes:
        if lower_result.startswith(prefix):
            result = result[len(prefix):].strip()
            break
    
    # Eliminar "sobre " al inicio si quedó después de eliminar prefijos
    if result.lower().startswith("sobre "):
        result = result[6:].strip()
    
    # Si el resultado quedó vacío, devolver el original
    if not result:
        return sub_goal.strip()
    
    # Caso especial: preservar "en Wikipedia" si estaba en el original
    if has_wikipedia and "wikipedia" not in result.lower():
        result = f"{result} en Wikipedia"
    
    return result


async def _process_single_subgoal(
    raw_sub_goal: str,
    browser: BrowserController,
    max_steps: int,
) -> tuple[List[StepResult], Optional[BrowserObservation], str]:
    """
    Procesa un sub-objetivo individual:
    - Normaliza el sub-objetivo para navegación
    - Navega a Wikipedia si es necesario
    - Ejecuta el agente LLM con el objetivo normalizado
    - Genera una respuesta parcial usando el objetivo original
    Devuelve (steps, last_observation, partial_answer)
    """
    # Normalizar el sub-objetivo para navegación
    navigation_goal = normalize_subgoal(raw_sub_goal)
    
    steps: List[StepResult] = []

    # Orientación dura a Wikipedia si el sub-objetivo normalizado lo pide
    text_lower = navigation_goal.lower()
    if "wikipedia" in text_lower:
        cleanup_phrases = [
            "en wikipedia en español",
            "en la wikipedia en español",
            "en wikipedia",
            "en la wikipedia",
        ]
        query_text = navigation_goal
        for phrase in cleanup_phrases:
            query_text = query_text.replace(phrase, "")
        query_text = query_text.strip() or navigation_goal.strip()

        search_param = quote_plus(query_text)
        wikipedia_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"

        forced_action = BrowserAction(type="open_url", args={"url": wikipedia_url})

        try:
            error = await _execute_action(forced_action, browser)
            if error:
                try:
                    current_obs = await browser.get_observation()
                except Exception:
                    from backend.shared.models import BrowserObservation
                    current_obs = BrowserObservation(
                        url="",
                        title="",
                        visible_text_excerpt="",
                        clickable_texts=[],
                        input_hints=[]
                    )
                steps.append(
                    StepResult(
                        observation=current_obs,
                        last_action=forced_action,
                        error=error,
                        info={"phase": "forced_wikipedia_error"},
                    )
                )
            else:
                obs = await browser.get_observation()
                steps.append(
                    StepResult(
                        observation=obs,
                        last_action=forced_action,
                        error=None,
                        info={"phase": "forced_wikipedia"},
                    )
                )
        except Exception as exc:  # pragma: no cover - defensivo
            try:
                current_obs = await browser.get_observation()
            except Exception:
                from backend.shared.models import BrowserObservation
                current_obs = BrowserObservation(
                    url="",
                    title="",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[]
                )
            steps.append(
                StepResult(
                    observation=current_obs,
                    last_action=forced_action,
                    error=str(exc),
                    info={"phase": "forced_wikipedia_error"},
                )
            )

    # Ejecutar el agente LLM para este sub-objetivo (usando el objetivo normalizado)
    try:
        more_steps = await run_llm_agent(goal=navigation_goal, browser=browser, max_steps=max_steps)
        steps.extend(more_steps)
    except Exception as exc:  # pragma: no cover - defensivo
        # Si falla, continuamos con los pasos que tengamos
        pass

    # Obtener la última observación de este sub-objetivo
    last_observation: Optional[BrowserObservation] = None
    for step in reversed(steps):
        if step.observation is not None:
            last_observation = step.observation
            break

    # Generar respuesta parcial
    partial_answer = ""
    if last_observation:
        url = last_observation.url or ""
        title = last_observation.title or ""
        visible = last_observation.visible_text_excerpt or ""

        system_prompt = SYSTEM_PROMPT_ANSWER
        user_prompt = (
            f"Sub-objetivo original del usuario:\n{raw_sub_goal}\n\n"
            f"Objetivo normalizado para la navegación: '{navigation_goal}'\n\n"
            f"URL visitada:\n{url}\n\n"
            f"Título de la página:\n{title}\n\n"
            "Contenido de la página (extracto del texto visible):\n"
            f"{visible}\n\n"
            "Responde brevemente a este sub-objetivo en español."
        )

        client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)
        try:
            response = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            partial_answer = response.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover - defensivo
            partial_answer = f"No he podido generar una respuesta para este sub-objetivo. Detalle: {exc}"
    else:
        partial_answer = f"No he podido obtener información para: {raw_sub_goal}"

    return steps, last_observation, partial_answer


def _is_wikipedia_search_url(url: Optional[str]) -> bool:
    """
    Devuelve True si la URL es una página de búsqueda de Wikipedia.
    """
    if not url:
        return False
    url_lower = url.lower()
    return (
        "wikipedia.org/wiki/especial:buscar" in url_lower
        or "/w/index.php?search=" in url_lower
    )


def _get_effective_focus_entity(goal: str, focus_entity: Optional[str]) -> Optional[str]:
    """
    Devuelve la entidad a usar para búsquedas / artículos de Wikipedia.
    
    Prioridad:
    1) focus_entity explícito (propagado por run_llm_task_with_answer)
    2) entidad extraída del goal con _extract_focus_entity_from_goal
    3) en caso contrario, None (NO usar el goal literal como título)
    
    v1.4: Limpia palabras conectoras al inicio (de, del, la, el) de la entidad.
    """
    def clean_entity(entity: str) -> str:
        """Limpia palabras conectoras al inicio de la entidad."""
        entity = entity.strip()
        # Palabras conectoras que pueden aparecer al inicio
        connectors = ["de ", "del ", "la ", "el ", "y ", "en "]
        for connector in connectors:
            if entity.lower().startswith(connector):
                entity = entity[len(connector):].strip()
        return entity
    
    if focus_entity:
        cleaned = clean_entity(focus_entity)
        return cleaned if cleaned else None
    
    inferred = _extract_focus_entity_from_goal(goal)
    if inferred:
        cleaned = clean_entity(inferred)
        return cleaned if cleaned else None
    
    return None


def _normalize_wikipedia_query(goal: str, focus_entity: Optional[str] = None) -> Optional[str]:
    """
    Devuelve la query de Wikipedia, siempre basada en una entidad corta,
    nunca en una frase literal.
    
    Prioridad:
    1) focus_entity (ya normalizada por quien llama)
    2) _extract_focus_entity_from_goal(goal)
    3) None si no se puede inferir nada razonable
    """
    effective = _get_effective_focus_entity(goal, focus_entity)
    return effective


def _normalize_image_query(goal: str, fallback_focus: Optional[str] = None) -> str:
    """
    Normaliza la query para búsquedas de imágenes en DuckDuckGo.
    
    Prioridad:
    1. Entidad detectada en el propio goal.
    2. fallback_focus (entidad global del objetivo compuesto).
    3. Goal limpiado de verbos imperativos comunes.
    
    v1.4: Evita duplicados "de de ..." y normaliza espacios.
    """
    text = goal.strip()
    
    # 1) Entidad del propio sub-goal
    focus = _extract_focus_entity_from_goal(text)
    
    # 2) Si no hay, usar entidad global
    if not focus and fallback_focus:
        focus = fallback_focus
    
    # v1.4: Si tenemos entidad, construir query limpia
    if focus:
        # Limpiar entidad de palabras conectoras
        clean_entity = focus.strip()
        # Construir query: siempre "imágenes de <entidad>"
        query = f"imágenes de {clean_entity}"
    else:
        # 3) Sin entidad clara: limpiar verbos imperativos típicos
        cleaned = re.sub(
            r"\b(muéstrame|muestrame|muestra|mira|ver|enséñame|enseñame|ensename|busca|buscar)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:¡!¿?")
        query = cleaned or goal.strip()
    
    # v1.4: Normalizar duplicados "de de ..." y espacios múltiples
    query = query.replace("de de ", "de ")
    query = query.replace("  ", " ").strip()
    
    return query


def _extract_focus_entity_from_goal(goal: str, fallback_focus_entity: Optional[str] = None) -> Optional[str]:
    """
    Extrae la entidad principal del sub-goal (ej. 'Ada Lovelace', 'Charles Babbage').
    Usada solo para trazabilidad y control.
    
    v1.4: Si el sub-goal contiene pronombres y no se extrae entidad explícita,
    retorna fallback_focus_entity.
    """
    goal_lower = goal.lower()
    
    # v1.4: Detectar pronombres
    pronouns = ["su", "sus", "suyas", "suyos", "él", "ella", "le", "la", "lo"]
    has_pronoun = any(pronoun in goal_lower for pronoun in pronouns)
    
    # Buscar y recortar "en wikipedia" o "en la wikipedia"
    topic_part = goal
    for suffix in [" en wikipedia", " en la wikipedia"]:
        if goal_lower.endswith(suffix):
            topic_part = goal[:len(goal) - len(suffix)].strip()
            break
    
    # Si no encontramos el sufijo, usar todo el texto
    if topic_part == goal:
        topic_part = goal.strip()
    
    # Dividir en tokens
    tokens = topic_part.split()
    if not tokens:
        # v1.4: Si hay pronombre y no hay tokens, usar fallback
        if has_pronoun and fallback_focus_entity:
            return fallback_focus_entity
        return None
    
    # Recorrer desde el final hacia atrás, acumulando palabras capitalizadas
    accumulated = []
    short_connectors = {"de", "del", "la", "el", "y", "en"}
    
    for token in reversed(tokens):
        # Limpiar puntuación del token
        clean_token = token.strip(" ,;.")
        if not clean_token:
            continue
        
        # Si es una palabra corta conectora, la incluimos para no cortar apellidos compuestos
        if clean_token.lower() in short_connectors:
            accumulated.append(clean_token)
            continue
        
        # Si la primera letra es alfabética y mayúscula, es un nombre propio
        if clean_token[0].isalpha() and clean_token[0].isupper():
            accumulated.append(clean_token)
        else:
            # Si encontramos una palabra no capitalizada, paramos
            break
    
    if not accumulated:
        # v1.4: Si hay pronombre y no se extrajo entidad, usar fallback
        if has_pronoun and fallback_focus_entity:
            return fallback_focus_entity
        return None
    
    # Invertir para obtener el orden normal
    entity = " ".join(reversed(accumulated))
    # Limpiar comas o puntos finales
    entity = entity.strip(" ,;.")
    
    return entity if entity else None


def _extract_wikipedia_title_from_goal(goal: str) -> Optional[str]:
    """
    Extrae un candidato de título de artículo a partir del objetivo textual.
    
    Busca palabras capitalizadas al final del texto (después de eliminar "en wikipedia").
    """
    goal_lower = goal.lower()
    
    # Buscar y recortar "en wikipedia" o "en la wikipedia"
    topic_part = goal
    for suffix in [" en wikipedia", " en la wikipedia"]:
        if goal_lower.endswith(suffix):
            topic_part = goal[:len(goal) - len(suffix)].strip()
            break
    
    # Si no encontramos el sufijo, usar todo el texto
    if topic_part == goal:
        topic_part = goal.strip()
    
    # Dividir en tokens
    tokens = topic_part.split()
    if not tokens:
        return None
    
    # Recorrer desde el final hacia atrás, acumulando palabras capitalizadas
    accumulated = []
    short_connectors = {"de", "del", "la", "el", "y", "en"}
    
    for token in reversed(tokens):
        # Limpiar puntuación del token
        clean_token = token.strip(" ,;.")
        if not clean_token:
            continue
        
        # Si es una palabra corta conectora, la incluimos para no cortar apellidos compuestos
        if clean_token.lower() in short_connectors:
            accumulated.append(clean_token)
            continue
        
        # Si la primera letra es alfabética y mayúscula, es un nombre propio
        if clean_token[0].isalpha() and clean_token[0].isupper():
            accumulated.append(clean_token)
        else:
            # Si encontramos una palabra no capitalizada, paramos
            break
    
    if not accumulated:
        return None
    
    # Invertir para obtener el orden normal
    title = " ".join(reversed(accumulated))
    # Limpiar comas o puntos finales
    title = title.strip(" ,;.")
    
    return title if title else None


def _build_wikipedia_article_url(search_url: str, title: str) -> str:
    """
    Construye la URL de artículo en Wikipedia a partir de una URL de búsqueda y un título.
    
    Extrae el esquema y host de search_url (ej: https://es.wikipedia.org)
    y genera la URL del artículo con el título dado.
    """
    from urllib.parse import urlparse
    
    # Extraer esquema + host de search_url
    parsed = urlparse(search_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    # Generar slug: reemplazar espacios por _ y usar quote_plus para escaparlo
    slug = title.strip().replace(" ", "_")
    encoded_slug = quote_plus(slug, safe="_")
    
    return f"{base}/wiki/{encoded_slug}"


async def _maybe_resolve_wikipedia_search(
    browser: BrowserController,
    goal: str,
    final_observation: Optional[BrowserObservation],
    focus_entity: Optional[str] = None,
) -> tuple[Optional[BrowserObservation], List[StepResult]]:
    """
    Resuelve determinísticamente una búsqueda de Wikipedia navegando al artículo correcto.
    
    v1.4: Solo resuelve artículos por entidad, nunca por frases literales.
    Si no hay entidad clara, no resuelve nada.
    v1.4: Endurecido - verifica que focus_entity esté contenido en final_title después de navegar.
    
    Devuelve (nueva_observación, [step_result]) si tiene éxito, o (final_observation, []) si no aplica o falla.
    """
    resolver_steps: List[StepResult] = []
    
    # Validaciones iniciales
    if final_observation is None:
        return (final_observation, resolver_steps)
    
    if not _is_wikipedia_search_url(final_observation.url or ""):
        return (final_observation, resolver_steps)
    
    goal_lower = goal.lower()
    if "wikipedia" not in goal_lower:
        return (final_observation, resolver_steps)
    
    # v1.4: Obtener entidad efectiva usando _normalize_wikipedia_query
    # Solo resolvemos si tenemos una entidad clara
    article_title = _normalize_wikipedia_query(goal, focus_entity=focus_entity)
    
    if not article_title:
        # No sabemos qué artículo concreto buscar; no tocamos nada
        return (final_observation, resolver_steps)
    
    try:
        # Construir URL del artículo usando solo la entidad
        from urllib.parse import urlparse
        
        parsed = urlparse(final_observation.url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        slug = article_title.replace(" ", "_")
        encoded_slug = quote_plus(slug, safe="_")
        article_url = f"{base}/wiki/{encoded_slug}"
        
        # Navegar al artículo
        action = BrowserAction(type="open_url", args={"url": article_url})
        error = await _execute_action(action, browser)
        
        if error:
            # Si hay error, devolver la observación original sin romper el flujo
            return (final_observation, resolver_steps)
        
        # Obtener la nueva observación
        article_observation = await browser.get_observation()
        
        # v1.4: Endurecer verificación - normalizar y comparar
        final_title = (article_observation.title or "").strip()
        final_title_normalized = final_title.lower()
        # Quitar paréntesis y su contenido
        final_title_normalized = re.sub(r"\s*\([^)]*\)\s*", "", final_title_normalized)
        
        # Normalizar focus_entity
        focus_normalized = ""
        if focus_entity:
            focus_normalized = focus_entity.lower().strip()
            focus_normalized = re.sub(r"\s*\([^)]*\)\s*", "", focus_normalized)
        
        # Verificación: si focus_entity NO está contenido en final_title, no continuar
        if focus_entity and focus_normalized:
            if focus_normalized not in final_title_normalized:
                # NO navegar más automáticamente - registrar error
                error_step = StepResult(
                    observation=article_observation,
                    last_action=action,
                    error=None,
                    info={
                        "resolver_error": "article_mismatch",
                        "expected_entity": focus_entity,
                        "final_title": final_title,
                        "resolver": "wikipedia_article_v2_failed",
                    }
                )
                resolver_steps.append(error_step)
                # Devolver la observación original (de la búsqueda)
                return (final_observation, resolver_steps)
        
        # Crear StepResult de éxito
        step_result = StepResult(
            observation=article_observation,
            last_action=action,
            error=None,
            info={
                "resolver": "wikipedia_article_v2",
                "article_title": article_title,
                "from_search_url": final_observation.url,
            }
        )
        
        resolver_steps.append(step_result)
        return (article_observation, resolver_steps)
    
    except Exception:
        # En caso de error, no rompemos el flujo
        return (final_observation, resolver_steps)


async def _run_llm_task_single(
    browser: BrowserController,
    goal: str,
    max_steps: int = 8,
    focus_entity: Optional[str] = None,
    reset_context: bool = False,
    sub_goal_index: Optional[int] = None,
) -> Tuple[List[StepResult], str]:
    """
    Ejecuta el agente LLM para un único objetivo (sin descomposición)
    y genera una respuesta final en lenguaje natural basada en la última
    observación.
    
    v1.3: Acepta focus_entity para normalizar queries.
    v1.4: Acepta reset_context para forzar contexto limpio al inicio.
    v1.4: Aislamiento estricto de steps - solo usa steps_local para el prompt.
    """
    # v1.4: Crear estructura local, no compartida
    steps_local: List[StepResult] = []

    # v1.4: Calcular focus_entity si no se proporciona
    if focus_entity is None:
        focus_entity = _extract_focus_entity_from_goal(goal)

    # v1.4: Orientación dura a Wikipedia si el objetivo lo pide
    # Solo si no estamos reseteando contexto (para evitar duplicar navegación)
    if not reset_context:
        text_lower = goal.lower()
        if "wikipedia" in text_lower:
            # v1.4: Usar query normalizada con focus_entity
            query = _normalize_wikipedia_query(goal, focus_entity=focus_entity)
            if query:
                search_param = quote_plus(query)
                wikipedia_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"

                forced_action = BrowserAction(type="open_url", args={"url": wikipedia_url})

                try:
                    error = await _execute_action(forced_action, browser)
                    if error:
                        try:
                            current_obs = await browser.get_observation()
                        except Exception:
                            from backend.shared.models import BrowserObservation
                            current_obs = BrowserObservation(
                                url="",
                                title="",
                                visible_text_excerpt="",
                                clickable_texts=[],
                                input_hints=[]
                            )
                        steps_local.append(
                            StepResult(
                                observation=current_obs,
                                last_action=forced_action,
                                error=error,
                                info={"phase": "forced_wikipedia_error"},
                            )
                        )
                    else:
                        obs = await browser.get_observation()
                        steps_local.append(
                            StepResult(
                                observation=obs,
                                last_action=forced_action,
                                error=None,
                                info={"phase": "forced_wikipedia"},
                            )
                        )
                except Exception as exc:  # pragma: no cover - defensivo
                    try:
                        current_obs = await browser.get_observation()
                    except Exception:
                        from backend.shared.models import BrowserObservation
                        current_obs = BrowserObservation(
                            url="",
                            title="",
                            visible_text_excerpt="",
                            clickable_texts=[],
                            input_hints=[]
                        )
                    steps_local.append(
                        StepResult(
                            observation=current_obs,
                            last_action=forced_action,
                            error=str(exc),
                            info={"phase": "forced_wikipedia_error"},
                        )
                    )

    # Ejecutar el agente LLM normal a partir del contexto actual
    # v1.4: Pasar focus_entity y reset_context a run_llm_agent
    more_steps = await run_llm_agent(
        goal=goal,
        browser=browser,
        max_steps=max_steps,
        focus_entity=focus_entity,
        reset_context=reset_context
    )
    # v1.4: Añadir solo a steps_local, no usar all_steps externos
    steps_local.extend(more_steps)

    # Obtener la última observación disponible (solo de steps_local)
    last_observation: Optional[BrowserObservation] = None
    for step in reversed(steps_local):
        if step.observation is not None:
            last_observation = step.observation
            break

    if last_observation is None:
        # Fallback duro si por alguna razón no hay observación
        return steps_local, "No he podido obtener ninguna observación del navegador para responder."

    # Resolver determinísticamente búsquedas de Wikipedia si es necesario
    # v1.4: Pasar focus_entity a _maybe_resolve_wikipedia_search
    resolved_observation, resolver_steps = await _maybe_resolve_wikipedia_search(
        browser, goal, last_observation, focus_entity=focus_entity
    )
    if resolved_observation is not None:
        steps_local.extend(resolver_steps)
        last_observation = resolved_observation

    # v1.4: Marcar todos los steps con sub_goal_index si se proporciona
    if sub_goal_index is not None:
        for s in steps_local:
            info = dict(s.info or {})
            info["sub_goal_index"] = sub_goal_index
            if focus_entity:
                info["focus_entity"] = focus_entity
            s.info = info

    # v1.4: Construir el prompt usando solo steps_local (todos son del sub-objetivo actual)
    # Filtrar por sub_goal_index si se proporciona (aunque todos deberían ser del mismo)
    relevant_steps = steps_local
    if sub_goal_index is not None:
        relevant_steps = [
            s for s in steps_local
            if s.info.get("sub_goal_index") == sub_goal_index
        ]
        # Si no hay steps filtrados, usar todos los del sub-objetivo actual
        if not relevant_steps:
            relevant_steps = steps_local
    # Si hay focus_entity, priorizar steps donde aparezca en title o url
    relevant_steps = steps_local
    if focus_entity and relevant_steps:
        focus_entity_lower = focus_entity.lower()
        prioritized_steps = []
        other_steps = []
        for step in relevant_steps:
            if step.observation:
                title_lower = (step.observation.title or "").lower()
                url_lower = (step.observation.url or "").lower()
                if focus_entity_lower in title_lower or focus_entity_lower in url_lower:
                    prioritized_steps.append(step)
                else:
                    other_steps.append(step)
        # Si encontramos steps prioritarios, usarlos; si no, usar todos
        if prioritized_steps:
            relevant_steps = prioritized_steps + other_steps
    
    # Construir bloque de observaciones relevantes
    observations_text = ""
    if relevant_steps:
        observations_parts = []
        for step in relevant_steps:
            if step.observation:
                obs = step.observation
                obs_text = f"URL: {obs.url or 'N/A'}\n"
                obs_text += f"Título: {obs.title or 'N/A'}\n"
                if obs.visible_text_excerpt:
                    obs_text += f"Contenido: {obs.visible_text_excerpt[:500]}...\n"
                observations_parts.append(obs_text)
        if observations_parts:
            observations_text = "\n---\n".join(observations_parts)
    
    # Construir el prompt para el LLM de respuesta final
    url = last_observation.url or ""
    title = last_observation.title or ""
    visible = last_observation.visible_text_excerpt or ""

    system_prompt = SYSTEM_PROMPT_ANSWER

    user_prompt = (
        f"Objetivo original del usuario:\n{goal}\n\n"
    )
    
    # v1.4: Añadir bloque de observaciones relevantes si hay
    if observations_text:
        user_prompt += (
            "Observaciones relevantes del agente:\n"
            f"{observations_text}\n\n"
        )
        # Si hay focus_entity pero no se encontró en las fuentes, añadir nota
        if focus_entity:
            found_entity = False
            for step in relevant_steps:
                if step.observation:
                    title_lower = (step.observation.title or "").lower()
                    url_lower = (step.observation.url or "").lower()
                    if focus_entity.lower() in title_lower or focus_entity.lower() in url_lower:
                        found_entity = True
                        break
            if not found_entity:
                user_prompt += (
                    "Nota: No se encontró una fuente que mencione explícitamente la entidad esperada "
                    f"({focus_entity}). Usa la mejor información disponible.\n\n"
                )
    
    user_prompt += (
        f"Última URL visitada por el agente:\n{url}\n\n"
        f"Título de la página:\n{title}\n\n"
        "Contenido de la página (extracto del texto visible):\n"
        f"{visible}\n\n"
        "Usa esta información para responder al objetivo del usuario en español."
    )

    client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        final_answer = response.choices[0].message.content or ""
    except Exception as exc:  # pragma: no cover - defensivo
        final_answer = (
            "He tenido un problema al generar la respuesta final a partir de la página "
            f"visitada. Detalle técnico: {exc}"
        )

    return steps_local, final_answer


async def run_llm_task_with_answer(
    goal: str,
    browser: BrowserController,
    max_steps: int = 8,
) -> tuple[List[StepResult], str, str, str, List[SourceInfo]]:
    """
    Orquesta la ejecución del agente para uno o varios sub-objetivos.

    - Si el objetivo no se descompone, delega en _run_llm_task_single.
    - Si se descompone en varios sub-objetivos, los ejecuta en secuencia,
      reutilizando el mismo navegador y agregando las respuestas.
    """
    # v1.4: Entidad global del objetivo completo
    # Primero intentamos desde el goal completo, luego desde el primer sub-goal con entidad
    global_focus_entity = _extract_focus_entity_from_goal(goal)
    
    sub_goals = _decompose_goal(goal)
    if not sub_goals:
        # Fallback de seguridad: usar el objetivo original
        sub_goals = [goal]
    
    # v1.4: Si no hay entidad global del goal completo, intentar desde el primer sub-goal
    if not global_focus_entity:
        for sub_goal in sub_goals:
            candidate = _extract_focus_entity_from_goal(sub_goal)
            if candidate:
                global_focus_entity = candidate
                break

    # Caso simple: un solo objetivo → comportamiento actual
    if len(sub_goals) == 1:
        sub_goal = sub_goals[0]
        # v1.4: Entidad específica del sub-goal con fallback para pronombres
        focus_entity = _extract_focus_entity_from_goal(sub_goal, fallback_focus_entity=global_focus_entity)
        if not focus_entity:
            focus_entity = global_focus_entity
        
        # v1.4: Primer sub-goal siempre resetea contexto
        steps, final_answer = await _run_llm_task_single(
            browser, sub_goal, max_steps, focus_entity=focus_entity, reset_context=True, sub_goal_index=1
        )
        
        # v1.4: Logging ligero para diagnóstico
        prompt_size = len(str(final_answer))  # Aproximación del tamaño del prompt
        print(f"[v1.4] Sub-goal 1: {len(steps)} steps, prompt_size ~{prompt_size} chars")
        
        # Añadir marcado de focus_entity a todos los steps
        for s in steps:
            info = dict(s.info or {})
            if focus_entity:
                info["focus_entity"] = focus_entity
            s.info = info
        
        # Calcular source_url, source_title y sources para mantener compatibilidad
        last_observation: Optional[BrowserObservation] = None
        for step in reversed(steps):
            if step.observation is not None:
                last_observation = step.observation
                break
        
        source_url = last_observation.url or "" if last_observation else ""
        source_title = last_observation.title or "" if last_observation else ""
        
        sources: List[SourceInfo] = []
        if source_url:
            sources.append(SourceInfo(url=source_url, title=source_title or None))
        
        seen_urls = {source_url} if source_url else set()
        for step in reversed(steps):
            obs = step.observation
            if not obs or not obs.url:
                continue
            url = obs.url
            if url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(SourceInfo(url=url, title=(obs.title or None)))
            if len(sources) >= 3:
                break
        
        return steps, final_answer, source_url, source_title, sources

    all_steps: List[StepResult] = []
    answers: List[str] = []
    all_observations: List[BrowserObservation] = []

    for idx, sub_goal in enumerate(sub_goals, start=1):
        # v1.4: Entidad específica del sub-goal con fallback para pronombres
        sub_focus_entity = _extract_focus_entity_from_goal(sub_goal, fallback_focus_entity=global_focus_entity)
        if not sub_focus_entity:
            sub_focus_entity = global_focus_entity
        
        # Refuerzo de contexto al inicio de cada sub-goal
        # Si el sub-goal contiene "wikipedia", forzar contexto limpio
        context_steps: List[StepResult] = []
        if "wikipedia" in sub_goal.lower():
            # v1.4: Normalizar la query usando sub_focus_entity como fallback
            query = _normalize_wikipedia_query(sub_goal, focus_entity=sub_focus_entity)
            if query:
                search_param = quote_plus(query)
                wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
                
                forced_action = BrowserAction(type="open_url", args={"url": wikipedia_search_url})
                
                try:
                    error = await _execute_action(forced_action, browser)
                    if error:
                        try:
                            current_obs = await browser.get_observation()
                        except Exception:
                            from backend.shared.models import BrowserObservation
                            current_obs = BrowserObservation(
                                url="",
                                title="",
                                visible_text_excerpt="",
                                clickable_texts=[],
                                input_hints=[]
                            )
                        context_steps.append(
                            StepResult(
                                observation=current_obs,
                                last_action=forced_action,
                                error=error,
                                info={"phase": "context_cleanup_error"},
                            )
                        )
                    else:
                        obs = await browser.get_observation()
                        context_steps.append(
                            StepResult(
                                observation=obs,
                                last_action=forced_action,
                                error=None,
                                info={"phase": "context_cleanup"},
                            )
                        )
                except Exception as exc:  # pragma: no cover - defensivo
                    try:
                        current_obs = await browser.get_observation()
                    except Exception:
                        from backend.shared.models import BrowserObservation
                        current_obs = BrowserObservation(
                            url="",
                            title="",
                            visible_text_excerpt="",
                            clickable_texts=[],
                            input_hints=[]
                        )
                    context_steps.append(
                        StepResult(
                            observation=current_obs,
                            last_action=forced_action,
                            error=str(exc),
                            info={"phase": "context_cleanup_error"},
                        )
                    )
        
        # v1.4: Ejecutar el sub-objetivo
        # Primer sub-goal (idx == 1) resetea contexto, los demás no
        reset_ctx = (idx == 1)
        steps, answer = await _run_llm_task_single(
            browser, sub_goal, max_steps, focus_entity=sub_focus_entity, reset_context=reset_ctx, sub_goal_index=idx
        )
        
        # v1.4: Logging ligero para diagnóstico
        prompt_size = len(str(answer))  # Aproximación del tamaño del prompt
        print(f"[v1.4] Sub-goal {idx}: {len(steps)} steps, prompt_size ~{prompt_size} chars")
        
        # Combinar context_steps con steps
        all_subgoal_steps = context_steps + steps

        # Anotar en info a qué sub-objetivo pertenece cada paso
        for s in all_subgoal_steps:
            info = dict(s.info or {})
            info["sub_goal_index"] = idx
            info["sub_goal"] = sub_goal
            # v1.4: Añadir focus_entity si está disponible
            if sub_focus_entity:
                info["focus_entity"] = sub_focus_entity
            s.info = info
            all_steps.append(s)
        
        # Guardar la última observación de este sub-objetivo
        for step in reversed(steps):
            if step.observation is not None:
                all_observations.append(step.observation)
                break

        # Guardar respuesta numerada
        answer = answer.strip()
        if answer:
            answers.append(f"{idx}. {answer}")
        else:
            answers.append(f"{idx}. (Sin información relevante encontrada para este sub-objetivo)")

    # Respuesta final agregada
    final_answer = "\n\n".join(answers)
    
    # Calcular source_url, source_title y sources desde todas las observaciones
    last_observation: Optional[BrowserObservation] = None
    if all_observations:
        last_observation = all_observations[-1]
    else:
        # Fallback: buscar en todos los steps
        for step in reversed(all_steps):
            if step.observation is not None:
                last_observation = step.observation
                break

    source_url = last_observation.url or "" if last_observation else ""
    source_title = last_observation.title or "" if last_observation else ""

    sources: List[SourceInfo] = []
    if source_url:
        sources.append(SourceInfo(url=source_url, title=source_title or None))

    seen_urls = {source_url} if source_url else set()

    # Recorrer todas las observaciones (de más reciente a más antigua)
    for obs in reversed(all_observations):
        if not obs or not obs.url:
            continue
        url = obs.url
        if url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(SourceInfo(url=url, title=(obs.title or None)))
        if len(sources) >= 3:
            break

    return all_steps, final_answer, source_url, source_title, sources

