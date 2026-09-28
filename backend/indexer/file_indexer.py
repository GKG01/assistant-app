from pathlib import Path
from collections.abc import Sequence

from permissions.paths import validate_path


class FileIndexer:
    def __init__(self, allowed_directories: Sequence[Path]) -> None:
        self._allowed_directories = tuple(allowed_directories)

    def index(self, directory: Path) -> int:
        validate_path(directory, self._allowed_directories)
        # Future: metadata only, explicit roots, no system-directory traversal,
        # no file contents, embeddings, or unbounded recursive scans.
        raise NotImplementedError("Metadata indexing is not implemented.")
