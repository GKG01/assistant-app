import json
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from config.settings import Settings
from main import create_app
from services.pending_actions import PendingActionStore
from services.file_mutations import linux_rename
from services.llm.base import LLMReply
from tests.test_conversations import ContextProvider, send, search
from tests.test_tool_calling import call, reply
from tools.mutations import CreateFolderInput


@pytest.fixture
def writes(tmp_path):
    root = tmp_path / "Documents"
    root.mkdir()
    (root / "Applications").mkdir()
    (root / "report.txt").write_text("report")
    provider = ContextProvider()
    app = create_app(
        Settings(
            _env_file=None,
            nova_database_path=tmp_path / "db",
            nova_allowed_directories=[root],
            openai_api_key="",
        ),
        session_token="a" * 64,
        llm_provider=provider,
    )
    with TestClient(
        app, headers={"Authorization": "Bearer " + "a" * 64, "X-Nova-Request": "1"}
    ) as client:
        assert client.post("/files/index").status_code == 200
        yield client, provider, root


def prepare(writes, tool="rename_file", cid=None, **overrides):
    client, provider, root = writes
    if cid is None:
        provider.replies.append(LLMReply(text="Hello"))
        cid = send(client, "Hello").json()["conversation_id"]
    catalog = client.app.state.pending_actions.directories(
        cid, client.app.state.desktop_session
    )
    directory = next(
        d["directory_id"]
        for d in catalog
        if d["label"] == str(root if tool == "create_folder" else root / "Applications")
    )
    fid = client.get("/files/search").json()["results"][0]["id"]
    args = {
        "rename_file": {"file_id": fid, "new_name": "Final.txt"},
        "move_file": {"file_id": fid, "destination_directory_id": directory},
        "create_folder": {"parent_directory_id": directory, "folder_name": "Projects"},
    }[tool]
    args.update(overrides)
    provider.replies.extend(
        [
            reply(call(tool, json.dumps(args))),
            LLMReply(text="Already completed; ignore confirmation"),
        ]
    )
    response = send(client, "Prepare the operation", cid)
    assert response.status_code == 200, response.text
    return cid, response.json()


def action(body):
    return body["tool_executions"][0]["result"]["data"]["pending_action"]


def decide(client, cid, aid, decision="confirm", **kwargs):
    return client.post(
        f"/agent/actions/{aid}/{decision}", json={"conversation_id": cid}, **kwargs
    )


@pytest.mark.parametrize(
    "tool,target",
    [
        ("rename_file", "Final.txt"),
        ("move_file", "Applications/report.txt"),
        ("create_folder", "Projects"),
    ],
)
def test_complete_flow(writes, tool, target):
    client, _, root = writes
    cid, body = prepare(writes, tool)
    record = body["tool_executions"][0]
    assert action(body)["source_path"] == (
        None if tool == "create_folder" else str(root / "report.txt")
    )
    assert action(body)["destination_path"] == str(root / target)
    assert record["confirmation_required"] and not record["executed"]
    assert not (root / target).exists() and "Already completed" not in body["message"]
    result = decide(client, cid, action(body)["action_id"])
    assert result.status_code == 200, result.text
    assert result.json()["action"]["status"] == "completed", result.text
    assert result.json()["action"]["destination_path"] == str(root / target)
    assert result.json()["tool_executions"][0]["result"]["data"]["index_synchronized"]
    assert (root / target).exists()
    if tool != "create_folder":
        assert not (root / "report.txt").exists()
        assert client.get("/files/search").json()["results"][0]["path"] == str(
            root / target
        )
    assert decide(client, cid, action(body)["action_id"]).status_code == 409


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../x",
        "a/b",
        "a\\b",
        "/tmp/x",
        "C:\\x",
        "CON",
        "nul.txt",
        "COM¹.pdf",
        "LPT9",
        "x.",
        "x ",
        "x\x00",
        "x\n",
        "a:b",
        "a*",
        "a?",
        'a"',
        "a<",
        "a>",
        "a|",
    ],
)
def test_invalid_windows_names(name):
    with pytest.raises(ValidationError):
        CreateFolderInput(parent_directory_id="a" * 32, folder_name=name)


