import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from database.repositories.files import FileRepository
from permissions.paths import PathPolicy
from services.file_models import FileMetadata, IndexStats


class FileIndexer:
    def __init__(self, policy: PathPolicy, repository: FileRepository,
                 excluded_paths: tuple[Path, ...] = ()) -> None:
        self.policy = policy
        self.repository = repository
        self.excluded_paths = frozenset(os.path.normcase(str(path.absolute())) for path in excluded_paths)

    def index(self, directory: Path) -> IndexStats:
        start = perf_counter()
        root = self.policy.validate_root(directory)
        result = IndexStats(roots_indexed=1)
        indexed_at = datetime.now(timezone.utc)
        records: list[FileMetadata] = []
        protected: list[str] = []
        pending = [root]

        while pending:
            folder = pending.pop()
            try:
                safe_folder = self.policy.validate(folder, must_exist=True)
                with os.scandir(safe_folder) as entries:
                    for entry in entries:
                        path = Path(entry.path)
                        try:
                            safe = self.policy.validate(path, must_exist=True)
                            if str(safe) in self.excluded_paths:
                                result.skipped += 1
                                continue
                            info = safe.lstat()
                            if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                                raise PermissionError("Reparse point changed during validation.")
                            if stat.S_ISDIR(info.st_mode):
                                pending.append(safe)
                            elif stat.S_ISREG(info.st_mode):
                                # stat only: never open, hash, parse, or hydrate file contents.
                                records.append(FileMetadata(
                                    name=path.name, extension=path.suffix.casefold(),
                                    path=str(safe), size=info.st_size,
                                    created_at=datetime.fromtimestamp(
                                        getattr(info, "st_birthtime", info.st_ctime), timezone.utc),
                                    modified_at=datetime.fromtimestamp(info.st_mtime, timezone.utc),
                                    indexed_at=indexed_at,
                                ))
                            else:
                                result.skipped += 1
                        except (OSError, ValueError, RuntimeError, OverflowError):
                            result.skipped += 1
                            protected.append(str(path))
            except (OSError, ValueError, RuntimeError):
                if folder == root:
                    # A missing/inaccessible root cannot justify deleting its index.
                    raise PermissionError("Configured directory cannot be scanned.") from None
                result.skipped += 1
                protected.append(str(folder))

        counts = self.repository.refresh_root(str(root), records, protected)
        for name, value in counts.items():
            setattr(result, name, value)
        result.indexed = len(records)
        result.duration_ms = round((perf_counter() - start) * 1000)
        if result.skipped:
            result.warnings.append("Some entries were skipped; inaccessible entries retain prior metadata.")
        return result
