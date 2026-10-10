import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from database.database import Database


class ActionRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def record(
        self,
        *,
        user_command: str,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        status: str,
    ) -> str:
        action_id = str(uuid4())
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO actions
                (id, timestamp, user_command, tool, arguments, result, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    action_id,
                    datetime.now(timezone.utc).isoformat(),
                    user_command,
                    tool,
                    json.dumps(arguments, allow_nan=False),
                    json.dumps(result, allow_nan=False) if result is not None else None,
                    status,
                ),
            )
        return action_id
