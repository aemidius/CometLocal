from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


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
        """
        Arranca Playwright y abre un navegador Chromium.
        """
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
        """
        Navega a una URL en la pestaña actual.
        """
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")
        await self.page.goto(url, wait_until="networkidle")

    async def screenshot(self, path: str = "screenshot.png"):
        """
        Guarda una captura de la página actual.
        """
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")
        await self.page.screenshot(path=path, full_page=True)

    async def close(self):
        """
        Cierra navegador y Playwright.
        """
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
        """
        Intenta hacer click en el primer botón que encuentre con alguno
        de los textos indicados. Devuelve True si ha clicado algo.
        """
        if not self.page:
            raise RuntimeError("BrowserController no está iniciado. Llama a start() primero.")

        # Primero probamos por rol=button (más robusto)
        for txt in texts:
            try:
                locator = self.page.get_by_role("button", name=txt, exact=False)
                await locator.first.click(timeout=1500)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                # Si por lo que sea falla el click, probamos con el siguiente texto
                continue

        # Como fallback, buscamos por texto general
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

    async def accept_cookies(self) -> bool:
        """
        Intenta aceptar cookies en la página actual.
        Devuelve True si ha pulsado algún botón 'Aceptar'.
        """
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
        return await self._click_any_button_with_texts(textos_aceptar)

    async def reject_cookies(self) -> bool:
        """
        Intenta rechazar cookies en la página actual.
        Devuelve True si ha pulsado algún botón 'Rechazar'.
        """
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
        return await self._click_any_button_with_texts(textos_rechazar)