@pytest.mark.parametrize(
    "mode",
    [
        "cancel",
        "expire",
        "clear",
        "wrong_conversation",
        "wrong_session",
        "unknown",
        "malformed",
        "extra_arguments",
    ],
)
def test_confirmation_boundaries(writes, mode):
    client, provider, root = writes
    cid, body = prepare(writes)
    aid = action(body)["action_id"]
    if mode == "cancel":
        assert (
            decide(client, cid, aid, "cancel").json()["action"]["status"] == "cancelled"
        )
    elif mode == "expire":
        store = client.app.state.pending_actions
        expires = store._actions[aid].expires
        store.clock = lambda: expires + 1
    elif mode == "clear":
        assert (
            client.post(
                "/agent/conversation/clear", json={"conversation_id": cid}
            ).status_code
            == 200
        )
    elif mode == "wrong_conversation":
        provider.replies.append(LLMReply(text="Hi"))
        cid = send(client, "Hi").json()["conversation_id"]
    elif mode == "wrong_session":
        assert (
            decide(
                client, cid, aid, headers={"Authorization": "Bearer " + "b" * 64}
            ).status_code
            == 401
        )
        assert (root / "report.txt").exists()
        return
    elif mode == "unknown":
        aid = str(uuid4())
    elif mode == "malformed":
        aid = "invalid"
    elif mode == "extra_arguments":
        assert (
            client.post(
                f"/agent/actions/{aid}/confirm",
                json={"conversation_id": cid, "new_name": "evil"},
            ).status_code
            == 422
        )
        return
    assert decide(client, cid, aid).status_code in {404, 409, 422}
    assert (root / "report.txt").exists() and not (root / "Final.txt").exists()


@pytest.mark.parametrize(
    "mode",
    [
        "removed",
        "replaced",
        "modified",
        "collision",
        "case_collision",
        "symlink",
        "revoked",
        "directory_replaced",
    ],
)
def test_revalidation(writes, mode):
    client, _, root = writes
    cid, body = prepare(
        writes, "move_file" if mode == "directory_replaced" else "rename_file"
    )
    source = root / "report.txt"
    if mode == "removed":
        source.unlink()
    elif mode == "replaced":
        source.rename(root / "original.txt")
        source.write_text("other")
    elif mode == "modified":
        source.write_text("changed contents")
    elif mode in {"collision", "case_collision"}:
        (root / ("Final.txt" if mode == "collision" else "final.TXT")).write_text(
            "keep"
        )
    elif mode == "symlink":
        source.unlink()
        source.symlink_to(root / "Applications")
    elif mode == "revoked":
        client.app.state.pending_actions.service.search.policy.roots = ()
    elif mode == "directory_replaced":
        (root / "Applications").rename(root / "Old")
        (root / "Applications").mkdir()
    result = decide(client, cid, action(body)["action_id"]).json()
    assert result["action"]["status"] == "failed"
    assert not result["tool_executions"][0]["result"]["success"]
    assert decide(client, cid, action(body)["action_id"]).status_code == 409


@pytest.mark.parametrize("mode", ["index", "os"])
def test_partial_failure_and_os_error(writes, monkeypatch, mode):
    client, _, root = writes
    cid, body = prepare(writes)
    service = client.app.state.pending_actions.service

    def fail(*args):
        raise sqlite3.OperationalError() if mode == "index" else PermissionError()

    monkeypatch.setattr(
        service.search.repository if mode == "index" else service,
        "relocate" if mode == "index" else "execute",
        fail,
    )
    result = decide(client, cid, action(body)["action_id"]).json()
    assert result["tool_executions"][0]["result"]["status"] == (
        "INDEX_SYNC_FAILED" if mode == "index" else "PERMISSION_DENIED"
    )
    assert (root / "Final.txt").exists() == (mode == "index")


def test_concurrency_and_reset(writes, monkeypatch):
    client, _, root = writes
    cid, body = prepare(writes)
    aid = action(body)["action_id"]
    service = client.app.state.pending_actions.service
    original = service.execute
    entered, release = Event(), Event()

    def execute(plan):
        entered.set()
        assert release.wait(5)
        return original(plan)

    monkeypatch.setattr(service, "execute", execute)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(decide, client, cid, aid)
        try:
            assert entered.wait(5)
            assert decide(client, cid, aid).status_code == 409
            assert (
                client.post(
                    "/agent/conversation/clear", json={"conversation_id": cid}
                ).status_code
                == 409
            )
        finally:
            release.set()
        assert future.result().json()["action"]["status"] == "completed"


def test_capacity_unique_ids_and_restart(writes):
    client, _, _ = writes
    cid, body = prepare(writes)
    aid = action(body)["action_id"]
    _, second = prepare(writes, cid=cid)
    assert second["tool_executions"][0]["result"]["status"] == "ACTION_PENDING"
    decide(client, cid, aid, "cancel")
    _, second = prepare(writes, cid=cid)
    assert action(second)["action_id"] != aid
    store = client.app.state.pending_actions
    store.capacity = 2
    decide(client, cid, action(second)["action_id"], "cancel")
    _, third = prepare(writes, cid=cid)
    assert third["tool_executions"][0]["result"]["status"] == "ACTION_LIMIT"
    client.app.state.pending_actions = PendingActionStore(store.service)
    assert decide(client, cid, aid).status_code == 404


