import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from database.schema import FILE_INDEXES, FILES_V2, SCHEMA


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("Database schema is newer than this Nova version.")
            connection.executescript(SCHEMA)
            if version < 2:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ALTER TABLE files RENAME TO files_v1")
                connection.execute(FILES_V2)
                connection.create_function("casefold", 1, str.casefold)
                connection.create_function("normcase", 1, os.path.normcase)
                connection.execute("""
                    INSERT INTO files (id, name, name_key, extension, path, size,
                                       created_at, modified_at, indexed_at)
                    SELECT id, name, casefold(name), extension, normcase(path), size,
                           created_at, modified_at, indexed_at FROM files_v1
                """)
                connection.execute("DROP TABLE files_v1")
                connection.execute("PRAGMA user_version = 2")
            for statement in FILE_INDEXES:
                connection.execute(statement)
