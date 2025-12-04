"""
Estrategias de contexto por dominio para el agente de navegación web.
v2.0.0: Sistema pluggable que separa la lógica específica de dominio del core del agente.

Cada estrategia encapsula:
- Cómo detectar si un objetivo aplica a ese dominio
- Cómo reorientar el navegador al contexto adecuado
- Cómo verificar si el objetivo está satisfecho en una observación
"""

from abc import ABC, abstractmethod
from typing import Optional, List
import re
import unicodedata
from urllib.parse import quote_plus, urlparse, parse_qs

from backend.shared.models import BrowserAction, BrowserObservation
from backend.config import DEFAULT_IMAGE_SEARCH_URL_TEMPLATE, DEFAULT_CAE_BASE_URL


class ContextStrategy(ABC):
    """
    Interfaz base para estrategias de contexto por dominio.
    Cada estrategia maneja un tipo específico de objetivo (Wikipedia, imágenes, etc.).
    """
    
    @abstractmethod
    def goal_applies(self, goal: str, focus_entity: Optional[str]) -> bool:
        """
        Determina si esta estrategia aplica al objetivo dado.
        
        Args:
            goal: Texto del objetivo
            focus_entity: Entidad focal (opcional)
            
        Returns:
            True si esta estrategia debe manejar este objetivo
        """
        pass
    
    @abstractmethod
    async def ensure_context(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str] = None,
    ) -> Optional[BrowserAction]:
        """
        Asegura que el navegador esté en el contexto adecuado para este tipo de objetivo.
        Devuelve una BrowserAction si se necesita reorientación, None en caso contrario.
        
        Args:
            goal: Texto del objetivo
            observation: Observación actual del navegador (puede ser None)
            focus_entity: Entidad focal (opcional)
            
        Returns:
            BrowserAction si se necesita navegación, None si ya estamos en el contexto correcto
        """
        pass
    
    @abstractmethod
    def is_goal_satisfied(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str],
    ) -> bool:
        """
        Verifica si el objetivo está satisfecho en la observación actual.
        
        Args:
            goal: Texto del objetivo
            observation: Observación actual del navegador
            focus_entity: Entidad focal (opcional)
            
        Returns:
            True si el objetivo está satisfecho, False en caso contrario
        """
        pass


