"""Canonical store access. SQLite is the operational authority; the JSONL
mirror under canonical/mirror is the portability guarantee (SOW 7, 124)."""
import sqlite3
from pathlib import Path
from . import SCHEMA_NAME, SCHEMA_VERSION
from .util import now_iso

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def connect(path, create=True):
    path = Path(path)
    if not path.exists() and not create:
        raise SystemExit("no canonical store at %s - run: secondbrain init" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")   # survives an interrupted job
    conn.execute("PRAGMA synchronous=FULL")   # correctness over throughput (SOW 120)
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT OR IGNORE INTO schema_meta"
        "(schema_name,schema_version,applied_at,migration_path,compatibility_rules)"
        " VALUES(?,?,?,?,?)",
        (SCHEMA_NAME, SCHEMA_VERSION, now_iso(),
         "1.0.0 is the initial schema; migrations land in migrations/NNNN_*.sql",
         "additive-only within a major version; a breaking change requires a "
         "major bump and a forward migration that is testable against the JSONL mirror"))
    conn.commit()


def schema_version(conn):
    r = conn.execute("SELECT schema_version FROM schema_meta WHERE schema_name=?"
                     " ORDER BY applied_at DESC LIMIT 1", (SCHEMA_NAME,)).fetchone()
    return r[0] if r else None
