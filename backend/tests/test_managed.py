import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

import managed


@pytest.mark.parametrize(
    "payload", ["", "{}", "[]", '{"token":"short"}', '{"token":null}']
)
def test_bootstrap_rejects_missing_or_invalid_secret(monkeypatch, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload + "\n"))
    with pytest.raises((ValueError, json.JSONDecodeError)):
        managed.read_token()


def test_bootstrap_reads_only_from_pipe(monkeypatch):
    token = secrets.token_hex(32)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"token": token}) + "\n"))
    assert managed.read_token() == token


@pytest.mark.skipif(
    os.name != "nt",
    reason="Managed Windows socket lifecycle is verified by Tauri/Rust tests on non-Windows hosts.",
)
def test_parent_pipe_closure_stops_child(tmp_path):
    # No HTTP requests, content access, or GUI launches; the database is disposable.
    env = dict(
        os.environ,
        NOVA_DATABASE_PATH=str(tmp_path / "index.db"),
        NOVA_ALLOWED_DIRECTORIES="[]",
        OPENAI_API_KEY="",
        NOVA_BACKEND_PORT="18080",
    )
    process = subprocess.Popen(
        [sys.executable, "-u", "managed.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    token = secrets.token_hex(32)
    try:
        process.stdin.write(json.dumps({"token": token}) + "\n")
        process.stdin.close()
        process.wait(timeout=12)
        stdout, stderr = process.stdout.read(), process.stderr.read()
        assert process.returncode == 0, (
            f"Managed backend did not exit cleanly: {stdout!r} {stderr!r}"
        )
        assert token not in stdout + stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
