# Nova

Nova is a local-first, Windows-first desktop personal/admin assistant.
Phase 2 provides deterministic local file indexing and search. Feature 3.1 adds
text-only AI responses through OpenAI. The backend still starts without a provider
key; deterministic file features remain available. Voice remains a stub.

## Architecture and stack

React, strict TypeScript, Vite, Tailwind CSS, and Tauri 2 form the desktop.
Python 3.12+, FastAPI, Pydantic v2, and standard-library SQLite form the backend.

- **BRAIN:** text generation, isolated behind a provider interface; no tools yet.
- **HANDS:** explicit metadata search/info and Windows open/reveal tools.
- **GUARD:** registered risk, direct-user-action checks, and centralized path policy.

```text
nova/
├── desktop/src/             # UI, file cards, API client, types, formatters
├── desktop/src-tauri/       # Minimal native host; no filesystem/shell permissions
├── backend/
│   ├── api/                 # FastAPI HTTP contracts
│   ├── agent/               # Explicit registry and future reasoning contracts
│   ├── permissions/         # Risk dispatch and path policy
│   ├── tools/               # Calculator, search/info, open/reveal
│   ├── services/            # Shared file application logic; LLM provider
│   ├── indexer/             # Metadata scanner
│   ├── database/            # Schema migration and repositories
│   ├── config/
│   └── tests/
├── data/                    # Local SQLite, excluded from Git
└── docs/
```

See [Architecture](docs/ARCHITECTURE.md) and [Security](docs/SECURITY.md).

## What works

- Health endpoint and backend status indicator.
- On-demand recursive metadata indexing of explicitly configured directories.
- Refreshes detect new/changed/deleted files without duplicates or reused IDs.
- Case-insensitive filename search, extension/directory/date/size filters, sorting,
  result counts, and pagination.
- UI search, extension/sort controls, refresh statistics, cards, Open and Show in Folder.
- Windows-native default-app opening of supported document/image types and Explorer selection.
- Guarded calculator and file tools, with automated tests using temporary files.

POST /agent/message returns text from the configured LLM. Tools are NOT connected
to the LLM. The voice route returns 501; Send and Mic stay disabled until later UI
integration. No conversation memory, content extraction, embeddings, background
watchers, or file move/rename/delete operations exist.

## Prerequisites

Use Python 3.12+ and Node.js 22.12+ with npm. On Ubuntu, install the venv package
matching Python, for example:

```bash
sudo apt update
sudo apt install python3.12-venv
```

