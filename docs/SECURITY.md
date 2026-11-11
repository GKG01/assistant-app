# Security model

## Trust boundary

The frontend is not a security boundary. Every indexed, returned, inspected, or
launched file passes deterministic backend policy. BRAIN may request
only the five explicitly approved tools, with separate interaction policy. It has no shell, generic subprocess, arbitrary Python,
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
| INTERACTIVE | Direct user initiation, or explicit AI reveal policy; AI opening always pending |
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
`get_file_info`, `open_file`, `show_in_folder`. It checks exact registered implementations
and expected READ or INTERACTIVE classifications, validates strict Pydantic JSON
schemas with unknown fields forbidden, then dispatches through PermissionManager.
READ tools retain `read_only=True`; interactions use the explicit policy below. No module scanning, dynamic imports,
attribute resolution, user-supplied risk or confirmation flags are used. All WRITE/DESTRUCTIVE tools remain unavailable to the agent.

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
this distinction, but deterministic capability restrictions enforce it. Feature 3.3 projects verified file results and failures into final responses.
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

Future reasoning must preserve the existing explicit tool boundary and continue treating
filenames and tool results as untrusted data. Durable WRITE confirmations and distribution
hardening remain separate tasks; the current session credential is not a user
login or a full OS security boundary.


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
Features 3.4 and 3.5 extend this boundary as documented below. Full chat UI,
permanent memory and Features 3.6–3.8 remain outside the implementation.
Run `cd backend && .venv/bin/python -m pytest -q` for offline fake-provider tests.
Existing manual commands and provider configuration apply unchanged.

## Feature 3.4 OS interaction authorization

The model supplies only a strict bounded positive indexed file ID. Paths are resolved
from SQLite but never trusted solely because they are stored there. Shared preflight
and execution enforce canonical allowed-directory paths, no links/reparse points,
existence and regular-file type. Pending requests also validate their targets.
Unknown fields reject command lines, executable selection, working directories,
environment overrides, confirmation flags and arbitrary paths.

INTERACTIVE remains distinct from READ. AI opening always requires confirmation;
there is no confirm/resume endpoint, and model/user prose saying “confirmed” does
not authorize execution. Existing direct buttons remain explicit separate actions.
AI reveal defaults pending; `NOVA_ALLOW_AGENT_REVEAL=true` explicitly authorizes
only reveal for authenticated desktop requests. It cannot authorize open, WRITE
or DESTRUCTIVE operations. Changing this backend setting requires restart.

The existing Phase 2 document/media extension allowlist is reused, case-insensitively.
Executables, scripts, shortcuts and unknown extensions fail with
`UNSUPPORTED_FILE_TYPE` before any launch. Reveal may select these files but never
opens them. Even allowed types and Explorer previews can invoke vulnerable handlers.
Filename instructions and shell metacharacters remain path data, never commands.
The native launcher uses fixed Windows APIs with no shell interpolation. No model
can add tools or change permissions through metadata.

Within a search-to-interaction request, the latest search must identify exactly one
returned file with the requested ID. Ambiguous, failed, empty or mismatched searches
cannot cause an interaction. Final responses report pending/failure or OS acceptance,
never successful rendering. Permission/argument/execution states are request-local;
this is not the persistent audit system planned for Feature 3.8.

Immediate path revalidation and Windows pinned handles reduce replacement races but
do not bind an asynchronous viewer after dispatch. WSL/Linux have no launch fallback.
Offline tests mock native launch operations and use temporary files/SQLite and fake
providers; they do not certify real Explorer behavior, file associations or live OpenAI.

Regression tests exercise mismatched IDs, failed latest searches, empty pagination
pages, revoked allowed roots, and default-policy reveal preflight. Scripted provider
responses falsely claiming successful interaction are replaced with verified error
or confirmation messages. A narrower subsequent search permits only its unique
indexed target; it does not grant opening authorization.

## Feature 3.5 session and context boundaries

Conversation IDs are random canonical UUIDv4 strings, validated before store access.
They identify context and grant no authority. Managed conversations are bound to the
existing authenticated desktop launch identity. Every continuation and clear request
must pass the existing Bearer, `X-Nova-Request`, JSON and origin checks to access that
scope. Omission/invalid credentials cannot downgrade an existing managed conversation
into standalone context. Wrong-owner and absent IDs both return generic 404s. There
is no history listing/enumeration endpoint. All agent POST bodies are size-bounded.

Standalone text/arithmetic access is intentionally preserved, with an unauthenticated
process-local owner scope. A caller with a standalone ID can reuse it; this is not
multi-user isolation. File tools remain unavailable there. Different authenticated
users are not modeled: the managed owner is the desktop launch, shared by authorized
clients. Malicious local processes or a compromised trusted frontend remain outside
the existing security boundary. No competing login/token scheme was added.

Context is bounded and volatile: 32 sessions, 30 minutes inactivity by default,
20 messages, 10,000 characters/message, 64 KiB serialized history and at most 50
references in the latest result set. Request-local results are 16 KiB each and the
agent checks a 256 KiB estimated context ceiling. Whole-turn eviction removes source
references; clear, session eviction, expiry and restart make IDs unavailable. Cleanup
is access-driven; inactive data may remain in memory until the next operation or
process exit, but expired sessions cannot be used. No durable chat store or background
worker exists. Busy sessions are protected from expiry/eviction and concurrent turn
or clear requests return 409. A short lock makes bookkeeping atomic without holding
all conversations behind a provider call. Anonymous creation cannot evict managed
sessions; capacity exhaustion returns 503 when no same-owner idle victim exists.

References come only from actual successful registered search/info execution records,
never user claims, provider-generated IDs, assistant prose or failed calls. Stored
references contain indexed IDs and display names, not arbitrary paths. New failed or
empty lookups invalidate old selections. Display numbering comes from backend tool
order, and the resolver uses that exact returned page; it does not parse assistant
ordering. Missing/ambiguous/out-of-range references fail closed with clarification.
The resolver is narrow (documented English phrases); it is not a general intent or
natural-language authorization system.

A resolved reference binds file ID and intended interaction for the entire request.
Model substitutions, operation changes, new searches and duplicate interaction
attempts are rejected. Valid calls still use exact approved registry implementations,
strict schemas, PermissionManager and current indexed-record/path/type checks.
Previous approval is never cached. Opening still requires unavailable backend
confirmation and cannot execute; reveal still follows the existing explicit policy.
Historical “confirmed” text and malicious filenames cannot set trusted dispatch flags.

System instructions remain separate from history. OpenAI receives completed
user/grounded-assistant roles; the compatibility adapter uses untrusted user-level
JSON. Raw provider continuation, SDK objects and tool batches are not retained across
turns, so trimming cannot orphan tool results. Historical assistant messages are
context, not evidence. Current execution records determine action claims. Provider
errors after tool outcomes commit and display verified outcomes alongside the safe
error; errors before outcomes do not add a turn. No side-effectful retry is added.

Offline tests cover ownership, expiry/clear/eviction, concurrency, bounded context,
ordered selection, cross-session substitution, hostile historical data, confirmation,
policy revocation, missing files, executable restrictions and symlink escapes. They
mock native launches and the provider/SDK transport. Existing native race limitations
and heuristic ordinary-text grounding limitations remain; neither live OpenAI nor
Windows-native behavior is certified by these tests. Features 3.6–3.8 remain separate.
