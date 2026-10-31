# Nova

Nova is a local-first, Windows-first desktop personal/admin assistant.
Phase 2 provides deterministic local file indexing and search. Features 3.1–3.4 add
AI responses, bounded structured tool calling, grounding, and guarded file interactions. The backend still starts without a provider
key; deterministic file features remain available. Voice remains a stub.

## Architecture and stack

React, strict TypeScript, Vite, Tailwind CSS, and Tauri 2 form the desktop.
Python 3.12+, FastAPI, Pydantic v2, and standard-library SQLite form the backend.

- **BRAIN:** provider-neutral text generation and structured tool requests.
- **HANDS:** explicit metadata search/info and Windows open/reveal tools.
- **GUARD:** registered risk, direct-user-action checks, and centralized path policy.

```text
nova/
├── desktop/src/             # UI, file cards, API client, types, formatters
├── desktop/src-tauri/       # Minimal native host; no filesystem/shell permissions
├── backend/
│   ├── api/                 # FastAPI HTTP contracts
│   ├── agent/               # Explicit registry and bounded agent orchestration
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

POST /agent/message returns text from the configured LLM, optionally using approved
tools: calculate, search_files, get_file_info, open_file, and show_in_folder. The voice route returns 501; Send and Mic stay disabled until later UI
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
| OPENAI_TIMEOUT_SECONDS | 30 | Deadline per provider call; greater than 0, at most 120 |
| OPENAI_MAX_OUTPUT_TOKENS | 1024 | Output cap including reasoning; 16–16384 |
| NOVA_ALLOWED_DIRECTORIES | [] | JSON array of explicit absolute native paths |
| NOVA_ALLOW_AGENT_REVEAL | false | Explicitly allow AI Explorer reveal for authenticated desktop requests; never authorizes AI opening |

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

## Feature 3.2: read-only AI tool calling

Features 3.1–3.4 are implemented. Each `/agent/message` request is independent;
there is no persistent conversation, chat UI integration, or write confirmation.
The existing response shape remains `message`, `result: null`, `pending_action: null`.

The agent sends approved schemas to the provider, receives structured tool calls,
validates JSON arguments, resolves the existing registry, checks the permission
manager, executes deterministic tools in the shared bounded threadpool, and returns
structured results to the model for its final text response. Ordinary model prose
is never parsed as a command. Only these tools are exposed:

| Tool | Model-facing arguments |
| --- | --- |
| `calculate` | Required `expression`: 1–500 characters; numeric literals, `+ - * /`, unary signs, parentheses, decimals |
| `search_files` | Optional `query` (filename substring), `extension`, `directory`, `modified_after`, `modified_before`, `min_size`, `max_size`, `sort`, `limit`, `offset` |
| `get_file_info` | Required `file_id`: integer 1–9223372036854775807 |
| `open_file` | Same strict `file_id`; confirmation required, no AI launch |
| `show_in_folder` | Same strict `file_id`; explicit backend policy or confirmation required |

Search reuses the SQLite metadata index; no scan or content read occurs. `query`
maps to the existing file API's `q`. Sort values are `name_asc`, `name_desc`,
`modified_asc` (oldest first), `modified_desc` (default), `size_asc`, `size_desc`.
Limit defaults to 20 and accepts 1–50; offset accepts 0–1,000,000. Dates must be
ISO 8601 strings, with timezone-free values interpreted as UTC. Size bounds are
inclusive integers from 0 to 2^63−1. Query/extension/directory limits are 500/30/4096
characters. Unknown fields, coercible wrong types, and invalid ranges are rejected.
The direct file API retains its existing 50 default / 200 maximum page size.

Every execution uses PermissionManager. READ tools retain their READ-only constraint;
open/reveal retain INTERACTIVE risk and the policy described below. Tool names,
implementation types and risk classifications must match the explicit allowlist.
Existing direct UI/API actions retain their explicit user authorization.
No shell, arbitrary Python, unrestricted SQL or file-content capability is exposed.
The calculator uses a restricted arithmetic AST, with at most 100 nodes and finite
intermediate magnitudes at most 1e100; no functions, variables, powers or attributes.
The existing deterministic operation/operands calculator contract remains supported
outside the agent.

Limits per request: **5 provider calls**, **10 tool calls**, **4 calls per model
response**, **8 KiB argument JSON per call**, **16 KiB serialized result per call**.
Calls run sequentially. An over-budget batch is not executed; the last iteration
cannot start more tools. The API returns a controlled partial-completion message.
Search results include `total`, `returned`, and `truncated`; whole records are removed
when necessary to fit the byte cap, preserving valid JSON. Other oversized results
return `RESULT_TOO_LARGE`. Empty searches succeed with an empty `results` array.
Tool failures return fixed structured errors to the model, without exception details.

### Configuration and access

Set backend-only `OPENAI_API_KEY` in the ignored root `.env` or process environment.
Defaults are `OPENAI_MODEL=gpt-4.1-mini`, `OPENAI_TIMEOUT_SECONDS=30`, and
`OPENAI_MAX_OUTPUT_TOKENS=1024`. Use an account-accessible Responses model supporting
function calling. Restart after changes. SDK retries are disabled; timeout and token
caps apply to each provider call, so a tool-assisted request can take longer than
one timeout period. No key is required to start the backend or use deterministic files.

Standalone `/agent/message` clients can use text and arithmetic. File tools require
**the same managed desktop Bearer credential and `X-Nova-Request: 1` header as the
file API**. Without them, file tools are omitted and explicit model requests for
those tools are denied. This prevents the agent from bypassing Phase 2's access gate.
Configure `NOVA_ALLOWED_DIRECTORIES` and refresh the index through the desktop before
searching real files. Requesting a search does not index files automatically.

The provider receives your prompt, tool schemas, and bounded returned metadata
(including filenames and full paths for authorized file requests). No file contents
are sent. `store=False` is used; provider-side data handling still applies. Nova
neither persists chat history nor logs prompts/results/secrets. Feature 3.3 adds conservative backend grounding of tool-assisted responses.

### Manual testing

From `backend/` on WSL/Linux:

```bash
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/agent/message -H 'Content-Type: application/json' -d '{"message":"Reply with exactly: Nova online"}'
curl -sS http://127.0.0.1:8000/agent/message -H 'Content-Type: application/json' -d '{"message":"What is 5293 + 824 + 192? Use the calculator tool."}'
```

To verify real tool execution, run this opt-in check from `backend/`:

```bash
.venv/bin/python -m scripts.check_agent_tools
```

On Windows use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`, and
`curl.exe` in place of `curl`. The check calls the real OpenAI provider through
FastAPI's in-process test client. It indexes temporary synthetic files into a
temporary SQLite database, supplies a temporary desktop credential, and verifies
successful calculator/search/info dispatches for four requests. It reports only
HTTP status and tool names/status, never the API key. It requires API credits.
No server process or changes to your personal index are required for this check.

