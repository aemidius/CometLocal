from typing import List, Optional, Tuple, Dict, Any
import re
import time
import logging
import unicodedata
from dataclasses import dataclass, field
from collections import defaultdict
from urllib.parse import quote_plus, urlparse, parse_qs

from openai import AsyncOpenAI

from backend.browser.browser import BrowserController
from backend.shared.models import BrowserAction, BrowserObservation, StepResult, SourceInfo
from backend.planner.simple_planner import SimplePlanner
from backend.planner.llm_planner import LLMPlanner
from backend.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, DEFAULT_IMAGE_SEARCH_URL_TEMPLATE

logger = logging.getLogger(__name__)


class EarlyStopReason:
    """
    Constantes centralizadas para los motivos de early-stop.
    v1.4.8: Centralización para evitar typos y facilitar mantenimiento.
    """
    GOAL_SATISFIED_ON_INITIAL_PAGE = "goal_satisfied_on_initial_page"
    GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM = "goal_satisfied_after_ensure_context_before_llm"
    GOAL_SATISFIED_AFTER_ACTION = "goal_satisfied_after_action"
    GOAL_SATISFIED_AFTER_REORIENTATION = "goal_satisfied_after_reorientation"


@dataclass
class SubGoalMetrics:
    """
    Métricas de un sub-objetivo individual.
    v1.5.0: Estructura para almacenar métricas por sub-objetivo.
    """
    goal: str
    focus_entity: Optional[str]
    goal_type: str  # "wikipedia", "images", "other"
    steps_taken: int
    early_stop_reason: Optional[str]  # EarlyStopReason.* o None
    elapsed_seconds: float
    success: bool


