"""secondbrain CLI (SOW 115, 116).

Every subcommand in SOW 115 exists. Those that cannot yet do real work say
NOT_IMPLEMENTED and name the phase that unblocks them, with a non-zero exit.
A command that silently pretends to succeed would violate SOW 43 and 107, so
none of them do.
"""
import argparse, json, os, shutil, sys
from pathlib import Path

from . import __version__, SCHEMA_VERSION, db, evidence, export, search, dedupe, validate, ids, graph, agent, sync, dr, insight
from .config import Paths
from .events import audit
from .util import now_iso, human, jdump

BANNER = "secondbrain %s (schema %s)" % (__version__, SCHEMA_VERSION)


def _conn(a, create=False):
    p = Paths(a.root).ensure() if create else Paths(a.root)
    return db.connect(p.db, create=create), p


def _out(a, obj):
    if getattr(a, "json", False):
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
        return True
    return False


def _todo(name, phase, why):
    print("%s: NOT_IMPLEMENTED" % name)
    print("  blocked on : %s" % phase)
    print("  reason     : %s" % why)
    print("\nThis is a deliberate refusal, not a failure. Reporting a stub as")
    print("working would violate SOW 43 (completion proof) and 107 (no invented")
    print("capabilities).")
    return 3


# --------------------------------------------------------------------------
def cmd_init(a):
    p = Paths(a.root).ensure()
    conn = db.connect(p.db, create=True)
    db.init_schema(conn)
    audit(conn, "system", "init", "OK", target=str(p.root))
    conn.commit()
    print(BANNER)
    print("initialised canonical store at %s" % p.root)
    print("  evidence/   EVIDENCE PLANE   immutable, content-addressed")
    print("  canonical/  KNOWLEDGE PLANE  authority: canonical.sqlite3 + mirror/")
    print("  derived/    DERIVED PLANE    rebuildable, safe to delete")
    print("\nCanonical authority note (SOW 21.1): the authoritative store belongs on")
    print("the Ubuntu server. This local tree is a working replica until the server")
    print("audit completes and Phase 25 sync is configured.")
    return 0


def cmd_status(a):
    conn, p = _conn(a)
    q = lambda s: conn.execute(s).fetchone()[0]
    srcs = conn.execute("SELECT state, COUNT(*) c FROM source GROUP BY state").fetchall()
    data = {
        "root": str(p.root), "schema": db.schema_version(conn),
        "servers_audited": q("SELECT COUNT(*) FROM object WHERE object_class='Source'"),
        "accounts": q("SELECT COUNT(*) FROM account"),
        "sources": q("SELECT COUNT(*) FROM source"),
        "source_states": {r["state"]: r["c"] for r in srcs},
        "files": q("SELECT COUNT(*) FROM object WHERE object_class='File'"),
        "urls": q("SELECT COUNT(*) FROM url"),
        "url_visits": q("SELECT COUNT(*) FROM url_visit"),
        "bookmarks": q("SELECT COUNT(*) FROM object WHERE object_class='Bookmark'"),
        "knowledge_objects": q("SELECT COUNT(*) FROM object"),
        "versions": q("SELECT COUNT(*) FROM object_version"),
        "relationships": q("SELECT COUNT(*) FROM relationship"),
        "claims": q("SELECT COUNT(*) FROM claim"),
        "events": q("SELECT COUNT(*) FROM event"),
        "evidence_blobs": q("SELECT COUNT(*) FROM evidence_blob"),
        "evidence_bytes": q("SELECT COALESCE(SUM(byte_size),0) FROM evidence_blob"),
        "duplicates_linked": q("SELECT COUNT(*) FROM duplicate_link"),
        "conflicts_open": q("SELECT COUNT(*) FROM conflict WHERE status='OPEN'"),
        "dead_letter_pending": q("SELECT COUNT(*) FROM dead_letter WHERE status='PENDING_REVIEW'"),
        "jobs": q("SELECT COUNT(*) FROM acquisition_manifest"),
        "audit_records": q("SELECT COUNT(*) FROM audit_event"),
    }
    if _out(a, data):
        return 0
    print("SECOND BRAIN STATUS"); print("=" * 60)
    print("Root              : %s" % data["root"])
    print("Schema            : %s" % data["schema"])
    print("-" * 60)
    for k in ("servers_audited","accounts","sources","files","urls","url_visits",
              "bookmarks","knowledge_objects","versions","relationships","claims",
              "events","evidence_blobs","duplicates_linked","conflicts_open",
              "dead_letter_pending","jobs","audit_records"):
        print("%-18s: %s" % (k.replace("_", " ").title(), data[k]))
    print("%-18s: %s" % ("Evidence Size", human(data["evidence_bytes"])))
    print("-" * 60)
    print("Source states     : %s" % (data["source_states"] or "none registered"))
    nis = [k for k, v in search.RANK_COMPONENTS.items() if v.startswith("NOT")]
    print("\nNot yet implemented (declared, not hidden):")
    print("  retrieval signals : %s" % ", ".join(nis))
    print("  dedup kinds       : %s" % ", ".join(
        k for k, v in dedupe.KINDS.items() if v.startswith("NOT")))
    return 0


def cmd_ingest(a):
    from .adapters import REGISTRY, NEEDS_IDENTITY, PHASE
    if a.adapter not in REGISTRY:
        print("unknown adapter %r. available:" % a.adapter)
        for name in sorted(REGISTRY):
            print("  %-14s phase %-5s %s" % (
                name, PHASE.get(name, "?"),
                "--identity required" if name in NEEDS_IDENTITY else ""))
        return 2
    conn, p = _conn(a)
    kw = {}
    if a.adapter in ("filesystem", "obsidian"):
        kw["include_excluded"] = a.include_excluded
    if a.adapter == "filesystem":
        kw["recurse"] = not a.no_recurse
    if a.adapter == "bookmarks":
        kw["browser"] = a.browser
    if a.adapter == "claude-export":
        kw["allow_partial"] = a.allow_partial
    if a.adapter in NEEDS_IDENTITY:
        kw["identity"] = a.identity
    if a.adapter == "mbox":
        kw["min_match"] = a.min_identity_match
    ad = REGISTRY[a.adapter](conn, p, account_id=a.account, **kw)
    job, res, status = ad.run(a.target, limit=a.limit, dry_run=a.dry_run)
    d = res.as_dict(); d.update({"job_id": job, "status": status,
                                 "adapter": a.adapter, "target": a.target})
    if hasattr(ad, "stats"):
        d["adapter_stats"] = ad.stats
    if _out(a, d):
        return 0 if status in ("COMPLETED", "SKIPPED") else 1
    print("JOB           : %s" % job)
    print("ADAPTER       : %s" % a.adapter)
    print("TARGET        : %s" % a.target)
    print("DISCOVERED    : %d" % res.discovered)
    print("ACQUIRED      : %d" % res.acquired)
    print("  created     : %d" % res.created)
    print("  versioned   : %d" % res.versioned)
    print("  unchanged   : %d" % res.unchanged)
    print("FAILED        : %d" % res.failed)
    print("SKIPPED       : %d" % res.skipped)
    if hasattr(ad, "stats"):
        for k, v in ad.stats.items():
            print("  %-11s : %s" % (k, v))
    print("STATUS        : %s" % status)
    if res.failed:
        print("\n%d failure(s) are in the dead-letter queue, not lost:" % res.failed)
        print("  secondbrain audit --dead-letter")
    return 0 if status in ("COMPLETED", "SKIPPED") else 1


