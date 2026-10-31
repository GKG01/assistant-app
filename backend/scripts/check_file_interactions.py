"""Offline check; --real-reveal opts into Explorer for a temporary text file."""

import argparse
import json
import os
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from config.settings import Settings
from main import create_app
from services.file_actions import WindowsFileLauncher
from services.llm.base import LLMReply
from tests.test_tool_calling import ScriptedProvider, call, reply


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-reveal", action="store_true")
    args = parser.parse_args()
    if args.real_reveal and os.name != "nt":
        parser.error("Real Explorer reveal requires native Windows Python.")
    with TemporaryDirectory(prefix="nova-interaction-") as directory:
        base = Path(directory)
        root = base / "documents"
        root.mkdir()
        (root / "safe.txt").write_text("Nova synthetic test document", encoding="utf-8")
        provider = ScriptedProvider(
            [
                reply(call("show_in_folder", '{"file_id":1}')),
                LLMReply(text="The file was displayed."),
                reply(call("open_file", '{"file_id":1}', id="open")),
                LLMReply(text="The file was opened."),
            ]
        )
        settings = Settings(
            _env_file=None,
            nova_database_path=base / "index.db",
            nova_allowed_directories=[root],
            nova_allow_agent_reveal=True,
            openai_api_key="",
        )
        # Temporary in-process app; no production fake-provider switch or credentials.
        token = "a" * 64
        with patch.object(WindowsFileLauncher, "open_file") as opening:
            guard = (
                nullcontext()
                if args.real_reveal
                else patch.object(WindowsFileLauncher, "show_in_folder")
            )
            with (
                guard as reveal,
                TestClient(
                    create_app(settings, session_token=token, llm_provider=provider),
                    headers={"Authorization": f"Bearer {token}", "X-Nova-Request": "1"},
                ) as client,
            ):
                assert client.post("/files/index").json()["created"] == 1
                for name in ("show_in_folder", "open_file"):
                    response = client.post(
                        "/agent/message", json={"message": f"{name} indexed file 1"}
                    )
                    assert response.status_code == 200
                    print(response.json()["message"])
                for index, expected in ((1, "SUCCESS"), (3, "CONFIRMATION_REQUIRED")):
                    result = json.loads(
                        provider.requests[index][1]["turns"][0].results[0].output
                    )
                    print(json.dumps(result))
                    assert result["status"] == expected
                opening.assert_not_called()
                if not args.real_reveal:
                    reveal.assert_called_once_with(root / "safe.txt")
                else:
                    input(
                        "Check Explorer selected safe.txt; press Enter to remove temporary files. "
                    )
        print("Offline interaction check passed. No OpenAI requests were made.")


if __name__ == "__main__":
    main()
