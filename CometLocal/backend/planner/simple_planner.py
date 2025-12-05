from typing import Optional, List
from backend.shared.models import BrowserAction, BrowserObservation


class SimplePlanner:
    """
    Very simple, rule-based planner used as a first step
    before plugging in a real LLM-based planner.
    """

    def __init__(self):
        """Initialize the planner with an empty action history."""
        self._action_history: List[BrowserAction] = []

    def next_action(
        self,
        goal: str,
        observation: BrowserObservation,
        step_index: int,
        action_history: Optional[List[BrowserAction]] = None
    ) -> BrowserAction:
        """
        Determines the next action based on simple rules.
        This is a placeholder planner for testing the agent loop.
        """
        # Use provided history or internal history
        history = action_history if action_history is not None else self._action_history
        
        # Normalize for comparisons
        url = observation.url or ""
        url_lower = url.lower()
        text = (observation.visible_text_excerpt or "").lower()
        goal_lower = goal.lower()

        # PRIORITY 1: Detect and handle cookie banners (only specific Google popup)
        # Check if we've already accepted cookies
        has_accepted_cookies = any(
            action.type == "accept_cookies" for action in history
        )
        
        # Only check for cookies if we haven't accepted them yet
        if not has_accepted_cookies:
            # Specific keywords for Google's "Antes de ir a Google" popup
            cookie_keywords = [
                "antes de ir a google",
                "usamos cookies y datos",
                "aceptar todo",
                "rechazar todo"
            ]
            
            if any(keyword in text for keyword in cookie_keywords):
                return BrowserAction(
                    type="accept_cookies",
                    args={}
                )

        # PRIORITY 2: Safety stop after a certain number of steps
        if step_index >= 6:
            return BrowserAction(type="stop", args={})

        # PRIORITY 3: Check if goal is already in visible text (early stop)
        if goal_lower in text:
            return BrowserAction(type="stop", args={})

        # PRIORITY 4: If not on Google, go to Google
        if "google." not in url_lower:
            return BrowserAction(
                type="open_url",
                args={"url": "https://www.google.com"}
            )

        # PRIORITY 5: We're on Google - perform search based on page state and history
        if "google." in url_lower:
            # Check if we're on search results page
            if "/search" in url_lower:
                # We're on results page
                if goal_lower in text:
                    return BrowserAction(type="stop", args={})
                return BrowserAction(type="noop", args={})
            else:
                # We're on Google homepage (not results yet)
                # Use history to determine next action
                has_fill_input = any(action.type == "fill_input" for action in history)
                has_press_key = any(action.type == "press_key" for action in history)
                
                if not has_fill_input:
                    # Haven't filled input yet, do it now
                    return BrowserAction(
                        type="fill_input",
                        args={"selector": "[name='q']", "text": goal}
                    )
                elif not has_press_key:
                    # Already filled input, now press Enter
                    return BrowserAction(
                        type="press_key",
                        args={"key": "Enter"}
                    )
                else:
                    # Already did fill_input and press_key, wait
                    return BrowserAction(type="noop", args={})

        # Default: stop if no clear rule applies
        return BrowserAction(type="stop", args={})