def cmd_validate(a):
    conn, p = _conn(a)
    r = validate.run(conn, p, deep=a.deep)
    if _out(a, r):
        return 0 if r["status"] == "PASSED" else 1
    print("VALIDATION"); print("=" * 60)
    for k, v in r["counts"].items():
        print("  %-22s %s" % (k, v))
    print("-" * 60)
    for c in r["checks"]:
        print("  [%-5s] %-38s %s" % (c["status"], c["check"], c["detail"]))
    print("-" * 60)
    print("STATUS: %s (%d failed check(s))" % (r["status"], r["failed_checks"]))
    if not a.deep:
        print("\nRe-run with --deep to re-hash every evidence blob (SOW 18 integrity).")
    return 0 if r["status"] == "PASSED" else 1


def cmd_search(a):
    conn, p = _conn(a)
    r = search.query(conn, p.fts_db, a.query, limit=a.limit,
                     expand=not a.no_expand, use_graph=not a.no_graph)
    res = r["results"]
    if _out(a, {"query": a.query, "results": res,
                "expansion_terms": r["expansion_terms"],
                "graph_entities": r["graph_entities"],
                "candidates_considered": r["pool_size"],
                "ranking": search.RANK_COMPONENTS}):
        return 0
    if not res:
        print("no matches for %r" % a.query); return 0
    for i, x in enumerate(res, 1):
        print("%2d. [%s] %s" % (i, x["object_class"], x["title"]))
        print("    %s  score=%s  authority=%s"
              % (x["object_id"], x["score"], x["authority"]))
        if x["snippet"]:
            print("    %s" % x["snippet"].replace("\n", " ")[:160])
        if a.explain:
            print("    signals: %s" % "  ".join(
                "%s=%s" % (k, v) for k, v in x["score_components"].items() if v))
    print()
    if r["expansion_terms"]:
        print("expanded with: %s" % ", ".join(r["expansion_terms"]))
        print("  (terms far more common in the strongest results than in the")
        print("   corpus - learned from YOUR documents, not a pretrained model)")
    if r["graph_entities"]:
        print("graph entities matched: %s" % ", ".join(r["graph_entities"][:6]))
    nis = [k for k, v in search.RANK_COMPONENTS.items() if v.startswith("NOT")]
    print("%d of %d ranking signals active. Still NOT_IMPLEMENTED: %s"
          % (len(search.RANK_COMPONENTS) - len(nis), len(search.RANK_COMPONENTS),
             ", ".join(nis)))
    return 0


def cmd_rebuild_index(a):
    conn, p = _conn(a)
    p.ensure()
    import sys, time
    before = search.build_progress(p.fts_db)
    if before and before.get("status") == "BUILDING":
        print("resuming an interrupted build at %s/%s object(s)"
              % (before.get("done"), before.get("total")))
        if before.get("queryable"):
            print("  (the previous index stays queryable until this one finishes)")
    t0 = time.time()

    def tick(done, total):
        if a.quiet:
            return
        rate = done / max(time.time() - t0, 0.001)
        sys.stderr.write("\r  indexed %d/%d (%.0f/s)   " % (done, total, rate))
        sys.stderr.flush()

    n = search.build(conn, p.fts_db, on_progress=tick)
    if not a.quiet:
        sys.stderr.write("\r" + " " * 40 + "\r")
    audit(conn, "derived", "rebuild_index", "OK",
          detail={"objects": n, "seconds": round(time.time() - t0, 1)})
    conn.commit()
    print("rebuilt FTS index from canonical content: %d object(s) in %.1fs"
          % (n, time.time() - t0))
    print("index path: %s (derived - safe to delete at any time)" % p.fts_db)
    return 0


def cmd_duplicates(a):
    conn, p = _conn(a)
    groups = dedupe.find_exact(conn)
    reclaim = sum(g["bytes_each"] * (g["count"] - 1) for g in groups)
    variants = dedupe.find_url_variants(conn)
    linked = 0
    if a.link:
        linked = dedupe.record(conn, groups, "exact")
        linked += dedupe.record(conn, variants, "url")
        if not getattr(a, "json", False):
            print("linked %d alias object(s) to their canonical object." % linked)
            print("Nothing was deleted: aliases keep their own provenance (SOW 19, 125.10).")
    payload = {"linked": linked, "url_variant_groups": len(variants),
               "exact_groups": len(groups),
               "redundant_objects": sum(g["count"] - 1 for g in groups),
               "reclaimable_bytes": reclaim,
               "reclaimable_human": human(reclaim),
               "kinds": dedupe.KINDS, "groups": groups[:50]}
    if _out(a, payload):
        return 0
    print("DUPLICATE ANALYSIS"); print("=" * 60)
    print("exact groups        : %d" % len(groups))
    print("url variant groups  : %d" % len(variants))
    print("redundant objects   : %d" % payload["redundant_objects"])
    print("reclaimable         : %s" % payload["reclaimable_human"])
    print("-" * 60)
    for k, v in dedupe.KINDS.items():
        print("  %-13s %s" % (k, v))
    for g in groups[:15]:
        print("  %s x%d  %s" % (g["content_hash"][:16], g["count"],
                                ",".join(g["object_ids"][:4])))
    if not a.link:
        print("\nRun with --link to record duplicate links (still deletes nothing).")
    return 0


