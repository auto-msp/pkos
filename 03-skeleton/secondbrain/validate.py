"""Validation and completion proof (SOW 43, 103, 111, 125).

Completion is never inferred from the absence of an error. Every check returns
a measured number, and `secondbrain validate` fails loudly when an invariant
that protects evidence is broken.
"""
import os
from pathlib import Path

from .util import human


def run(conn, paths, deep=False):
    checks = []
    extras = {}

    def chk(name, ok, detail, severity="ERROR"):
        checks.append({"check": name, "status": "PASS" if ok else severity,
                       "detail": detail})

    n_obj = conn.execute("SELECT COUNT(*) c FROM object").fetchone()["c"]
    n_ver = conn.execute("SELECT COUNT(*) c FROM object_version").fetchone()["c"]
    n_prov = conn.execute("SELECT COUNT(*) c FROM provenance").fetchone()["c"]
    n_evt = conn.execute("SELECT COUNT(*) c FROM event").fetchone()["c"]
    n_blob = conn.execute("SELECT COUNT(*) c FROM evidence_blob").fetchone()["c"]

    # SOW 125.6 - every object has identity and a current version
    orphan = conn.execute(
        "SELECT COUNT(*) c FROM object WHERE current_version IS NULL").fetchone()["c"]
    chk("every_object_has_current_version", orphan == 0,
        "%d object(s) without a current version" % orphan)

    # SOW 125.2 - every version has provenance
    noprov = conn.execute(
        "SELECT COUNT(*) c FROM object_version v LEFT JOIN provenance p"
        " ON p.version_id=v.version_id WHERE p.provenance_id IS NULL").fetchone()["c"]
    chk("every_version_has_provenance", noprov == 0,
        "%d version(s) with no provenance row" % noprov)

    # SOW 125.5 - version chains are intact
    badchain = conn.execute(
        "SELECT COUNT(*) c FROM object_version v WHERE v.parent_version_id IS NOT NULL"
        " AND NOT EXISTS(SELECT 1 FROM object_version p"
        "                WHERE p.version_id=v.parent_version_id)").fetchone()["c"]
    chk("version_chains_intact", badchain == 0,
        "%d version(s) point at a missing parent" % badchain)

    # SOW 125.7 - acquisition is always evidenced by an event
    noevt = conn.execute(
        "SELECT COUNT(*) c FROM object o WHERE NOT EXISTS"
        "(SELECT 1 FROM event e WHERE e.object_id=o.object_id)").fetchone()["c"]
    chk("every_object_has_event_history", noevt == 0,
        "%d object(s) with no event history" % noevt)

    # SOW 125.11 - account boundaries never collapsed.
    #
    # The obvious check - "does one native_id appear under more than one
    # account?" - is WRONG, and was wrong here until a second Claude account
    # made it visible. Native ids are only unique within an account: every
    # Claude export contains `memory:conversations_memory:0`, and memory files
    # are keyed by path, so two people's archives legitimately share a native
    # id. Under correct behaviour those are two source_object rows under two
    # accounts. The old check called that a violation - it would have fired the
    # first time a second account was ingested, and until then it passed only
    # because there was nothing that could break it.
    #
    # What actually matters is the opposite direction: knowing WHOSE each row
    # is. A row with no account under a source that HAS accounts is one where
    # ownership has been lost, and that is what a later merge feeds on.
    orphaned = conn.execute(
        "SELECT COUNT(*) c FROM source_object so"
        " WHERE so.account_id IS NULL AND EXISTS"
        "   (SELECT 1 FROM account a WHERE a.source_id = so.source_id)").fetchone()["c"]
    chk("account_boundaries_preserved", orphaned == 0,
        "%d source object(s) have no account under a source that has accounts" % orphaned)

    # And the collapse itself. If a second account's item is wrongly matched
    # onto the first account's object there is only ever ONE source_object row,
    # so nothing "spans" anything and no per-row check can see it. Check the
    # canonical object directly: one object, one account, always.
    shared = conn.execute(
        "SELECT COUNT(*) c FROM (SELECT p.object_id,"
        "        COUNT(DISTINCT COALESCE(so.account_id,'~')) a"
        "   FROM provenance p"
        "   JOIN source_object so ON so.source_object_id = p.source_object_id"
        "  GROUP BY p.object_id HAVING a>1)").fetchone()["c"]
    chk("objects_not_shared_across_accounts", shared == 0,
        "%d canonical object(s) carry provenance from more than one account" % shared)

    # The integrity check walks the DATABASE and looks for its files. Nothing
    # walks the other way, so a file sitting in the evidence plane that no row
    # knows about is invisible - and those exist: evidence.store_file writes
    # ".tmp-<pid>" then renames, so every process killed mid-write leaves one
    # behind. Small individually; over a decade, an unaudited pile inside the
    # one plane that is supposed to be exactly accounted for.
    #
    # It walks every file, which on a network or FUSE-mounted store costs far
    # more than the rest of validate put together, so it rides with --deep
    # rather than slowing down the check people run constantly. When it does
    # not run it says so, instead of quietly not appearing.
    if deep:
        known = {r["content_hash"] for r in conn.execute(
            "SELECT content_hash FROM evidence_blob")}
        orphans, partials = [], []
        blobs_root = Path(paths.blobs)
        if blobs_root.exists():
            for root, _dirs, files in os.walk(str(blobs_root)):
                for name in files:
                    if ".tmp-" in name:
                        partials.append(os.path.join(root, name))
                    elif name not in known:
                        orphans.append(os.path.join(root, name))
        example = ""
        if partials or orphans:
            example = " - e.g. %s" % os.path.basename((partials + orphans)[0])
        chk("evidence_fully_accounted_for", not orphans and not partials,
            "%d interrupted write(s) and %d unreferenced file(s) under blobs/%s"
            % (len(partials), len(orphans), example),
            severity="WARN")
        extras["unaccounted_blob_files"] = (partials + orphans)[:50]
    else:
        chk("evidence_fully_accounted_for", False,
            "not run - it walks every file under blobs/; use --deep",
            severity="SKIPPED")

    # SOW 125.10 - duplicates linked, not deleted
    dups = conn.execute("SELECT COUNT(*) c FROM duplicate_link").fetchone()["c"]
    ghost = conn.execute(
        "SELECT COUNT(*) c FROM duplicate_link d WHERE NOT EXISTS"
        "(SELECT 1 FROM object o WHERE o.object_id=d.alias_object)").fetchone()["c"]
    chk("duplicates_linked_not_deleted", ghost == 0,
        "%d duplicate link(s) reference a deleted object (%d links total)" % (ghost, dups))

    # SOW 125.12 - conflicts are recorded, not silently resolved
    openc = conn.execute("SELECT COUNT(*) c FROM conflict WHERE status='OPEN'").fetchone()["c"]
    chk("conflicts_surfaced", True,
        "%d open conflict(s) awaiting review" % openc, severity="INFO")

    # SOW 125.14 - no secret values in the canonical store
    leak = conn.execute(
        "SELECT COUNT(*) c FROM credential_registry WHERE storage_location LIKE '%BEGIN%'"
        " OR storage_location LIKE 'sk-%' OR storage_location LIKE 'ghp_%'").fetchone()["c"]
    chk("no_secret_values_stored", leak == 0,
        "%d credential row(s) look like they contain a secret VALUE" % leak)

    # SOW 28/125.14 - no secret VALUE anywhere in canonical content.
    # This scans object BODIES. An earlier version only checked the credential
    # registry and therefore passed while 280 objects held live credentials.
    from .secrets import scan_body
    leaked = []
    for r in conn.execute("SELECT o.object_id, v.body FROM object o"
                          " JOIN object_version v ON v.version_id=o.current_version"
                          " WHERE v.body IS NOT NULL"):
        k = scan_body(r["body"])
        if k:
            leaked.append((r["object_id"], k))
    chk("no_secret_values_in_bodies", not leaked,
        "%d object body/bodies contain credential material%s" % (
            len(leaked), (" e.g. " + leaked[0][0] + ":" + ",".join(leaked[0][1])) if leaked else ""))

    # SOW 88 - derived indexes are marked rebuildable
    stale = conn.execute(
        "SELECT COUNT(*) c FROM derived_index_registry WHERE status='STALE'").fetchone()["c"]
    chk("derived_indexes_registered", True,
        "%d derived index(es) stale and awaiting rebuild" % stale, severity="INFO")

    integrity = None
    if deep:
        from . import evidence
        integrity = evidence.verify(conn, paths.blobs)
        chk("evidence_blobs_intact",
            integrity["missing"] == 0 and integrity["corrupt"] == 0,
            "ok=%d missing=%d corrupt=%d" % (integrity["ok"], integrity["missing"],
                                             integrity["corrupt"]))

    fails = [c for c in checks if c["status"] == "ERROR"]
    total_bytes = conn.execute(
        "SELECT COALESCE(SUM(byte_size),0) b FROM evidence_blob").fetchone()["b"]
    return {
        "counts": {"objects": n_obj, "versions": n_ver, "provenance": n_prov,
                   "events": n_evt, "evidence_blobs": n_blob,
                   "evidence_bytes": total_bytes,
                   "evidence_bytes_human": human(total_bytes)},
        "checks": checks,
        "integrity": integrity,
        "extras": extras,
        "status": "PASSED" if not fails else "FAILED",
        "failed_checks": len(fails),
    }
