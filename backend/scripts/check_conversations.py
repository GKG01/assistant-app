"""Offline Feature 3.5 demo with synthetic files and mocked OS interactions."""

import json
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
    with TemporaryDirectory(prefix="nova-context-") as directory:
        base = Path(directory)
        root = base / "documents"
        root.mkdir()
        for index in range(1, 4):
            (root / f"resume-{index}.txt").write_text(
                "Synthetic document", encoding="utf-8"
            )
        provider = ScriptedProvider([])
        settings = Settings(
            _env_file=None,
            nova_database_path=base / "index.db",
            nova_allowed_directories=[root],
            nova_allow_agent_reveal=True,
            openai_api_key="",
        )
        with (
            patch.object(WindowsFileLauncher, "open_file") as opening,
            patch.object(WindowsFileLauncher, "show_in_folder") as reveal,
            TestClient(
                create_app(settings, session_token="a" * 64, llm_provider=provider),
                headers={"Authorization": "Bearer " + "a" * 64, "X-Nova-Request": "1"},
            ) as client,
        ):
            assert client.post("/files/index").json()["created"] == 3
            provider.replies = iter(
                [
                    reply(call("search_files", '{"query":"resume","sort":"name_asc"}')),
                    LLMReply(text="Results"),
                ]
            )
            first = client.post("/agent/message", json={"message": "Find resumes"})
            assert first.status_code == 200
            cid = first.json()["conversation_id"]
            print("Conversation:", cid)
            print(first.json()["message"])
            search_result = json.loads(
                provider.requests[-1][1]["turns"][0].results[0].output
            )
            selected_id = search_result["data"]["results"][1]["id"]
            for tool, message, expected in (
                ("show_in_folder", "Show the second one in File Explorer", "SUCCESS"),
                ("open_file", "Open the second one", "CONFIRMATION_REQUIRED"),
            ):
                provider.replies = iter(
                    [
                        reply(call(tool, json.dumps({"file_id": selected_id}))),
                        LLMReply(text="Opened successfully"),
                    ]
                )
                result = client.post(
                    "/agent/message", json={"conversation_id": cid, "message": message}
                )
                assert result.status_code == 200
                print(result.json()["message"])
                outcome = json.loads(
                    provider.requests[-1][1]["turns"][0].results[0].output
                )
                assert outcome["status"] == expected
                print("Selected indexed ID:", selected_id, "Status:", expected)
            reveal.assert_called_once_with(root / "resume-2.txt")
            opening.assert_not_called()
            second = client.post(
                "/agent/message", json={"message": "Open the second one"}
            )
            assert second.json()["conversation_id"] != cid
            assert "No verified" in second.json()["message"]
            assert (
                client.post(
                    "/agent/conversation/clear", json={"conversation_id": cid}
                ).status_code
                == 200
            )
            assert (
                client.post(
                    "/agent/message",
                    json={"conversation_id": cid, "message": "Open the second one"},
                ).status_code
                == 404
            )
            print("Isolation and clearing verified.")
    print(
        "Offline conversation check passed. No network calls or real application launches."
    )


if __name__ == "__main__":
    main()
