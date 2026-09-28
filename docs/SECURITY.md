# Security model

## Trust boundary

The frontend is not a security boundary. Every indexed, returned, inspected, or
launched file passes deterministic backend policy. BRAIN remains unimplemented;
future models only propose registered ToolCalls. They receive no shell, generic
subprocess, code evaluation, arbitrary filesystem, or direct database capability.
This is an application boundary, not an OS sandbox against a compromised account.

Tauri still has an empty capability list and no native plugins/custom commands.
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

The header is public, not a credential. Origin-free local scripts are allowed.
There is no authentication system: malicious local processes, a compromised trusted
frontend, or another process controlling an allowed local origin are outside this
boundary. Do not expose the backend to a LAN or the internet. A stronger desktop
session binding remains necessary before distribution to untrusted environments.

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
and generated artifacts remain ignored. No new secret or external integration exists;
OPENAI_API_KEY remains an unused backend-only setting.

## Remaining limits

- Path checks cannot atomically bind a pathname to the object later opened by a
  viewer. Concurrent directory/reparse replacement races remain possible. Native
  handle-based access would be needed for stronger guarantees; there are no file
  mutations in this phase.
- Hard links and changed mount topology are not a content-isolation boundary.
- Reparse rejection may exclude OneDrive-backed folders even when user-visible.
- System-directory detection is conservative, not a complete Windows known-folder API.
- Indexing uses memory proportional to one root and validates paths repeatedly.
  Name substring search scans candidate keys. Extremely large roots need later tuning.
- A scan that loses access keeps old metadata; refresh after restoring access to
  reconcile it. Client disconnection does not cancel a running scan.
- Linux tests cover native-independent policy and mock Windows launches; they do
  not certify Windows shell associations, Explorer selection, or real junction races.

Future reasoning must use the existing READ tools and continue treating filenames
and tool results as untrusted data. Durable WRITE confirmations, stronger session
binding, and distribution hardening remain separate tasks.