class AgentMetrics:
    """
    Recolecta y agrega métricas de ejecución del agente.
    v1.5.0: Infraestructura de observabilidad para medir eficiencia y patrones.
    """
    def __init__(self):
        self.sub_goals: List[SubGoalMetrics] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self):
        """Marca el inicio de la ejecución completa."""
        self.start_time = time.monotonic()
    
    def finish(self):
        """Marca el fin de la ejecución completa."""
        self.end_time = time.monotonic()
    
    def add_subgoal_metrics(
        self,
        goal: str,
        focus_entity: Optional[str],
        goal_type: str,
        steps_taken: int,
        early_stop_reason: Optional[str],
        elapsed_seconds: float,
        success: bool,
    ):
        """
        Añade métricas de un sub-objetivo.
        
        Args:
            goal: Texto del sub-objetivo
            focus_entity: Entidad focal (si existe)
            goal_type: Tipo de objetivo ("wikipedia", "images", "other")
            steps_taken: Número de pasos ejecutados
            early_stop_reason: Razón de early-stop (EarlyStopReason.*) o None
            elapsed_seconds: Tiempo transcurrido en segundos
            success: True si terminó exitosamente (early-stop por objetivo cumplido)
        """
        metrics = SubGoalMetrics(
            goal=goal,
            focus_entity=focus_entity,
            goal_type=goal_type,
            steps_taken=steps_taken,
            early_stop_reason=early_stop_reason,
            elapsed_seconds=elapsed_seconds,
            success=success,
        )
        self.sub_goals.append(metrics)
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Genera un resumen serializable de todas las métricas.
        
        Returns:
            Dict con:
            - sub_goals: Lista de métricas por sub-objetivo
            - summary: Resumen agregado (totales, ratios, conteos)
        """
        total_sub_goals = len(self.sub_goals)
        total_steps = sum(m.steps_taken for m in self.sub_goals)
        total_time = sum(m.elapsed_seconds for m in self.sub_goals)
        
        # Conteo por early_stop_reason
        early_stop_counts: Dict[str, int] = defaultdict(int)
        for m in self.sub_goals:
            reason = m.early_stop_reason or "none"
            early_stop_counts[reason] += 1
        
        # Conteo por goal_type
        goal_type_counts: Dict[str, int] = defaultdict(int)
        goal_type_success: Dict[str, int] = defaultdict(int)
        for m in self.sub_goals:
            goal_type_counts[m.goal_type] += 1
            if m.success:
                goal_type_success[m.goal_type] += 1
        
        # Ratios de éxito por goal_type
        goal_type_success_ratio: Dict[str, float] = {}
        for goal_type, total in goal_type_counts.items():
            success_count = goal_type_success[goal_type]
            ratio = success_count / total if total > 0 else 0.0
            goal_type_success_ratio[goal_type] = round(ratio, 3)
        
        # Tiempo total (si se marcó inicio/fin)
        execution_time = None
        if self.start_time is not None and self.end_time is not None:
            execution_time = round(self.end_time - self.start_time, 3)
        
        # Serializar sub_goals
        sub_goals_data = []
        for m in self.sub_goals:
            sub_goals_data.append({
                "goal": m.goal,
                "focus_entity": m.focus_entity,
                "goal_type": m.goal_type,
                "steps_taken": m.steps_taken,
                "early_stop_reason": m.early_stop_reason,
                "elapsed_seconds": round(m.elapsed_seconds, 3),
                "success": m.success,
            })
        
        return {
            "sub_goals": sub_goals_data,
            "summary": {
                "total_sub_goals": total_sub_goals,
                "total_steps": total_steps,
                "total_time_seconds": round(total_time, 3),
                "execution_time_seconds": execution_time,
                "early_stop_counts": dict(early_stop_counts),
                "goal_type_counts": dict(goal_type_counts),
                "goal_type_success_ratio": goal_type_success_ratio,
            }
        }


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


def _infer_goal_type(goal: str) -> str:
    """
    Infiere el tipo de objetivo basándose en el contenido del goal.
    v1.5.0: Helper para clasificar objetivos en "wikipedia", "images", o "other".
    """
    goal_lower = goal.lower()
    if _goal_mentions_wikipedia(goal):
        return "wikipedia"
    elif _goal_mentions_images(goal):
        return "images"
    else:
        return "other"


def _extract_sources_from_steps(steps: List[StepResult]) -> List[Dict[str, Any]]:
    """
    Extrae fuentes únicas de una lista de StepResult.
    v1.6.0: Helper para agrupar fuentes por sub-goal.
    """
    seen_urls = set()
    sources = []
    
    for step in steps:
        if not step.observation or not step.observation.url:
            continue
        
        url = step.observation.url
        if url in seen_urls:
            continue
        
        seen_urls.add(url)
        title = step.observation.title or ""
        
        # Inferir goal_type de la URL
        goal_type = "other"
        if "wikipedia.org" in url.lower():
            goal_type = "wikipedia"
        elif "duckduckgo.com" in url.lower() and ("ia=images" in url.lower() or "iax=images" in url.lower()):
            goal_type = "images"
        
        sources.append({
            "url": url,
            "title": title,
            "goal_type": goal_type,
        })
    
    return sources


def _build_final_answer(
    original_goal: str,
    sub_goals: List[str],
    sub_goal_answers: List[str],
    all_steps: List[StepResult],
    agent_metrics: Optional[AgentMetrics] = None,
) -> Dict[str, Any]:
    """
    Construye una estructura de respuesta final enriquecida.
    v1.6.0: Estructura mejorada con secciones por sub-goal, fuentes y métricas.
    
    Returns:
        Dict con:
        - answer_text: texto final estructurado en español
        - sections: lista de secciones por sub-goal
        - sources: lista global de fuentes deduplicadas
        - metrics_summary: resumen de métricas (si disponible)
    """
    # Agrupar steps por sub_goal_index
    steps_by_subgoal: Dict[int, List[StepResult]] = defaultdict(list)
    for step in all_steps:
        sub_goal_idx = step.info.get("sub_goal_index")
        if sub_goal_idx is not None:
            steps_by_subgoal[sub_goal_idx].append(step)
        else:
            # Si no tiene índice, asignar al primero (caso de un solo sub-goal)
            steps_by_subgoal[1].append(step)
    
    # Construir secciones por sub-goal
    sections = []
    all_sources_dict: Dict[str, Dict[str, Any]] = {}  # url -> source info
    
    for idx, (sub_goal, answer) in enumerate(zip(sub_goals, sub_goal_answers), start=1):
        # Obtener steps de este sub-goal
        sub_goal_steps = steps_by_subgoal.get(idx, [])
        
        # Extraer fuentes de este sub-goal
        sub_goal_sources = _extract_sources_from_steps(sub_goal_steps)
        
        # Obtener información del sub-goal desde los steps o inferirla
        focus_entity = None
        goal_type = _infer_goal_type(sub_goal)
        
        # Buscar focus_entity en los steps
        for step in sub_goal_steps:
            if step.info and step.info.get("focus_entity"):
                focus_entity = step.info["focus_entity"]
                break
        
        # Si no hay focus_entity, intentar extraerla del sub_goal
        if not focus_entity:
            focus_entity = _extract_focus_entity_from_goal(sub_goal)
        
        # Construir sección
        section = {
            "index": idx,
            "sub_goal": sub_goal,
            "answer": answer.strip(),
            "goal_type": goal_type,
            "focus_entity": focus_entity,
            "sources": sub_goal_sources,
        }
        sections.append(section)
        
        # Agregar fuentes al diccionario global (deduplicar por URL)
        for source in sub_goal_sources:
            url = source["url"]
            if url not in all_sources_dict:
                all_sources_dict[url] = {
                    "url": url,
                    "title": source["title"],
                    "goal_type": source["goal_type"],
                    "sub_goals": [],
                }
            # Añadir este sub-goal a la lista si no está ya
            if idx not in all_sources_dict[url]["sub_goals"]:
                all_sources_dict[url]["sub_goals"].append(idx)
    
    # Convertir diccionario de fuentes a lista
    all_sources = list(all_sources_dict.values())
    
    # Construir texto final estructurado
    answer_parts = []
    
    # Resumen global breve
    if len(sub_goals) > 1:
        answer_parts.append(f"He completado {len(sub_goals)} sub-objetivos relacionados con tu petición.")
    else:
        answer_parts.append("He completado tu petición.")
    
    answer_parts.append("")  # Línea en blanco
    
    # Secciones por sub-goal
    for section in sections:
        idx = section["index"]
        sub_goal = section["sub_goal"]
        answer = section["answer"]
        goal_type = section["goal_type"]
        focus_entity = section.get("focus_entity")
        
        # Título de la sección
        if goal_type == "wikipedia" and focus_entity:
            section_title = f"{idx}. Sobre {focus_entity} (Wikipedia)"
        elif goal_type == "images" and focus_entity:
            section_title = f"{idx}. Imágenes de {focus_entity}"
        elif goal_type == "images":
            section_title = f"{idx}. Imágenes"
        else:
            section_title = f"{idx}. {sub_goal}"
        
        answer_parts.append(section_title)
        answer_parts.append(answer)
        
        # Mencionar fuentes principales (sin URLs completas)
        sources = section["sources"]
        if sources:
            source_domains = set()
            source_titles = []
            for source in sources[:2]:  # Máximo 2 fuentes principales
                url = source["url"]
                title = source.get("title", "")
                
                # Extraer dominio
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc.replace("www.", "")
                    if domain:
                        source_domains.add(domain)
                except Exception:
                    pass
                
                if title and title not in source_titles:
                    source_titles.append(title)
            
            if source_domains or source_titles:
                source_text = "Fuentes: "
                if source_titles:
                    source_text += ", ".join(source_titles[:2])
                elif source_domains:
                    source_text += ", ".join(sorted(source_domains)[:2])
                answer_parts.append(source_text)
        
        answer_parts.append("")  # Línea en blanco entre secciones
    
    answer_text = "\n".join(answer_parts).strip()
    
    # Obtener métricas si están disponibles
    metrics_summary = None
    if agent_metrics:
        metrics_summary = agent_metrics.to_summary_dict()
    
    return {
        "answer_text": answer_text,
        "sections": sections,
        "sources": all_sources,
        "metrics_summary": metrics_summary,
    }


def _goal_mentions_pronoun(goal: str) -> bool:
    """
    Devuelve True si el objetivo contiene pronombres de tercera persona
    que suelen referirse a una entidad mencionada antes.
    
    v1.4.3: Función auxiliar para detectar pronombres en el goal.
    """
    lower = goal.lower()
    pronouns = [
        " él", " ella", " ellos", " ellas",
        " su ", " sus ", " suyo", " suya", " suyos", " suyas",
    ]
    padded = f" {lower} "
    return any(p in padded for p in pronouns)


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
    v1.4.1: Performance hotfix - avoid unnecessary reloads if already in correct context.
    """
    # v1.4: Si observation es None, tratamos como contexto desconocido
    current_url = observation.url if observation else None
    
    # PRIORIDAD 1 (v1.2): Image search - tiene prioridad sobre Wikipedia
    # v1.4.1: No recargar si ya estamos en búsqueda de imágenes
    # v1.4.5: Si hay focus_entity, usar directamente sin _normalize_image_query
    if _goal_mentions_images(goal):
        # v1.4.1: Si ya estamos en una URL de búsqueda de imágenes, no recargar
        if current_url and _is_url_in_image_search(current_url):
            return None
        
        # v1.4.7: Usar helper para construir query normalizada
        image_query = _build_image_search_query(goal, focus_entity)
        
        # v1.4.7: Logging para diagnóstico
        logger.info(
            "[image-query] goal=%r focus_entity=%r query=%r",
            goal,
            focus_entity,
            image_query,
        )
        
        image_search_url = DEFAULT_IMAGE_SEARCH_URL_TEMPLATE.format(query=quote_plus(image_query))
        return BrowserAction(type="open_url", args={"url": image_search_url})
    
    # PRIORIDAD 2: Wikipedia con entidad específica
    # Solo aplica si NO menciona imágenes (ya manejado en PRIORIDAD 1)
    # v1.4.1: No recargar si ya estamos en el artículo correcto de Wikipedia
    if _goal_mentions_wikipedia(goal):
        # v1.4: Usar _get_effective_focus_entity para obtener entidad
        entity = _get_effective_focus_entity(goal, focus_entity)
        
        if entity:
            # v1.4.1: Si ya estamos en Wikipedia y el título contiene la entidad, no recargar
            if current_url and _is_url_in_wikipedia(current_url) and observation and observation.title:
                title_lower = observation.title.lower()
                if entity.lower() in title_lower:
                    return None
            
            # v1.4: Construir URL de búsqueda
            wiki_query = _normalize_wikipedia_query(goal, focus_entity=entity)
            if wiki_query:
                search_param = quote_plus(wiki_query)
                wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
                return BrowserAction(type="open_url", args={"url": wikipedia_search_url})
    
    # PRIORIDAD 3: OBLIGATORY CONTEXT: Wikipedia (sin entidad específica o fallback)
    # v1.4: Solo forzamos búsqueda si tenemos una entidad clara
    # v1.4.1: No recargar si ya estamos en Wikipedia con el título correcto
    if _goal_requires_wikipedia(goal):
        # v1.4: Usar _normalize_wikipedia_query que solo devuelve entidades o None
        wiki_query = _normalize_wikipedia_query(goal, focus_entity=focus_entity)
        
        # Si no hay entidad, NO forzamos búsqueda (dejamos que el agente navegue normalmente)
        if wiki_query is None:
            return None
        
        # v1.4.1: Si ya estamos en Wikipedia y el título coincide, no recargar
        if current_url and _is_url_in_wikipedia(current_url) and observation and observation.title:
            title_lower = observation.title.lower()
            if (
                wiki_query.lower() in title_lower
                or (focus_entity and focus_entity.lower() in title_lower)
            ):
                return None
        
        # v1.4: Construir URL de búsqueda
        search_param = quote_plus(wiki_query)
        wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
        return BrowserAction(type="open_url", args={"url": wikipedia_search_url})
    
    # No reorientation needed
    return None


