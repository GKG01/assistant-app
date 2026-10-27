# Security model

## Trust boundary

The frontend is not a security boundary. Every indexed, returned, inspected, or
launched file passes deterministic backend policy. Feature 3.2 BRAIN may request
only approved read-only tools. It has no shell, generic subprocess, arbitrary Python,
direct filesystem or database access. The provider receives schemas, never executors.
This is an application boundary, not an OS sandbox against a compromised account.

Tauri has one narrowly scoped custom command, `backend_session`, available only
to the main window and trusted local origins. It returns a random per-launch
credential; no shell, subprocess, or filesystem capability is exposed.
The React client uses the loopback HTTP backend under the existing CSP.

## Allowed directories and path validation

NOVA_ALLOWED_DIRECTORIES is a JSON array of absolute native-platform paths.
Empty means deny. Roots are never auto-discovered; the index API accepts only an
empty request body, not an arbitrary path. Overlapping roots are collapsed.

PathPolicy is the shared boundary for indexing, search, metadata lookup, and launch:

1. Require an absolute native path; reject parent traversal, all-dot traversal
   variants, NULs, and foreign separators.
2. Check lexical ancestry using Path.is_relative_to before stat'ing a candidate
   outside configured roots. No raw string prefix authorization is used.
3. Reject whole drive roots, UNC/network/device namespaces, known system locations,
   reserved Windows names, alternate data streams, and ambiguous trailing dots/spaces.
4. lstat every existing ancestor and the target. Deny symlinks and any Windows
   FILE_ATTRIBUTE_REPARSE_POINT, including junctions and some cloud placeholders.
5. Resolve/canonicalize and recheck path ancestry/system policy. Normalize Windows
   path case for database identity. Require existence for scanning and actions.

System exclusions include Windows, Program Files, ProgramData, Recovery,
System Volume Information and recycle-bin directory names; Linux system trees
include /etc, /usr, /proc, /sys, /dev, /bin, /sbin, /boot, /root and /var.
The exclusions are conservative and not an exhaustive OS-directory inventory.
Configure personal folders, not whole profiles, mount collections, or system roots.

Indexer validates each entry and directory; no link is followed intentionally,
including links within an allowed root. No content reads, document parsing, hashes,
embedding generation, or filesystem writes are part of indexing. Unsupported special
files are skipped. SQLite and its journal files are excluded from scans.
Stale cleanup removes database rows only.

Search is SQLite-backed. Before returning/counting results, the service rechecks
each candidate against current path policy, including links introduced after indexing.
Changing configuration requires restart. Revoked data stays in SQLite but is hidden.
Deletion freshness is handled by explicit refresh; stale entries cannot be opened
after the existence check fails.

## Execution classification

| Risk | Behavior |
| --- | --- |
| READ | Registered calculate/search/info may execute after input validation |
| INTERACTIVE | Open/reveal require direct user initiation; otherwise pending |
| WRITE | Pending only; no execution/confirmation API |
| DESTRUCTIVE | Denied |

INTERACTIVE is a Phase 2 addition because opening a file has effects beyond reading
metadata. Fixed HTTP action handlers supply trusted user intent to the guard. Neither
risk nor user_initiated can be supplied in ToolCall arguments. A future model cannot
confirm its own proposal. WRITE cannot be executed using interactive intent.

Open/reveal take a positive indexed ID, not an arbitrary path, executable, verb, URL,
or command argument. SQLite AUTOINCREMENT prevents an old deleted ID from silently
referring to a newly indexed file.

