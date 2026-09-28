import secrets

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from config.settings import Settings
from main import create_app
from permissions.session import DesktopSession


@pytest.mark.parametrize("authorization", [None, "", "Bearer ", "Basic abc", "Bearer wrong", "Bearer é"])
def test_missing_or_malformed_token_is_unauthorized(authorization):
    with pytest.raises(HTTPException) as error:
        DesktopSession(secrets.token_hex(32)).authorize(authorization)
    assert error.value.status_code == 401


def test_session_without_token_fails_closed():
    with pytest.raises(HTTPException):
        DesktopSession(None).authorize("Bearer " + secrets.token_hex(32))


def test_token_from_previous_launch_is_rejected():
    old, current = secrets.token_hex(32), secrets.token_hex(32)
    session = DesktopSession(current)
    session.authorize("Bearer " + current)
    with pytest.raises(HTTPException):
        session.authorize("Bearer " + old)


@pytest.mark.parametrize(("method", "path"), [
    ("get", "/files/search"), ("post", "/files/index"),
    ("get", "/files/1"), ("post", "/files/1/open"), ("post", "/files/1/reveal"),
    ("get", "/session"),
])
def test_public_header_is_not_authentication(file_client, method, path):
    client, _ = file_client
    response = client.request(method, path, headers={"Authorization": ""})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_health_public_but_standalone_backend_cannot_execute(tmp_path):
    settings = Settings(_env_file=None, nova_database_path=tmp_path / "index.db",
                        nova_allowed_directories=[])
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/files/search", headers={"X-Nova-Request": "1"}).status_code == 401


def test_credential_not_in_responses_and_wrong_token_rejected(file_client):
    client, _ = file_client
    credential = client.headers["Authorization"].split(" ", 1)[1]
    response = client.get("/session")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert credential not in response.text
    response = client.get("/files/search", headers={"Authorization": "Bearer " + secrets.token_hex(32)})
    assert response.status_code == 401
    assert credential not in response.text


def test_authenticated_browser_still_needs_allowed_origin(file_client):
    client, _ = file_client
    assert client.get("/files/search", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/files/search", headers={"Origin": "http://127.0.0.1:1420"}).status_code == 200


def test_preflight_allows_authorization_only_for_trusted_origin(client):
    response = client.options("/files/search", headers={
        "Origin": "http://127.0.0.1:1420",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization,X-Nova-Request",
    })
    assert response.status_code == 200