def _goal_is_satisfied(
    goal: str,
    observation: Optional[BrowserObservation],
    focus_entity: Optional[str],
) -> bool:
    """
    Devuelve True si, para objetivos sencillos de Wikipedia o de imágenes,
    la página actual cumple razonablemente el objetivo del sub-goal.
    No intenta cubrir todos los casos complejos.
    
    v1.4.5: Helper para early-stop por sub-objetivo.
    """
    if not observation or not observation.url:
        return False

    url = observation.url
    title = (observation.title or "").lower()
    goal_lower = goal.lower()
    entity_lower = (focus_entity or "").lower()

    # Caso 1: objetivos de Wikipedia (quién fue X, info en Wikipedia, etc.)
    if "wikipedia" in goal_lower and _is_url_in_wikipedia(url):
        # Si tenemos entidad, comprobamos que el título contenga la entidad
        if entity_lower:
            if entity_lower in title:
                return True
        else:
            # Sin entidad clara, aceptamos cualquier artículo que no sea una página de búsqueda
            if not _is_wikipedia_search_url(url):
                return True

    # Caso 2: objetivos de imágenes
    # v1.4.8: Reforzado para detectar entidad en URL codificada o título con normalización robusta
    if _goal_mentions_images(goal):
        # 1) La URL tiene que ser un buscador de imágenes (DuckDuckGo)
        if not _is_url_in_image_search(url):
            return False
        
        # 2) Determinar la entidad relevante (focus_entity tiene prioridad)
        entity = focus_entity
        if not entity:
            # Intentar extraer del goal como fallback
            entity = _extract_focus_entity_from_goal(goal)
        
        entity = entity.strip() if entity else None
        
        # 3) Si hay focus_entity, validar que la query contiene la entidad normalizada
        if entity:
            # Normalizar entidad para comparación
            entity_normalized = _normalize_text_for_comparison(entity)
            if not entity_normalized:
                return False
            
            # Extraer query de la URL
            try:
                parsed = urlparse(url)
                query_params = parse_qs(parsed.query)
                q_value = query_params.get('q', [''])[0]
                # Decodificar espacios codificados
                q_value = q_value.replace('+', ' ').replace('%20', ' ')
                q_normalized = _normalize_text_for_comparison(q_value)
                
                # Verificar que la query normalizada contiene la entidad normalizada
                if entity_normalized in q_normalized:
                    return True
            except Exception:
                # Si falla el parsing, intentar verificación directa en URL
                pass
            
            # Fallback: verificar en URL y título con normalización
            url_normalized = _normalize_text_for_comparison(url)
            title_normalized = _normalize_text_for_comparison(title)
            
            # Verificar variantes codificadas en URL
            entity_variants = [
                entity_normalized,
                entity_normalized.replace(" ", "+"),
                entity_normalized.replace(" ", "%20"),
                entity_normalized.replace(" ", "_"),
            ]
            
            for variant in entity_variants:
                if variant in url_normalized:
                    return True
            
            if entity_normalized in title_normalized:
                return True
            
            return False
        
        # 4) Si no hay focus_entity, ser conservador: solo satisfecho si la query coincide razonablemente
        # con el goal descriptivo (ej: "imágenes de computadoras antiguas")
        # v1.4.8: Ser más estricto para evitar falsos positivos
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            q_value = query_params.get('q', [''])[0]
            q_value = q_value.replace('+', ' ').replace('%20', ' ')
            q_normalized = _normalize_text_for_comparison(q_value)
            
            # Extraer términos descriptivos del goal (sin verbos imperativos ni pronombres)
            goal_cleaned = _build_image_search_query(goal, None)
            
            # Si el goal limpiado es solo "imágenes" (sin entidad), no podemos confirmar satisfacción
            if goal_cleaned.lower().strip() == "imágenes":
                return False
            
            goal_normalized = _normalize_text_for_comparison(goal_cleaned)
            
            # Extraer palabras significativas (más de 3 caracteres, excluyendo "imagenes")
            goal_words = [w for w in goal_normalized.split() if len(w) > 3 and w != "imagenes"]
            if not goal_words:
                # Si no hay palabras significativas, no podemos confirmar
                return False
            
            # Verificar que al menos el 70% de las palabras clave del goal aparecen en la query
            # y que hay al menos 2 palabras coincidentes (para evitar coincidencias accidentales)
            matches = sum(1 for word in goal_words if word in q_normalized)
            if matches >= max(2, len(goal_words) * 0.7):  # Al menos 70% de coincidencia y mínimo 2 palabras
                return True
        except Exception:
            pass
        
        # Si no se puede asegurar, devolver False y dejar que el LLM actúe
        return False

    return False


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
    """
    Runs an agent loop on top of BrowserController using the LLMPlanner.
    v1.5.0: Calcula métricas de ejecución y las añade a StepResult.info["metrics_subgoal"].
    """
    planner = LLMPlanner()
    steps: List[StepResult] = []
    
    # v1.5.0: Iniciar medición de tiempo
    start_time = time.monotonic()
    
    # v1.4: Calcular focus_entity si no se proporciona
    if focus_entity is None:
        focus_entity = _extract_focus_entity_from_goal(goal)

    # v1.4.7: Reordenar flujo de early-stop para evitar doble carga
    # 1) Observación inicial sin tocar nada
    early_stop_reason: Optional[str] = None
    try:
        initial_observation = await browser.get_observation()
        
        # Si reset_context, ignorar la observación inicial para forzar navegación
        if reset_context:
            initial_observation = None
        
        # 2) Early-stop con el estado inicial (antes de ensure_context)
        if initial_observation and _goal_is_satisfied(goal, initial_observation, focus_entity):
            logger.info(
                "[early-stop] goal satisfied on initial page goal=%r focus_entity=%r url=%r title=%r",
                goal,
                focus_entity,
                initial_observation.url if initial_observation else None,
                initial_observation.title if initial_observation else None,
            )
            early_stop_reason = EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE
            steps.append(StepResult(
                observation=initial_observation,
                last_action=None,
                error=None,
                info={
                    "reason": early_stop_reason,
                    "focus_entity": focus_entity,
                }
            ))
            # v1.5.0: Añadir métricas antes de retornar
            elapsed = time.monotonic() - start_time
            _add_metrics_to_steps(steps, goal, focus_entity, len(steps), early_stop_reason, elapsed, success=True)
            return steps
        
        # 3) Si no está satisfecho, entonces y solo entonces llamamos ensure_context
        reorientation_action = await ensure_context(goal, initial_observation, browser, focus_entity=focus_entity)
        
        if reorientation_action:
            # Ejecutar reorientación
            error = await _execute_action(reorientation_action, browser)
            if not error:
                # Obtener nueva observación después de reorientación
                try:
                    initial_observation = await browser.get_observation()
                    steps.append(StepResult(
                        observation=initial_observation,
                        last_action=reorientation_action,
                        error=None,
                        info={}
                    ))
                except Exception:
                    # Si no podemos obtener observación, usar la anterior
                    pass
        
        # 4) Early-stop tras ensure_context, antes del primer paso del LLM
        # v1.4.8: Asegurar que se ejecuta siempre con focus_entity correcto
        if initial_observation and _goal_is_satisfied(goal, initial_observation, focus_entity):
            logger.info(
                "[early-stop] goal satisfied after ensure_context before LLM "
                "goal=%r focus_entity=%r url=%r title=%r",
                goal,
                focus_entity,
                initial_observation.url if initial_observation else None,
                initial_observation.title if initial_observation else None,
            )
            # Actualizar el último step con la razón
            early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM
            if steps:
                last_step = steps[-1]
                info = dict(last_step.info or {})
                info["reason"] = early_stop_reason
                if focus_entity:
                    info["focus_entity"] = focus_entity
                last_step.info = info
            # v1.5.0: Añadir métricas antes de retornar
            elapsed = time.monotonic() - start_time
            _add_metrics_to_steps(steps, goal, focus_entity, len(steps), early_stop_reason, elapsed, success=True)
            return steps
        
        # v1.4.8: Logging defensivo para imágenes no satisfechas
        if _goal_mentions_images(goal) and initial_observation and not _goal_is_satisfied(goal, initial_observation, focus_entity):
            logger.debug(
                "[image-goal] not satisfied yet goal=%r focus_entity=%r url=%r title=%r",
                goal,
                focus_entity,
                initial_observation.url if initial_observation else None,
                initial_observation.title if initial_observation else None,
            )
    except Exception:
        # Si hay error obteniendo la observación inicial, continuar con el bucle normal
        pass

    for step_idx in range(max_steps):
        try:
            # Get observation
            observation = await browser.get_observation()
            
            # v1.4: Si reset_context es True y es el primer paso, ignorar la observación actual
            # para forzar navegación a nuevo contexto
            if reset_context and step_idx == 0:
                observation = None

            # v1.4.1: Context reorientation layer: solo al inicio del sub-objetivo
            # v1.4.6: Si ya hicimos reorientación antes del bucle (steps no está vacío),
            # no volver a hacerla en step_idx == 0 para evitar duplicación
            reorientation_action = None
            if step_idx == 0 or observation is None:
                # v1.4.6: Solo reorientar si no se hizo antes del bucle
                # (si steps está vacío al entrar al bucle, significa que no se hizo reorientación previa)
                if len(steps) == 0 or step_idx > 0:
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
                        
                        # v1.4.5: early-stop después de reorientación si el objetivo ya está satisfecho
                        if _goal_is_satisfied(goal, observation, focus_entity):
                            early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_REORIENTATION
                            logger.info(
                                "[early-stop] goal satisfied after reorientation for goal=%r focus_entity=%r step_idx=%d url=%r title=%r",
                                goal,
                                focus_entity,
                                step_idx,
                                observation.url if observation else None,
                                observation.title if observation else None,
                            )
                            break
                    except Exception:
                        # If we can't get observation, continue with previous one
                        pass
                
                # IMPORTANT: After reorientation, continue loop without consulting LLMPlanner
                # This ensures we don't skip the reorientation step
                # v1.5: Pero si el objetivo ya está satisfecho, salimos del bucle
                if observation and _goal_is_satisfied(goal, observation, focus_entity):
                    early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_REORIENTATION
                    break
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
            
            # v1.4.5: early-stop cuando el sub-objetivo actual ya está satisfecho
            if _goal_is_satisfied(goal, observation_after, focus_entity):
                early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION
                logger.info(
                    "[early-stop] goal satisfied for goal=%r focus_entity=%r step_idx=%d url=%r title=%r",
                    goal,
                    focus_entity,
                    step_idx,
                    observation_after.url if observation_after else None,
                    observation_after.title if observation_after else None,
                )
                break

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

    # v1.5.0: Calcular métricas finales y añadirlas al último step
    elapsed = time.monotonic() - start_time
    steps_taken = len(steps)
    
    # Determinar si fue exitoso: True si terminó con early-stop por objetivo cumplido
    success = early_stop_reason is not None and early_stop_reason.startswith("goal_satisfied")
    
    # Si no hay early_stop_reason y llegamos aquí, puede ser:
    # - max_steps alcanzado
    # - error
    # - stop action sin early-stop
    if early_stop_reason is None:
        # Verificar si el último step tiene error
        if steps and steps[-1].error:
            early_stop_reason = None  # Error
        elif steps_taken >= max_steps:
            early_stop_reason = None  # Max steps alcanzado
        else:
            early_stop_reason = None  # Stop action normal
    
    _add_metrics_to_steps(steps, goal, focus_entity, steps_taken, early_stop_reason, elapsed, success)
    
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
    Descomposición de un objetivo en sub-objetivos ordenados.
    
    v1.4.4: Mejorado para reconocer múltiples conectores secuenciales y devolver
    sub-goals limpios sin arrastrar partes de otros sub-objetivos.
    
    Reglas:
    - Si no detecta conectores, devuelve [goal] tal cual.
    - Divide recursivamente por múltiples conectores secuenciales.
    - Si el objetivo original menciona "wikipedia" y alguna parte no la
      menciona, se añade " en Wikipedia" a esa parte.
    - Limpia espacios y signos de puntuación sobrantes en los extremos.
    """
    text = " ".join(goal.strip().split())
    lower = text.lower()
    
    # v1.4.4: Lista ampliada de conectores secuenciales
    CONNECTORS = [
        " y luego ",
        " y después ",
        " y despues ",
        ", luego ",
        "; luego ",
        ", después ",
        ", despues ",
        "; después ",
        "; despues ",
        " y finalmente ",
        ", y finalmente ",
        "; y finalmente ",
    ]
    
    # v1.4.4: Buscar todos los conectores y sus posiciones
    connector_positions = []
    for connector in CONNECTORS:
        start = 0
        while True:
            idx = lower.find(connector, start)
            if idx == -1:
                break
            connector_positions.append((idx, idx + len(connector), len(connector), connector))
            start = idx + 1
    
    # Si no hay conectores, devolver el objetivo tal cual
    if not connector_positions:
        sub_goals = [text] if text else []
    else:
        # Ordenar por posición de inicio
        connector_positions.sort(key=lambda x: x[0])
        
        # v1.4.4: Filtrar solapamientos (si un conector está dentro de otro, mantener solo el más largo)
        filtered_positions = []
        for i, (start, end, length, connector) in enumerate(connector_positions):
            # Verificar si este conector se solapa con alguno ya añadido
            overlaps = False
            for prev_start, prev_end, _, _ in filtered_positions:
                # Si se solapa (inicio dentro del rango anterior o fin dentro del rango anterior)
                if (prev_start <= start < prev_end) or (prev_start < end <= prev_end):
                    overlaps = True
                    break
            if not overlaps:
                filtered_positions.append((start, end, length, connector))
        
        # Ordenar de nuevo por posición de inicio
        filtered_positions.sort(key=lambda x: x[0])
        
        # Dividir el texto por los conectores encontrados
        sub_goals = []
        start = 0
        
        for pos_start, pos_end, length, connector in filtered_positions:
            # Extraer la parte antes del conector
            part = text[start:pos_start].strip()
            if part:
                sub_goals.append(part)
            start = pos_end
        
        # Añadir la parte final
        if start < len(text):
            part = text[start:].strip()
            if part:
                sub_goals.append(part)
    
    # v1.4.4: Limpiar cada sub-goal
    cleaned_sub_goals = []
    for sub in sub_goals:
        # Limpiar espacios y signos de puntuación residuales
        sub = sub.strip()
        sub = sub.strip(" ,.;")
        if sub:  # Ignorar sub-goals vacíos
            cleaned_sub_goals.append(sub)
    
    if not cleaned_sub_goals:
        return [text] if text else []
    
    # Propagar contexto de Wikipedia:
    # Si el objetivo global menciona "wikipedia" y una parte no lo menciona,
    # añade " en Wikipedia" a esa parte.
    # EXCEPCIÓN v1.2: NO propagar "en Wikipedia" a sub-goals que mencionen imágenes
    if "wikipedia" in lower:
        new_parts: List[str] = []
        for p in cleaned_sub_goals:
            if "wikipedia" not in p.lower():
                # v1.2: Si el sub-goal menciona imágenes, NO añadir "en Wikipedia"
                if not _goal_mentions_images(p):
                    p = p + " en Wikipedia"
            new_parts.append(p)
        cleaned_sub_goals = new_parts
    
    # v1.4.4: Logging para depuración
    logger.info(
        "[decompose_goal] goal=%r -> sub_goals=%r",
        goal,
        cleaned_sub_goals,
    )
    
    return cleaned_sub_goals


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


def _normalize_text_for_comparison(s: str) -> str:
    """
    Normaliza texto para comparación robusta (case-insensitive, sin diacríticos).
    v1.4.8: Helper para comparaciones en _goal_is_satisfied.
    """
    if not s:
        return ""
    # Pasar a minúsculas
    normalized = s.lower()
    # Eliminar diacríticos usando unicodedata
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Recortar espacios extra
    normalized = ' '.join(normalized.split())
    return normalized


def _build_image_search_query(goal: str, focus_entity: Optional[str]) -> str:
    """
    Construye una query limpia para búsquedas de imágenes.
    
    Reglas:
    - Si hay focus_entity: devolver "imágenes de {focus_entity}" (idioma español).
    - Si no hay focus_entity:
        - eliminar verbos tipo "muéstrame", "muestrame", "enséñame", "enseñame", "búscame", "pon", etc.
        - eliminar pronombres tipo "suyas", "suyos", "de él", "de ella"
        - convertir "fotos" a "imágenes"
        - devolver algo razonable, sin verbos imperativos.
    
    v1.4.7: Helper para normalizar queries de imágenes y evitar literales del goal.
    v1.4.8: Mejorado para cubrir más variantes de lenguaje natural en español.
    """
    # v1.4.8: Si hay focus_entity -> SIEMPRE usarla (prioridad absoluta)
    if focus_entity and focus_entity.strip():
        return f"imágenes de {focus_entity.strip()}".strip()
    
    # v1.4.8: Si no hay focus_entity, limpiar el goal de forma exhaustiva
    text = goal.strip()
    lower = text.lower()
    
    # v1.4.8: Convertir "fotos" a "imágenes" antes de procesar
    text = re.sub(r"\bfotos?\b", "imágenes", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfotografías?\b", "imágenes", text, flags=re.IGNORECASE)
    
    # v1.4.8: Eliminar verbos imperativos ampliados (con y sin tilde)
    verbs = [
        "muéstrame", "muestrame", "muestra", "muestras", "muestren", "muestrenme",
        "enséñame", "enseñame", "ensename", "enseña", "enseñas", "enseñen", "enseñenme",
        "mira", "mirar", "ver", "veo", "vemos",
        "busca", "buscar", "búscame", "buscame", "buscas", "buscan",
        "pon", "ponme", "poner",
        "dame", "dar", "quiero ver", "quiero",
    ]
    for verb in verbs:
        # Eliminar verbos al inicio o seguidos de espacio
        pattern = rf"\b{re.escape(verb)}\s*"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    
    # v1.4.8: Eliminar pronombres y frases relacionadas de forma exhaustiva
    pronouns = [
        r"\bsuyas\b", r"\bsuyos\b", r"\bsuya\b", r"\bsuyo\b",
        r"\bde él\b", r"\bde ella\b", r"\bde ellos\b", r"\bde ellas\b",
        r"\bél\b", r"\bella\b", r"\bellos\b", r"\bellas\b",
        r"\bde mí\b", r"\bde ti\b", r"\bmí\b", r"\bti\b",
    ]
    for pronoun in pronouns:
        text = re.sub(pronoun, "", text, flags=re.IGNORECASE)
    
    # Limpiar espacios múltiples y puntuación
    text = re.sub(r"\s+", " ", text).strip(" ,.;:¡!¿?")
    
    # v1.4.8: Si tras limpiar no queda nada útil o solo quedan pronombres, devolver "imágenes"
    if not text or len(text.strip()) < 3:
        return "imágenes"
    
    # Verificar que no queden solo pronombres comunes
    remaining_lower = text.lower().strip()
    if remaining_lower in ["él", "ella", "ellos", "ellas", "mí", "ti", "suyas", "suyos"]:
        return "imágenes"
    
    # Si el texto es exactamente "imágenes" (o variantes), devolver directamente
    if remaining_lower in ["imágenes", "imagenes", "imagen"]:
        return "imágenes"
    
    # Asegurar que la query empieza por "imágenes" (solo si no empieza ya con "imagen")
    # Primero, eliminar cualquier "imágenes" duplicada al inicio
    text = re.sub(r"^imágenes\s+imágenes\s*", "imágenes ", text, flags=re.IGNORECASE)
    remaining_lower = text.lower().strip()
    
    # Verificar si ya empieza con "imágenes" (con o sin tilde)
    starts_with_imagenes = (
        remaining_lower.startswith("imágenes") or 
        remaining_lower.startswith("imagenes") or
        remaining_lower.startswith("imagen ")
    )
    
    if not starts_with_imagenes:
        # Si no empieza con "imagen", añadir el prefijo
        text = f"imágenes {text}"
    else:
        # Si ya empieza con "imágenes", asegurar que no haya duplicados
        text = re.sub(r"^imágenes\s+imágenes\s*", "imágenes ", text, flags=re.IGNORECASE)
    
    # v1.4.8: Verificación final - si aún contiene pronombres problemáticos, devolver solo "imágenes"
    problematic_patterns = [
        r"\bél\b", r"\bella\b", r"\bsuyas\b", r"\bsuyos\b",
        r"\bde él\b", r"\bde ella\b",
    ]
    for pattern in problematic_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return "imágenes"
    
    return text.strip()


def _normalize_image_query(goal: str, fallback_focus: Optional[str] = None) -> str:
    """
    Normaliza la query para búsquedas de imágenes en DuckDuckGo.
    
    Prioridad:
    1. Si hay pronombres y fallback_focus -> usar siempre fallback_focus.
    2. Si hay fallback_focus -> usar fallback_focus.
    3. Entidad detectada en el propio goal.
    4. Goal limpiado de verbos imperativos comunes.
    
    v1.4: Evita duplicados "de de ..." y normaliza espacios.
    v1.4.2: Corrige uso de pronombres con fallback_focus.
    """
    text = goal.strip()
    lower = text.lower()
    
    # v1.4.2: Definir pronombres relevantes
    PRONOUN_TOKENS = [
        " su ", " sus ", " suyo", " suya", " suyos", " suyas",
        " él", " ella", " ellos", " ellas",
    ]
    
    # v1.4.2: Detectar si el objetivo contiene pronombres
    has_pronoun = any(token in f" {lower} " for token in PRONOUN_TOKENS)
    
    # v1.4.2: 1) Pronombres + focus_entity -> usar siempre la entidad
    if has_pronoun and fallback_focus:
        clean_entity = fallback_focus.strip()
        query = f"imágenes de {clean_entity}"
        # Normalizar duplicados "de de ..." y espacios múltiples
        query = query.replace("de de ", "de ")
        query = query.replace("  ", " ").strip()
        return query
    
    # v1.4.2: 2) Sin pronombres pero con focus_entity -> también preferir la entidad
    if fallback_focus:
        clean_entity = fallback_focus.strip()
        query = f"imágenes de {clean_entity}"
        # Normalizar duplicados "de de ..." y espacios múltiples
        query = query.replace("de de ", "de ")
        query = query.replace("  ", " ").strip()
        return query
    
    # 3) Entidad del propio sub-goal
    focus = _extract_focus_entity_from_goal(text)
    
    if focus:
        # Limpiar entidad de palabras conectoras
        clean_entity = focus.strip()
        # Construir query: siempre "imágenes de <entidad>"
        query = f"imágenes de {clean_entity}"
    else:
        # 4) Sin entidad clara: limpiar verbos imperativos típicos
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
                    f"({focus_entity}). Se utilizan las mejores páginas disponibles para responder igualmente.\n\n"
                )
    
    user_prompt += (
        f"Última URL visitada por el agente:\n{url}\n\n"
        f"Título de la página:\n{title}\n\n"
        "Contenido de la página (extracto del texto visible):\n"
        f"{visible}\n\n"
        "Instrucciones importantes:\n"
        "- Prioriza la información procedente de Wikipedia cuando el objetivo sea 'quién fue X' o 'información sobre X'.\n"
        "- Prioriza la información procedente de las páginas de imágenes cuando el objetivo hable de 'imágenes', 'fotos' o 'fotografías'.\n"
        "- No debes bloquear la respuesta solo porque haya otras páginas menos relevantes en el historial de pasos.\n"
        "- Ignora las páginas que claramente no estén relacionadas con la entidad del objetivo actual.\n"
        "- Indica siempre de qué página principal (URL y título) has sacado la información para tu respuesta.\n"
        "- Si realmente no encuentras ninguna fuente útil relacionada con la entidad, dilo explícitamente.\n\n"
        "Usa esta información para responder al objetivo del usuario en español."
    )
    
    # v1.4: Calcular tamaño real del prompt para logging
    prompt_len = len(system_prompt) + len(user_prompt)

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

    # v1.4: Almacenar prompt_len en el último step para logging posterior
    if steps_local:
        last_step = steps_local[-1]
        info = dict(last_step.info or {})
        info["prompt_len"] = prompt_len
        last_step.info = info

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
    
    v1.5.0: Recolecta métricas de ejecución usando AgentMetrics.
    """
    # v1.5.0: Inicializar métricas
    agent_metrics = AgentMetrics()
    agent_metrics.start()
    
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
        t0 = time.perf_counter()
        steps, final_answer = await _run_llm_task_single(
            browser, sub_goal, max_steps, focus_entity=focus_entity, reset_context=True, sub_goal_index=1
        )
        t1 = time.perf_counter()
        
        # v1.5.0: Extraer métricas del último step y añadirlas a AgentMetrics
        metrics_data = None
        for step in reversed(steps):
            if step.info and "metrics_subgoal" in step.info:
                metrics_data = step.info["metrics_subgoal"]
                break
        
        if metrics_data:
            agent_metrics.add_subgoal_metrics(
                goal=metrics_data["goal"],
                focus_entity=metrics_data.get("focus_entity"),
                goal_type=metrics_data["goal_type"],
                steps_taken=metrics_data["steps_taken"],
                early_stop_reason=metrics_data.get("early_stop_reason"),
                elapsed_seconds=metrics_data["elapsed_seconds"],
                success=metrics_data["success"],
            )
        else:
            # Fallback: calcular métricas básicas si no están en StepResult
            agent_metrics.add_subgoal_metrics(
                goal=sub_goal,
                focus_entity=focus_entity,
                goal_type=_infer_goal_type(sub_goal),
                steps_taken=len(steps),
                early_stop_reason=None,
                elapsed_seconds=t1 - t0,
                success=False,
            )
        
        # v1.5.0: Logging de métricas por sub-objetivo
        if metrics_data:
            logger.info(
                "[metrics] sub-goal idx=1 type=%s steps=%d early_stop=%s elapsed=%.2fs success=%s",
                metrics_data["goal_type"],
                metrics_data["steps_taken"],
                metrics_data.get("early_stop_reason") or "none",
                metrics_data["elapsed_seconds"],
                metrics_data["success"],
            )
        else:
            logger.info(
                "[sub-goal] idx=1 sub_goal=%r focus_entity=%r steps=%d elapsed=%.2fs",
                sub_goal,
                focus_entity,
                len(steps),
                t1 - t0,
            )
        
        # Añadir marcado de focus_entity a todos los steps
        for s in steps:
            info = dict(s.info or {})
            if focus_entity:
                info["focus_entity"] = focus_entity
            s.info = info
        
        # v1.5.0: Finalizar métricas y obtener resumen
        agent_metrics.finish()
        metrics_summary = agent_metrics.to_summary_dict()
        logger.info("[metrics] summary=%r", metrics_summary)
        
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
        
        # v1.6.0: Construir respuesta estructurada
        structured_answer = _build_final_answer(
            original_goal=goal,
            sub_goals=sub_goals,
            sub_goal_answers=[final_answer],
            all_steps=steps,
            agent_metrics=agent_metrics,
        )
        
        # v1.5.0: Añadir métricas y estructura al último step para que estén disponibles en la respuesta
        if steps:
            last_step = steps[-1]
            info = dict(last_step.info or {})
            info["metrics"] = metrics_summary
            info["structured_answer"] = structured_answer
            last_step.info = info
        
        # v1.6.0: Usar answer_text estructurado como final_answer (mantiene compatibilidad)
        final_answer = structured_answer["answer_text"]
        
        return steps, final_answer, source_url, source_title, sources

    all_steps: List[StepResult] = []
    answers: List[str] = []
    all_observations: List[BrowserObservation] = []
    
    # v1.4.3: Mantener memoria de la última entidad nombrada explícitamente
    last_named_entity: Optional[str] = global_focus_entity

    for idx, sub_goal in enumerate(sub_goals, start=1):
        # v1.4.3: Calcular sub_focus_entity con memoria de última entidad nombrada
        direct_entity = _extract_focus_entity_from_goal(sub_goal)
        
        if direct_entity:
            # Si el sub-objetivo menciona explícitamente una entidad (ej. "Charles Babbage")
            sub_focus_entity = direct_entity
            last_named_entity = direct_entity
        else:
            # No hay entidad explícita
            if _goal_mentions_pronoun(sub_goal) and last_named_entity:
                # Caso "muéstrame imágenes suyas", "de él", etc.
                sub_focus_entity = last_named_entity
            else:
                # Fallback: usar la global si existe, si no la última conocida
                sub_focus_entity = global_focus_entity or last_named_entity
        
        # v1.4.3: Logging para diagnóstico
        logger.info(
            f"[cometlocal] sub_goal_index={idx} sub_goal={sub_goal!r} focus_entity={sub_focus_entity!r}"
        )
        
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
        t0 = time.perf_counter()
        steps, answer = await _run_llm_task_single(
            browser, sub_goal, max_steps, focus_entity=sub_focus_entity, reset_context=reset_ctx, sub_goal_index=idx
        )
        t1 = time.perf_counter()
        
        # v1.5.0: Extraer métricas del último step y añadirlas a AgentMetrics
        metrics_data = None
        for step in reversed(steps):
            if step.info and "metrics_subgoal" in step.info:
                metrics_data = step.info["metrics_subgoal"]
                break
        
        if metrics_data:
            agent_metrics.add_subgoal_metrics(
                goal=metrics_data["goal"],
                focus_entity=metrics_data.get("focus_entity"),
                goal_type=metrics_data["goal_type"],
                steps_taken=metrics_data["steps_taken"],
                early_stop_reason=metrics_data.get("early_stop_reason"),
                elapsed_seconds=metrics_data["elapsed_seconds"],
                success=metrics_data["success"],
            )
            # v1.5.0: Logging de métricas por sub-objetivo
            logger.info(
                "[metrics] sub-goal idx=%d type=%s steps=%d early_stop=%s elapsed=%.2fs success=%s",
                idx,
                metrics_data["goal_type"],
                metrics_data["steps_taken"],
                metrics_data.get("early_stop_reason") or "none",
                metrics_data["elapsed_seconds"],
                metrics_data["success"],
            )
        else:
            # Fallback: calcular métricas básicas si no están en StepResult
            agent_metrics.add_subgoal_metrics(
                goal=sub_goal,
                focus_entity=sub_focus_entity,
                goal_type=_infer_goal_type(sub_goal),
                steps_taken=len(steps),
                early_stop_reason=None,
                elapsed_seconds=t1 - t0,
                success=False,
            )
            logger.info(
                "[sub-goal] idx=%d sub_goal=%r focus_entity=%r steps=%d elapsed=%.2fs",
                idx,
                sub_goal,
                sub_focus_entity,
                len(steps),
                t1 - t0,
            )
        
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

        # v1.6.0: Guardar respuesta sin numeración (la numeración se añade en _build_final_answer)
        answer = answer.strip()
        if answer:
            answers.append(answer)
        else:
            answers.append("(Sin información relevante encontrada para este sub-objetivo)")

    # v1.6.0: Construir respuesta estructurada
    agent_metrics.finish()
    metrics_summary = agent_metrics.to_summary_dict()
    logger.info("[metrics] summary=%r", metrics_summary)
    
    structured_answer = _build_final_answer(
        original_goal=goal,
        sub_goals=sub_goals,
        sub_goal_answers=answers,
        all_steps=all_steps,
        agent_metrics=agent_metrics,
    )
    
    # v1.6.0: Usar answer_text estructurado como final_answer (mantiene compatibilidad)
    final_answer = structured_answer["answer_text"]
    
    logger.info("[structured-answer] built final answer with %d sections", len(structured_answer["sections"]))
    
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

    # v1.5.0 y v1.6.0: Añadir métricas y estructura al último step para que estén disponibles en la respuesta
    if all_steps:
        last_step = all_steps[-1]
        info = dict(last_step.info or {})
        info["metrics"] = metrics_summary
        info["structured_answer"] = structured_answer
        last_step.info = info

    return all_steps, final_answer, source_url, source_title, sources

