"""Sensitive folders can't be a project's source folder (audit A-010): not when the path is
saved, and not when an index run starts. No database, no model call."""

import os
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from app.modules.rag.source import InvalidSourcePath, resolve_source_path, sensitive_reason
from tests.test_rag_scanner import link_dir


def reason_of(raw: str, home: Path) -> str:
    with pytest.raises(InvalidSourcePath) as info:
        resolve_source_path(raw, home=home)
    assert info.value.status_code == 422 and info.value.code == "invalid_source_path"
    return info.value.details["reason"]


@pytest.fixture
def home(tmp_path: Path) -> Path:
    folder = tmp_path / "Users" / "dev"
    folder.mkdir(parents=True)
    return folder


# ---- the rules, on plain paths of both systems ---------------------------------------------

WIN_HOME = PureWindowsPath("C:/Users/dev")
POSIX_HOME = PurePosixPath("/home/dev")


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("C:/", "filesystem_root"),
        ("D:/", "filesystem_root"),
        ("C:/Users/dev", "home"),
        ("C:/Users", "home"),
        ("C:/Windows", "system_folder"),
        ("c:/windows/System32", "system_folder"),
        ("C:/Program Files/App", "system_folder"),
        ("D:/Program Files (x86)/Tool", "system_folder"),
        ("C:/ProgramData/Thing", "system_folder"),
        ("C:/Users/dev/AppData", "sensitive_folder"),
        ("C:/Users/dev/appdata/Roaming/Code", "sensitive_folder"),
        ("C:/Users/dev/AppData/Local/Google/Chrome/User Data", "sensitive_folder"),
        ("C:/Users/dev/.ssh", "sensitive_folder"),
        ("C:/Users/dev/.AWS", "sensitive_folder"),
        ("C:/Users/dev/.azure/x", "sensitive_folder"),
        ("C:/Users/dev/.kube", "sensitive_folder"),
        ("C:/Users/dev/.gnupg", "sensitive_folder"),
        ("C:/Users/dev/.docker", "sensitive_folder"),
        ("C:/Users/dev/.config/gcloud", "sensitive_folder"),
        ("D:/backup/.ssh", "sensitive_folder"),
        ("C:/Users/dev/Documents/Bitwarden", "sensitive_folder"),
        ("C:/Users/dev/Documents/KeePassXC", "sensitive_folder"),
        ("C:/Users/dev/1Password", "sensitive_folder"),
    ],
)
def test_windows_paths(path: str, reason: str) -> None:
    assert sensitive_reason(PureWindowsPath(path), WIN_HOME, windows=True) == reason


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/", "filesystem_root"),
        ("/home", "home"),
        ("/etc", "system_folder"),
        ("/etc/nginx", "system_folder"),
        ("/usr/local/src/app", "system_folder"),
        ("/var/www/site", "system_folder"),
        ("/System/Library", "system_folder"),
        ("/home/dev/.ssh", "sensitive_folder"),
        ("/home/dev/.config", "sensitive_folder"),
        ("/home/dev/.mozilla/firefox", "sensitive_folder"),
        ("/home/dev/.password-store", "sensitive_folder"),
        ("/home/dev/.local/share/keyrings", "sensitive_folder"),
        ("/home/dev/Library", "sensitive_folder"),
        ("/home/dev/Library/Keychains", "sensitive_folder"),
        ("/home/dev/Library/Application Support/Google/Chrome", "sensitive_folder"),
    ],
)
def test_posix_paths(path: str, reason: str) -> None:
    assert sensitive_reason(PurePosixPath(path), POSIX_HOME, windows=False) == reason


@pytest.mark.parametrize(
    ("path", "home", "windows"),
    [
        ("C:/Users/dev/code/my-app", WIN_HOME, True),
        ("C:/Users/dev/Documents/projects/api", WIN_HOME, True),
        ("D:/work/Library", WIN_HOME, True),  # "Library" only counts in the home folder
        ("D:/work/windows-tools", WIN_HOME, True),  # only the drive's own Windows folder
        ("/home/dev/code/app", POSIX_HOME, False),
        ("/home/dev/src/var", POSIX_HOME, False),  # /var only at the root
        ("/srv/projects/app", POSIX_HOME, False),
    ],
)
def test_normal_project_folders_are_allowed(path: str, home: PurePosixPath, windows: bool) -> None:
    pure = PureWindowsPath(path) if windows else PurePosixPath(path)
    assert sensitive_reason(pure, home, windows=windows) is None


# ---- on disk ----------------------------------------------------------------------------------


def test_a_project_inside_the_home_folder_still_works(home: Path) -> None:
    project = home / "code" / "my-app"
    project.mkdir(parents=True)
    assert resolve_source_path(str(project), home=home) == project.resolve()


@pytest.mark.parametrize("name", ["AppData", ".ssh", ".aws", ".gnupg", ".kube", ".config"])
def test_credential_and_profile_folders_are_refused(home: Path, name: str) -> None:
    (home / name / "inner").mkdir(parents=True)
    assert reason_of(str(home / name), home) == "sensitive_folder"
    assert reason_of(str(home / name / "inner"), home) == "sensitive_folder"


def test_dot_dot_is_resolved_before_the_check(home: Path) -> None:
    (home / "code").mkdir()
    (home / ".ssh").mkdir()
    assert reason_of(str(home / "code" / ".." / ".ssh"), home) == "sensitive_folder"


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive paths are a Windows rule")
def test_case_does_not_matter_on_windows(home: Path) -> None:
    (home / "AppData" / "Roaming").mkdir(parents=True)
    assert reason_of(str(home / "APPDATA" / "roaming"), home) == "sensitive_folder"


def test_a_link_into_a_sensitive_folder_is_refused(home: Path) -> None:
    secret = home / ".aws"
    secret.mkdir()
    link = home / "code-link"
    link_dir(link, secret)
    assert reason_of(str(link), home) == "sensitive_folder"


def test_a_folder_that_holds_a_credential_folder_is_refused(home: Path, tmp_path: Path) -> None:
    backup = tmp_path / "old-laptop"
    (backup / ".ssh").mkdir(parents=True)
    assert reason_of(str(backup), home) == "sensitive_folder"


def test_the_error_names_no_path(home: Path) -> None:
    (home / ".ssh").mkdir()
    with pytest.raises(InvalidSourcePath) as info:
        resolve_source_path(str(home / ".ssh"), home=home)
    assert str(home) not in str(info.value) and ".ssh" not in str(info.value.details)


@pytest.mark.skipif(os.name != "nt", reason="needs the real Windows folder")
def test_the_real_windows_folder_is_refused() -> None:
    windows = Path(Path.cwd().anchor) / "Windows"
    if not windows.is_dir():
        pytest.skip("no Windows folder on this drive")
    assert reason_of(str(windows), Path.home()) == "system_folder"
