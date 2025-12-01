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
    observation: BrowserObservation,
    browser: BrowserController,
) -> Optional[BrowserAction]:
    """
    Context reorientation layer: ensures the browser is in a reasonable site
    for the current goal before delegating to the LLM planner.
    Returns a BrowserAction if reorientation is needed, None otherwise.
    
    For obligatory contexts (like Wikipedia), this function ALWAYS returns
    the reorientation action if the context is not met, without exceptions.
    """
    # PRIORIDAD 1: Wikipedia con entidad específica
    # Si el goal menciona Wikipedia y podemos extraer una entidad, navegar directamente al artículo
    if _goal_mentions_wikipedia(goal):
        entity = _extract_wikipedia_entity_from_goal(goal)
        if entity:
            # Si ya estamos en el artículo de esa entidad, no hacer nada
            if _is_url_entity_article(observation.url, entity):
                # Ya estamos en el artículo correcto, dejar que el planner actúe
                # No hacer nada más, retornar None para que el planner tome el control
                return None
            else:
                # Construir URL del artículo y navegar
                article_url = _build_wikipedia_article_url(entity)
                return BrowserAction(type="open_url", args={"url": article_url})
    
    # PRIORIDAD 2: OBLIGATORY CONTEXT: Wikipedia (sin entidad específica o fallback)
    # If goal requires Wikipedia and we're not in Wikipedia, ALWAYS redirect
    # Solo aplica si no encontramos una entidad específica en PRIORIDAD 1
    if _goal_requires_wikipedia(goal):
        if not _is_url_in_wikipedia(observation.url):
            # Always return Wikipedia navigation action - no exceptions
            return BrowserAction(type="open_url", args={"url": "https://www.wikipedia.org"})
    
    # PRIORIDAD 3: OPTIONAL CONTEXT: Image search
    # This is still optional/orientative, not obligatory
    if _goal_mentions_images(goal):
        if not _is_url_in_image_search(observation.url):
            # Extract query from goal (simple: use the whole goal as query)
            query = goal.strip()
            image_search_url = DEFAULT_IMAGE_SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
            return BrowserAction(type="open_url", args={"url": image_search_url})
    
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
) -> List[StepResult]:
    """Runs an agent loop on top of BrowserController using the LLMPlanner."""
    planner = LLMPlanner()
    steps: List[StepResult] = []

    for _ in range(max_steps):
        try:
            # Get observation
            observation = await browser.get_observation()

            # Context reorientation layer: ensure we're in the right context
            reorientation_action = await ensure_context(goal, observation, browser)
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
                    reorientation_action = await ensure_context(goal, observation, browser)
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
    "usando SOLO la información disponible en el texto y el objetivo.\n"
    "IMPORTANTE: Si la URL indica que estás en una página de resultados de imágenes "
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
    if "wikipedia" in lower:
        new_parts: List[str] = []
        for p in parts:
            if "wikipedia" not in p.lower():
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


