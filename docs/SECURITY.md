# Security model

## Trust and least privilege

The model is an untrusted proposer. It cannot authorize execution, register tools,
execute arbitrary code, mutate SQLite, or access the OS directly. Backend code is
trusted and must preserve these boundaries. This is an application-level boundary,
not an OS sandbox against malicious Python code or a compromised local account.

Only the explicitly registered calculator can currently run through the guard.
No shell, PowerShell, CMD, generic subprocess, eval, exec, or arbitrary Python tool
exists. Tauri has an empty capability list, no plugins, and no custom Rust commands.
The UI uses browser fetch to the loopback backend. Its CSP restricts connections
to the backend; development additionally permits Vite hot-reload WebSockets.
See [Tauri capabilities](https://v2.tauri.app/security/capabilities/).

## Risk and confirmation

| Risk | Policy |
| --- | --- |
| READ | May execute after registry lookup and input validation |
| WRITE | Return a pending action; execution is unavailable |
| DESTRUCTIVE | Deny in V1; future support needs stronger confirmation |

Risk is assigned by trusted tool code, never by a model or incoming request.
Input schemas reject extra arguments. Unknown tool names are rejected.
The backend guard is the only intended execution entry point.

Future confirmations must reference a stored action ID and immutable normalized
arguments, expire, be single-use, be bound to the active desktop session, and
support cancellation. The model must not have access to the confirmation channel.
A returned PendingAction alone is not authorization. Re-check paths and policy at
execution time. Moving, renaming, and creating require confirmation. Opening a
file or launching Explorer also requires confirmation; file opening may run active
content through OS associations. No deletion or overwrite tool is provided.

## Filesystem boundary

`NOVA_ALLOWED_DIRECTORIES` is an explicit JSON list. The default is empty.
Nothing automatically grants access to Desktop, Documents, Downloads, or Pictures.
Whole-drive roots are rejected by the path utility. Do not select system directories.

`validate_path` requires an absolute path, rejects parent traversal, canonicalizes
symlinks, and checks actual path ancestry instead of unsafe string prefixes.
Future tools must validate every source and destination, including rename targets,
at execution time. Indexing must check every discovered entry and avoid following
links into unapproved locations. Metadata only: no document contents, embeddings,
or drive-wide discovery.

This baseline does not eliminate filesystem race conditions. A link or Windows
junction could change between validation and use. Before filesystem mutation ships,
use platform-appropriate safe handles and reparse-point controls, test UNC paths,
device namespaces, alternate data streams, case handling, junctions, and
time-of-check/time-of-use races on Windows. Consider denial of network paths and
executable file types. Linux path tests are not Windows security certification.

## Local HTTP boundary

Uvicorn defaults to `127.0.0.1:8000`; do not bind to `0.0.0.0`.
Trusted hosts and exact development/Tauri CORS origins reduce browser exposure.
CORS is not authentication and does not block arbitrary local clients.
Only health is functional; computer-action routes return 501.

Before enabling real action endpoints, add a local desktop session boundary with
request-origin checks, CSRF/replay protections as appropriate, and bounded requests.
A full authentication system is out of scope for this boilerplate.
Do not deploy this backend publicly.

## Data, audit records, and secrets

SQLite contains file metadata and action-history schema. Repositories use
parameterized SQL and JSON serialization. The actions repository is implemented,
but automatic audit logging is not yet connected. Future orchestration must record
proposal, denial, confirmation, execution, and failure with correlation IDs, and
define retention/redaction. Audit data may contain sensitive paths and commands.

The database is not encrypted and depends on OS account permissions.
Environment files, databases, virtual environments, and build artifacts are ignored
by Git. The example environment file contains no key. API keys remain in backend
environment/configuration, wrapped as SecretStr; never pass them through Vite
variables, logs, tool results, or frontend bundles. Startup works with no key and
the OpenAI provider makes no network calls.

## Before expanding capabilities

Add Windows-specific path tests, durable confirmations, execution audit integration,
resource limits, prompt-injection-resistant handling of tool output, dependency
review, and secure backend lifecycle management before shipping computer actions.
The model can propose a malicious action even when its prompt forbids it;
deterministic policy must remain authoritative.