class WikipediaContextStrategy(ContextStrategy):
    """
    Estrategia para objetivos relacionados con Wikipedia.
    Maneja la navegación a artículos de Wikipedia y verificación de satisfacción.
    """
    
    def goal_applies(self, goal: str, focus_entity: Optional[str]) -> bool:
        """Detecta objetivos que mencionan Wikipedia."""
        text = goal.lower()
        return "wikipedia" in text
    
    async def ensure_context(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str] = None,
    ) -> Optional[BrowserAction]:
        """
        Asegura que el navegador esté en Wikipedia con el artículo correcto.
        Si ya estamos en el artículo correcto, no recarga.
        """
        current_url = observation.url if observation else None
        
        # Obtener entidad efectiva
        entity = self._get_effective_focus_entity(goal, focus_entity)
        
        if not entity:
            # Sin entidad, no podemos navegar específicamente
            return None
        
        # Si ya estamos en Wikipedia y el título contiene la entidad, no recargar
        if current_url and self._is_url_in_wikipedia(current_url) and observation and observation.title:
            title_lower = observation.title.lower()
            if entity.lower() in title_lower:
                return None
        
        # Construir URL de búsqueda de Wikipedia
        wiki_query = self._normalize_wikipedia_query(goal, focus_entity=entity)
        if wiki_query:
            search_param = quote_plus(wiki_query)
            wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
            return BrowserAction(type="open_url", args={"url": wikipedia_search_url})
        
        return None
    
    def is_goal_satisfied(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str],
    ) -> bool:
        """
        Verifica si estamos en el artículo correcto de Wikipedia.
        """
        if not observation or not observation.url:
            return False
        
        url = observation.url
        title = (observation.title or "").lower()
        goal_lower = goal.lower()
        entity_lower = (focus_entity or "").lower()
        
        # Solo aplica si el goal menciona Wikipedia y estamos en Wikipedia
        if "wikipedia" not in goal_lower or not self._is_url_in_wikipedia(url):
            return False
        
        # Si tenemos entidad, comprobamos que el título contenga la entidad
        if entity_lower:
            if entity_lower in title:
                return True
        else:
            # Sin entidad clara, aceptamos cualquier artículo que no sea una página de búsqueda
            if not self._is_wikipedia_search_url(url):
                return True
        
        return False
    
    def _is_url_in_wikipedia(self, url: Optional[str]) -> bool:
        """Verifica si la URL está en Wikipedia."""
        if not url:
            return False
        return "wikipedia.org" in url.lower()
    
    def _is_wikipedia_search_url(self, url: Optional[str]) -> bool:
        """Verifica si la URL es una página de búsqueda de Wikipedia."""
        if not url:
            return False
        url_lower = url.lower()
        return (
            "wikipedia.org/wiki/especial:buscar" in url_lower
            or "/w/index.php?search=" in url_lower
        )
    
    def _get_effective_focus_entity(self, goal: str, focus_entity: Optional[str]) -> Optional[str]:
        """
        Devuelve la entidad a usar para búsquedas / artículos de Wikipedia.
        Prioridad: focus_entity explícito > entidad extraída del goal > None
        """
        def clean_entity(entity: str) -> str:
            """Limpia palabras conectoras al inicio de la entidad."""
            entity = entity.strip()
            connectors = ["de ", "del ", "la ", "el ", "y ", "en "]
            for connector in connectors:
                if entity.lower().startswith(connector):
                    entity = entity[len(connector):].strip()
            return entity
        
        if focus_entity:
            cleaned = clean_entity(focus_entity)
            return cleaned if cleaned else None
        
        # Importar aquí para evitar dependencia circular
        from backend.agents.agent_runner import _extract_focus_entity_from_goal
        inferred = _extract_focus_entity_from_goal(goal)
        if inferred:
            cleaned = clean_entity(inferred)
            return cleaned if cleaned else None
        
        return None
    
    def _normalize_wikipedia_query(self, goal: str, focus_entity: Optional[str] = None) -> Optional[str]:
        """
        Devuelve la query de Wikipedia, siempre basada en una entidad corta.
        """
        effective = self._get_effective_focus_entity(goal, focus_entity)
        return effective


