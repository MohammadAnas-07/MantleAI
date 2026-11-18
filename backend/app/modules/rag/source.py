"""Validation of a project's source folder (the folder that gets indexed).

Only the rag module touches project files (rule 10), so the check lives here; the projects
module stores the validated path.
"""

import asyncio
import os
from pathlib import Path

from app.core.errors import AppError


class InvalidSourcePath(AppError):
    status_code = 422
    code = "invalid_source_path"


def _fail(message: str, reason: str) -> InvalidSourcePath:
    return InvalidSourcePath(message, details={"reason": reason})


def resolve_source_path(raw: str, *, home: Path | None = None) -> Path:
    """Check `raw` and return the real, absolute folder it points to.

    Refuses relative paths, missing paths, files, unreadable folders, a filesystem root, the
    user's home folder and any folder that contains it: indexing one of those would send far
    more than one project to the embedding provider.
    """
    text = raw.strip()
    if not text:
        raise _fail("The source path is empty.", "empty")
    if "\x00" in text:
        raise _fail("The source path contains a null byte.", "invalid")
    path = Path(text)
    if not path.is_absolute():
        raise _fail("Use an absolute path, for example C:\\code\\my-app.", "not_absolute")
    if not path.exists():
        raise _fail("The source path does not exist.", "missing")
    if not path.is_dir():
        raise _fail("The source path is a file, not a folder.", "not_a_directory")
    real = path.resolve(strict=True)
    if real.parent == real:
        raise _fail("A filesystem root can't be a project folder.", "filesystem_root")
    home_dir = (home or Path.home()).resolve()
    if real == home_dir or home_dir.is_relative_to(real):
        raise _fail("Your home folder (or a folder above it) can't be a project folder.", "home")
    if not os.access(real, os.R_OK | os.X_OK):
        raise _fail("The source folder can't be read.", "unreadable")
    try:
        with os.scandir(real) as entries:
            next(entries, None)
    except OSError as exc:
        raise _fail("The source folder can't be read.", "unreadable") from exc
    return real


async def validate_source_path(raw: str) -> str:
    """Async wrapper for `resolve_source_path` (it touches the disk). Returns the real path."""
    return str(await asyncio.to_thread(resolve_source_path, raw))
