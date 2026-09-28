import pytest
import secrets
from fastapi.testclient import TestClient

from config.settings import Settings
from main import create_app
from database.database import Database
from database.repositories.files import FileRepository
from indexer.file_indexer import FileIndexer
from permissions.paths import PathPolicy
from services.file_search import FileSearchService


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, nova_database_path=tmp_path / "test.db",
                        openai_api_key="", nova_allowed_directories=[])
    token = secrets.token_hex(32)
    with TestClient(create_app(settings, session_token=token),
                    headers={"Authorization": f"Bearer {token}"}) as instance:
        yield instance


@pytest.fixture
def file_stack(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    database = Database(tmp_path / "index.db")
    database.initialize()
    repository = FileRepository(database)
    policy = PathPolicy([root])
    return root, database, repository, FileIndexer(policy, repository), FileSearchService(repository, policy)


@pytest.fixture
def file_client(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    settings = Settings(_env_file=None, nova_database_path=tmp_path / "index.db",
                        openai_api_key="", nova_allowed_directories=[root])
    token = secrets.token_hex(32)
    with TestClient(create_app(settings, session_token=token),
                    headers={"X-Nova-Request": "1", "Authorization": f"Bearer {token}"}) as instance:
        yield instance, root
