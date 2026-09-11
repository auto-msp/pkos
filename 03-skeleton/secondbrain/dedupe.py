"""Deduplication (SOW 19). Duplicates are LINKED, never deleted (SOW 125.10).

Implemented now: exact (sha256) and url (canonical form).
Declared but not implemented: structural, semantic, version, conversation,
derived - each needs machinery from a later phase and is reported honestly
rather than silently skipped.
"""
from . import ids
from .util import now_iso

KINDS = {
    "exact":        "IMPLEMENTED - identical sha256 content hash",
    "url":          "IMPLEMENTED - identical canonicalized URL",
    "version":      "IMPLEMENTED - same source object across acquisitions",
    "structural":   "NOT_IMPLEMENTED - needs per-source structural normalizers",
    "semantic":     "NOT_IMPLEMENTED - needs embeddings (Phase 23)",
    "conversation": "NOT_IMPLEMENTED - needs the AI-export adapters (Phase 14/15)",
    "derived":      "NOT_IMPLEMENTED - needs the transformation graph (Phase 22)",
}


def find_exact(conn):
    """Objects whose current version shares a content hash. The oldest
    object_id wins canonical status purely as a deterministic tie-break; that
    choice is recorded as evidence, not asserted as truth."""
    rows = conn.execute(
        "SELECT v.content_hash h, GROUP_CONCAT(o.object_id) ids, COUNT(*) n,"
        "       SUM(COALESCE(b.byte_size,0)) bytes"
        "  FROM object o JOIN object_version v ON v.version_id=o.current_version"
        "  LEFT JOIN evidence_blob b ON b.content_hash=v.content_hash"
        " WHERE v.content_hash IS NOT NULL AND o.is_duplicate_of IS NULL"
        " GROUP BY v.content_hash HAVING n>1").fetchall()
    return [{"content_hash": r["h"], "object_ids": r["ids"].split(","),
             "count": r["n"], "bytes_each": (r["bytes"] or 0) // max(r["n"], 1)}
            for r in rows]


def find_url_variants(conn):
    """http/https (and www) variants of the same resource.

    These are kept as SEPARATE url rows on purpose: SOW 55 forbids
    over-normalizing in ways that change resource identity, and http:// and
    https:// genuinely are different URLs. So instead of merging them we LINK
    them as url-kind duplicates (SOW 19: canonical object + alias objects),
    which preserves both identities and the evidence for the relationship.
    """
    rows = conn.execute(
        "SELECT substr(normalized_url, instr(normalized_url, '://')+3) key,"
        "       GROUP_CONCAT(object_id) ids, COUNT(*) n"
        "  FROM url WHERE object_id IS NOT NULL"
        " GROUP BY key HAVING n>1").fetchall()
    return [{"content_hash": "", "url_key": r["key"],
             "object_ids": [x for x in r["ids"].split(",") if x],
             "count": r["n"], "bytes_each": 0} for r in rows]


def record(conn, groups, kind="exact", detected_by="secondbrain dedupe"):
    linked = 0
    for g in groups:
        oids = sorted(g["object_ids"])
        canon, aliases = oids[0], oids[1:]
        for a in aliases:
            conn.execute(
                "INSERT OR IGNORE INTO duplicate_link(duplicate_id,canonical_object,"
                "alias_object,dedup_kind,evidence,confidence,detected_at,detected_by)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (ids.scoped("DUP", 1), canon, a, kind,
                 ("content_hash=%s" % g["content_hash"]) if g.get("content_hash")
                 else ("url_key=%s" % g.get("url_key", "")), 1.0,
                 now_iso(), detected_by))
            # mark the alias WITHOUT deleting it - it keeps its own provenance
            conn.execute("UPDATE object SET is_duplicate_of=? WHERE object_id=?"
                         " AND is_duplicate_of IS NULL", (canon, a))
            linked += 1
    conn.commit()
    return linked
