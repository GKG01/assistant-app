from pathlib import Path

import pytest

from permissions.paths import validate_path


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
