import json

import pytest

from database.database import Database
from database.repositories.actions import ActionRepository
from database.repositories.files import FileRepository
from database.schema import SCHEMA


def test_database_and_repositories(tmp_path):
    database = Database(tmp_path / "data" / "nova.db")
    database.initialize()
    database.initialize()
    assert FileRepository(database).find_by_name("' OR 1=1 --") == []
    action_id = ActionRepository(database).record(
        user_command="Add numbers", tool="calculate", arguments={"operands": [1, 2]},
        result={"value": 3}, status="completed",
    )
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        assert json.loads(row["result"]) == {"value": 3}
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    with pytest.raises(ValueError):
        FileRepository(database).find_by_name("file", limit=0)


def test_version_one_migration_preserves_data(tmp_path):
    database = Database(tmp_path / "legacy.db")
    with database.connect() as connection:
        connection.executescript(SCHEMA)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (42, "Resume.pdf", ".pdf", str(tmp_path / "Resume.pdf"), 20,
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    action = ActionRepository(database).record(
        user_command="test", tool="calculate", arguments={}, result={}, status="completed",
    )
    database.initialize()
    database.initialize()
    assert FileRepository(database).get_file_by_id(42).name == "Resume.pdf"
    with database.connect() as connection:
        assert connection.execute("SELECT id FROM actions WHERE id = ?", (action,)).fetchone()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_future_schema_is_not_downgraded(tmp_path):
    database = Database(tmp_path / "future.db")
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError):
        database.initialize()
