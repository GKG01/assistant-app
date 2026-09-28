SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    extension TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL CHECK (size >= 0),
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_command TEXT NOT NULL,
    tool TEXT NOT NULL,
    arguments TEXT NOT NULL,
    result TEXT,
    status TEXT NOT NULL
);
"""

FILES_V2 = """
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    extension TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL CHECK (size >= 0),
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    root_path TEXT NOT NULL DEFAULT ''
)
"""

FILE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS files_name ON files(name_key)",
    "CREATE INDEX IF NOT EXISTS files_extension ON files(extension)",
    "CREATE INDEX IF NOT EXISTS files_modified ON files(modified_at)",
    "CREATE INDEX IF NOT EXISTS files_size ON files(size)",
    "CREATE INDEX IF NOT EXISTS files_root ON files(root_path)",
)
