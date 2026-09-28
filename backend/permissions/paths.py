from pathlib import Path
from collections.abc import Sequence


def validate_path(path: Path, allowed_directories: Sequence[Path]) -> Path:
    """Resolve traversal and symlinks before checking configured directory boundaries.

    This is a baseline, not protection against concurrent symlink/junction swaps.
    Future filesystem tools must revalidate at execution and use safe OS handles.
    """
    if not path.is_absolute():
        raise ValueError("An absolute path is required.")
    if ".." in path.parts:
        raise ValueError("Parent traversal is not permitted.")
    resolved = path.resolve()
    for root in allowed_directories:
        if not root.is_absolute():
            raise ValueError("Allowed directories must be absolute.")
        canonical_root = root.resolve(strict=True)
        if canonical_root == Path(canonical_root.anchor) or not canonical_root.is_dir():
            raise ValueError("An allowed root must be a directory, not a drive root.")
        if resolved.is_relative_to(canonical_root):
            return resolved
    raise PermissionError("Path is outside configured allowed directories.")
