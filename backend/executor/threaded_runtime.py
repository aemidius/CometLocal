from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool


async def run_actions_threaded(rt: Any, **kwargs):
    """
    Ejecuta rt.run_actions(**kwargs) fuera del event loop (threadpool).

    Necesario porque ExecutorRuntimeH4 usa Playwright Sync API.
    """
    return await run_in_threadpool(lambda: rt.run_actions(**kwargs))


