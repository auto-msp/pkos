#!/usr/bin/env python3
"""Measure what the first (pre-SOW-75) Obsidian vault ingest actually cost.

READ ONLY. This script opens the canonical database in SQLite read-only mode
and writes nothing, anywhere. It exists to answer one question before a
decision is taken, not to take the decision: SOW 97 requires an impact report
before any destructive operation, and this is that report's input.

It classifies every object the Obsidian adapter ingested against the exclusion
lists the adapter uses TODAY (imported from the live code, never copied), and
splits evidence bytes into:

  gross      - bytes of every blob a would-be-excluded object references
  exclusive  - bytes of blobs referenced ONLY by would-be-excluded objects

Only `exclusive` is recoverable. A blob shared with a file the laptop adapter
also ingested stays regardless, because the evidence plane is content-addressed
and one address is one blob (SOW 5.1).

Usage:  python3 bin/measure-vault-cost.py [/path/to/pkos-store]
"""
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_ROOT = "/root/pkos/pkos-store"
SOURCE_ID = "SRC-obsidian"


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0


def load_rules():
    """Exclusion lists from the LIVE adapter code, so this can never drift."""
    here = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(here))
    try:
        from secondbrain.adapters.filesystem import EXCLUDE_EXT, EXCLUDE_DIRS
        try:
            from secondbrain.adapters.obsidian import VAULT_META_DIRS
            origin = "live code"
        except ImportError:
            # This store predates the SOW 75 fix, which is the whole reason you
            # are running this. Measure against the rules that fix WILL apply.
            VAULT_META_DIRS = {".obsidian", ".trash", ".smart-env", ".space",
                               ".stversions"}
            origin = "live code + pending fix"
        return set(EXCLUDE_EXT), set(EXCLUDE_DIRS) | set(VAULT_META_DIRS), origin
    except Exception as exc:                                   # pragma: no cover
        print("!! could not import the adapter rules (%s)" % exc)
        print("!! run this from inside the skeleton, beside secondbrain/")
        raise SystemExit(2)


def lock_report(db):
    """Report WAL state without opening the database (SOW 43: state a number)."""
    print("== files ==")
    missing = False
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.exists():
            print("   %-14s %12s" % (p.name, human(p.stat().st_size)))
        else:
            if suffix == "":
                missing = True
            print("   %-14s %12s" % (p.name, "absent"))
    if missing:
        print("!! %s does not exist. Pass the store root as argv[1]." % db)
        raise SystemExit(2)
    wal = Path(str(db) + "-wal")
    if wal.exists() and wal.stat().st_size > 64 * 1024 * 1024:
        print("   NOTE: the WAL is large. A writer died mid-transaction, or no")
        print("         checkpoint has run. That is the usual cause of a lock.")
    print()


