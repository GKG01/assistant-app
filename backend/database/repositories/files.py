import os
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from database.database import Database
from services.file_models import FileMetadata, IndexedFile, SearchFilters, SearchResponse

SORTS = {
    "name_asc": "name_key ASC", "name_desc": "name_key DESC",
    "modified_asc": "modified_at ASC", "modified_desc": "modified_at DESC",
    "size_asc": "size ASC", "size_desc": "size DESC",
}


class FileRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def get_file_by_id(self, file_id: int) -> IndexedFile | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return IndexedFile.model_validate(dict(row)) if row else None

    def get_file_by_path(self, path: str) -> IndexedFile | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT * FROM files WHERE path = ?", (os.path.normcase(path),)).fetchone()
        return IndexedFile.model_validate(dict(row)) if row else None

    def get_files_for_root(self, root: str) -> list[IndexedFile]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM files WHERE root_path = ?", (os.path.normcase(root),)).fetchall()
        return [IndexedFile.model_validate(dict(row)) for row in rows]

    def refresh_root(self, root: str, files: Sequence[FileMetadata],
                     protected: Sequence[str]) -> dict[str, int]:
        """One atomic transaction per root. Failed subtrees retain previous records."""
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prefix = root.rstrip(os.sep) + os.sep
            upper = prefix[:-1] + chr(ord(prefix[-1]) + 1)
            previous = {row["path"]: dict(row) for row in connection.execute(
                "SELECT * FROM files WHERE path >= ? AND path < ?", (prefix, upper)
            )}
            counts = {"created": 0, "updated": 0, "unchanged": 0, "removed": 0}
            seen: set[str] = set()
            values: list[tuple[Any, ...]] = []
            fields = ("name", "extension", "size", "created_at", "modified_at")
            for file in files:
                item = file.model_dump(mode="json")
                seen.add(file.path)
                old = previous.get(file.path)
                if old is None:
                    counts["created"] += 1
                elif any(old[key] != item[key] for key in fields):
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
                values.append((file.name, file.name.casefold(), file.extension, file.path,
                               file.size, item["created_at"], item["modified_at"],
                               item["indexed_at"], root))
            connection.executemany(
                """INSERT INTO files
                (name, name_key, extension, path, size, created_at, modified_at, indexed_at, root_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                name=excluded.name, name_key=excluded.name_key, extension=excluded.extension,
                size=excluded.size, created_at=excluded.created_at,
                modified_at=excluded.modified_at, indexed_at=excluded.indexed_at,
                root_path=excluded.root_path""", values,
            )
            protected_paths = {Path(path) for path in protected}
            stale = [
                (old["id"],) for path, old in previous.items()
                if path not in seen and not protected_paths.intersection((Path(path), *Path(path).parents))
            ]
            connection.executemany("DELETE FROM files WHERE id = ?", stale)
            counts["removed"] = len(stale)
        return counts

    def search_files(self, filters: SearchFilters, allowed: Callable[[str], bool],
                     directory: str | None = None) -> SearchResponse:
        conditions: list[str] = []
        parameters: list[Any] = []
        if filters.q:
            conditions.append("instr(name_key, ?) > 0")
            parameters.append(filters.q.casefold())
        if filters.extension:
            conditions.append("extension = ?")
            parameters.append(filters.extension)
        if directory:
            prefix = directory.rstrip(os.sep) + os.sep
            conditions.append("path >= ? AND path < ?")
            parameters.extend([prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)])
        for value, column, operator in [
            (filters.min_size, "size", ">="), (filters.max_size, "size", "<="),
            (filters.modified_after, "modified_at", ">="),
            (filters.modified_before, "modified_at", "<="),
        ]:
            if value is not None:
                conditions.append(f"{column} {operator} ?")
                parameters.append(
                    value.isoformat(timespec="microseconds").replace("+00:00", "Z")
                    if isinstance(value, datetime) else value
                )
        conditions.append("nova_allowed(path) = 1")
        where = " AND ".join(conditions)
        with self._database.connect() as connection:
            connection.create_function("nova_allowed", 1, allowed)
            connection.execute("BEGIN")
            total = connection.execute(f"SELECT count(*) FROM files WHERE {where}", parameters).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM files WHERE {where} ORDER BY {SORTS[filters.sort]}, id ASC LIMIT ? OFFSET ?",
                [*parameters, filters.limit, filters.offset],
            ).fetchall()
        return SearchResponse(results=[IndexedFile.model_validate(dict(row)) for row in rows],
                              total=total, limit=filters.limit, offset=filters.offset)

    def find_by_name(self, name: str, limit: int = 100) -> list[dict[str, Any]]:
        # Internal compatibility API; HTTP/tools must use the policy-aware service.
        return [file.model_dump(mode="json") for file in self.search_files(
            SearchFilters(q=name, limit=limit), lambda _: True
        ).results]