Native Tauri also requires Rust and platform prerequisites.
See [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

## Backend: WSL/Ubuntu

From the repository root, copy the example only if you do not already have .env:

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Keep the default loopback address, `127.0.0.1:8000`, and use one worker.
Check `http://127.0.0.1:8000/health`; API docs are at `/docs`.
If `python` is Python 3.12+, `python -m venv .venv` is equivalent.

## Backend: Windows PowerShell

From the repository root, create .env only if it does not already exist:

```powershell
Copy-Item .env.example .env
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Optional activation: `.\.venv\Scripts\Activate.ps1` in PowerShell or
`.venv\Scripts\activate.bat` in Command Prompt. Direct Python commands above
avoid activation-policy issues. Keep Windows and WSL environments separate.

## Frontend and desktop

In another terminal, from the repository root:

```bash
cd desktop
npm install
npm run dev
```

Open `http://127.0.0.1:1420`. This browser preview is useful for layout work;
file operations require the managed Tauri desktop session.
For native Windows, install Windows Node/npm, Rust MSVC, Visual Studio Build Tools
with **Desktop development with C++**, Windows SDK, and WebView2. Follow
[Tauri's Windows prerequisites](https://v2.tauri.app/start/prerequisites/#windows).

Stop any separate Vite server, then from `desktop/`:

```powershell
npm run tauri dev
```

Tauri starts Vite itself on port 1420 and starts the FastAPI backend as a managed
child process. Do not run a second backend on port 8000 or reuse WSL node_modules.
`npm run tauri build` builds a native executable; installer bundling is disabled.

WSL supports backend tests and browser UI development. Tauri in WSL builds a Linux
app and needs Linux GTK/WebKit dependencies plus WSLg/display support. It does not
validate Windows behavior. Run the backend and Tauri natively on Windows for Open
and Show in Folder. There is no automatic Windows/WSL path conversion. Do not bind
the backend to all network interfaces to work around localhost forwarding.

## Configuration

The root .env is backend-only. Process environment overrides it; restart the
backend after editing it.

| Variable | Default | Meaning |
| --- | --- | --- |
| NOVA_ENV | development | Environment label |
| NOVA_DATABASE_PATH | data/nova.db | Repository-relative or absolute SQLite path |
| OPENAI_API_KEY | empty | Backend-only provider secret; optional for non-AI features |
| OPENAI_MODEL | gpt-4.1-mini | Responses-compatible text model |
| OPENAI_TIMEOUT_SECONDS | 30 | Total AI request deadline; greater than 0, at most 120 |
| OPENAI_MAX_OUTPUT_TOKENS | 1024 | Output cap including reasoning; 16–16384 |
| NOVA_ALLOWED_DIRECTORIES | [] | JSON array of explicit absolute native paths |

Example (replace with your real folders):

```dotenv
NOVA_ALLOWED_DIRECTORIES=["C:/Users/your-account/Documents","C:/Users/your-account/Downloads"]
```

Forward slashes in Windows JSON avoid backslash escaping. In WSL use Linux paths,
for example `["/home/your-account/Documents"]`. Empty configuration denies access.
No standard folder is auto-allowed. Symlinks, junctions, all reparse points (including
some OneDrive placeholders), UNC/device paths, whole drives, and system directories
are rejected. Configure ordinary local directories, not system folders or whole profiles.

The frontend backend URL is centralized in `desktop/src/services/api.ts`.
Changing it also requires deliberate CORS/CSP review. Never put keys in Vite assets.

## Indexing and searching

1. Configure folders and restart Python.
2. Click **Refresh Files** and wait for the actual statistics.
3. Search `resume`; optionally enter `pdf` or `.pdf` and choose a sort.
4. Click Open or Show in Folder on a result.

Indexing collects name, extension, canonical path, byte size, and UTC timestamps.
No file contents are read, hashed, or stored. Windows birth time is used where
available; Linux `created_at` falls back to ctime (metadata-change time), not a
guaranteed creation date.

Each root is persisted in one transaction with bulk upserts. Overlapping roots
are collapsed, scans are serialized per process, and no indexing occurs at startup.
Failed subtrees retain old records; a failed root never triggers stale cleanup.
Deleted entries are removed from **SQLite only**, never from disk. A rename
appears as a deletion plus a new file. Refresh updates indexed_at on every seen file.

Search reads SQLite and revalidates candidate paths against the current policy.
Revoked roots remain stored but are hidden. Deleted files may appear until refresh;
attempting to open a deleted file returns 404. Name substring matching is Unicode
casefolded; it requires scanning candidate name keys. B-tree indexes support name
sorting, extension, size, modified time, root ownership, and path ranges.
Memory use is proportional to one scanned root; this is not a million-file indexer.

Open supports `.pdf .txt .csv .png .jpg .jpeg .gif .bmp .webp .docx .xlsx .pptx`.
Other types can be indexed/revealed but not launched by Nova. Opening documents
still depends on local file associations and viewer security. Action responses
mean Windows accepted a launch request, not that the viewer rendered successfully.

### File API

All file requests require `X-Nova-Request: 1` and a per-launch Bearer session
issued only to the Tauri main window. The browser preview and a manually started
backend cannot access file endpoints.

| Endpoint | Behavior |
| --- | --- |
| POST /files/index | Refresh all configured roots; optional empty JSON body only |
| GET /files/search | Filtered indexed metadata and total count |
| GET /files/{id} | Indexed metadata for an existing allowed regular file |
| POST /files/{id}/open | Direct user request to open a supported file |
| POST /files/{id}/reveal | Direct user request to reveal a file in Explorer |

Search parameters: `q`, `extension`, `directory`, `modified_after`,
`modified_before`, `min_size`, `max_size`, `sort`, `limit`, `offset`.
Dates are ISO 8601; timezone-free dates mean UTC; bounds are inclusive.
Sizes are bytes. Sorts: `name_asc`, `name_desc`, `modified_asc`,
`modified_desc`, `size_asc`, `size_desc`. Limit defaults to 50 and is capped at
200; offset is capped at 1,000,000. Directory filters require an allowed native path.

```bash
These endpoints are exercised from the Tauri app. Requests without the managed
session return `401 Unauthorized`.
```

In PowerShell use `curl.exe`. Empty configuration returns 400 on refresh.
All roots failing returns 503 with statistics; partial success returns 200 with
warnings. Invalid filters return 422, disallowed paths/types 403, missing files
404, overlapping refresh requests 409, and unsupported Windows actions 501.
The UI waits up to ten minutes for refresh. A client timeout does not cancel a scan.

## Feature 3.1: text-only AI

### Pending live verification — postponed 2026-10-10

Automated tests with mocked providers passed, but successful text generation from
the real OpenAI API remains **unverified**. A manual request returned HTTP 429
with Nova's `rate_limit` error. The tester reported not having added API credits;
missing credits are the suspected cause, not a confirmed provider diagnosis.
Live verification is intentionally postponed until API credits are available.

- [ ] Once credits are available, run the manual request below with
  `Reply with exactly: Nova online`. Confirm HTTP 200 and a real text response
  in `message`, with `result` and `pending_action` both null.
- [ ] Record the verification date, configured model, and outcome here, without
  recording the API key. Until then, do not mark live integration as verified.

### Configuration and manual test

Install the updated backend requirements. Set these in the repository-root `.env`
(ignored by Git), or in the backend process environment, then restart the backend:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=1024
```

Fill in `OPENAI_API_KEY` locally; never put it in frontend configuration or source.
Only the key is required for AI. The other values above are defaults. Use a model
available to your API account that supports text generation through Responses.
The timeout is a total request deadline (maximum 120 seconds); SDK retries are
explicitly disabled. Output is capped at 1,024 tokens by default (including any
reasoning tokens); incomplete responses are reported as provider failures.

From `backend/`, start the standalone backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

From a second PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body '{"message":"Reply with exactly: Nova online"}'
```

On WSL/Linux, use `.venv/bin/python` in place of the Windows Python path, then:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/agent/message -H 'Content-Type: application/json' -d '{"message":"Reply with exactly: Nova online"}'
```

A successful response contains `message` plus the existing `result: null` and
`pending_action: null` placeholders. Every request is independent. Asking to open
or search files only produces text; no action can execute. The prompt asks Nova
to explain this limitation, but model text can still be inaccurate.

Messages must contain 1–10,000 characters and cannot be whitespace-only. Raw bodies
are capped at 128 KiB before JSON parsing, including chunked requests. Invalid
messages return 422; oversized bodies 413. Missing keys, authentication errors,
and connection failures return 503; rate limits 429; timeouts 504; invalid, empty,
incomplete or failed provider responses 502. Errors use `detail` with safe text.

This text-only endpoint is available to local API clients without a desktop session;
JSON content type is required and untrusted browser origins are rejected. Keep the
server on loopback: local processes can still consume your provider quota. File
APIs retain their separate managed-desktop authentication requirement.

The provider sends the system prompt and your message to OpenAI with `store=False`.
Nova does not save chat history or log prompts/responses; provider-side data handling
still applies. No indexed metadata, file contents, tool definitions, or credentials
are included in the model input. Without a key, `/health` and managed desktop file
operations work, while `/agent/message` returns "Nova's AI provider is not configured."

## Tests and checks

GitHub Actions runs frontend formatting and TypeScript checks, backend formatting,
and Rust formatting on all pull requests.

Install backend development tools and check formatting from `backend/`:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff format --check .
```

Use `python -m ruff format .` to apply backend formatting.

From backend with the virtual environment activated:

```bash
pytest
pytest -m performance -s
```

Tests create temporary files, mock launch operations, and never launch real viewers.
Agent tests use fake providers; SDK tests use in-memory HTTP transports. Automated
tests do not call OpenAI.
The performance test creates 5,000 empty temporary files and measures two refreshes
plus search, without a hard timing threshold. On Windows without symlink privileges,
symlink tests skip. Pure Windows path-syntax and mocked reparse checks run everywhere.

From desktop:

```bash
npm run format:check
npm run typecheck
npm run build
```

Use `npm run format` to apply frontend formatting. `package-lock.json` is retained;
use `npm ci` for reproducible clean installs.

From the repository root, check the native host with
`cargo +stable fmt --manifest-path desktop/src-tauri/Cargo.toml --all -- --check`.
Remove `-- --check` to apply Rust formatting.

## Security and storage

Windows Open/Show in Folder validates and holds metadata handles for the file and
its parent directories during dispatch. Reparse points, changed paths, and
conflicting write/delete handles are rejected. An external viewer may open the
path after these handles close; this is additional hardening, not complete race
elimination. Windows-native validation: from `backend`, run
`python -m pytest -q tests/permissions/test_windows_handles.py`.

Tools are explicitly registered. READ operations run through the guard.
INTERACTIVE open/reveal needs trusted direct-user context; model-shaped calls stay
pending. WRITE remains pending; DESTRUCTIVE remains denied. There is no generic
shell, subprocess, code-evaluation, or direct model database capability.

SQLite migrates Phase 1 to schema version 2, preserving existing IDs and actions.
Open/reveal record requests and launch failures; search results and file contents
are not logged. Data is not encrypted. .env, database files, and test/build artifacts
are excluded from Git. Tauri exposes only the narrowly scoped backend-session
command; it does not expose shell or filesystem commands.

Loopback and browser-origin checks do not protect against a malicious local process.
Concurrent filesystem replacement races cannot be fully eliminated by path checks;
see [Security](docs/SECURITY.md) for the implemented boundary and limits.

## Next step

Feature 3.2 — Read-Only Tool Calling, reviewed separately. Feature 3.1 does not
connect ToolRegistry to the model. Native Windows Open/Show in Folder validation,
voice, WRITE confirmation, and packaging remain separate work.

MIT licensed; see [LICENSE](LICENSE).
