"""Settings read from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    debug: bool
    allowed_origins: tuple[str, ...]


def load_settings() -> Settings:
    """Read TASKBOARD_* variables; debug is off unless TASKBOARD_DEBUG is "1"."""
    return Settings(
        database_url=os.environ.get("TASKBOARD_DATABASE_URL", "postgresql://localhost/taskboard"),
        debug=os.environ.get("TASKBOARD_DEBUG") == "1",
        allowed_origins=tuple(os.environ.get("TASKBOARD_ORIGINS", "http://localhost:5173").split(",")),
    )