**Live integration remains unverified.** During Feature 3.2 validation no API key
was configured, so live requests were skipped. The earlier Feature 3.1 manual
attempt returned HTTP 429; suspected missing credits were not confirmed.
Automated tests use fake providers and in-memory SDK transports, never real API calls.

Messages accept 1–10,000 nonblank characters; raw bodies are capped at 128 KiB.
Invalid requests return 422, oversized bodies 413. Missing key/authentication/network
failures return 503, rate limits 429, provider timeouts 504, malformed/incomplete
provider responses 502. Errors contain safe fixed text. `/health` remains available.
JSON and trusted browser-origin requirements remain enforced. Keep the server on
loopback; local processes can consume provider quota, and this is not a user login.

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
INTERACTIVE opening needs trusted direct-user context. AI reveal requires the
explicit backend setting; otherwise model requests remain confirmation-required. WRITE remains pending; DESTRUCTIVE remains denied. There is no generic
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

Feature 3.5 — Conversation Context. Features 3.5–3.8 are not implemented.
Native Windows Open/Show in Folder validation,
voice, WRITE confirmation, and packaging remain separate work.

MIT licensed; see [LICENSE](LICENSE).


## Feature 3.3: grounded responses

Request → orchestrator → model tool request → registry, validation and permissions
→ deterministic execution → verified result → model response → grounding → response.
Request-local execution records distinguish rejection, start, completion and failure.
The permission manager signals the actual execution start. Records are not persisted.
The existing result envelope gains `status`: SUCCESS, NO_RESULTS, NOT_FOUND,
INVALID_ARGUMENTS, UNKNOWN_TOOL, PERMISSION_DENIED, TOOL_ERROR or
EXECUTION_LIMIT_REACHED. Legacy error_code fields remain compatible. Provider
failures retain sanitized HTTP errors and never retry tools.

