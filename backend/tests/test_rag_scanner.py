"""Source folder validation and the file scanner. Plain files in tmp_path, no database."""

import os
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.modules.rag import scanner
from app.modules.rag.scanner import SkipReason, WalkLimits, read_text, walk
from app.modules.rag.source import InvalidSourcePath, resolve_source_path

LIMITS = WalkLimits(max_file_bytes=1_000_000, max_files=1000)


def write(root: Path, rel: str, content: str | bytes = "x = 1\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode())
    return path


def files(root: Path, limits: WalkLimits = LIMITS) -> list[str]:
    return [f.path for f in walk(root, limits).files]


def reasons(root: Path, limits: WalkLimits = LIMITS) -> dict[str, str]:
    return {s.path: s.reason for s in walk(root, limits).skipped}


def link_dir(link: Path, target: Path) -> None:
    """A directory link: a symlink, or a junction on Windows without symlink rights."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("symlinks not available")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


# ---- source path ---------------------------------------------------------------------------


def reason_of(raw: str, home: Path | None = None) -> str:
    with pytest.raises(InvalidSourcePath) as info:
        resolve_source_path(raw, home=home)
    return info.value.details["reason"]


def test_missing_path(tmp_path: Path) -> None:
    assert reason_of(str(tmp_path / "nope")) == "missing"


def test_file_instead_of_folder(tmp_path: Path) -> None:
    assert reason_of(str(write(tmp_path, "a.py"))) == "not_a_directory"


def test_relative_and_empty_paths() -> None:
    assert reason_of("some/project") == "not_absolute"
    assert reason_of("   ") == "empty"


def test_filesystem_root_is_refused() -> None:
    root = Path.cwd().anchor  # "C:\\" on Windows, "/" elsewhere
    assert reason_of(root) == "filesystem_root"


def test_home_and_folders_above_it_are_refused(tmp_path: Path) -> None:
    home = tmp_path / "home" / "dev"
    home.mkdir(parents=True)
    assert reason_of(str(home), home=home) == "home"
    assert reason_of(str(tmp_path / "home"), home=home) == "home"
    (home / "code").mkdir()
    assert resolve_source_path(str(home / "code"), home=home) == (home / "code").resolve()


def test_spaces_and_windows_separators(tmp_path: Path) -> None:
    folder = tmp_path / "My Projects" / "app one"
    folder.mkdir(parents=True)
    raw = str(folder).replace("/", "\\") if sys.platform == "win32" else str(folder)
    assert resolve_source_path(f"  {raw}  ") == folder.resolve()
    if sys.platform == "win32":
        assert resolve_source_path(str(folder).replace("\\", "/")) == folder.resolve()


def test_linked_root_resolves_to_the_real_folder(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link_dir(tmp_path / "link", real)
    assert resolve_source_path(str(tmp_path / "link")) == real.resolve()


# ---- walking -------------------------------------------------------------------------------


def test_gitignore_nested_and_negation(tmp_path: Path) -> None:
    write(tmp_path, ".gitignore", "*.txt\n!keep.txt\ngenerated/\n")
    write(tmp_path, "app.txt", "x")
    write(tmp_path, "keep.txt", "x")
    write(tmp_path, "generated/out.py")
    write(tmp_path, "pkg/.gitignore", "local_*.py\n!local_ok.py\n/only_here.md\n")
    write(tmp_path, "pkg/local_a.py")
    write(tmp_path, "pkg/local_ok.py")
    write(tmp_path, "pkg/only_here.md", "x")
    write(tmp_path, "pkg/sub/only_here.md", "x")
    write(tmp_path, "pkg/main.py")
    found = files(tmp_path)
    skipped = reasons(tmp_path)
    assert "pkg/main.py" in found and "pkg/local_ok.py" in found
    assert "keep.txt" in found  # re-included by the negation
    assert "pkg/sub/only_here.md" in found  # anchored pattern applies to pkg/ only
    assert skipped["app.txt"] == SkipReason.GITIGNORED
    assert skipped["generated/"] == SkipReason.GITIGNORED
    assert skipped["pkg/local_a.py"] == SkipReason.GITIGNORED
    assert skipped["pkg/only_here.md"] == SkipReason.GITIGNORED


def test_forced_skips(tmp_path: Path) -> None:
    for rel in (".git/config", "node_modules/x/index.js", "__pycache__/a.py", "dist/a.js",
                "build/a.py", ".pytest_cache/a.txt", "myenv/lib/a.py"):  # fmt: skip
        write(tmp_path, rel)
    write(tmp_path, "myenv/pyvenv.cfg", "home = x")
    write(tmp_path, "package-lock.json", "{}")
    write(tmp_path, "poetry.lock", "x")
    write(tmp_path, "static/app.min.js", "x")
    write(tmp_path, "logo.png", b"\x89PNG")
    write(tmp_path, "docs/manual.pdf", b"%PDF")
    write(tmp_path, "bundle.zip", b"PK")
    write(tmp_path, "src/main.py")
    skipped = reasons(tmp_path)
    assert files(tmp_path) == ["src/main.py"]
    for folder in (".git/", "node_modules/", "__pycache__/", "dist/", "build/", "myenv/"):
        assert skipped[folder] == SkipReason.IGNORED_DIR
    assert skipped["package-lock.json"] == SkipReason.LOCK_FILE
    assert skipped["poetry.lock"] == SkipReason.LOCK_FILE
    assert skipped["static/app.min.js"] == SkipReason.MINIFIED
    assert {skipped["logo.png"], skipped["docs/manual.pdf"], skipped["bundle.zip"]} == {
        SkipReason.BINARY
    }


def test_sensitive_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    names = [".env", ".env.local", "prod.env", "server.pem", "tls.key", "id_rsa", "id_ed25519",
             "credentials.json", "secrets.yaml", "cert.pfx", "config/.env.test"]  # fmt: skip
    for name in names:
        write(tmp_path, name, "x")
    write(tmp_path, "private/notes.md", "# notes")
    monkeypatch.setattr(settings, "index_sensitive_patterns", ["private/"])
    skipped = reasons(tmp_path)
    for name in names:
        assert skipped[name] == SkipReason.SENSITIVE_NAME, name
    assert skipped["private/notes.md"] == SkipReason.SENSITIVE_NAME
    assert files(tmp_path) == []


def test_size_and_count_limits(tmp_path: Path) -> None:
    write(tmp_path, "big.py", "x" * 2000)
    for i in range(3):
        write(tmp_path, f"f{i}.py")
    result = walk(tmp_path, WalkLimits(max_file_bytes=1000, max_files=2))
    assert [f.path for f in result.files] == ["f0.py", "f1.py"]
    skipped = {s.path: s.reason for s in result.skipped}
    assert skipped == {"big.py": SkipReason.TOO_LARGE, "f2.py": SkipReason.TOO_MANY_FILES}
    report = result.report.as_dict()
    assert report["too_large"] == {"count": 1, "examples": ["big.py"]}


def test_symlink_out_of_root_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    write(outside, "stolen.py")
    root = tmp_path / "root"
    write(root, "main.py")
    link_dir(root / "linked", outside)
    assert files(root) == ["main.py"]
    assert reasons(root)["linked"] == SkipReason.SYMLINK


def test_symlink_loop_is_not_followed(tmp_path: Path) -> None:
    write(tmp_path, "a/main.py")
    link_dir(tmp_path / "a" / "loop", tmp_path / "a")
    assert files(tmp_path) == ["a/main.py"]


def test_unknown_types_are_skipped(tmp_path: Path) -> None:
    write(tmp_path, "data.weird", "x")
    write(tmp_path, "Dockerfile", "FROM python")
    assert files(tmp_path) == ["Dockerfile"]
    assert reasons(tmp_path)["data.weird"] == SkipReason.UNSUPPORTED_TYPE


# ---- reading -------------------------------------------------------------------------------


def test_secret_content_skips_the_whole_file(tmp_path: Path) -> None:
    # Built at runtime so no secret-shaped string sits in the repository.
    header = "-----BEGIN " + "RSA PRIVATE KEY-----"
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    openai = "sk-" + "proj-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
    for i, secret in enumerate((header, aws, openai)):
        path = write(tmp_path, f"conf{i}.py", f"def f():\n    return '{secret}'\n")
        assert read_text(path, 10_000).skip_reason == SkipReason.POSSIBLE_SECRET


def test_binary_and_encodings(tmp_path: Path) -> None:
    assert read_text(write(tmp_path, "a.py", b"x\x00y"), 1000).skip_reason == SkipReason.BINARY
    utf16 = "x = 1\n".encode("utf-16")
    assert (
        read_text(write(tmp_path, "b.py", utf16), 1000).skip_reason
        == SkipReason.UNSUPPORTED_ENCODING
    )
    latin = "name = 'caf\xe9'\n".encode("latin-1")
    assert (
        read_text(write(tmp_path, "c.py", latin), 1000).skip_reason
        == SkipReason.UNSUPPORTED_ENCODING
    )


def test_bom_and_crlf_are_normalized(tmp_path: Path) -> None:
    path = write(tmp_path, "a.py", b"\xef\xbb\xbfx = 1\r\ny = 2\rz = 3\r\n")
    result = read_text(path, 1000)
    assert result.text == "x = 1\ny = 2\nz = 3\n"
    lf = read_text(write(tmp_path, "b.py", b"x = 1\ny = 2\nz = 3\n"), 1000)
    assert lf.text == result.text


def test_empty_whitespace_and_long_lines(tmp_path: Path) -> None:
    assert read_text(write(tmp_path, "a.py", ""), 1000).skip_reason == SkipReason.EMPTY
    assert read_text(write(tmp_path, "b.py", " \n\t\n"), 1000).skip_reason == SkipReason.EMPTY
    long_line = "x = '" + "a" * 20_000 + "'\n"
    assert (
        read_text(write(tmp_path, "c.js", long_line), 100_000).skip_reason == SkipReason.LONG_LINES
    )


def test_unreadable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path, "a.py")

    def locked(*args: object, **kwargs: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(scanner, "open", locked, raising=False)
    assert read_text(path, 1000).skip_reason == SkipReason.UNREADABLE


def test_file_changed_while_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path, "a.py")
    real_stat = os.stat
    calls = {"n": 0}

    def changing_stat(p: Path) -> os.stat_result:
        calls["n"] += 1
        info = real_stat(p)
        if calls["n"] == 1:
            return info
        values = list(info)
        values[8] += 1  # st_mtime
        return os.stat_result(values, {"st_mtime_ns": info.st_mtime_ns + 1_000_000_000})

    monkeypatch.setattr(scanner, "_stat", changing_stat)
    assert read_text(path, 1000).skip_reason == SkipReason.CHANGED_WHILE_READING


def test_file_grown_past_limit_between_walk_and_read(tmp_path: Path) -> None:
    path = write(tmp_path, "a.py", "x" * 50)
    assert read_text(path, 10).skip_reason == SkipReason.TOO_LARGE
