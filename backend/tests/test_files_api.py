import sqlite3

import pytest

from services.file_actions import WindowsFileLauncher


def test_api_complete_flow(file_client, monkeypatch):
    client, root = file_client
    file = root / "Resume.pdf"
    file.touch()
    assert client.get("/health").status_code == 200
    first = client.post("/files/index")
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 1
    assert client.post("/files/index").json()["unchanged"] == 1
    response = client.get("/files/search", params={"q": "resume", "extension": "pdf"})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    file_id = response.json()["results"][0]["id"]
    assert client.get(f"/files/{file_id}").json()["name"] == "Resume.pdf"
    launched = []
    monkeypatch.setattr(WindowsFileLauncher, "open_file", lambda self, path: launched.append(("open", path)))
    monkeypatch.setattr(WindowsFileLauncher, "show_in_folder", lambda self, path: launched.append(("reveal", path)))
    assert client.post(f"/files/{file_id}/open").status_code == 200
    assert client.post(f"/files/{file_id}/reveal").status_code == 200
    assert launched == [("open", file), ("reveal", file)]
    file.unlink()
    assert client.post(f"/files/{file_id}/open").status_code == 404
    assert client.post("/files/index").json()["removed"] == 1
    assert client.get("/files/search").json()["total"] == 0


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 201}, {"offset": -1}, {"sort": "DROP TABLE files"},
    {"min_size": -1}, {"min_size": 10, "max_size": 1},
    {"modified_after": "bad"}, {"extension": "../"},
    {"modified_after": "2026-02-01", "modified_before": "2026-01-01"},
])
def test_invalid_filters(file_client, params):
    response = file_client[0].get("/files/search", params=params)
    assert response.status_code == 422, response.text


def test_header_origin_and_arbitrary_roots_rejected(file_client):
    client, root = file_client
    assert client.post("/files/index", json={"directory": str(root.parent)}).status_code == 422
    assert client.post("/files/index", headers={"X-Nova-Request": ""}).status_code == 403
    assert client.post("/files/index", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/files/search", params={"directory": str(root.parent)}).status_code == 403
    assert client.get("/files/search", params={"directory": str(root / "..")}).status_code == 400
    assert client.get("/files/search", params={"directory": str(root.parent / "documents-evil")}).status_code == 403
    assert client.post("/files/0/open").status_code == 422
    assert client.post("/files/999/open").status_code == 404


def test_executable_open_blocked(file_client, monkeypatch):
    client, root = file_client
    (root / "bad.exe").touch()
    client.post("/files/index")
    file_id = client.get("/files/search").json()["results"][0]["id"]
    monkeypatch.setattr(WindowsFileLauncher, "open_file", lambda *a: pytest.fail("Unsafe launch"))
    assert client.post(f"/files/{file_id}/open").status_code == 403


def test_unconfigured_index(client):
    assert client.post("/files/index", headers={"X-Nova-Request": "1"}).status_code == 400


def test_missing_root_is_not_treated_as_deleted(file_client):
    client, root = file_client
    (root / "keep.txt").touch()
    client.post("/files/index")
    root.rename(root.parent / "renamed")
    response = client.post("/files/index")
    assert response.status_code == 503
    assert response.json()["detail"]["statistics"]["roots_failed"] == 1
    with client.app.state.database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 1


def test_database_failure_is_sanitized(file_client, monkeypatch):
    client, _ = file_client
    def fail():
        raise sqlite3.OperationalError("sensitive internal path")
    monkeypatch.setattr(client.app.state.indexing, "refresh", fail)
    response = client.post("/files/index")
    assert response.status_code == 503
    assert "sensitive" not in response.text


def test_index_busy(file_client):
    client, _ = file_client
    with client.app.state.indexing._lock:
        assert client.post("/files/index").status_code == 409


def test_unsupported_platform(file_client, monkeypatch):
    client, root = file_client
    (root / "file.txt").touch()
    client.post("/files/index")
    file_id = client.get("/files/search").json()["results"][0]["id"]
    def unsupported(*args):
        raise NotImplementedError()
    monkeypatch.setattr(WindowsFileLauncher, "open_file", unsupported)
    assert client.post(f"/files/{file_id}/open").status_code == 501