def _extract_focus_entity_from_goal(goal: str) -> Optional[str]:
    """
    Extrae la entidad principal del sub-goal (ej. 'Ada Lovelace', 'Charles Babbage').
    Usada solo para trazabilidad y control.
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
) -> tuple[Optional[BrowserObservation], List[StepResult]]:
    """
    Resuelve determinísticamente una búsqueda de Wikipedia navegando al artículo correcto.
    
    Si final_observation está en una página de búsqueda de Wikipedia y el goal menciona Wikipedia,
    intenta extraer el título del artículo y navegar directamente a él.
    
    Devuelve (nueva_observación, [step_result]) si tiene éxito, o (None, []) si no aplica o falla.
    """
    # Validaciones iniciales
    if final_observation is None:
        return (None, [])
    
    if not _is_wikipedia_search_url(final_observation.url):
        return (None, [])
    
    goal_lower = goal.lower()
    if "wikipedia" not in goal_lower:
        return (None, [])
    
    # Extraer título del artículo
    title = _extract_wikipedia_title_from_goal(goal)
    if not title:
        return (None, [])
    
    # Construir URL del artículo
    try:
        article_url = _build_wikipedia_article_url(final_observation.url, title)
    except Exception:
        return (None, [])
    
    # Navegar al artículo
    try:
        action = BrowserAction(type="open_url", args={"url": article_url})
        error = await _execute_action(action, browser)
        
        if error:
            # Si hay error, devolver None para no romper el flujo
            return (None, [])
        
        # Obtener la nueva observación
        article_observation = await browser.get_observation()
        
        # Crear StepResult
        step_result = StepResult(
            observation=article_observation,
            last_action=action,
            error=None,
            info={
                "resolver": "wikipedia_article_v1",
                "article_title": title,
                "from_search_url": final_observation.url,
            }
        )
        
        return (article_observation, [step_result])
    
    except Exception:
        # Cualquier error: devolver None para no romper el flujo
        return (None, [])


async def _run_llm_task_single(
    browser: BrowserController,
    goal: str,
    max_steps: int = 8,
) -> Tuple[List[StepResult], str]:
    """
    Ejecuta el agente LLM para un único objetivo (sin descomposición)
    y genera una respuesta final en lenguaje natural basada en la última
    observación.
    """
    steps: List[StepResult] = []

    # Orientación dura a Wikipedia si el objetivo lo pide
    text_lower = goal.lower()
    if "wikipedia" in text_lower:
        raw_goal = goal
        cleanup_phrases = [
            "en wikipedia en español",
            "en la wikipedia en español",
            "en wikipedia",
            "en la wikipedia",
        ]
        query_text = raw_goal
        for phrase in cleanup_phrases:
            query_text = query_text.replace(phrase, "")
        query_text = query_text.strip() or raw_goal.strip()

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

    # Ejecutar el agente LLM normal a partir del contexto actual
    more_steps = await run_llm_agent(goal=goal, browser=browser, max_steps=max_steps)
    all_steps = steps + more_steps

    # Obtener la última observación disponible
    last_observation: Optional[BrowserObservation] = None
    for step in reversed(all_steps):
        if step.observation is not None:
            last_observation = step.observation
            break

    if last_observation is None:
        # Fallback duro si por alguna razón no hay observación
        return all_steps, "No he podido obtener ninguna observación del navegador para responder."

    # Resolver determinísticamente búsquedas de Wikipedia si es necesario
    resolved_observation, resolver_steps = await _maybe_resolve_wikipedia_search(
        browser, goal, last_observation
    )
    if resolved_observation is not None:
        all_steps.extend(resolver_steps)
        last_observation = resolved_observation

    # Construir el prompt para el LLM de respuesta final
    url = last_observation.url or ""
    title = last_observation.title or ""
    visible = last_observation.visible_text_excerpt or ""

    system_prompt = SYSTEM_PROMPT_ANSWER

    user_prompt = (
        f"Objetivo original del usuario:\n{goal}\n\n"
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

    return all_steps, final_answer


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
    sub_goals = _decompose_goal(goal)
    if not sub_goals:
        # Fallback de seguridad: usar el objetivo original
        sub_goals = [goal]

    # Caso simple: un solo objetivo → comportamiento actual
    if len(sub_goals) == 1:
        sub_goal = sub_goals[0]
        focus_entity = _extract_focus_entity_from_goal(sub_goal)
        
        steps, final_answer = await _run_llm_task_single(browser, sub_goal, max_steps)
        
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
        # Refuerzo de contexto al inicio de cada sub-goal
        # Si el sub-goal contiene "wikipedia", forzar contexto limpio
        context_steps: List[StepResult] = []
        if "wikipedia" in sub_goal.lower():
            # Limpiar frases comunes para construir la búsqueda
            cleanup_phrases = [
                "en wikipedia en español",
                "en la wikipedia en español",
                "en wikipedia",
                "en la wikipedia",
            ]
            query_text = sub_goal
            for phrase in cleanup_phrases:
                query_text = query_text.replace(phrase, "")
            query_text = query_text.strip() or sub_goal.strip()
            
            search_param = quote_plus(query_text)
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
        
        # Extraer focus_entity para marcado
        focus_entity = _extract_focus_entity_from_goal(sub_goal)
        
        # Ejecutar el sub-objetivo
        steps, answer = await _run_llm_task_single(browser, sub_goal, max_steps)
        
        # Combinar context_steps con steps
        all_subgoal_steps = context_steps + steps

        # Anotar en info a qué sub-objetivo pertenece cada paso
        for s in all_subgoal_steps:
            info = dict(s.info or {})
            info["sub_goal_index"] = idx
            info["sub_goal"] = sub_goal
            if focus_entity:
                info["focus_entity"] = focus_entity
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

    all_steps: List[StepResult] = []
    partial_answers: List[str] = []
    all_observations: List[BrowserObservation] = []

    # Procesar cada sub-objetivo
    for idx, sub_goal in enumerate(sub_goals):
        try:
            steps, last_obs, partial_answer = await _process_single_subgoal(
                raw_sub_goal=sub_goal,
                browser=browser,
                max_steps=max_steps,
            )
            all_steps.extend(steps)
            partial_answers.append(partial_answer)
            if last_obs:
                all_observations.append(last_obs)
        except Exception as exc:  # pragma: no cover - defensivo
            # Si falla un sub-objetivo, continuamos con los siguientes
            partial_answers.append(f"Error al procesar: {sub_goal}. Detalle: {exc}")

    # Combinar respuestas parciales
    if len(partial_answers) == 1:
        final_answer = partial_answers[0]
    else:
        # Combinar con encabezados numerados
        combined_parts = []
        for idx, answer in enumerate(partial_answers, 1):
            combined_parts.append(f"{idx}. {answer}")
        final_answer = "\n\n".join(combined_parts)

    # Obtener la última observación global (para source_url/source_title)
    last_observation: Optional[BrowserObservation] = None
    if all_observations:
        last_observation = all_observations[-1]
    else:
        # Fallback: buscar en todos los steps
        for step in reversed(all_steps):
            if step.observation is not None:
                last_observation = step.observation
                break

    if last_observation is None:
        return all_steps, final_answer, "", "", []

    # Extraer información de la fuente principal
    source_url = last_observation.url or ""
    source_title = last_observation.title or ""

    # Calcular lista de fuentes (hasta 3) desde todas las observaciones
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

