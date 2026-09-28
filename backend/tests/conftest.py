import pytest
from fastapi.testclient import TestClient

from config.settings import Settings
from main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, nova_database_path=tmp_path / "test.db",
                        openai_api_key="", nova_allowed_directories=[])
    with TestClient(create_app(settings)) as instance:
        yield instance
