import json

import pytest

from database.database import Database
from database.repositories.actions import ActionRepository
from database.repositories.files import FileRepository


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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    with pytest.raises(ValueError):
        FileRepository(database).find_by_name("file", limit=0)
