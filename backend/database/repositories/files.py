from typing import Any

from database.database import Database


class FileRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def find_by_name(self, name: str, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000.")
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM files WHERE instr(lower(name), lower(?)) > 0 LIMIT ?",
                (name, limit),
            ).fetchall()
        return [dict(row) for row in rows]