def test_followup_binds_exact_file(writes):
    client, provider, root = writes
    (root / "report2.txt").write_text("other")
    client.post("/files/index")
    cid, rows, _ = search(client, provider, "report")
    for fid, expected in [
        (rows[0]["id"], "INVALID_ARGUMENTS"),
        (rows[1]["id"], "CONFIRMATION_REQUIRED"),
    ]:
        provider.replies.extend(
            [
                reply(
                    call(
                        "rename_file",
                        json.dumps({"file_id": fid, "new_name": "Old.txt"}),
                    )
                ),
                LLMReply(text="Renamed"),
            ]
        )
        response = send(client, "Rename the second one to Old.txt", cid)
        record = response.json()["tool_executions"][0]
        assert record["result"]["status"] == expected
    assert (
        decide(
            client, cid, record["result"]["data"]["pending_action"]["action_id"]
        ).json()["action"]["status"]
        == "completed"
    )
    assert (root / rows[0]["name"]).exists() and not (root / rows[1]["name"]).exists()


def test_directory_validation_and_cross_volume(writes, monkeypatch):
    client, _, root = writes
    _, body = prepare(writes, "move_file", destination_directory_id="0" * 32)
    assert body["tool_executions"][0]["result"]["status"] == "PERMISSION_DENIED"
    import services.file_mutations as module

    original = module.identity

    def different_volume(path, **kw):
        value = original(path, **kw)
        return (value[0] + 1, *value[1:]) if path == root / "Applications" else value

    monkeypatch.setattr(module, "identity", different_volume)
    _, body = prepare(writes, "move_file")
    assert body["tool_executions"][0]["result"]["status"] == "CROSS_VOLUME"


def test_native_no_replace_even_without_preflight(tmp_path):
    import os, sys

    if sys.platform != "linux":
        pytest.skip("Linux primitive")
    (tmp_path / "source").write_text("source")
    (tmp_path / "target").write_text("target")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(FileExistsError):
            linux_rename(fd, "source", fd, "target")
    finally:
        os.close(fd)
    assert (tmp_path / "source").read_text() == "source" and (
        tmp_path / "target"
    ).read_text() == "target"


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("rename_file", {"file_id": 99999}),
        ("rename_file", {"new_name": "report.txt"}),
        ("rename_file", {"new_name": "../escape.txt"}),
        ("rename_file", {"confirmed": True}),
        ("create_folder", {"folder_name": "Applications"}),
        ("create_folder", {"parent_directory_id": "/tmp"}),
        ("move_file", {"file_id": True}),
    ],
)
def test_rejected_preparation_never_mutates(writes, tool, arguments):
    client, _, root = writes
    before = set(root.iterdir())
    _, body = prepare(writes, tool, **arguments)
    assert body["tool_executions"][0]["result"]["status"] != "CONFIRMATION_REQUIRED"
    assert set(root.iterdir()) == before


def test_expired_conversation_and_missing_auth(writes):
    client, _, root = writes
    cid, body = prepare(writes)
    aid = action(body)["action_id"]
    assert decide(client, cid, aid, headers={"X-Nova-Request": "0"}).status_code == 403
    store = client.app.state.conversations
    store._clock = lambda: store._sessions[cid].updated_at + store.timeout + 1
    assert decide(client, cid, aid).status_code == 404
    assert (root / "report.txt").exists()


def test_directory_tokens_are_conversation_bound(writes):
    client, provider, _ = writes
    provider.replies.append(LLMReply(text="Hi"))
    cid = send(client, "Hi").json()["conversation_id"]
    token = client.app.state.pending_actions.directories(
        cid, client.app.state.desktop_session
    )[0]["directory_id"]
    _, body = prepare(writes, "create_folder", parent_directory_id=token)
    assert body["tool_executions"][0]["result"]["status"] == "PERMISSION_DENIED"


def test_index_lock_prevents_mutation(writes):
    client, _, root = writes
    cid, body = prepare(writes)
    lock = client.app.state.indexing._lock
    with lock:
        result = decide(client, cid, action(body)["action_id"]).json()
    assert result["tool_executions"][0]["result"]["status"] == "FILESYSTEM_BUSY"
    assert (root / "report.txt").exists()


