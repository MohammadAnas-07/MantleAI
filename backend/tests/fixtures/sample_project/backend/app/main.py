"""Taskboard API entry point."""

import asyncio

from app.config import load_settings
from app.db import check_database

HEALTH_CHECK_TIMEOUT_SECONDS = 2.0


def create_app():
    settings = load_settings()
    app = {"name": "taskboard", "debug": settings.debug, "routes": {}}
    app["routes"]["/health"] = health
    return app


async def health() -> dict:
    """Report whether the API and the database are up. Never waits longer than the timeout."""
    try:
        up = await asyncio.wait_for(check_database(), timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        up = False
    return {"status": "ok", "database": "up" if up else "down"}
