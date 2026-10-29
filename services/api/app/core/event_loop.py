"""Opt-in process-local loop factory; no global event-loop policy changes.

The current Windows/Python 3.13 aiomysql TLS compatibility path uses Selector.
Unix keeps asyncio's configured default. Importing this module creates no loop.
"""

import asyncio
from sys import platform


def new_event_loop() -> asyncio.AbstractEventLoop:
    """Uvicorn custom --loop callable and asyncio.run(loop_factory=...) factory."""
    if platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
