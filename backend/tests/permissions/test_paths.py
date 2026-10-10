from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
import stat

import pytest

from permissions.paths import check_windows_syntax, validate_path


def test_allowed_path(tmp_path):
    assert validate_path(tmp_path / "new.txt", [tmp_path]) == tmp_path / "new.txt"


def test_no_roots_denies(tmp_path):
    with pytest.raises(PermissionError):
        validate_path(tmp_path / "file", [])


def test_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        validate_path(tmp_path / ".." / "outside", [tmp_path])


def test_relative_rejected(tmp_path):
    with pytest.raises(ValueError):
        validate_path(Path("relative"), [tmp_path])


def test_sibling_prefix_rejected(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    with pytest.raises(PermissionError):
        validate_path(tmp_path / "allowed-other" / "file", [root])


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks require developer mode or privileges on Windows")
    with pytest.raises(PermissionError):
        validate_path(root / "link" / "file", [root])


def test_drive_root_rejected(tmp_path):
    with pytest.raises(ValueError):
        validate_path(tmp_path, [Path(tmp_path.anchor)])


@pytest.mark.parametrize("component", ["..", "....", "../outside", "..\\outside"])
def test_traversal_variants(tmp_path, component):
    with pytest.raises(ValueError):
        validate_path(tmp_path / component, [tmp_path])


@pytest.mark.parametrize(
    "path",
    [
        "C:/Documents/file.txt:stream",
        "C:/Documents/NUL.txt",
        "C:/Documents/trailing.",
        "C:/Documents/trailing ",
        "//server/share/file.txt",
        "//?/C:/Documents/file.txt",
        "C:relative.txt",
    ],
)
def test_windows_ambiguous_paths(path):
    with pytest.raises(PermissionError):
        check_windows_syntax(PureWindowsPath(path))


def test_windows_local_syntax():
    check_windows_syntax(PureWindowsPath("C:/Users/example/Documents/resume.pdf"))


def test_reparse_attribute_rejected(tmp_path, monkeypatch):
    file = tmp_path / "cloud.txt"
    file.touch()
    original = Path.lstat

    def lstat(path):
        if path == file:
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(PermissionError):
        validate_path(file, [tmp_path])
