import json
from typing import List

from openai import AsyncOpenAI

from backend.shared.models import BrowserAction, BrowserObservation, StepResult
from backend.config import (
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_MODEL,
    DEFAULT_SEARCH_BASE_URL,
    DEFAULT_IMAGE_SEARCH_URL_TEMPLATE,
)


ALLOWED_ACTION_TYPES = {
    "open_url",
    "click_text",
    "fill_input",
    "press_key",
    "accept_cookies",
    "wait",
    "noop",
    "stop",
}

SYSTEM_PROMPT = (
    "You are the navigation planner for the local web agent CometLocal.\n"
    "You NEVER browse the web yourself.\n"
    "You only decide the NEXT ACTION for a real browser controlled by another component.\n"
    "You must ALWAYS respond with a single JSON object with fields: `type` and `args`.\n"
    "Allowed action types: "
    + ", ".join(sorted(ALLOWED_ACTION_TYPES))
    + ".\n"
    "\n"
    "FORMAT OF INPUT:\n"
    "You receive an observation with:\n"
    "- url: The current page URL\n"
    "- title: The page title\n"
    "- visible_text_excerpt: A text excerpt of what's visible on the page\n"
    "- clickable_texts: List of clickable text elements on the page\n"
    "- input_hints: List of input field hints/placeholders\n"
    "\n"
    "FORMAT OF OUTPUT:\n"
    "You must return a single JSON object (BrowserAction) with:\n"
    "- type: One of the allowed action types\n"
    "- args: A dictionary with action-specific parameters\n"
    "  * For 'open_url': args={'url': 'https://...'}\n"
    "  * For 'click_text': args={'text': 'exact clickable text'}\n"
    "  * For 'fill_input': args={'text': 'text to fill', 'hint': 'input hint'}\n"
    "  * For 'press_key': args={'key': 'Enter' or other key}\n"
    "  * For 'accept_cookies': args={}\n"
    "  * For 'wait': args={}\n"
    "  * For 'noop': args={}\n"
    "  * For 'stop': args={}\n"
    "\n"
    "GENERAL RULES:\n"
    "IMPORTANT: The default search engine is DuckDuckGo (https://duckduckgo.com).\n"
    "When the user's goal mentions images, photos, or pictures, use DuckDuckGo Images search.\n"
    "For image searches, use the URL format: https://duckduckgo.com/?q={query}&ia=images&iax=images\n"
    "If you are unsure, or the page is a CAPTCHA or an 'unusual traffic' warning, respond with type `stop`.\n"
    "\n"
    "SPECIAL RULES FOR WIKIPEDIA:\n"
    "If the goal mentions 'wikipedia' or the current URL contains 'wikipedia.org', apply these special rules:\n"
    "\n"
    "1) Wikipedia homepage or generic page:\n"
    "   - If the URL contains 'wikipedia.org' but does NOT contain '/wiki/' nor 'Especial:Buscar'\n"
    "     (for example, the homepage), then:\n"
    "     * Locate the internal Wikipedia search box.\n"
    "       - Usually the placeholder or input_hint includes 'Buscar en Wikipedia' or 'search'.\n"
    "     * Use a 'fill_input' action to write the main term from the goal\n"
    "       (for example 'Ada Lovelace') in the search box.\n"
    "     * Then, use 'press_key' with 'Enter' to launch the search.\n"
    "\n"
    "2) 'Especial:Buscar' page (Wikipedia search results):\n"
    "   - If the URL contains 'Especial:Buscar' or the visible text indicates 'Resultados de la búsqueda':\n"
    "     * You must examine 'clickable_texts'.\n"
    "     * Look for the link that most closely resembles the main term from the goal. Examples:\n"
    "       - Goal: 'información sobre Ada Lovelace en Wikipedia'\n"
    "         → look for a clickable text similar to 'Ada Lovelace'.\n"
    "     * If you find a link very similar to the main term:\n"
    "       - Use the 'click_text' action with that exact text.\n"
    "     * If you don't find anything sufficiently similar:\n"
    "       - You can refine the search using the internal search box again (fill_input + press_key).\n"
    "\n"
    "3) Wikipedia article page:\n"
    "   - If the URL contains '/wiki/' and does NOT contain ':' (to avoid special pages like 'Wikipedia:LoQueSea')\n"
    "     and the page title or initial visible text clearly mentions the main term from the goal:\n"
    "     * Consider that you have already reached the correct article.\n"
    "     * In this case, normally the best action is 'stop'.\n"
    "\n"
    "4) General preferences within Wikipedia:\n"
    "   - Avoid navigating to external sites while the goal is 'en Wikipedia'.\n"
    "   - If by error you end up outside wikipedia.org, try to return using the search box again\n"
    "     or by opening directly 'https://es.wikipedia.org' or a Wikipedia search.\n"
    "\n"
    "Remember: You must ALWAYS return a single action in JSON format (BrowserAction), as already defined.\n"
    "Do not include any explanation, only valid JSON."
)


class LLMPlanner:
    """Planner that uses a chat-based LLM (via LM Studio) to decide the next BrowserAction."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=LLM_API_BASE,
            api_key=LLM_API_KEY,
        )

    async def next_action(
        self,
        goal: str,
        observation: BrowserObservation,
        history: List[StepResult],
    ) -> BrowserAction:
        # Build history summary
        history_lines: List[str] = []
        for idx, step in enumerate(history[-5:]):
            action_type = step.last_action.type if step.last_action else "unknown"
            error = step.error or ""
            if error:
                history_lines.append(f"Step {idx}: action={action_type}, error={error}")
            else:
                history_lines.append(f"Step {idx}: action={action_type}, ok")

        history_block = "\n".join(history_lines) if history_lines else "(no previous steps)"

        clickable_block = "\n".join(f"- {t}" for t in observation.clickable_texts)
        input_block = "\n".join(f"- {h}" for h in observation.input_hints)

        # Check if goal mentions images/photos/pictures
        goal_lower = goal.lower()
        is_image_search = any(
            keyword in goal_lower
            for keyword in ["imagen", "imágenes", "foto", "fotos", "picture", "pictures", "image", "images"]
        )

        # Build search URL hint
        if is_image_search:
            # Extract query from goal (simple heuristic: remove image-related words)
            query = goal.strip()
            search_url_hint = f"For image search, use: {DEFAULT_IMAGE_SEARCH_URL_TEMPLATE.format(query=query)}"
        else:
            search_url_hint = f"Default search engine: {DEFAULT_SEARCH_BASE_URL}"

        user_content = f"""GOAL:
{goal}

{search_url_hint}

CURRENT PAGE:
URL: {observation.url}
TITLE: {observation.title}

VISIBLE_TEXT_EXCERPT:
{observation.visible_text_excerpt}

CLICKABLE_TEXTS:
{clickable_block}

INPUT_HINTS:
{input_block}

HISTORY (last steps):
{history_block}

Decide ONLY ONE next action as a JSON object with fields `type` and `args`.
"""

        try:
            response = await self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
        except Exception:
            # On any communication error, stop safely
            return BrowserAction(type="stop", args={})

        # Try to parse JSON
        try:
            obj = json.loads(content)
            if not isinstance(obj, dict):
                raise ValueError("LLM response is not a JSON object")
            action_type = obj.get("type", "stop")
            args = obj.get("args", {}) or {}
            if action_type not in ALLOWED_ACTION_TYPES:
                action_type = "stop"
            if not isinstance(args, dict):
                args = {}
            return BrowserAction(type=action_type, args=args)
        except Exception:
            # Fallback to stop on any parsing/validation problem
            return BrowserAction(type="stop", args={})

