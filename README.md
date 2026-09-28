# Nova

Nova is a local-first, Windows-first desktop personal/admin assistant.
Phase 2 provides deterministic local file indexing and search. AI and voice remain
stubs: no provider key is required and no model is called.

## Architecture and stack

React, strict TypeScript, Vite, Tailwind CSS, and Tauri 2 form the desktop.
Python 3.12+, FastAPI, Pydantic v2, and standard-library SQLite form the backend.

- **BRAIN:** future reasoning, isolated behind a provider interface.
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
│   ├── services/            # Shared file application logic; provider stubs
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

Agent and voice routes return 501. Send and Mic stay disabled. No LLM, content
extraction, embeddings, background watchers, or file move/rename/delete operations exist.

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

Open `http://127.0.0.1:1420`. Keep the backend running separately.
For native Windows, install Windows Node/npm, Rust MSVC, Visual Studio Build Tools
with **Desktop development with C++**, Windows SDK, and WebView2. Follow
[Tauri's Windows prerequisites](https://v2.tauri.app/start/prerequisites/#windows).

Stop any separate Vite server, then from `desktop/`:

```powershell
npm run tauri dev
```

Tauri starts Vite itself on port 1420. Do not reuse WSL node_modules on Windows.
`npm run tauri build` builds a native executable; installer bundling is disabled.
Backend lifecycle/packaging remains separate: Tauri does not start Python.

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
| OPENAI_API_KEY | empty | Reserved, unused provider secret |
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

All file requests require `X-Nova-Request: 1`; untrusted browser Origins are
rejected. This header is CSRF hardening, not a secret or local-process authentication.
The browser client supplies it automatically.

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
curl -X POST -H "X-Nova-Request: 1" http://127.0.0.1:8000/files/index
curl -H "X-Nova-Request: 1" "http://127.0.0.1:8000/files/search?q=resume&extension=pdf&sort=modified_desc&limit=20"
```

In PowerShell use `curl.exe`. Empty configuration returns 400 on refresh.
All roots failing returns 503 with statistics; partial success returns 200 with
warnings. Invalid filters return 422, disallowed paths/types 403, missing files
404, overlapping refresh requests 409, and unsupported Windows actions 501.
The UI waits up to ten minutes for refresh. A client timeout does not cancel a scan.

## Tests and checks

From backend with the virtual environment activated:

```bash
pytest
pytest -m performance -s
```

Tests create temporary files, mock launch operations, and never launch real viewers.
The performance test creates 5,000 empty temporary files and measures two refreshes
plus search, without a hard timing threshold. On Windows without symlink privileges,
symlink tests skip. Pure Windows path-syntax and mocked reparse checks run everywhere.

From desktop:

```bash
npm run typecheck
npm run build
```

No frontend lint command is configured. `package-lock.json` is retained; use
`npm ci` for reproducible clean installs.

## Security and storage

Tools are explicitly registered. READ operations run through the guard.
INTERACTIVE open/reveal needs trusted direct-user context; model-shaped calls stay
pending. WRITE remains pending; DESTRUCTIVE remains denied. There is no generic
shell, subprocess, code-evaluation, or direct model database capability.

SQLite migrates Phase 1 to schema version 2, preserving existing IDs and actions.
Open/reveal record requests and launch failures; search results and file contents
are not logged. Data is not encrypted. .env, database files, and test/build artifacts
are excluded from Git. Tauri retains an empty native capability list.

Loopback and browser-origin checks do not protect against a malicious local process.
Concurrent filesystem replacement races cannot be fully eliminated by path checks;
see [Security](docs/SECURITY.md) for the implemented boundary and limits.

## Next step

Validate native Windows Open/Show in Folder with a disposable local folder.
Phase 3 can then add provider-neutral single-step reasoning over these existing
READ tools with strict output validation and permission-bypass tests. Voice,
WRITE confirmation, and packaging remain separate future work.

MIT licensed; see [LICENSE](LICENSE).