File responses use backend-rendered JSON metadata labeled as untrusted data;
multiple total matches ask the user to narrow the request, even with pagination.
Empty pages with nonzero totals are not described as no matches. Failure text is
fixed and sanitized. Calculator prose is retained only for exact verified numeric
answers; other answers use deterministic values. Ordinary text remains available.
A conservative keyword guard blocks common unverified local-action claims in
text-only responses; it is not a general natural-language truth verifier and can
produce false positives or miss paraphrases. Tool-assisted file prose is deliberately
conservative. Indexed metadata can be stale until refresh.

Tool strings remain JSON data, never privileged instructions. The existing exact
tool allowlist, desktop authorization and filesystem policy remain authoritative.
Feature 3.4 extends this boundary as documented below. No frontend, memory or
Features 3.5–3.8 are introduced.
Run `cd backend && .venv/bin/python -m pytest -q` for offline fake-provider tests.
Existing manual commands and provider configuration apply unchanged.

## Feature 3.4: file interaction tools

`open_file(file_id)` and `show_in_folder(file_id)` share Phase 2's tools,
FileActionService, SQLite ID lookup, canonical path policy, and Windows launcher.
Only positive strict integer IDs up to 2^63−1 are accepted. Extra fields, paths,
commands, application arguments and model-supplied confirmation are rejected.
Both tools require the existing managed desktop session and file request header.

Opening always returns `CONFIRMATION_REQUIRED` for a valid supported file, without
launching it. There is no confirmation/resume endpoint: use the existing desktop
Open button as a separate direct action. Reveal also defaults to confirmation.
Set `NOVA_ALLOW_AGENT_REVEAL=true` in backend configuration and restart to explicitly
permit AI reveal. This never permits AI opening or writes. The existing document
allowlist is reused case-insensitively: `.pdf .txt .csv .png .jpg .jpeg .gif .bmp
.webp .docx .xlsx .pptx`. All other types (including scripts, executables and shortcuts)
return `UNSUPPORTED_FILE_TYPE` for opening; they may be revealed under reveal policy.
The Phase 2 allowlist is retained for compatibility, not a guarantee of content safety.

Paths are revalidated even for pending requests. Missing records/files, replaced
directories, outside paths and symlink/reparse escapes fail safely. A chained
interaction requires the latest search in that request to return exactly one match
and the requested ID; pagination does not make an ambiguous search unique. Narrow
searches are allowed within the same request; no history survives the request.

Structured results retain `success`, `status`, `data`, `error_code`, `error_message`.
New statuses include `CONFIRMATION_REQUIRED`, `UNSUPPORTED_FILE_TYPE`, `OS_ERROR`,
and `UNSUPPORTED_PLATFORM`. Validation/permission failures use existing statuses.
Request-local execution records track argument validation, permission approval,
confirmation required and actual tool execution. Final text uses verified results;
success means Windows accepted a request, never that the viewer rendered the file.
The HTTP response shape stays unchanged, including null `pending_action`.

Windows-native Python is required for real OS interactions. WSL/Linux return a
structured unsupported-platform error for permitted reveal, with no shell fallback
or path conversion. Windows handle pinning is preserved; asynchronous viewer access
can still race after handles close. Explorer preview handlers and file associations
remain platform risks. Live OpenAI and real Windows GUI behavior remain unverified.

### Offline manual checks (no OpenAI credits)

Install `requirements-dev.txt`, then from `backend/`:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.check_file_interactions
```

The smoke check reuses the test-only scripted fake provider, creates a temporary
allowed directory, safe text file and SQLite index, and calls `/agent/message` via
FastAPI TestClient. It prints structured results and grounded text for reveal success
(mocked OS) and confirmation-required opening. It sets reveal authorization only
in the temporary app. No `.env`, real index, provider credentials or personal files
are needed. Security/path failures are covered by `tests/test_file_interactions.py`.

For an optional real Explorer check, run **native Windows PowerShell** from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_file_interactions --real-reveal
```

This reveals only the generated temporary `safe.txt`, waits for visual inspection,
then cleans up. Opening remains mocked and must never be called: confirmation is
not bypassed. Use `.\.venv\Scripts\python.exe` for the other commands on Windows.
Features 3.5–3.8, conversation storage, full chat UI and write confirmation are absent.