Open permits only .pdf, .txt, .csv, .png, .jpg, .jpeg, .gif, .bmp, .webp, .docx, .xlsx,
and .pptx. Executables, scripts, shortcuts, HTML, SVG and unknown types are not launched.
The guard and FileActionService revalidate paths immediately before Windows dispatch.
os.startfile uses a fixed open verb without caller-controlled arguments.
On Windows, FileActionService also pins every path component from the drive root
to the file with metadata-only CreateFileW handles. OPEN_REPARSE_POINT prevents
following the component itself; each handle's attributes and final DOS path are
checked before proceeding. Write/delete sharing is denied, and all handles stay
open through shell dispatch. Conflicting existing handles fail closed. Handles
are released in reverse order on success or failure; no file contents are read.
See [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
Reveal uses typed native SHParseDisplayName/SHOpenFolderAndSelectItems calls, selecting
the item in Explorer. There is no shell command construction or subprocess launcher.
See [Microsoft's API contract](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems).

Supported extensions do not make a document safe. Malicious documents, unsafe local
associations, viewer vulnerabilities, and Explorer preview handlers remain risks.
Only open files you trust. Native launch success is not viewer success.

## Local HTTP protections

Keep Uvicorn bound to 127.0.0.1 and use one worker. TrustedHost and exact CORS origins
remain in place. Every /files endpoint also requires X-Nova-Request: 1 and rejects
untrusted Origin values. The custom header requires cross-origin browser preflight,
blocking simple form/link-triggered launches. The frontend adds it centrally.

The header is public, not a credential. The Tauri-managed backend additionally
requires its per-launch Bearer credential; a manually started backend has no
credential and fails closed for file operations. There is no user login system:
malicious local processes or a compromised trusted frontend remain outside this
application boundary. Do not expose the backend to a LAN or the internet.

## SQLite and audit safety

Queries are parameterized and sort clauses use a fixed mapping. Versioned migrations
preserve existing IDs/action data and refuse unknown future versions.
A root refresh uses one transaction and batched writes. A failed scan subtree retains
old metadata; a failed transaction rolls back the root refresh. No commit-per-file
or deletion of the entire index occurs.

Open/reveal persist a request record before invoking the OS; an audit-write failure
prevents launch. OS/unsupported-platform failures get a separate failed record.
These records indicate requested/failed dispatch, not verified viewer completion.
Policy rejections, searches, and indexing are not comprehensively audit-logged yet.

SQLite metadata and action history are unencrypted and may reveal filenames and paths.
Protect them using OS account permissions. .env, SQLite files, virtual environments,
and generated artifacts remain ignored. OPENAI_API_KEY is used only by the backend
provider as described below.

## Feature 3.2 AI isolation and secrets

`OPENAI_API_KEY` comes from backend settings/environment (including the ignored
root `.env`) and is held as `SecretStr` until SDK construction. It is never exposed
through React, API responses, or application logs. `.env.example` has an empty key.
Model/timeout/output settings are backend-only; restart after changing them.

OpenAI SDK calls and types remain isolated in OpenAIProvider. Model context now
includes approved schemas and bounded tool results, including filenames, full paths
and indexed metadata for authenticated file requests. No file contents or credentials
are sent. Ordinary tool-shaped prose is never parsed for execution; only structured
function-call items may request execution. Missing/invalid/duplicate call IDs,
incomplete responses and unsupported provider tool types fail closed.

The agent adapter uses an explicit allowlist: `calculate`, `search_files`,
`get_file_info`. It checks the exact registered implementation and READ classification,
validates strict Pydantic JSON schemas with unknown fields forbidden, then dispatches
through the existing PermissionManager with `read_only=True`. The guard independently
rejects every non-READ risk before execution. No module scanning, dynamic imports,
attribute resolution, user-supplied risk or confirmation flags are used. Registered
open/reveal and all WRITE/DESTRUCTIVE tools remain unavailable to the agent.

Search uses the existing SQLite repository and current PathPolicy; directory filters
cannot widen allowed roots. Info accepts a bounded indexed ID, never an arbitrary
path. No content reads were added. The calculator evaluates a restricted arithmetic
AST without eval/exec: only numeric literals, signs, addition, subtraction,
multiplication, division and parentheses; functions, names, attributes and powers
are rejected. Expressions are limited to 500 characters, 100 nodes, and finite
intermediate magnitudes no greater than 1e100.

Agent limits are 5 provider iterations, 10 total tool calls, 4 per response, 8 KiB
argument JSON and 16 KiB serialized result per call. Search defaults to 20 records
and permits at most 50. Oversized search results lose whole records with explicit
truncation metadata; other oversized results return an error. No invalid JSON slices
are sent. Limits stop execution and return a partial-completion message; no hidden
extra model call is made. Synchronous tools run sequentially in the bounded shared
threadpool. Provider deadlines apply per call, not across the whole agent loop.

Filenames, paths and tool results are untrusted data. They are JSON-serialized tool
outputs, never system instructions or executable input. The concise prompt reinforces
this distinction, but deterministic capability restrictions enforce it. These controls
do not guarantee truthful model prose; expanded grounding belongs to Feature 3.3.
There is no persisted conversation, write confirmation or background autonomy.

Text is sent to the cloud provider. `store=False` disables response storage through
this API option; it is not a claim of zero provider retention. Nova does not persist
chat history. Logs contain request start/completion, duration, and safe failure
categories, never full prompts, responses, raw exceptions, or headers. SDK/transport
debug logging is suppressed to avoid payload logging. Do not override these logging
levels when handling sensitive information.

The client is lazy, with a bounded timeout and token cap per provider call, and retries disabled.
Missing keys affect AI requests only; deterministic file features and health remain
available. Failure responses use fixed messages rather than provider error bodies.
Request validation rejects blank or oversized messages, and raw body limits apply
before parsing, even without Content-Length.

Text and calculator requests remain available to standalone local clients without
a desktop token. Agent file tools require the same managed Bearer session and
`X-Nova-Request: 1` header as direct file operations. Without authorization, those
schemas are omitted and any attempted file calls are denied. It requires JSON and rejects untrusted Origin or
cross-site Fetch Metadata. Existing host/CORS protections apply. Local processes
can call it and incur provider usage; this is not authentication or quota control.
Keep the backend bound to loopback. Broader usage controls belong to later hardening.

## Remaining limits

- Windows open/reveal pins components during dispatch, but the external viewer or
  Explorer may resolve the pathname after dispatch returns and handles close.
  This reduces replacement races; it does not guarantee the viewer consumes the
  validated object. Indexing/search still use path-based metadata checks. There
  are no file mutations in this phase. Conflicting writers may prevent launch.
- Hard links and changed mount topology are not a content-isolation boundary.
- Reparse rejection may exclude OneDrive-backed folders even when user-visible.
- System-directory detection is conservative, not a complete Windows known-folder API.
- Indexing uses memory proportional to one root and validates paths repeatedly.
  Name substring search scans candidate keys. Extremely large roots need later tuning.
- A scan that loses access keeps old metadata; refresh after restoring access to
  reconcile it. Client disconnection does not cancel a running scan.
- Linux tests cover native-independent policy and mock Windows launches; they do
  not certify Windows shell associations, Explorer selection, or real junction races.

Future reasoning must preserve the existing READ tool boundary and continue treating
filenames and tool results as untrusted data. Durable WRITE confirmations and distribution
hardening remain separate tasks; the current session credential is not a user
login or a full OS security boundary.