def connect_ro(db):
    uri = "file:%s?mode=ro" % str(db).replace("?", "%3f").replace("#", "%23")
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA query_only=ON")
    return conn


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1
                else os.environ.get("PKOS_ROOT") or DEFAULT_ROOT)
    db = root / "canonical" / "canonical.sqlite3"
    print("store : %s" % root)
    print("db    : %s" % db)
    print()
    lock_report(db)

    excl_ext, skip_dirs, origin = load_rules()
    print("rules : %d extensions, %d directory names (from %s)"
          % (len(excl_ext), len(skip_dirs), origin))
    print()

    try:
        conn = connect_ro(db)
        conn.execute("SELECT 1 FROM object LIMIT 1").fetchall()
    except sqlite3.OperationalError as exc:
        print("!! cannot read the database: %s" % exc)
        print("!! nothing was written. If this says 'locked', find the holder:")
        print("     fuser -v %s" % db)
        print("     ps aux | grep '[s]econdbrain'")
        print("   then, once no PKOS process is running:")
        print("     python3 -c \"import sqlite3;c=sqlite3.connect(r'%s');"
              "print(c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())\"" % db)
        raise SystemExit(1)

    rows = conn.execute(
        "SELECT so.native_path AS path, so.evidence_hash AS ev,"
        "       o.object_id AS oid, o.object_class AS cls"
        "  FROM source_object so"
        "  JOIN provenance pv ON pv.source_object_id = so.source_object_id"
        "  JOIN object o ON o.object_id = pv.object_id"
        " WHERE so.source_id = ?"
        " GROUP BY so.source_object_id", (SOURCE_ID,)).fetchall()

    if not rows:
        print("no %s objects in this store. Nothing was ingested from a vault,"
              % SOURCE_ID)
        print("or the source id differs. Sources present:")
        for r in conn.execute("SELECT source_id, COUNT(*) n FROM source_object"
                              " GROUP BY source_id ORDER BY n DESC LIMIT 15"):
            print("   %-28s %8d" % (r["source_id"], r["n"]))
        return

    def excluded(path):
        if not path:
            return False, ""
        p = Path(path)
        for part in p.parts[:-1]:
            if part in skip_dirs:
                return True, "dir:%s" % part
        if p.suffix.lower() in excl_ext:
            return True, "ext:%s" % p.suffix.lower()
        return False, ""

    keep_ids, drop_ids = [], []
    by_reason, by_ext = {}, {}
    for r in rows:
        is_x, reason = excluded(r["path"])
        if is_x:
            drop_ids.append(r["oid"])
            by_reason[reason] = by_reason.get(reason, 0) + 1
            ext = Path(r["path"]).suffix.lower() or "(none)"
            by_ext[ext] = by_ext.get(ext, 0) + 1
        else:
            keep_ids.append(r["oid"])

    print("== %s objects ==" % SOURCE_ID)
    print("   total ingested        %8d" % len(rows))
    print("   still wanted          %8d" % len(keep_ids))
    print("   now excluded by 75    %8d" % len(drop_ids))
    print()

    if not drop_ids:
        print("Nothing to decide: every vault object passes the current rules.")
        return

    print("== why excluded (top 15) ==")
    for k, v in sorted(by_reason.items(), key=lambda kv: -kv[1])[:15]:
        print("   %-24s %8d" % (k, v))
    print()
    print("== by extension (top 15) ==")
    for k, v in sorted(by_ext.items(), key=lambda kv: -kv[1])[:15]:
        print("   %-24s %8d" % (k, v))
    print()

    # ---- evidence cost -----------------------------------------------------
    tmp_drop = set(drop_ids)
    ev_drop, ev_keep = {}, set()
    for r in rows:
        if not r["ev"]:
            continue
        if r["oid"] in tmp_drop:
            ev_drop.setdefault(r["ev"], 0)
            ev_drop[r["ev"]] += 1
        else:
            ev_keep.add(r["ev"])

    # blobs this vault's artefacts reference that ANY other source also references
    shared_elsewhere = set()
    if ev_drop:
        hashes = list(ev_drop)
        for i in range(0, len(hashes), 500):
            chunk = hashes[i:i + 500]
            q = ("SELECT DISTINCT evidence_hash h FROM source_object"
                 " WHERE evidence_hash IN (%s) AND source_id <> ?"
                 % ",".join("?" * len(chunk)))
            for row in conn.execute(q, chunk + [SOURCE_ID]):
                shared_elsewhere.add(row["h"])

    exclusive = [h for h in ev_drop if h not in ev_keep and h not in shared_elsewhere]

    def bytes_for(hashes):
        total, found = 0, 0
        hashes = list(hashes)
        for i in range(0, len(hashes), 500):
            chunk = hashes[i:i + 500]
            q = ("SELECT byte_size FROM evidence_blob WHERE content_hash IN (%s)"
                 % ",".join("?" * len(chunk)))
            for row in conn.execute(q, chunk):
                total += row["byte_size"] or 0
                found += 1
        return total, found

    gross_b, gross_n = bytes_for(ev_drop)
    excl_b, excl_n = bytes_for(exclusive)

    print("== evidence cost ==")
    print("   distinct blobs referenced by excluded objects   %8d  %12s"
          % (gross_n, human(gross_b)))
    print("   of those, also referenced elsewhere             %8d"
          % (len(ev_drop) - len(exclusive)))
    print("   EXCLUSIVE to excluded objects (recoverable)     %8d  %12s"
          % (excl_n, human(excl_b)))
    print()

    tot_blobs, tot_bytes = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(byte_size),0) b FROM evidence_blob"
    ).fetchone()
    if tot_bytes:
        print("   whole evidence plane                           %8d  %12s"
              % (tot_blobs, human(tot_bytes)))
        print("   excluded share of it                                      %.1f%% of bytes"
              % (100.0 * excl_b / tot_bytes))
    print()

    vers = 0
    ids = list(drop_ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = ("SELECT COUNT(*) n FROM object_version WHERE object_id IN (%s)"
             % ",".join("?" * len(chunk)))
        vers += conn.execute(q, chunk).fetchone()["n"]
    print("== canonical cost ==")
    print("   objects that would be retired   %8d" % len(drop_ids))
    print("   versions beneath them           %8d" % vers)
    print()
    print("Nothing was written. This script cannot delete anything.")


if __name__ == "__main__":
    main()
