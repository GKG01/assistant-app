from threading import Lock
from time import perf_counter
from pathlib import Path

from indexer.file_indexer import FileIndexer
from services.file_models import IndexStats


class IndexBusyError(RuntimeError):
    pass


class FileIndexingService:
    def __init__(self, indexer: FileIndexer) -> None:
        self.indexer = indexer
        self._lock = Lock()

    def refresh(self) -> IndexStats:
        if not self._lock.acquire(blocking=False):
            raise IndexBusyError("An index refresh is already running.")
        try:
            start = perf_counter()
            if not self.indexer.policy.roots:
                raise ValueError("Configure NOVA_ALLOWED_DIRECTORIES before refreshing files.")
            # Collapse overlaps so a file has one owner and is counted once.
            roots = sorted(self.indexer.policy.roots, key=lambda root: len(root.parts))
            selected: list[Path] = []
            for root in roots:
                if not any(root.is_relative_to(parent) for parent in selected):
                    selected.append(root)
            total = IndexStats()
            for number, root in enumerate(selected, 1):
                try:
                    result = self.indexer.index(root)
                    for field in ("indexed", "created", "updated", "unchanged", "removed",
                                  "skipped", "roots_indexed"):
                        setattr(total, field, getattr(total, field) + getattr(result, field))
                    total.warnings.extend(result.warnings)
                except (OSError, ValueError, RuntimeError):
                    total.roots_failed += 1
                    total.skipped += 1
                    total.warnings.append(
                        f"Configured directory {number} is unavailable or disallowed; its index was preserved."
                    )
            total.duration_ms = round((perf_counter() - start) * 1000)
            return total
        finally:
            self._lock.release()
