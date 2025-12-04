from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from backend.shared.models import BrowserObservation


class BrowserController:
    """
    Controla un navegador Chromium mediante Playwright (API asíncrona).
    Se arranca una vez en el startup de FastAPI.
    """

    def __init__(self):
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self, headless: bool = False):
        """Arranca Playwright y abre un navegador Chromium."""
        if self._playwright is not None:
            # Ya está iniciado
            return

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        self.page = await self.context.new_page()

    async def goto(self, url: str):
        """Navega a una URL en la pestaña actual."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")
        await self.page.goto(url, wait_until="networkidle")

    async def screenshot(self, path: str = "screenshot.png"):
        """Guarda una captura de la página actual."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")
        await self.page.screenshot(path=path, full_page=True)

    async def close(self):
        """Cierra navegador y Playwright."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # -----------------------------
    #  ACCIONES DE COOKIES
    # -----------------------------

    async def _click_any_button_with_texts(self, texts: list[str]) -> bool:
        """Intenta hacer click en un botón con alguno de los textos dados."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        # Intento rápido por rol=button
        for txt in texts:
            try:
                locator = self.page.get_by_role("button", name=txt, exact=False)
                await locator.first.click(timeout=1500)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        # Fallback: por texto general
        for txt in texts:
            try:
                locator = self.page.get_by_text(txt, exact=False)
                await locator.first.click(timeout=1500)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        return False

    async def _bruteforce_click_button_text_contains(self, texts: list[str]) -> bool:
        """Recorre frames y botones buscando textos que contengan alguna de las cadenas."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        texts_lower = [t.lower() for t in texts]

        for frame in self.page.frames:
            try:
                elements = await frame.query_selector_all("button, [role=button]")
            except Exception:
                continue

            for el in elements:
                try:
                    txt = (await el.inner_text()).strip().lower()
                except Exception:
                    continue

                if any(t in txt for t in texts_lower):
                    try:
                        await el.click()
                        return True
                    except Exception:
                        continue

        return False

    async def accept_cookies(self) -> bool:
        """Intenta aceptar cookies en la página actual."""
        textos_aceptar = [
            "Aceptar",
            "Aceptar todo",
            "Aceptar todas",
            "Acepto",
            "Aceptar y cerrar",
            "Accept",
            "Accept all",
            "I agree",
            "Allow all",
        ]

        if await self._click_any_button_with_texts(textos_aceptar):
            return True

        return await self._bruteforce_click_button_text_contains(textos_aceptar)

    async def reject_cookies(self) -> bool:
        """Intenta rechazar cookies en la página actual."""
        textos_rechazar = [
            "Rechazar",
            "Rechazar todo",
            "Rechazar todas",
            "Rechazar cookies no necesarias",
            "Solo usar cookies necesarias",
            "Reject",
            "Reject all",
            "Continue without accepting",
        ]

        if await self._click_any_button_with_texts(textos_rechazar):
            return True

        return await self._bruteforce_click_button_text_contains(textos_rechazar)

    # -----------------------------
    #  ACCIONES GENERALES
    # -----------------------------

    async def click_by_text(self, label: str) -> bool:
        """
        Hace click en un elemento interactivo (botón, enlace, etc.)
        cuyo texto contenga la etiqueta dada.
        """
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        texts = [label]

        # Intento rápido con roles de botón y enlace
        for txt in texts:
            for role in ("button", "link"):
                try:
                    locator = self.page.get_by_role(role, name=txt, exact=False)
                    await locator.first.click(timeout=1500)
                    return True
                except PlaywrightTimeoutError:
                    continue
                except Exception:
                    continue

        # Fallback: por texto directo
        for txt in texts:
            try:
                locator = self.page.get_by_text(txt, exact=False)
                await locator.first.click(timeout=1500)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        # Fallback final: recorrer elementos clicables
        texts_lower = [t.lower() for t in texts]
        for frame in self.page.frames:
            try:
                elements = await frame.query_selector_all(
                    "a, button, [role=button], input[type='button'], input[type='submit']"
                )
            except Exception:
                continue

            for el in elements:
                try:
                    txt = (await el.inner_text()).strip().lower()
                except Exception:
                    continue

                if any(t in txt for t in texts_lower):
                    try:
                        await el.click()
                        return True
                    except Exception:
                        continue

        return False

    async def type_text(self, text: str) -> bool:
        """Escribe texto en el campo de entrada más razonable."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        # 1) Si hay un elemento activo que pueda recibir texto, escribimos ahí
        try:
            has_active = await self.page.evaluate(
                "() => !!document.activeElement && ['input','textarea'].includes(document.activeElement.tagName.toLowerCase())"
            )
        except Exception:
            has_active = False

        if has_active:
            try:
                await self.page.keyboard.type(text)
                return True
            except Exception:
                pass

        # 2) Buscar un input de texto razonable
        selectors = [
            "input[type='text']",
            "input[type='search']",
            "textarea",
            "input",
        ]

        for sel in selectors:
            loc = self.page.locator(sel)
            try:
                first = loc.first
                await first.click(timeout=1500)
                await first.fill(text)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        return False

    async def press_enter(self) -> None:
        """Pulsa la tecla Enter en la página actual."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")
        await self.page.keyboard.press("Enter")

    async def google_search(self, query: str) -> bool:
        """Realiza una búsqueda en Google con la query indicada."""
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        try:
            if "google." not in (self.page.url or ""):
                await self.goto("https://www.google.com")
                # Intento silencioso de aceptar cookies si aparecen
                try:
                    await self.accept_cookies()
                except Exception:
                    pass

            # Localizar el campo de búsqueda principal
            search_locator = self.page.locator("textarea[name='q'], input[name='q']").first
            await search_locator.click(timeout=3000)
            await search_locator.fill(query)
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_load_state("networkidle")
            return True
        except Exception:
            return False

    # -----------------------------
    #  UPLOAD DE ARCHIVOS (v2.3.0)
    # -----------------------------

    async def upload_file(self, selector: str, file_path: str) -> BrowserObservation:
        """
        Localiza un input[type='file'] por selector CSS/XPath y le asigna file_path.
        Devuelve una Observation después de que el navegador haya procesado el cambio.
        
        v2.3.0: Soporte básico para uploads en formularios HTML estándar.
        
        Args:
            selector: Selector CSS o XPath para el input[type='file']
            file_path: Ruta absoluta del archivo a subir
            
        Returns:
            BrowserObservation del estado de la página después del upload
            
        Raises:
            RuntimeError: Si el browser no está iniciado
            Exception: Si no se encuentra el input o hay error al subir
        """
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")
        
        try:
            # Intentar localizar el input file
            # Primero intentar como selector CSS
            try:
                file_input = self.page.locator(selector).first
                # Verificar que es un input file
                input_type = await file_input.get_attribute("type")
                if input_type != "file":
                    raise ValueError(f"Elemento encontrado con selector '{selector}' no es un input[type='file']")
            except Exception as e:
                # Si falla, intentar buscar el primer input[type='file'] visible si el selector es genérico
                if selector == "input[type='file']":
                    file_input = self.page.locator("input[type='file']:visible").first
                else:
                    raise ValueError(f"No se encontró input[type='file'] con selector '{selector}': {e}")
            
            # Subir el archivo usando set_input_files de Playwright
            await file_input.set_input_files(file_path)
            
            # Esperar un momento para que el navegador procese el cambio
            await self.page.wait_for_timeout(500)
            
            # Devolver la observación actualizada
            return await self.get_observation()
            
        except Exception as e:
            # Si hay error, devolver observación actual pero con información del error
            obs = await self.get_observation()
            # El error se manejará en el StepResult
            raise Exception(f"Error al subir archivo '{file_path}' con selector '{selector}': {e}")

    # -----------------------------
    #  OBSERVACIÓN (API para planner)
    # -----------------------------

    async def get_observation(self) -> BrowserObservation:
        """
        Returns a structured observation of the current page state,
        designed to be consumed by a planner (human or LLM).
        This method only reads the page, it does not perform any actions.
        
        This is the API that will be used by the future planner.
        """
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        # Initialize defaults
        url = ""
        title = ""
        visible_text_excerpt = ""
        clickable_texts: list[str] = []
        input_hints: list[str] = []

        try:
            # Get URL
            url = self.page.url or ""
        except Exception:
            pass

        try:
            # Get title
            title = await self.page.title() or ""
        except Exception:
            pass

        try:
            # Get visible text excerpt (limited to 3000 chars)
            body_text = await self.page.inner_text("body")
            if body_text:
                visible_text_excerpt = body_text[:3000]
                if len(body_text) > 3000:
                    visible_text_excerpt += "..."
        except Exception:
            pass

        try:
            # Extract clickable texts from various elements
            clickable_selectors = [
                "a",
                "button",
                "[role='button']",
                "input[type='button']",
                "input[type='submit']",
            ]
            
            seen_texts = set()
            for selector in clickable_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for el in elements:
                        try:
                            # Check if element is visible
                            is_visible = await el.is_visible()
                            if not is_visible:
                                continue
                            
                            # Get text content
                            text = (await el.inner_text()).strip()
                            
                            # Normalize and filter
                            text_normalized = " ".join(text.split())
                            if text_normalized and len(text_normalized) >= 2:
                                text_lower = text_normalized.lower()
                                if text_lower not in seen_texts:
                                    seen_texts.add(text_lower)
                                    clickable_texts.append(text_normalized)
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

        try:
            # Extract input hints (placeholders, aria-labels, names, associated labels)
            input_selectors = ["input[type='text']", "input[type='search']", "input[type='email']", 
                             "input[type='password']", "textarea"]
            
            seen_hints = set()
            for selector in input_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for el in elements:
                        try:
                            # Check if element is visible
                            is_visible = await el.is_visible()
                            if not is_visible:
                                continue
                            
                            # Try to get placeholder
                            placeholder = await el.get_attribute("placeholder")
                            if placeholder and placeholder.strip():
                                hint = placeholder.strip()
                                if hint.lower() not in seen_hints:
                                    seen_hints.add(hint.lower())
                                    input_hints.append(hint)
                            
                            # Try to get aria-label
                            aria_label = await el.get_attribute("aria-label")
                            if aria_label and aria_label.strip():
                                hint = aria_label.strip()
                                if hint.lower() not in seen_hints:
                                    seen_hints.add(hint.lower())
                                    input_hints.append(hint)
                            
                            # Try to get name attribute
                            name = await el.get_attribute("name")
                            if name and name.strip():
                                hint = name.strip()
                                if hint.lower() not in seen_hints:
                                    seen_hints.add(hint.lower())
                                    input_hints.append(hint)
                            
                            # Try to find associated label
                            input_id = await el.get_attribute("id")
                            if input_id:
                                try:
                                    label_el = await self.page.query_selector(f"label[for='{input_id}']")
                                    if label_el:
                                        label_text = (await label_el.inner_text()).strip()
                                        if label_text:
                                            hint = label_text
                                            if hint.lower() not in seen_hints:
                                                seen_hints.add(hint.lower())
                                                input_hints.append(hint)
                                except Exception:
                                    pass
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

        # Return observation even if some fields failed to extract
        return BrowserObservation(
            url=url,
            title=title,
            visible_text_excerpt=visible_text_excerpt,
            clickable_texts=clickable_texts,
            input_hints=input_hints
        )