class ImageSearchContextStrategy(ContextStrategy):
    """
    Estrategia para objetivos relacionados con búsqueda de imágenes.
    Maneja la navegación a DuckDuckGo imágenes y verificación de satisfacción.
    """
    
    def goal_applies(self, goal: str, focus_entity: Optional[str]) -> bool:
        """Detecta objetivos que mencionan imágenes."""
        text = goal.lower()
        keywords = ["imagen", "imágenes", "foto", "fotos", "picture", "pictures", "image", "images"]
        return any(keyword in text for keyword in keywords)
    
    async def ensure_context(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str] = None,
    ) -> Optional[BrowserAction]:
        """
        Asegura que el navegador esté en una búsqueda de imágenes.
        Si ya estamos en búsqueda de imágenes, no recarga.
        """
        current_url = observation.url if observation else None
        
        # Si ya estamos en una URL de búsqueda de imágenes, no recargar
        if current_url and self._is_url_in_image_search(current_url):
            return None
        
        # Construir query normalizada
        image_query = self._build_image_search_query(goal, focus_entity)
        
        image_search_url = DEFAULT_IMAGE_SEARCH_URL_TEMPLATE.format(query=quote_plus(image_query))
        return BrowserAction(type="open_url", args={"url": image_search_url})
    
    def is_goal_satisfied(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str],
    ) -> bool:
        """
        Verifica si estamos en una búsqueda de imágenes con la entidad correcta.
        """
        if not observation or not observation.url:
            return False
        
        url = observation.url
        title = (observation.title or "").lower()
        
        # 1) La URL tiene que ser un buscador de imágenes (DuckDuckGo)
        if not self._is_url_in_image_search(url):
            return False
        
        # 2) Determinar la entidad relevante (focus_entity tiene prioridad)
        entity = focus_entity
        if not entity:
            # Importar aquí para evitar dependencia circular
            from backend.agents.agent_runner import _extract_focus_entity_from_goal
            entity = _extract_focus_entity_from_goal(goal)
        
        entity = entity.strip() if entity else None
        
        # 3) Si hay focus_entity, validar que la query contiene la entidad normalizada
        if entity:
            # Normalizar entidad para comparación
            entity_normalized = self._normalize_text_for_comparison(entity)
            if not entity_normalized:
                return False
            
            # Extraer query de la URL
            try:
                parsed = urlparse(url)
                query_params = parse_qs(parsed.query)
                q_value = query_params.get('q', [''])[0]
                # Decodificar espacios codificados
                q_value = q_value.replace('+', ' ').replace('%20', ' ')
                q_normalized = self._normalize_text_for_comparison(q_value)
                
                # Verificar que la query normalizada contiene la entidad normalizada
                if entity_normalized in q_normalized:
                    return True
            except Exception:
                pass
            
            # Fallback: verificar en URL y título con normalización
            url_normalized = self._normalize_text_for_comparison(url)
            title_normalized = self._normalize_text_for_comparison(title)
            
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
        # con el goal descriptivo
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            q_value = query_params.get('q', [''])[0]
            q_value = q_value.replace('+', ' ').replace('%20', ' ')
            q_normalized = self._normalize_text_for_comparison(q_value)
            
            # Extraer términos descriptivos del goal (sin verbos imperativos ni pronombres)
            goal_cleaned = self._build_image_search_query(goal, None)
            
            # Si el goal limpiado es solo "imágenes" (sin entidad), no podemos confirmar satisfacción
            if goal_cleaned.lower().strip() == "imágenes":
                return False
            
            goal_normalized = self._normalize_text_for_comparison(goal_cleaned)
            
            # Extraer palabras significativas (más de 3 caracteres, excluyendo "imagenes")
            goal_words = [w for w in goal_normalized.split() if len(w) > 3 and w != "imagenes"]
            if not goal_words:
                return False
            
            # Verificar que al menos el 70% de las palabras clave del goal aparecen en la query
            matches = sum(1 for word in goal_words if word in q_normalized)
            if matches >= max(2, len(goal_words) * 0.7):
                return True
        except Exception:
            pass
        
        return False
    
    def _is_url_in_image_search(self, url: Optional[str]) -> bool:
        """Verifica si la URL está en búsqueda de imágenes."""
        if not url:
            return False
        url_lower = url.lower()
        return (
            "ia=images" in url_lower
            or "iax=images" in url_lower
            or ("duckduckgo.com" in url_lower and "/images" in url_lower)
        )
    
    def _build_image_search_query(self, goal: str, focus_entity: Optional[str]) -> str:
        """
        Construye una query limpia para búsquedas de imágenes.
        
        Reglas:
        - Si hay focus_entity: devolver "imágenes de {focus_entity}"
        - Si no hay focus_entity: limpiar el goal de verbos imperativos y pronombres
        """
        # Si hay focus_entity -> SIEMPRE usarla (prioridad absoluta)
        if focus_entity and focus_entity.strip():
            return f"imágenes de {focus_entity.strip()}".strip()
        
        # Si no hay focus_entity, limpiar el goal de forma exhaustiva
        text = goal.strip()
        lower = text.lower()
        
        # Convertir "fotos" a "imágenes" antes de procesar
        text = re.sub(r"\bfotos?\b", "imágenes", text, flags=re.IGNORECASE)
        text = re.sub(r"\bfotografías?\b", "imágenes", text, flags=re.IGNORECASE)
        
        # Eliminar verbos imperativos ampliados
        verbs = [
            "muéstrame", "muestrame", "muestra", "muestras", "muestren", "muestrenme",
            "enséñame", "enseñame", "ensename", "enseña", "enseñas", "enseñen", "enseñenme",
            "mira", "mirar", "ver", "veo", "vemos",
            "busca", "buscar", "búscame", "buscame", "buscas", "buscan",
            "pon", "ponme", "poner",
            "dame", "dar", "quiero ver", "quiero",
        ]
        for verb in verbs:
            pattern = rf"\b{re.escape(verb)}\s*"
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        
        # Eliminar pronombres y frases relacionadas
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
        
        # Si tras limpiar no queda nada útil, devolver "imágenes"
        if not text or len(text.strip()) < 3:
            return "imágenes"
        
        # Verificar que no queden solo pronombres comunes
        remaining_lower = text.lower().strip()
        if remaining_lower in ["él", "ella", "ellos", "ellas", "mí", "ti", "suyas", "suyos"]:
            return "imágenes"
        
        # Si el texto es exactamente "imágenes", devolver directamente
        if remaining_lower in ["imágenes", "imagenes", "imagen"]:
            return "imágenes"
        
        # Asegurar que la query empieza por "imágenes" (solo si no empieza ya con "imagen")
        text = re.sub(r"^imágenes\s+imágenes\s*", "imágenes ", text, flags=re.IGNORECASE)
        remaining_lower = text.lower().strip()
        
        starts_with_imagenes = (
            remaining_lower.startswith("imágenes") or 
            remaining_lower.startswith("imagenes") or
            remaining_lower.startswith("imagen ")
        )
        
        if not starts_with_imagenes:
            text = f"imágenes {text}"
        else:
            text = re.sub(r"^imágenes\s+imágenes\s*", "imágenes ", text, flags=re.IGNORECASE)
        
        # Verificación final - si aún contiene pronombres problemáticos, devolver solo "imágenes"
        problematic_patterns = [
            r"\bél\b", r"\bella\b", r"\bsuyas\b", r"\bsuyos\b",
            r"\bde él\b", r"\bde ella\b",
        ]
        for pattern in problematic_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return "imágenes"
        
        return text.strip()
    
    def _normalize_text_for_comparison(self, s: str) -> str:
        """
        Normaliza texto para comparación robusta (case-insensitive, sin diacríticos).
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


class CAEContextStrategy(ContextStrategy):
    """
    Estrategia para objetivos relacionados con plataformas CAE (prevención de riesgos).
    Maneja la navegación a plataformas CAE y verificación de satisfacción.
    v2.1.0: Estrategia básica para plataformas tipo CAE.
    """
    
    def __init__(self, base_url: str = "https://example-cae.local", platform_name: str = "Plataforma CAE Demo"):
        """
        Inicializa la estrategia CAE con una URL base y nombre de plataforma.
        
        Args:
            base_url: URL base de la plataforma CAE
            platform_name: Nombre descriptivo de la plataforma
        """
        self.base_url = base_url.rstrip('/')
        self.platform_name = platform_name
    
    def goal_applies(self, goal: str, focus_entity: Optional[str]) -> bool:
        """
        Detecta objetivos que mencionan CAE, prevención de riesgos, o plataforma CAE.
        """
        text = goal.lower()
        keywords = [
            "cae",
            "prevención de riesgos",
            "prevencion de riesgos",
            "plataforma cae",
            "documentación cae",
            "documentacion cae",
            "entra en la plataforma",
            "revisa la documentación",
            "comprueba la documentación",
        ]
        applies = any(keyword in text for keyword in keywords)
        # v2.1.0: Logging cuando se detecta un objetivo CAE
        if applies:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"[cae-context] goal applies: {goal!r}")
        return applies
    
    async def ensure_context(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str] = None,
    ) -> Optional[BrowserAction]:
        """
        Asegura que el navegador esté en la plataforma CAE.
        Si ya estamos en el dominio correcto, no recarga.
        """
        current_url = observation.url if observation else None
        
        # Si ya estamos en el dominio correcto, no recargar
        if current_url and self._is_url_in_cae_domain(current_url):
            return None
        
        # Navegar a la URL base de la plataforma CAE
        return BrowserAction(type="open_url", args={"url": self.base_url})
    
    def is_goal_satisfied(
        self,
        goal: str,
        observation: Optional[BrowserObservation],
        focus_entity: Optional[str],
    ) -> bool:
        """
        Verifica si estamos en la plataforma CAE.
        Considera satisfecho si estamos en el dominio correcto.
        Opcionalmente, si el título/URL contiene "documentación", es un bonus.
        """
        if not observation or not observation.url:
            return False
        
        url = observation.url
        
        # Verificar que estamos en el dominio CAE
        if not self._is_url_in_cae_domain(url):
            return False
        
        # Opcional: si el título contiene "documentación" o similar, es un bonus
        # pero no es estrictamente necesario para considerar satisfecho
        title = (observation.title or "").lower()
        if "documentación" in title or "documentacion" in title or "documentation" in title:
            return True
        
        # Si estamos en el dominio correcto, consideramos satisfecho
        # (aunque no estemos específicamente en documentación)
        return True
    
    def _is_url_in_cae_domain(self, url: Optional[str]) -> bool:
        """Verifica si la URL pertenece al dominio de la plataforma CAE."""
        if not url:
            return False
        
        # Extraer el dominio de base_url
        try:
            from urllib.parse import urlparse
            base_parsed = urlparse(self.base_url)
            base_domain = base_parsed.netloc.lower()
            
            current_parsed = urlparse(url)
            current_domain = current_parsed.netloc.lower()
            
            # Verificar que el dominio coincide (o es un subdominio)
            return current_domain == base_domain or current_domain.endswith('.' + base_domain)
        except Exception:
            # Fallback: verificar si base_url está en la URL
            return self.base_url.lower() in url.lower()


def build_context_strategies(strategy_names: Optional[List[str]] = None, cae_base_url: Optional[str] = None) -> List[ContextStrategy]:
    """
    Construye una lista de estrategias de contexto basándose en nombres simbólicos.
    
    Args:
        strategy_names: Lista de nombres de estrategias ("wikipedia", "images", "cae", etc.)
                       Si es None, devuelve DEFAULT_CONTEXT_STRATEGIES
        cae_base_url: URL base para CAEContextStrategy (opcional, usa default si no se proporciona)
    
    Returns:
        Lista de instancias de ContextStrategy en el orden especificado
    """
    if strategy_names is None:
        return DEFAULT_CONTEXT_STRATEGIES.copy()
    
    strategies = []
    strategy_map = {
        "wikipedia": WikipediaContextStrategy,
        "images": ImageSearchContextStrategy,
        "cae": lambda: CAEContextStrategy(base_url=cae_base_url or DEFAULT_CAE_BASE_URL),
    }
    
    for name in strategy_names:
        name_lower = name.lower()
        if name_lower in strategy_map:
            if name_lower == "cae":
                strategies.append(strategy_map[name_lower]())
            else:
                strategies.append(strategy_map[name_lower]())
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[context-strategies] Unknown strategy name: {name}, skipping")
    
    return strategies


# Registro de estrategias disponibles (orden importa: imágenes tiene prioridad sobre Wikipedia)
DEFAULT_CONTEXT_STRATEGIES = [
    ImageSearchContextStrategy(),  # Prioridad 1: imágenes
    WikipediaContextStrategy(),   # Prioridad 2: Wikipedia
]

