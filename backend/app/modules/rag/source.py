"""Validation of a project's source folder (the folder that gets indexed).

Only the rag module touches project files (rule 10), so the check lives here; the projects
module stores the validated path.
"""

import asyncio
import os
from pathlib import Path, PurePath

from app.core.errors import AppError

# Folders right under a filesystem root (any drive on Windows) that belong to the system.
_SYSTEM_TOP_WINDOWS = frozenset({"windows", "program files", "program files (x86)", "programdata"})
_SYSTEM_TOP_POSIX = frozenset(
    {"etc", "usr", "var", "bin", "sbin", "lib", "lib64", "boot", "dev", "proc", "sys", "root",
     "private", "system", "library"}
)  # fmt: skip
# Credential, profile and password-manager folders, wherever they are in the path. Compared
# lower-case. Browser profiles live inside AppData, .config, .mozilla or ~/Library.
_SENSITIVE_NAMES = frozenset(
    {".ssh", ".aws", ".gnupg", ".azure", ".kube", ".docker", ".config", ".mozilla",
     ".password-store", "keyrings", "keychains", "1password", "bitwarden", "keepass",
     "keepassxc", "lastpass", "dashlane"}
)  # fmt: skip
# Folders that are sensitive only right inside the home folder.
_SENSITIVE_IN_HOME = frozenset({"appdata", "library"})
# A source folder that directly holds one of these is a profile or a copy of one.
_CREDENTIAL_CHILDREN = frozenset(
    {".ssh", ".aws", ".gnupg", ".azure", ".kube", ".password-store", "appdata"}
)  # fmt: skip


class InvalidSourcePath(AppError):
    status_code = 422
    code = "invalid_source_path"


def _fail(message: str, reason: str) -> InvalidSourcePath:
    return InvalidSourcePath(message, details={"reason": reason})


def _parts(path: PurePath, windows: bool) -> tuple[str, ...]:
    return tuple(p.lower() for p in path.parts) if windows else path.parts


def sensitive_reason(path: PurePath, home: PurePath, *, windows: bool) -> str | None:
    """Why `path` (absolute, already resolved) can't be a project folder, or None.

    `filesystem_root`, `home` (the home folder or a folder above it), `system_folder` or
    `sensitive_folder`. On Windows the comparison ignores case.
    """
    parts, home_parts = _parts(path, windows), _parts(home, windows)
    if len(parts) <= 1:
        return "filesystem_root"
    if parts == home_parts[: len(parts)]:
        return "home"
    top = parts[1] if windows else parts[1].lower()
    if top in (_SYSTEM_TOP_WINDOWS if windows else _SYSTEM_TOP_POSIX):
        return "system_folder"
    if any(p.lower() in _SENSITIVE_NAMES for p in parts[1:]):
        return "sensitive_folder"
    inside_home = parts[: len(home_parts)] == home_parts
    if inside_home and parts[len(home_parts)].lower() in _SENSITIVE_IN_HOME:
        return "sensitive_folder"
    return None


_REFUSALS = {
    "filesystem_root": "A filesystem root can't be a project folder.",
    "home": "Your home folder (or a folder above it) can't be a project folder.",
    "system_folder": "A system folder can't be a project folder.",
    "sensitive_folder": (
        "This folder holds credentials, app profiles or passwords, so it can't be a project "
        "folder. Pick the folder of one project."
    ),
}


def resolve_source_path(raw: str, *, home: Path | None = None) -> Path:
    """Check `raw` and return the real, absolute folder it points to.

    Refuses relative paths, missing paths, files and unreadable folders, and, after links and
    `..` are resolved, a filesystem root, the home folder or a folder above it, system
    folders, and credential or profile folders (or a folder that directly holds one): indexing
    one of those would send far more than one project, or secrets, to the embedding provider.
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
    windows = os.name == "nt"
    home_dir = (home or user_home()).resolve()
    reason = sensitive_reason(real, home_dir, windows=windows)
    if real.parent == real:
        reason = "filesystem_root"  # a UNC share root, too
    if reason is not None:
        raise _fail(_REFUSALS[reason], reason)
    if not os.access(real, os.R_OK | os.X_OK):
        raise _fail("The source folder can't be read.", "unreadable")
    try:
        with os.scandir(real) as entries:
            children = {e.name.lower() for e in entries if e.is_dir(follow_symlinks=False)}
    except OSError as exc:
        raise _fail("The source folder can't be read.", "unreadable") from exc
    if children & _CREDENTIAL_CHILDREN:
        raise _fail(_REFUSALS["sensitive_folder"], "sensitive_folder")
    return real


def user_home() -> Path:
    """The user's home folder (a function, so tests can point it elsewhere)."""
    return Path.home()


async def validate_source_path(raw: str) -> str:
    """Async wrapper for `resolve_source_path` (it touches the disk). Returns the real path."""
    return str(await asyncio.to_thread(resolve_source_path, raw))
