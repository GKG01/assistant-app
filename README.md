# Nova

Nova is a local-first, Windows-first desktop AI personal/admin assistant.
This repository is the V1 foundation, not a complete assistant.

## Scope and architecture

React in Tauri 2 communicates with a loopback FastAPI backend. Python 3.12+,
Pydantic v2, and SQLite support the backend. Vite, strict TypeScript, and
Tailwind CSS support the UI. npm is the only frontend package manager.

- **BRAIN:** a provider-neutral LLM interface proposes structured tool calls.
- **GUARD:** deterministic policy decides whether registered tools may execute.
- **HANDS:** explicit Python tools perform bounded operations.

See [Architecture](docs/ARCHITECTURE.md) and [Security](docs/SECURITY.md).

```text
nova/
├── desktop/
│   ├── src/          # React components, pages, hooks, API client, contracts
│   └── src-tauri/    # Minimal Rust host and restricted Tauri configuration
├── backend/
│   ├── api/          # HTTP boundary
│   ├── agent/        # Contracts, registry, orchestration stub
│   ├── permissions/  # Risk policies, dispatch, path validation
│   ├── tools/        # Calculator and future filesystem tool boundaries
│   ├── services/     # LLM and speech interfaces
│   ├── database/     # SQLite schema and repositories
│   ├── indexer/      # Metadata indexing stub
│   ├── config/
│   └── tests/
├── data/             # Local SQLite data; ignored by Git
└── docs/
```

## What works

- FastAPI startup initializes SQLite tables for file metadata and action records.
- `GET /health` returns `{"status":"ok","service":"nova-backend"}`.
- React displays backend connection status and refreshes it every ten seconds.
- The registered calculator handles add/subtract/multiply/divide in Python tests.
- Guarded dispatch rejects unknown tools, validates arguments, executes READ tools,
  produces pending WRITE actions, and denies DESTRUCTIVE actions.
- Path validation rejects relative paths, parent traversal, paths outside allowed
  roots, drive-wide roots, and symlink escapes.

The calculator has no public execution endpoint yet. The command bar is a preview;
Send and Mic are disabled. Agent, search, index, and transcription routes return
HTTP 501 with JSON `detail`. No real LLM requests, file scans, filesystem mutations,
confirmation workflow, or automatic action logging occur.

## Prerequisites

Use Python 3.12+ and Node.js 22.12+ with npm. A supported Node LTS is recommended.
For WSL/Ubuntu, ensure the matching Python venv package is installed:

```bash
sudo apt update
sudo apt install python3.12-venv
```

Rust and platform dependencies are needed only for the native Tauri host.
See the [official Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

## Backend development (WSL/Ubuntu)

From the repository root:

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

If `python` is Python 3.12+, `python -m venv .venv` is equivalent.
The server listens on `127.0.0.1:8000`. Keep this loopback binding.
In another terminal:

```bash
curl http://127.0.0.1:8000/health
cd backend
source .venv/bin/activate
pytest
```

Interactive API documentation is at `http://127.0.0.1:8000/docs`.
Tests use temporary databases and directories.

### Windows-native backend (PowerShell)

From the repository root, using a separate Windows virtual environment:

```powershell
Copy-Item .env.example .env
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

If local execution policy prevents activation, invoke
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and
`.\.venv\Scripts\python.exe -m uvicorn main:app --reload` directly.
Do not share a virtual environment between Windows and WSL.

## Frontend development

In a separate terminal, from the repository root:

```bash
cd desktop
npm install
npm run dev
```

Open `http://127.0.0.1:1420`. Start the backend separately.
For checks and a production web build:

```bash
npm run typecheck
npm run build
```

`package-lock.json` is version controlled. Use `npm ci` for clean reproducible
installs. The API base URL lives only in `src/services/api.ts`; changing the
backend address also requires deliberate review of the Tauri CSP and backend CORS.
The root `.env` is backend-only and must never be copied into frontend assets.

## Native Tauri development

For a Windows desktop build, use **native Windows Node/npm, Rust MSVC, Visual
Studio Build Tools with Desktop development with C++, Windows SDK, and WebView2**.
Follow the [Windows prerequisites](https://v2.tauri.app/start/prerequisites/#windows).
Use a Windows checkout with freshly installed dependencies, not WSL
`node_modules` or a WSL virtual environment.

Start the Python backend separately on Windows, then from the repository root:

```powershell
cd desktop
npm install
npm run tauri dev
```

Tauri starts Vite itself; stop any separately running Vite on port 1420 first.
For a native executable:

```powershell
npm run tauri build
```

Installer bundling is intentionally disabled. Python is not embedded or launched
by Tauri yet; backend lifecycle, packaging, final branding, signing, and installers are
future tasks.

WSL is suitable for Python tests and browser-based React development. Running
Tauri in WSL builds a Linux application and requires Linux GTK/WebKit dependencies
and a display/WSLg; it does not validate a Windows build. Windows releases should
be built and tested with native Windows tooling. Cross-OS localhost forwarding
varies by WSL configuration, so run both processes natively on Windows for native
desktop validation. Do not expose the backend on all network interfaces to work
around connectivity.

## Configuration

Copy `.env.example` to `.env`; startup also works without either an API key or
a local `.env`. Process environment variables take precedence.

| Variable | Default | Meaning |
| --- | --- | --- |
| NOVA_ENV | development | Environment label |
| NOVA_DATABASE_PATH | data/nova.db | Relative to repository root, or absolute |
| OPENAI_API_KEY | empty | Reserved backend secret; provider is a stub |
| NOVA_ALLOWED_DIRECTORIES | [] | JSON array of explicit absolute directory paths |

Use a JSON array for allowed directories, for example
`["C:/Users/your-account/Documents"]` on Windows or an explicit absolute Linux
directory in WSL. These are examples only: nothing is scanned or auto-allowed.
Do not configure whole drives or system directories. Native platform path semantics
apply; Windows paths must be validated by a Windows backend.
An empty list denies all filesystem access. SQLite stores metadata locally;
database and environment files are excluded from Git.

## Security philosophy

No model-driven shell, PowerShell, CMD, subprocess, arbitrary code, or direct
database access exists. Tools are registered explicitly, and risk comes from
trusted tool metadata. WRITE requests cannot execute yet. Destructive tools are
disabled. Tauri grants no IPC capabilities and includes no shell/filesystem plugins.

CORS and loopback binding are not authentication. This foundation intentionally
has no authentication system and exposes no working computer-action API. Before
exposing real actions, implement a desktop-to-backend session boundary, execution-time
path validation, durable confirmation, and audit logging. See
[Security](docs/SECURITY.md) for limits and next requirements.

## Next milestones

1. Add one metadata-only `get_file_info` tool with Windows path tests and action logging.
2. Implement provider-neutral single-step orchestration and structured output validation.
3. Add durable, expiring, single-use confirmation for WRITE actions.
4. Implement bounded metadata indexing and search within user-selected directories.
5. Add transcription, native backend lifecycle, and Windows packaging.

No deletion, cloud integrations, vector search, background autonomy, or always-on
microphone is included. MIT licensed; see [LICENSE](LICENSE).
