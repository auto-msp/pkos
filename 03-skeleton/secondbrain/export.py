"""JSONL mirror (SOW 7, 88, 91, 124).

This is the migration guarantee. Every canonical table is written to plain
JSONL, one file per table, sorted for stable diffs. If SQLite is ever the wrong
choice, this mirror plus the content-addressed evidence blobs is a complete,
inspectable, vendor-neutral copy of the canonical plane.

Class A sync content (SOW 22) - these files are what Git tracks, never the
SQLite file itself.
"""
import json
from pathlib import Path
from .util import now_iso

TABLES = ["schema_meta","id_sequence","source","account","profile_workspace",
          "evidence_blob","source_object","object","object_version","provenance",
          "event","relationship","claim","claim_evidence","conflict",
          "duplicate_link","acquisition_manifest","processing_manifest",
          "dead_letter","audit_event","credential_registry","sync_state",
          "url","url_visit","web_snapshot","derived_index_registry"]


def export_all(conn, mirror_dir):
    mirror = Path(mirror_dir); mirror.mkdir(parents=True, exist_ok=True)
    manifest = {"exported_at": now_iso(), "tables": {}}
    for t in TABLES:
        rows = [dict(r) for r in conn.execute("SELECT * FROM %s" % t)]
        rows.sort(key=lambda d: json.dumps(d, sort_keys=True, default=str))
        p = mirror / ("%s.jsonl" % t)
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str))
                f.write("\n")
        manifest["tables"][t] = {"rows": len(rows), "file": p.name,
                                 "bytes": p.stat().st_size}
    (mirror / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (mirror / "README.md").write_text(
        "# Canonical JSONL mirror\n\n"
        "One file per canonical table, one JSON object per line, sorted for\n"
        "stable diffs. This is the portability guarantee (SOW 7, 91, 124):\n"
        "SQLite is the operational store, but this mirror plus the\n"
        "content-addressed blobs under `evidence/blobs/` is a complete and\n"
        "vendor-neutral copy of the canonical knowledge plane.\n\n"
        "Sync class A (SOW 22). Git tracks THESE files, never the .sqlite3.\n\n"
        "Regenerate: `secondbrain export`\n", encoding="utf-8")
    return manifest