def cmd_history(a):
    conn, p = _conn(a)
    top_dom = conn.execute(
        "SELECT registrable_domain d, COUNT(*) n, SUM(visit_count) v FROM url"
        " WHERE registrable_domain IS NOT NULL GROUP BY d ORDER BY n DESC LIMIT ?",
        (a.limit,)).fetchall()
    years = conn.execute(
        "SELECT substr(timestamp,1,4) y, COUNT(*) n FROM url_visit"
        " WHERE timestamp IS NOT NULL GROUP BY y ORDER BY y").fetchall()
    span = conn.execute(
        "SELECT MIN(timestamp) a, MAX(timestamp) b FROM url_visit"
        " WHERE timestamp IS NOT NULL").fetchone()
    data = {"urls": conn.execute("SELECT COUNT(*) c FROM url").fetchone()["c"],
            "visits": conn.execute("SELECT COUNT(*) c FROM url_visit").fetchone()["c"],
            "domains": conn.execute(
                "SELECT COUNT(DISTINCT registrable_domain) c FROM url").fetchone()["c"],
            "first_seen": span["a"], "last_seen": span["b"],
            "by_year": {r["y"]: r["n"] for r in years},
            "top_domains": [{"domain": r["d"], "urls": r["n"], "visits": r["v"]}
                            for r in top_dom]}
    if _out(a, data):
        return 0
    print("HISTORICAL WEB CORPUS"); print("=" * 60)
    print("urls        : %d" % data["urls"])
    print("visits      : %d" % data["visits"])
    print("domains     : %d" % data["domains"])
    print("span        : %s -> %s" % (data["first_seen"], data["last_seen"]))
    print("-" * 60)
    print("by year (SOW 62 temporal clustering input):")
    for y, n in sorted(data["by_year"].items()):
        print("  %s  %5d  %s" % (y, n, "#" * min(50, n // max(1, max(data["by_year"].values()) // 50 or 1))))
    print("-" * 60)
    print("top domains (SOW 61 research domain graph input):")
    for d in data["top_domains"]:
        print("  %-40s %5d urls" % (d["domain"][:40], d["urls"]))
    return 0


def cmd_inventory(a):
    conn, p = _conn(a)
    rows = conn.execute(
        "SELECT object_class, COUNT(*) n FROM object GROUP BY object_class"
        " ORDER BY n DESC").fetchall()
    srcs = conn.execute(
        "SELECT s.source_id, s.display_name, s.state, s.capability_verified,"
        " (SELECT COUNT(*) FROM source_object o WHERE o.source_id=s.source_id) items"
        " FROM source s ORDER BY items DESC").fetchall()
    data = {"by_class": {r["object_class"]: r["n"] for r in rows},
            "sources": [dict(r) for r in srcs]}
    if _out(a, data):
        return 0
    print("KNOWLEDGE INVENTORY"); print("=" * 60)
    for k, v in data["by_class"].items():
        print("  %-24s %6d" % (k, v))
    print("-" * 60)
    print("SOURCE REGISTRY")
    print("  %-28s %-22s %-10s %s" % ("source", "state", "items", "verified"))
    for s in data["sources"]:
        print("  %-28s %-22s %-10d %s" % (s["source_id"][:28], s["state"],
              s["items"], "yes" if s["capability_verified"] else "UNVERIFIED"))
    return 0


def cmd_accounts(a):
    conn, p = _conn(a)
    rows = conn.execute(
        "SELECT a.account_id,a.source_id,a.identifier,a.display_name,a.verified,"
        "a.discovered_via,a.state FROM account a ORDER BY a.source_id").fetchall()
    if _out(a, [dict(r) for r in rows]):
        return 0
    print("ACCOUNT INVENTORY (SOW 45: never assume one account)"); print("=" * 60)
    if not rows:
        print("  none registered yet.")
        print("  Account discovery is MANDATORY (SOW 125.31) - an empty registry")
        print("  means discovery has not run, not that only one account exists.")
        return 0
    for r in rows:
        print("  %-22s %-30s %s  via=%s" % (
            r["source_id"][:22], r["identifier"][:30],
            "verified" if r["verified"] else "UNVERIFIED", r["discovered_via"]))
    return 0


def cmd_audit(a):
    conn, p = _conn(a)
    if a.dead_letter:
        rows = conn.execute(
            "SELECT dl_id,job_id,stage,item_ref,error,status,last_failed_at"
            " FROM dead_letter ORDER BY last_failed_at DESC LIMIT ?", (a.limit,)).fetchall()
        if _out(a, [dict(r) for r in rows]):
            return 0
        print("DEAD LETTER QUEUE (%d shown)" % len(rows)); print("=" * 60)
        for r in rows:
            print("  [%s] %s" % (r["stage"], r["item_ref"][:80]))
            print("       %s" % r["error"].replace("\n", " ")[:150])
        return 0
    rows = conn.execute(
        "SELECT timestamp,actor,category,action,outcome,target,job_id"
        " FROM audit_event ORDER BY timestamp DESC LIMIT ?", (a.limit,)).fetchall()
    if _out(a, [dict(r) for r in rows]):
        return 0
    print("AUDIT LOG (%d most recent)" % len(rows)); print("=" * 60)
    for r in rows:
        print("  %s  %-12s %-22s %-8s %s" % (r["timestamp"], r["category"],
              r["action"], r["outcome"], (r["target"] or "")[:40]))
    return 0


def cmd_export(a):
    conn, p = _conn(a); p.ensure()
    m = export.export_all(conn, p.mirror)
    total = sum(t["rows"] for t in m["tables"].values())
    if _out(a, m):
        return 0
    print("exported %d rows across %d tables -> %s" % (total, len(m["tables"]), p.mirror))
    for t, i in sorted(m["tables"].items()):
        if i["rows"]:
            print("  %-26s %6d rows  %s" % (t, i["rows"], human(i["bytes"])))
    print("\nThis JSONL mirror is the portability guarantee (SOW 7, 91, 124).")
    return 0


def cmd_backup(a):
    conn, p = _conn(a)
    if a.status:
        places = a.dest_list or ([a.dest] if a.dest else [])
        st = dr.status(conn, places)
        if _out(a, st):
            return 0
        print("RECOVERY POSITION (SOW 26/93)"); print("=" * 68)
        print("  live store: %d objects, %d versions, %s of evidence"
              % (st["live"]["objects"], st["live"]["versions"],
                 human(st["live"]["evidence_bytes"])))
        for tier, x in st["tiers"].items():
            print("  %-10s backups=%-3d newest=%-21s last PROVEN=%s"
                  % (tier, x["backups"], x["newest"] or "-", x["last_proven"] or "NEVER"))
        for w in st["warnings"]:
            print("  ! %s" % w)
        if not st["warnings"]:
            print("  no warnings.")
        return 0

    if a.drill:
        rep = dr.drill(a.drill, live_conn=conn)
        audit(conn, "backup", "restore_drill", "OK" if rep["ok"] else "FAILED",
              target=a.drill, detail={"steps": rep["steps"]}); conn.commit()
        if _out(a, rep):
            return 0 if rep["ok"] else 1
        print("RESTORE DRILL (SOW 93)"); print("=" * 68)
        print("  backup: %s" % rep["backup"])
        for s in rep["steps"]:
            mark = "PASS" if s["ok"] else ("----" if s["ok"] is None else "FAIL")
            print("  [%s] %-40s %s" % (mark, s["step"], s["detail"]))
        print("-" * 68)
        print("VERDICT: %s" % ("RESTORE PROVEN" if rep["ok"] else "NOT PROVEN"))
        if rep["ok"]:
            print("The backup's manifest is now marked proven, dated today.")
        return 0 if rep["ok"] else 1

    if not a.dest:
        print("say --dest DIR to back up, --drill DIR to prove one, "
              "or --status --dest DIR")
        return 2
    r = dr.create(conn, p, a.dest, tier=a.tier,
                  include_evidence=a.include_evidence, label=a.label)
    if _out(a, r):
        return 0 if r["ok"] else 1
    if not r["ok"]:
        print("BACKUP REFUSED: %s" % r["error"]); return 1
    m = r["manifest"]
    print("backup written: %s" % r["path"])
    print("  tier      : %s" % m["tier"])
    print("  objects   : %d" % m["counts"]["objects"])
    print("  evidence  : %s" % ("yes, %s" % human(m["evidence_bytes_copied"])
                                if m["includes_evidence"] else
                                "NO - the database would restore, the bytes it "
                                "cites would not (--include-evidence)"))
    print("  derived   : intentionally excluded - rebuildable (SOW 88)")
    print("\nThis is a HYPOTHESIS until a restore proves it (SOW 93):")
    print("  secondbrain backup --drill %s" % r["path"])
    return 0


def cmd_health(a):
    conn, p = _conn(a)
    issues = []
    dl = conn.execute("SELECT COUNT(*) c FROM dead_letter WHERE status='PENDING_REVIEW'").fetchone()["c"]
    if dl: issues.append("%d item(s) in the dead-letter queue" % dl)
    st = conn.execute("SELECT COUNT(*) c FROM derived_index_registry WHERE status='STALE'").fetchone()["c"]
    if st: issues.append("%d derived index(es) stale" % st)
    cf = conn.execute("SELECT COUNT(*) c FROM conflict WHERE status='OPEN'").fetchone()["c"]
    if cf: issues.append("%d unresolved conflict(s)" % cf)
    bl = conn.execute("SELECT COUNT(*) c FROM source WHERE state IN ('BLOCKED','FAILED','AWAITING_CREDENTIALS')").fetchone()["c"]
    if bl: issues.append("%d source(s) blocked/failed/awaiting credentials" % bl)
    try:
        du = shutil.disk_usage(str(p.root))
        free_pct = 100.0 * du.free / du.total
        if free_pct < 30:
            issues.append("only %.1f%% free on the canonical volume (SOW 48 threshold)" % free_pct)
    except OSError:
        free_pct = None
    data = {"issues": issues, "free_pct": free_pct,
            "status": "OK" if not issues else "ATTENTION"}
    if _out(a, data):
        return 0
    print("HEALTH: %s" % data["status"])
    for i in issues: print("  - %s" % i)
    if free_pct is not None:
        print("  disk free: %.1f%%" % free_pct)
    if not issues: print("  no issues detected")
    return 0


def cmd_servers(a):
    conn, p = _conn(a)
    rows = conn.execute(
        "SELECT o.object_id,o.title,v.body FROM object o"
        " JOIN object_version v ON v.version_id=o.current_version"
        " WHERE o.object_class='Source' AND o.title LIKE 'Server audit:%'").fetchall()
    if not rows:
        print("SERVER MATRIX (SOW 102): NO EVIDENCE")
        print("=" * 60)
        print("No server audit has been ingested. Phases 1 and 2 are BLOCKED.")
        print("\nNeither shell available to this session can reach the servers")
        print("(SSH blocked from the container; 'Network is unreachable' from the")
        print("laptop VM; proxy returns 403 for the server IPs). This is a measured")
        print("finding, not an assumption.")
        print("\nTo unblock:")
        print("  1. run pkos/99-runbooks/pkos-server-audit.sh on each server")
        print("  2. drop the JSON into pkos/90-evidence/servers/")
        print("  3. secondbrain ingest server-audit <that folder>")
        return 3
    out = []
    for r in rows:
        try: out.append(json.loads(r["body"]))
        except (ValueError, TypeError): pass
    if _out(a, out): return 0
    print("SERVER MATRIX (SOW 102)"); print("=" * 100)
    print("%-18s %-22s %-6s %-8s %s" % ("HOST","AUDITED","ROOT","ERRORS","LOW-FREE FILESYSTEMS"))
    for s in out:
        lf = s.get("low_free_filesystems") or []
        print("%-18s %-22s %-6s %-8s %s" % (
            (s.get("host") or "?")[:18], (s.get("generated_at_utc") or "?")[:22],
            s.get("ran_as_root"), s.get("error_count"),
            (lf[0][:44] if lf else "none >=70% used")))
        if s.get("missing_sections"):
            print("   MISSING SECTIONS: %s" % ", ".join(s["missing_sections"]))
    return 0


def _top(d, n=4):
    if not d:
        return "(none)"
    items = sorted(d.items(), key=lambda x: -x[1])[:n]
    return ", ".join("%s=%d" % (k, v) for k, v in items)

def cmd_secrets(a):
    from . import secrets as sec
    conn, p = _conn(a)
    found = sec.find_all(conn)
    payload = {"objects_with_secrets": len(found),
               "by_kind": {}, "sample": found[:25]}
    for f in found:
        for k in f["kinds"]:
            payload["by_kind"][k] = payload["by_kind"].get(k, 0) + 1
    if getattr(a, "sample", False):
        payload["triage"] = sec.sample(conn)
    if a.redact:
        if not found:
            payload["redacted"] = 0
        else:
            n = sec.redact(conn, found,
                           surgical=not getattr(a, 'whole_body', False))
            payload["redacted"] = n
    if _out(a, payload):
        return 0
    print("SECRET SCAN (SOW 28, 32)"); print("=" * 60)
    print("  objects with credential material : %d" % len(found))
    for k, v in sorted(payload["by_kind"].items(), key=lambda x: -x[1]):
        print("    %-14s %4d" % (k, v))
    if getattr(a, "sample", False):
        tri = payload["triage"]
        for kind in sorted(tri["examples"], key=lambda k: -payload["by_kind"].get(k, 0)):
            print("\n" + "-" * 60)
            print("  %s  (%d objects)" % (kind, payload["by_kind"].get(kind, 0)))
            print("  by object class : %s" % _top(tri["by_class"].get(kind, {})))
            print("  by source       : %s" % _top(tri["by_source"].get(kind, {})))
            print("  examples (match masked, shown in context):")
            for e in tri["examples"][kind]:
                print("    %s [%s]" % (e["object_id"], e["object_class"]))
                print("      ...%s..." % e["context"][:150])
        print("\n" + "-" * 60)
        print("  Read these before redacting. A pattern like ?token= matches a")
        print("  Drive share link exactly as happily as a live credential, and")
        print("  redaction replaces the whole body with a marker (SOW 97).")
    if a.redact:
        print("\n  REDACTED %d object body/bodies (%s)."
              % (payload["redacted"],
                 "whole body" if getattr(a, "whole_body", False)
                 else "matched spans only; rest of each document kept"))
        print("  Raw bytes untouched in the evidence plane. Each redaction is a")
        print("  new version (change_type=corrected) with an event, so it is")
        print("  auditable and reversible - never silent (SOW 10, 11, 125.10).")
        print("  Objects reclassified RESTRICTED. Re-run rebuild-index next.")
    else:
        print("\n  Nothing changed. Re-run with --redact to remove these from")
        print("  canonical bodies (the evidence plane keeps the originals).")
    return 0


def cmd_storage(a):   return _todo("storage", "Phase 1/2", "needs ingested server audits; run `secondbrain servers` for the unblock steps.")
def cmd_discover(a):  return _todo("discover", "Phase 0/21", "automated trace discovery (SOW 109) is a supervised process; wave 1 discovery ran as an agent swarm and its evidence is in pkos/90-evidence/.")
def cmd_graph(a):
    conn, p = _conn(a)
    if a.rebuild:
        p.ensure()
        st = graph.rebuild(conn, p)
        if _out(a, st):
            return 0
        print("GRAPH REBUILD (SOW 22)")
        print("=" * 60)
        for k, v in st.items():
            print("  %-26s %s" % (k, v))
        print("\nEntities come from structured evidence only. MENTIONS edges are")
        print("withheld for any term appearing in more than %.0f%% of objects." % (graph.SATURATION * 100))
        return 0

    if a.merge:
        if len(a.merge) != 2:
            print("--merge takes exactly two ids: CANONICAL ALIAS"); return 2
        if not a.confirmed_by:
            print("REFUSED: --merge requires --confirmed-by <name>.")
            print("Merging two entities is a judgement, not a computation.")
            print("The store records WHO decided it, so it can be questioned later.")
            return 2
        try:
            r = graph.merge_entities(conn, a.merge[0], a.merge[1],
                                     a.confirmed_by, a.reason)
        except ValueError as e:
            print("REFUSED: %s" % e); return 2
        if _out(a, r):
            return 0
        if r["already"]:
            print("already merged; nothing to do")
        else:
            print("merged %s <- %s" % (a.merge[0], a.merge[1]))
            print("  %d edge(s) inherited by the canonical entity" % r["edges_inherited"])
            print("  the alias keeps its id, history and edges (SOW 19)")
        return 0

    if a.find:
        rows = graph.find(conn, a.find)
        if _out(a, {"query": a.find, "entities": rows}):
            return 0
        if not rows:
            print("no entity matching %r. Run `secondbrain graph --rebuild` first?" % a.find)
            return 1
        for r in rows:
            print("  %-12s [%-9s] %-40s in-degree=%d"
                  % (r["object_id"], r["object_class"], r["title"][:40], r["in_degree"]))
        return 0

    if a.object:
        rows = graph.neighbours(conn, a.object, limit=a.limit)
        o = conn.execute("SELECT object_class, title FROM object WHERE object_id=?",
                         (a.object,)).fetchone()
        if _out(a, {"object_id": a.object, "neighbours": rows}):
            return 0
        if not o:
            print("no such object: %s" % a.object); return 1
        print("%s  [%s]  %s" % (a.object, o["object_class"], (o["title"] or "")[:60]))
        print("=" * 60)
        for r in rows:
            arrow = "->" if r["dir"] == "out" else "<-"
            print("  %s %-12s %-12s [%-9s] %s"
                  % (arrow, r["t"], r["id"], r["k"], (r["title"] or "")[:44]))
        if not rows:
            print("  (no edges)")
        return 0

    s = graph.stats(conn)
    if a.top or a.entity_class:
        rows = graph.top_entities(conn, a.entity_class, a.limit)
        if _out(a, {"stats": s, "top": rows}):
            return 0
        print("MOST CONNECTED ENTITIES%s" % (" [%s]" % a.entity_class if a.entity_class else ""))
        print("=" * 60)
        for r in rows:
            print("  %-12s [%-9s] %-42s %d edge(s)"
                  % (r["object_id"], r["object_class"], (r["title"] or "")[:42], r["deg"]))
        return 0

    if _out(a, s):
        return 0
    print("KNOWLEDGE GRAPH (SOW 22)")
    print("=" * 60)
    if not s["entity_total"]:
        print("  no entities yet - run: secondbrain graph --rebuild")
        return 0
    print("  entities: %d" % s["entity_total"])
    for k, v in sorted(s["entities"].items(), key=lambda x: -x[1]):
        print("    %-12s %6d" % (k, v))
    print("  relationships: %d" % s["relationship_total"])
    for k, v in s["relationships"].items():
        print("    %-12s %6d" % (k, v))
    return 0
def cmd_sync(a):
    conn, p = _conn(a)
    remote = None
    if a.against:
        remote = json.loads(Path(a.against).read_text(encoding="utf-8"))

    if a.manifest:
        m = sync.manifest(conn, with_blobs=not a.no_blobs)
        Path(a.manifest).write_text(json.dumps(m, indent=1), encoding="utf-8")
        if _out(a, {"written": a.manifest, "counts": m["counts"],
                    "lineage": m["store_lineage"]}):
            return 0
        print("manifest written: %s" % a.manifest)
        print("  lineage %s  ids to %d" % ((m["store_lineage"] or "?")[:8], m["id_high_water"]))
        for k, v in m["counts"].items():
            print("    %-16s %s" % (k, v))
        print("\nCopy this to the other machine and run: sync --plan --against <file>")
        return 0

    if a.plan:
        pl = sync.plan(sync.manifest(conn), remote)
        if _out(a, pl):
            return 0 if pl["can_send"] else 1
        print("SYNC PLAN (SOW 21.1: server is master, laptop is replica)")
        print("=" * 66)
        for r in pl["refusals"]:
            print("  REFUSED: %s" % r)
        for w in pl["warnings"]:
            print("  warning: %s" % w)
        if "db_delta" in pl:
            print("  canonical delta (local minus remote):")
            for k, v in pl["db_delta"].items():
                print("    %-16s %+d" % (k, v))
        print("  blobs to send  : %d (%s)"
              % (len(pl["blobs_to_send"]), human(pl["bytes_to_send"])))
        if not pl["can_send"]:
            print("\nNothing was built. Fix the refusal above first.")
        return 0 if pl["can_send"] else 1

    if a.export:
        r = sync.export_bundle(conn, p, a.export, against=remote,
                               canonical_only=a.canonical_only)
        if _out(a, r):
            return 0 if r["ok"] else 1
        if not r["ok"]:
            print("EXPORT REFUSED")
            for x in r["plan"]["refusals"]:
                print("  %s" % x)
            if r.get("error"):
                print("  %s" % r["error"])
            return 1
        print("bundle written: %s" % r["dir"])
        for n, s in r["sizes"].items():
            print("  %-24s %s" % (n, human(s)))
        print("  blobs in bundle          : %d" % r["blobs_in_bundle"])
        print("\nMove the directory to the target machine, then there:")
        print("  secondbrain sync --import <dir>")
        return 0

    if a.import_dir:
        r = sync.import_bundle(p, a.import_dir, local_conn=conn, force=a.force)
        if _out(a, r):
            return 0 if r["ok"] else 1
        print("SYNC IMPORT")
        print("=" * 66)
        for c in r["checked"]:
            print("  %-24s %s" % (c["file"], "ok" if c["ok"] else "MISMATCH"))
        if r["refusals"]:
            print("\nREFUSED - nothing was changed:")
            for x in r["refusals"]:
                print("  ! %s" % x)
            return 1
        print("  blobs added / verified   : %d / %d" % (r["blobs_added"], r["blobs_verified"]))
        if r.get("previous_db_moved_to"):
            print("  previous database moved  : %s" % r["previous_db_moved_to"])
        print("  integrity_check          : %s" % r["integrity_check"])
        print("  objects                  : %d" % r["objects"])
        print("\nNow run:  secondbrain validate --deep  &&  secondbrain rebuild-index")
        return 0 if r["ok"] else 1

    print("say what to do: --manifest FILE | --plan | --export DIR | --import DIR")
    return 2
def cmd_prune_writes(a):
    """SOW 97 gate, in miniature: discover, report impact, prove redundancy,
    require an explicit human flag, execute, audit."""
    conn, p = _conn(a)
    found = evidence.find_interrupted_writes(conn, p.blobs)
    prunable = [f for f in found if f["prunable"]]
    stuck = [f for f in found if not f["prunable"]]
    if _out(a, {"found": len(found), "prunable": len(prunable),
                "needs_review": len(stuck),
                "bytes_prunable": sum(f["bytes"] for f in prunable),
                "items": found[:200], "executed": bool(a.execute)}):
        pass
    else:
        print("INTERRUPTED WRITES (SOW 5.1, 97)")
        print("=" * 60)
        print("  fragments found     : %d" % len(found))
        print("  provably redundant  : %d (%s)"
              % (len(prunable), human(sum(f["bytes"] for f in prunable))))
        print("  need human review   : %d" % len(stuck))
        for f in stuck[:10]:
            print("    ! %s" % f["path"])
            print("      the blob it was becoming is %s; this fragment may be the"
                  % ("present but does NOT re-hash correctly"
                     if f["final_blob_present"] else "ABSENT"))
            print("      only copy of something acquired - do not delete it blindly")
    if not found:
        return 0
    if not a.execute:
        if not getattr(a, "json", False):
            print("\nNothing deleted. Re-run with --execute to remove the %d"
                  " provably redundant fragment(s)." % len(prunable))
        return 0
    removed, freed, refused = evidence.prune_interrupted_writes(conn, p.blobs, found)
    if not getattr(a, "json", False):
        print("\nremoved %d fragment(s), freed %s" % (len(removed), human(freed)))
        if refused:
            print("kept %d fragment(s) that were not provably redundant" % len(refused))
    return 0


def cmd_ask(a):
    """Assemble evidence. Deliberately answers nothing (SOW 3)."""
    conn, p = _conn(a)
    pack = agent.ask(conn, p, a.question, limit=a.limit)
    if _out(a, pack):
        return 0
    print("INQUIRY %s" % pack["inquiry_id"])
    print("=" * 70)
    print("question: %s" % pack["question"])
    r = pack["retrieval"]
    if r["expansion_terms"]:
        print("expanded: %s" % ", ".join(r["expansion_terms"]))
    if r["graph_entities"]:
        print("entities: %s" % ", ".join(r["graph_entities"][:6]))
    print()
    for i, e in enumerate(pack["evidence"], 1):
        flag = "" if e["traceable_to_bytes"] else "  [NOT TRACEABLE TO BYTES]"
        print("%2d. %s [%s] %s%s" % (i, e["object_id"], e["object_class"],
                                     (e["title"] or "")[:52], flag))
        if e["chain_breaks"]:
            for b in e["chain_breaks"]:
                print("      ! %s" % b)
        if e["excerpt"]:
            print("      %s" % e["excerpt"][:200].replace("\n", " "))
    g = pack["coverage_gaps"]
    print()
    print("WHAT THIS STORE CANNOT ANSWER FROM")
    print("-" * 70)
    print("  ingested   : %s" % ", ".join(g["sources_ingested"]))
    print("  NOT ingested: %s" % ", ".join(sorted(g["sources_declared_but_absent"])))
    print("  corpus spans: %s .. %s" % (g["corpus_spans"]["from"] or "?",
                                        g["corpus_spans"]["to"] or "?"))
    print("  ranking signals off: %s" % ", ".join(g["ranking_signals_off"]))
    print("  %d object(s) redacted for credentials; %d item(s) in the dead-letter queue"
          % (g["redacted_objects"], g["items_in_dead_letter"]))
    print()
    print("No answer is produced here. This is evidence, and what is missing")
    print("from it. Interpretation is a separate, recorded act:")
    print("  secondbrain answer --inquiry %s --model <id> --text <file> --cite <ids>"
          % pack["inquiry_id"])
    return 0


def cmd_answer(a):
    conn, p = _conn(a)
    text = Path(a.text).read_text(encoding="utf-8") if a.text else (a.body or "")
    if not text.strip():
        print("refusing to record an empty answer"); return 2
    oid, linked = agent.record_answer(conn, a.question or "(from inquiry)", text,
                                      a.cite or [], a.model, a.inquiry)
    if _out(a, {"object_id": oid, "cited": linked, "model": a.model}):
        return 0
    print("recorded %s" % oid)
    print("  knowledge_state : SYNTHESIZED  (a model wrote this, not you)")
    print("  validation      : REQUIRES_HUMAN_REVIEW")
    print("  cited           : %d source object(s) linked DERIVED_FROM" % linked)
    print("\nIt will never be retrieved as something you said. To promote it:")
    print("  secondbrain validate-answer %s --accept --note '...'" % oid)
    return 0


def cmd_validate_answer(a):
    conn, p = _conn(a)
    if not (a.accept or a.reject):
        print("say --accept or --reject"); return 2
    state = agent.validate_answer(conn, a.object_id,
                                 "accept" if a.accept else "reject",
                                 note=a.note)
    if _out(a, {"object_id": a.object_id, "knowledge_state": state}):
        return 0
    print("%s is now %s" % (a.object_id, state))
    return 0


def cmd_cite(a):
    conn, p = _conn(a)
    ch = agent.provenance_chain(conn, a.object_id)
    if ch is None:
        print("no such object: %s" % a.object_id); return 1
    srcs = [dict(r) for r in conn.execute(
        "SELECT o.object_id, o.object_class, o.title FROM relationship r"
        "  JOIN object o ON o.object_id=r.target_object"
        " WHERE r.source_object=? AND r.relationship_type='DERIVED_FROM'",
        (a.object_id,))]
    if _out(a, {"chain": ch, "derived_from": srcs}):
        return 0
    o, v, pr, b = ch["object"], ch["version"], ch["provenance"], ch["evidence_blob"]
    print("%s  [%s]  %s" % (o["object_id"], o["object_class"], (o["title"] or "")[:52]))
    print("  knowledge_state : %s" % o["knowledge_state"])
    print("  version         : %s (%s by %s)"
          % (v["version_id"], v["change_type"], v["changed_by"]) if v else "  version: MISSING")
    if pr:
        print("  provenance      : source=%s account=%s" % (pr["source_system"], pr["source_account"]))
        if pr["original_path"]:
            print("                    path=%s" % pr["original_path"])
        if pr["model"]:
            print("                    model=%s prompt=%s" % (pr["model"], pr["prompt_reference"]))
    if b:
        print("  evidence blob   : %s" % b["content_hash"])
        print("                    %s bytes at evidence/%s" % (b["byte_size"], b["storage_path"]))
    if srcs:
        print("  derived from    :")
        for s in srcs:
            print("      %s [%s] %s" % (s["object_id"], s["object_class"], (s["title"] or "")[:44]))
    print()
    if ch["complete"]:
        print("CHAIN COMPLETE - this traces to raw bytes on disk.")
        return 0

    # A synthesised object has no bytes of its own; that is not a break, it is
    # what synthesis MEANS. What matters is whether its parents trace. Calling
    # a well-sourced answer "do not cite this as fact" because it has no blob
    # of its own would train you to ignore the warning - and then it is worth
    # nothing when a chain is genuinely broken.
    if srcs and o["knowledge_state"] in ("SYNTHESIZED", "DERIVED", "HUMAN_VALIDATED"):
        parents = [agent.provenance_chain(conn, s["object_id"]) for s in srcs]
        good = [c for c in parents if c and c["complete"]]
        if len(good) == len(parents) and parents:
            print("CHAIN COMPLETE VIA %d PARENT(S) - this object has no bytes of"
                  % len(parents))
            print("its own (it was synthesised), and every source it rests on")
            print("traces to raw bytes on disk.")
            return 0
        print("CHAIN INCOMPLETE - %d of %d sources do not trace to bytes:"
              % (len(parents) - len(good), len(parents)))
        for s, c in zip(srcs, parents):
            if not (c and c["complete"]):
                print("  ! %s %s" % (s["object_id"], (c or {}).get("breaks", ["missing"])[0]))
        return 1

    print("CHAIN INCOMPLETE - do not cite this as fact:")
    for x in ch["breaks"]:
        print("  ! %s" % x)
    return 1


def cmd_gaps(a):
    conn, p = _conn(a)
    g = insight.gaps(conn)
    if _out(a, g):
        return 0
    print("KNOWLEDGE GAPS (SOW 73)"); print("=" * 74)
    print("What this store does NOT know. Every line is counted, and every")
    print("line names the thing that would close it.\n")
    for x in g["gaps"]:
        print("[%-6s] %-34s %s" % (x["severity"].upper(), x["gap"], "{:,}".format(x["count"])))
        print("           %s" % x["what"])
        print("           -> %s" % x["action"])
        if x["detail"] and a.detail:
            d = x["detail"]
            print("           %s" % (", ".join(d) if isinstance(d, list)
                                     else ", ".join(sorted(d))))
        print()
    if not g["gaps"]:
        print("no gaps detected - which on a corpus this size means the checks")
        print("are too narrow, not that the store is complete.")
    return 0


def cmd_meta(a):
    conn, p = _conn(a)
    m = insight.meta(conn)
    if _out(a, m):
        return 0
    def block(title, d, fmt="%-22s %s"):
        print("\n%s" % title); print("-" * 74)
        for k, v in d.items():
            print("  " + fmt % (k, "{:,}".format(v) if isinstance(v, int) else v))
    print("WHAT THIS STORE KNOWS ABOUT ITSELF (SOW 74)"); print("=" * 74)
    block("scale", m["scale"])
    block("by knowledge state", m["by_knowledge_state"])
    block("by authority", m["by_authority"])
    block("by decay status", m["by_decay"])
    v = m["voice"]
    print("\nvoice"); print("-" * 74)
    print("  first-hand (your words)   %s  (%.1f%%)"
          % ("{:,}".format(v["first_hand"]), v["first_hand_pct"]))
    print("  machine-generated         %s  (%.1f%%)"
          % ("{:,}".format(v["machine_generated"]), v["machine_pct"]))
    print("  %s" % v["note"])
    pr = m["provenance"]
    print("\nprovenance health"); print("-" * 74)
    print("  acquired objects          %s" % "{:,}".format(pr["acquired_objects"]))
    print("    tracing to raw bytes    %s  (%.2f%%)"
          % ("{:,}".format(pr["acquired_tracing_to_bytes"]),
             pr["traceable_pct_of_acquired"]))
    print("    NOT traceable           %s" % "{:,}".format(pr["acquired_untraceable"]))
    print("  derived objects           %s  (traced via parents)"
          % "{:,}".format(pr["derived_objects"]))
    r = m["read_vs_write"]
    print("\nread vs write"); print("-" * 74)
    print("  inquiries recorded        %s" % "{:,}".format(r["inquiries_recorded"]))
    print("  objects ever surfaced     %s  (%.3f%% of the store)"
          % ("{:,}".format(r["distinct_objects_ever_surfaced"]),
             r["pct_of_store_ever_surfaced"]))
    print("  %s" % r["note"])
    if a.by_year:
        block("authored by year", m["authored_by_year"])
    return 0


def cmd_cleanup(a):
    if not a.dry_run:
        print("cleanup: REFUSED without --dry-run.")
        print("Destructive operations require the SOW 97 gate: discover -> dry run ->")
        print("impact report -> dependency analysis -> backup check -> HUMAN APPROVAL.")
        print("This tool will not delete anything on the strength of a flag alone.")
        return 2
    return _todo("cleanup --dry-run", "Phase 2",
                 "the dry-run impact report is computed from server audit evidence, which has not been ingested yet.")


# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="secondbrain", description=BANNER)
    p.add_argument("--root", help="PKOS root (default $PKOS_ROOT or ~/.pkos)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help):
        s = sub.add_parser(name, help=help); s.set_defaults(fn=fn); return s

    add("init", cmd_init, "create the three-plane store")
    add("status", cmd_status, "master status dashboard (SOW 114)")
    add("inventory", cmd_inventory, "knowledge + source registry inventory")
    add("accounts", cmd_accounts, "account inventory (SOW 45)")
    add("servers", cmd_servers, "server matrix (SOW 102)")
    add("storage", cmd_storage, "storage heatmap")
    add("discover", cmd_discover, "digital trace discovery")
    s = add("graph", cmd_graph, "knowledge graph: entities, edges, traversal (SOW 22)")
    s.add_argument("--rebuild", action="store_true",
                   help="derive entities and edges from structured canonical data")
    s.add_argument("--find", metavar="TERM", help="find entities by name")
    s.add_argument("--object", metavar="KB-ID", help="show one object's edges")
    s.add_argument("--top", action="store_true", help="most connected entities")
    s.add_argument("--entity-class", metavar="CLASS",
                   help="restrict --top to one entity class (Domain, Folder, ...)")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--merge", nargs=2, metavar=("CANONICAL", "ALIAS"),
                   help="record that two entities are the same thing")
    s.add_argument("--confirmed-by", metavar="WHO",
                   help="required with --merge: who decided this")
    s.add_argument("--reason", help="why they are the same")
    s = add("sync", cmd_sync, "one-way replication, master -> replica (SOW 21.1/25)")
    s.add_argument("--manifest", metavar="FILE", help="write this store's manifest")
    s.add_argument("--no-blobs", action="store_true", help="manifest without the blob list")
    s.add_argument("--plan", action="store_true", help="what would move, and what is refused")
    s.add_argument("--export", metavar="DIR", help="build a transfer bundle")
    s.add_argument("--import", metavar="DIR", dest="import_dir", help="apply a bundle")
    s.add_argument("--against", metavar="FILE", help="the far end's manifest")
    s.add_argument("--force", action="store_true",
                   help="import even though this store is ahead (discards local work)")
    s.add_argument("--canonical-only", action="store_true",
                   help="ship the database without evidence; the importer verifies "
                        "it already holds every blob the database references")
    add("health", cmd_health, "operational health")
    s = add("secrets", cmd_secrets, "scan canonical bodies for credential material (SOW 28)")
    s.add_argument("--redact", action="store_true",
                   help="replace offending bodies with a marker; evidence plane untouched")
    s.add_argument("--whole-body", action="store_true",
                   help="replace the ENTIRE body with a marker instead of just "
                        "the matched spans. Rarely right: it removes the "
                        "document along with the key")
    s.add_argument("--sample", action="store_true",
                   help="show WHAT matched, in context and masked, plus the "
                        "distribution by object class and source. Run this "
                        "before --redact: it is the SOW 97 impact report")
    add("export", cmd_export, "write the canonical JSONL mirror")

    s = add("ingest", cmd_ingest, "run a source adapter")
    s.add_argument("adapter"); s.add_argument("target")
    s.add_argument("--account"); s.add_argument("--limit", type=int)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--include-excluded", action="store_true",
                   help="also ingest files SOW 75 excludes (code/build artefacts)")
    s.add_argument("--no-recurse", action="store_true",
                   help="filesystem adapter: only the loose files directly under the target")
    s.add_argument("--browser", default="unknown", help="bookmarks adapter: source browser")
    s.add_argument("--identity", default=None,
                   help="the account this export belongs to (email or handle). "
                        "REQUIRED by every adapter whose export carries no "
                        "trustworthy account marker - SOW 45/46: account "
                        "identity is explicit, never inferred")
    s.add_argument("--min-identity-match", type=float, default=0.05,
                   help="mbox adapter: refuse a mailbox where fewer than this "
                        "fraction of messages name --identity in any address "
                        "header (default 0.05; pass 0 to disable)")
    s.add_argument("--allow-partial", action="store_true",
                   help="claude-export adapter: ingest even though the manifest "
                        "names parts that are not present (the gap is recorded, "
                        "not hidden)")

    s = add("validate", cmd_validate, "invariant checks + completion proof (SOW 43)")
    s.add_argument("--deep", action="store_true", help="re-hash every evidence blob")

    s = add("search", cmd_search, "hybrid search over canonical content (SOW 71/72)")
    s.add_argument("query"); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--explain", action="store_true",
                   help="show each ranking signal's contribution per result")
    s.add_argument("--no-expand", action="store_true",
                   help="lexical only: skip pseudo-relevance-feedback expansion")
    s.add_argument("--no-graph", action="store_true",
                   help="skip the graph-connectivity signal")

    s = add("rebuild-index", cmd_rebuild_index, "rebuild derived indexes (SOW 88)")
    s.add_argument("--quiet", action="store_true", help="no progress output")

    s = add("duplicates", cmd_duplicates, "duplicate analysis (SOW 19)")
    s.add_argument("--link", action="store_true", help="record duplicate links (deletes nothing)")

    s = add("history", cmd_history, "historical web corpus (SOW 60-62)")
    s.add_argument("--limit", type=int, default=25)

    s = add("audit", cmd_audit, "audit log / dead-letter queue (SOW 95)")
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("--dead-letter", action="store_true")

    s = add("backup", cmd_backup,
            "backup, restore drill, recovery position (SOW 26/93)")
    s.add_argument("--dest", help="where backups live")
    s.add_argument("--dest-list", nargs="*", help="several locations, for --status")
    s.add_argument("--tier", default="primary", choices=list(dr.TIERS))
    s.add_argument("--label")
    s.add_argument("--include-evidence", action="store_true",
                   help="copy the evidence plane too; without it only the "
                        "database is recoverable")
    s.add_argument("--drill", metavar="DIR",
                   help="restore a backup into scratch and PROVE it")
    s.add_argument("--status", action="store_true",
                   help="how long ago did we last prove we could restore?")

    s = add("ask", cmd_ask, "assemble evidence for a question (answers nothing)")
    s.add_argument("question"); s.add_argument("--limit", type=int, default=8)

    s = add("answer", cmd_answer, "record an agent's interpretation, attributed")
    s.add_argument("--model", required=True, help="which model wrote it")
    s.add_argument("--inquiry", help="the INQ- id this answers")
    s.add_argument("--question"); s.add_argument("--text", help="file holding the answer")
    s.add_argument("--body", help="the answer inline")
    s.add_argument("--cite", nargs="*", help="object ids the answer rests on")

    s = add("validate-answer", cmd_validate_answer, "human accept/reject of an answer")
    s.add_argument("object_id"); s.add_argument("--accept", action="store_true")
    s.add_argument("--reject", action="store_true"); s.add_argument("--note")

    s = add("cite", cmd_cite, "walk an object back to the bytes it came from (SOW 17)")
    s.add_argument("object_id")

    s = add("gaps", cmd_gaps, "what this store does NOT know (SOW 73)")
    s.add_argument("--detail", action="store_true", help="list the specifics")

    s = add("meta", cmd_meta, "what this store knows about itself (SOW 74)")
    s.add_argument("--by-year", action="store_true")

    s = add("prune-writes", cmd_prune_writes,
            "remove blob fragments left by processes killed mid-write (gated)")
    s.add_argument("--execute", action="store_true",
                   help="actually delete the fragments proven redundant")

    s = add("cleanup", cmd_cleanup, "storage remediation (gated, SOW 97)")
    s.add_argument("--dry-run", action="store_true")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr); return 1
        raise
    except BrokenPipeError:
        return 0
