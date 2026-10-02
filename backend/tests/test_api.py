import pytest


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nova-backend"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/agent/message", {"message": "Find my resume"}),
        ("post", "/voice/transcribe", None),
    ],
)
def test_unimplemented_routes(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]


def test_cors_rejects_unknown_origin(client):
    response = client.options(
        "/agent/message",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_host_rejected(client):
    assert (
        client.get("/health", headers={"host": "untrusted.example"}).status_code == 400
    )
