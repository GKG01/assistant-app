"""Opt-in live integration check: python -m scripts.check_agent_tools.

Uses the real provider via FastAPI with temporary files/database and a temporary
managed-session credential. Reports tool names/status only, never credentials.
"""

import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from config.settings import Settings
from main import create_app


def main() -> int:
    settings = Settings()
    if not settings.openai_api_key.get_secret_value().strip():
        print("SKIPPED: OPENAI_API_KEY is not configured.")
        return 0
    with TemporaryDirectory(prefix="nova-live-") as temporary:
        root = Path(temporary) / "documents"
        root.mkdir()
        (root / "resume.pdf").touch()
        (root / "notes.pdf").touch()
        configuration = settings.model_copy(
            update={
                "nova_database_path": Path(temporary) / "index.db",
                "nova_allowed_directories": [root],
            }
        )
        token = secrets.token_hex(32)
        with TestClient(
            create_app(configuration, session_token=token),
            headers={
                "Authorization": f"Bearer {token}",
                "X-Nova-Request": "1",
            },
        ) as client:
            assert client.post("/files/index").status_code == 200
            file_id = client.get("/files/search").json()["results"][0]["id"]
            calls: list[tuple[str, str]] = []
            dispatch = client.app.state.permissions.dispatch

            def traced(call, **kwargs):
                result = dispatch(call, **kwargs)
                calls.append((call.tool, result.status))
                return result

            client.app.state.permissions.dispatch = traced
            checks = [
                ("What is 5293 + 824 + 192? Use the calculator tool.", "calculate"),
                (
                    "Find the five most recently modified PDF files in my indexed folders.",
                    "search_files",
                ),
                ("Find files with resume in the filename.", "search_files"),
                (f"Get information about indexed file ID {file_id}.", "get_file_info"),
            ]
            for prompt, expected in checks:
                calls.clear()
                response = client.post("/agent/message", json={"message": prompt})
                print(f"{expected}: HTTP {response.status_code}; dispatches={calls}")
                if response.status_code != 200 or (expected, "completed") not in calls:
                    print("FAILED: expected successful tool dispatch was not verified.")
                    return 1
            print("PASSED: all four live API requests executed the expected tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