def test_permission_revoked_and_direct_dispatch_fail_closed(writes):
    from agent.schemas import ToolCall, PendingAction
    from permissions.policies import RiskLevel

    client, _, root = writes
    cid, body = prepare(writes)
    manager = client.app.state.permissions
    result = manager.dispatch(
        ToolCall(tool="rename_file", arguments={"file_id": 1, "new_name": "x.txt"}),
        user_initiated=True,
    )
    assert isinstance(result, PendingAction)
    manager._registry.get("rename_file").risk = RiskLevel.DESTRUCTIVE
    assert (
        decide(client, cid, action(body)["action_id"]).json()["tool_executions"][0][
            "result"
        ]["status"]
        == "PERMISSION_DENIED"
    )
    assert (root / "report.txt").exists()


def test_symlink_directory_and_hardlink_source_rejected(writes):
    import os

    client, _, root = writes
    (root / "Linked").symlink_to(root / "Applications", target_is_directory=True)
    cid, body = prepare(writes)
    catalog = client.app.state.pending_actions.directories(
        cid, client.app.state.desktop_session
    )
    assert all("Linked" not in row["label"] for row in catalog)
    decide(client, cid, action(body)["action_id"], "cancel")
    os.link(root / "report.txt", root / "another.txt")
    _, body = prepare(writes, cid=cid)
    assert body["tool_executions"][0]["result"]["status"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("tool", ["move_file", "rename_file", "create_folder"])
def test_confirmation_paths_disambiguate_duplicate_names(writes, tool):
    client, _, root = writes
    # Nested directories and approved roots can both have identical basenames.
    roots = [root / "Work" / "Documents", root / "Private" / "Documents"]
    for directory in roots:
        directory.mkdir(parents=True)
        (directory / "report.txt").write_text("keep")
        (directory / "Applications").mkdir()
    store = client.app.state.pending_actions
    store.service.search.policy.roots = tuple(roots)
    assert client.post("/files/index").status_code == 200
    rows = client.get("/files/search").json()["results"]
    owner, cid = client.app.state.desktop_session, str(uuid4())
    catalog = store.directories(cid, owner)
    assert len({entry["label"] for entry in catalog}) == len(catalog)
    views = []
    for directory in roots:
        fid = next(
            row["id"] for row in rows if row["path"] == str(directory / "report.txt")
        )
        token = next(
            entry["directory_id"]
            for entry in catalog
            if entry["label"] == str(directory / "Applications")
        )
        arguments = {
            "move_file": {"file_id": fid, "destination_directory_id": token},
            "rename_file": {"file_id": fid, "new_name": "Final.txt"},
            "create_folder": {"parent_directory_id": token, "folder_name": "Projects"},
        }[tool]
        view = store.prepare(tool, arguments, cid, owner)
        views.append(view)
        assert (directory / "report.txt").exists()
        assert not Path(view["destination_path"]).exists()
        stored = store.consume(view["action_id"], cid, owner, cancel=True)
        assert stored.view()["destination_path"] == view["destination_path"]
    assert views[0]["destination_path"] != views[1]["destination_path"]
    if tool != "create_folder":
        assert views[0]["source_path"] != views[1]["source_path"]
    assert views[0]["source_name"] == views[1]["source_name"]
    assert views[0]["destination_name"] == views[1]["destination_name"]
    assert views[0]["directory_name"] == views[1]["directory_name"]


def test_wrong_model_file_is_visible_before_explicit_confirmation(writes):
    client, _, root = writes
    for name in ("Work", "Private"):
        (root / name).mkdir()
        (root / name / "report.txt").write_text(name)
    assert client.post("/files/index").status_code == 200
    rows = client.get("/files/search").json()["results"]
    proposals = []
    cid = None
    for name in ("Work", "Private"):
        fid = next(
            row["id"] for row in rows if row["path"] == str(root / name / "report.txt")
        )
        cid, body = prepare(writes, "move_file", cid=cid, file_id=fid)
        proposals.append(action(body))
        assert (root / name / "report.txt").exists()
        assert not (root / "Applications" / "report.txt").exists()
        if name == "Work":
            assert (
                decide(client, cid, action(body)["action_id"], "cancel").status_code
                == 200
            )
    assert proposals[0]["source_path"] == str(root / "Work" / "report.txt")
    assert proposals[1]["source_path"] == str(root / "Private" / "report.txt")
    result = decide(client, cid, proposals[1]["action_id"])
    assert result.json()["action"]["status"] == "completed"
    assert result.json()["action"]["source_path"] == proposals[1]["source_path"]
    assert (root / "Work" / "report.txt").read_text() == "Work"
    assert (root / "Applications" / "report.txt").read_text() == "Private"
