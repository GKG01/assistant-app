import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath

WINDOWS_SYSTEM_NAMES = frozenset(
    {
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "$recycle.bin",
        "system volume information",
        "recovery",
    }
)
UNIX_SYSTEM_ROOTS = (
    "/etc",
    "/usr",
    "/proc",
    "/sys",
    "/dev",
    "/bin",
    "/sbin",
    "/boot",
    "/root",
    "/var",
)


def check_syntax(path: Path) -> None:
    raw = str(path)
    if not path.is_absolute():
        raise ValueError("An absolute native-platform path is required.")
    if "\x00" in raw or any(
        part and set(part) == {"."} and len(part) >= 2
        for part in re.split(r"[/\\]", raw)
    ):
        raise ValueError("Directory traversal is not permitted.")
    if raw.startswith(("\\\\", "//")):
        raise PermissionError("Network and device paths are not permitted.")
    if os.name == "nt":
        check_windows_syntax(PureWindowsPath(raw))
    elif "\\" in raw:
        raise ValueError("Use native-platform path separators.")


def check_windows_syntax(path: PureWindowsPath) -> None:
    if not path.is_absolute() or path.drive.startswith("\\\\"):
        raise PermissionError("Only absolute local Windows drive paths are permitted.")
    for part in path.parts[1:]:
        if part.endswith((".", " ")) or any(char in part for char in ':*?"<>|'):
            raise PermissionError("Ambiguous Windows paths are not permitted.")
        if PureWindowsPath(part).is_reserved():
            raise PermissionError("Reserved Windows paths are not permitted.")


def check_system_path(path: Path) -> None:
    if any(part.casefold() in WINDOWS_SYSTEM_NAMES for part in path.parts):
        raise PermissionError("System directories are not permitted.")
    if os.name != "nt" and any(
        path.is_relative_to(root) for root in map(Path, UNIX_SYSTEM_ROOTS)
    ):
        raise PermissionError("System directories are not permitted.")


def check_no_links(path: Path) -> None:
    # Check ancestors before resolving: resolving first would erase evidence of links.
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if (
            stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise PermissionError("Links and reparse points are not permitted.")


def canonical_path(path: Path) -> Path:
    check_syntax(path)
    check_system_path(path)
    check_no_links(path)
    resolved = path.resolve()
    check_system_path(resolved)
    return Path(os.path.normcase(str(resolved)))


class PathPolicy:
    def __init__(self, allowed_directories: Sequence[Path]) -> None:
        # Keep configured paths, not resolved aliases; recheck links on each operation.
        self.roots = tuple(dict.fromkeys(allowed_directories))

    def validate(self, path: Path, *, must_exist: bool = False) -> Path:
        check_syntax(path)
        # First check lexical ancestry, so outside candidates are not stat'ed.
        candidates = [
            root
            for root in self.roots
            if root.is_absolute() and path.is_relative_to(root)
        ]
        if not candidates:
            raise PermissionError("Path is outside configured allowed directories.")
        resolved = canonical_path(path)
        for root in candidates:
            canonical_root = canonical_path(root)
            if canonical_root == Path(canonical_root.anchor):
                raise ValueError("A drive root cannot be allowed.")
            if not resolved.is_relative_to(canonical_root):
                continue
            if must_exist:
                resolved.stat()
            return resolved
        raise PermissionError("Path is outside configured allowed directories.")

    def validate_root(self, path: Path) -> Path:
        resolved = self.validate(path, must_exist=True)
        if not resolved.is_dir():
            raise ValueError("The indexing root must be a directory.")
        return resolved

    def permits(self, raw_path: str) -> bool:
        try:
            self.validate(Path(raw_path))
            return True
        except (OSError, ValueError, RuntimeError):
            return False


def validate_path(path: Path, allowed_directories: Sequence[Path]) -> Path:
    return PathPolicy(allowed_directories).validate(path)
