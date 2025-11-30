from playwright.async_api import async_playwright


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
