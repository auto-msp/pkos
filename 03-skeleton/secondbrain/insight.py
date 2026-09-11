"""Continuous knowledge intelligence (SOW 73, 74 - Phase 27).

TWO QUESTIONS NOBODY ASKS THEIR NOTES
=====================================
    gaps  what does this store NOT know, and how would I close it?
    meta  what does this store know ABOUT ITSELF?

Every knowledge system can tell you what it holds. Almost none will tell you
what it is missing, because that requires deciding in advance what absence
looks like - and absence never raises an exception. That is the same blindness
that let a staging deploy die in June and get noticed in September.

So every gap here is COUNTABLE and comes with the action that closes it. A gap
you cannot count is an anxiety, not a finding.

Nothing in this module interprets. It measures, and it says what it cannot
measure. Interpretation is the agent's job (Phase 24), and the numbers here are
exactly the sort of thing an agent should be handed rather than left to guess.
"""
import collections
import json

from . import search
from .util import now_iso


# ---------------------------------------------------------------- gaps (73)
def gaps(conn):
    out = {"generated_at": now_iso(), "gaps": []}

    def gap(key, count, what, action, severity="info", detail=None):
        if count:
            out["gaps"].append({"gap": key, "count": count, "what": what,
                                "action": action, "severity": severity,
                                "detail": detail})

    q = lambda s, *a: conn.execute(s, a).fetchone()[0]

    gap("urls_never_fetched",
        q("SELECT COUNT(*) FROM url WHERE fetch_status='NOT_FETCHED'"),
        "URLs whose page CONTENT was never captured - the store holds the "
        "address and the title, not what the page said",
        "Phase 7: fetch and snapshot them, or accept them as pointers",
        "high")

    gap("files_named_but_never_acquired",
        q("SELECT COUNT(*) FROM object WHERE object_class='FileReference'"),
        "files referenced inside Claude conversations whose BYTES the export "
        "never contained",
        "re-upload the originals, or accept them as citations that cannot be "
        "opened",
        "high")

    # An aggregate count here is useless. "6,932 objects have no body" reads
    # as a catastrophe; broken down it is mostly FileReference objects, which
    # have no body BY DESIGN because the export never carried the bytes. A
    # finding you cannot act on is an anxiety, so this one arrives split by
    # class with the by-design share named.
    empty_by_class = {r["object_class"]: r["n"] for r in conn.execute(
        "SELECT o.object_class, COUNT(*) n FROM object o JOIN object_version v"
        "  ON v.version_id=o.current_version"
        " WHERE (v.body IS NULL OR v.body='') AND v.body_ref IS NULL"
        " GROUP BY 1 ORDER BY 2 DESC")}
    BY_DESIGN = {"FileReference"}       # named in an export, bytes never sent
    unexpected = sum(n for k, n in empty_by_class.items() if k not in BY_DESIGN)
    gap("objects_with_no_body_unexpected", unexpected,
        "objects with no readable content, EXCLUDING the classes that are "
        "empty by design (%s)" % ", ".join(sorted(BY_DESIGN)),
        "mostly genuinely-empty chat messages; investigate any other class "
        "here, it usually means a parser gave up quietly",
        "medium", detail=empty_by_class)

    gap("content_withheld_for_credentials",
        q("SELECT COUNT(*) FROM object WHERE classification='RESTRICTED'"),
        "objects whose body was replaced because it held credential material",
        "the original bytes are intact in the evidence plane; retrieve "
        "deliberately with `cite` if you need one",
        "info")

    gap("items_in_dead_letter",
        q("SELECT COUNT(*) FROM dead_letter"),
        "items that failed to ingest and were isolated rather than lost",
        "secondbrain audit --dead-letter",
        "medium")

    gap("answers_awaiting_human_review",
        q("SELECT COUNT(*) FROM object WHERE object_class='Answer'"
          "   AND knowledge_state='SYNTHESIZED'"),
        "agent answers nobody has accepted or rejected",
        "secondbrain validate-answer <id> --accept|--reject",
        "medium")

    gap("open_conflicts",
        q("SELECT COUNT(*) FROM conflict WHERE status='OPEN'"),
        "contradictions the store has recorded and nobody has resolved",
        "review them; an unresolved conflict silently picks a winner at "
        "retrieval time",
        "high")

    # sources declared in the SOW but never ingested
    present = {r[0] for r in conn.execute("SELECT DISTINCT source_id FROM source_object")}
    from .agent import DECLARED_BUT_ABSENT
    gap("sources_never_ingested", len(DECLARED_BUT_ABSENT),
        "whole sources named in the SOW that have never been acquired",
        "each needs an export you request; see NEXT-STEPS.md",
        "high", detail=DECLARED_BUT_ABSENT)

    # ranking signals still off
    off = [k for k, v in search.RANK_COMPONENTS.items() if v.startswith("NOT")]
    gap("ranking_signals_unimplemented", len(off),
        "retrieval signals declared by the SOW that do not yet contribute",
        "Phase 7 / a labelled benchmark; see search.RANK_COMPONENTS",
        "info", detail=off)

    # temporal holes: months inside the corpus span with nothing acquired
    months = [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(source_created_at,1,7) m FROM source_object"
        " WHERE source_created_at IS NOT NULL AND length(source_created_at)>=7"
        " ORDER BY 1") if r[0]]
    dark = []
    if len(months) >= 2:
        y, m = (int(x) for x in months[0].split("-"))
        ey, em = (int(x) for x in months[-1].split("-"))
        have = set(months)
        while (y, m) <= (ey, em):
            key = "%04d-%02d" % (y, m)
            if key not in have:
                dark.append(key)
            m += 1
            if m == 13:
                y, m = y + 1, 1
    gap("months_with_nothing_captured", len(dark),
        "months inside the corpus span where NOTHING was acquired - either "
        "you were quiet, or a source that covers that period is missing",
        "compare against the uningested sources above before assuming quiet",
        "medium", detail=dark[:40])

    out["gaps"].sort(key=lambda g: ({"high": 0, "medium": 1, "info": 2}[g["severity"]],
                                    -g["count"]))
    return out


# ------------------------------------------------------------- meta (74)
def meta(conn):
    rows = lambda s: [dict(r) for r in conn.execute(s)]
    q = lambda s: conn.execute(s).fetchone()[0]
    m = {"generated_at": now_iso()}

    m["scale"] = {
        "objects": q("SELECT COUNT(*) FROM object"),
        "versions": q("SELECT COUNT(*) FROM object_version"),
        "relationships": q("SELECT COUNT(*) FROM relationship"),
        "evidence_blobs": q("SELECT COUNT(*) FROM evidence_blob"),
        "evidence_bytes": q("SELECT COALESCE(SUM(byte_size),0) FROM evidence_blob"),
        "accounts": q("SELECT COUNT(*) FROM account"),
        "sources": q("SELECT COUNT(DISTINCT source_id) FROM source_object"),
    }

    m["by_knowledge_state"] = {r["knowledge_state"]: r["n"] for r in rows(
        "SELECT knowledge_state, COUNT(*) n FROM object GROUP BY 1 ORDER BY 2 DESC")}
    m["by_authority"] = {r["authority"] or "unset": r["n"] for r in rows(
        "SELECT authority, COUNT(*) n FROM object GROUP BY 1 ORDER BY 2 DESC")}
    m["by_class"] = {r["object_class"]: r["n"] for r in rows(
        "SELECT object_class, COUNT(*) n FROM object GROUP BY 1 ORDER BY 2 DESC")}
    m["by_decay"] = {r["decay_status"]: r["n"] for r in rows(
        "SELECT decay_status, COUNT(*) n FROM object GROUP BY 1 ORDER BY 2 DESC")}

    # How much of this is actually YOURS versus a machine's account of it.
    total = m["scale"]["objects"] or 1
    mine = q("SELECT COUNT(*) FROM object WHERE authority='PRIMARY SOURCE'")
    ai = q("SELECT COUNT(*) FROM object WHERE authority='AI-GENERATED'")
    m["voice"] = {
        "first_hand": mine, "machine_generated": ai,
        "first_hand_pct": round(100.0 * mine / total, 1),
        "machine_pct": round(100.0 * ai / total, 1),
        "note": "AI-GENERATED objects rank at 0.1 against 1.0 for first-hand "
                "material, so a large machine share does not drown out your "
                "own words - but it is worth knowing the ratio.",
    }

    # Provenance health. The first version of this divided "objects with a
    # blob" by "objects minus derived ones" and reported 100.1% traceable.
    # A percentage over 100 is the arithmetic saying the numerator and the
    # denominator describe different populations - some DERIVED objects do
    # carry an original_hash. Both figures are now computed over the SAME
    # population, so the ratio means something.
    DERIVED_STATES = "('DERIVED','SYNTHESIZED','HUMAN_VALIDATED')"
    acquired = q("SELECT COUNT(*) FROM object WHERE knowledge_state NOT IN %s"
                 % DERIVED_STATES)
    traceable_acquired = q(
        "SELECT COUNT(*) FROM object o JOIN provenance p"
        "  ON p.version_id=o.current_version"
        " WHERE o.knowledge_state NOT IN %s"
        "   AND p.original_hash IS NOT NULL AND EXISTS"
        "  (SELECT 1 FROM evidence_blob b WHERE b.content_hash=p.original_hash)"
        % DERIVED_STATES)
    derived = q("SELECT COUNT(*) FROM object WHERE knowledge_state IN %s"
                % DERIVED_STATES)
    derived_traceable = q(
        "SELECT COUNT(*) FROM object o JOIN provenance p"
        "  ON p.version_id=o.current_version"
        " WHERE o.knowledge_state IN %s"
        "   AND p.original_hash IS NOT NULL AND EXISTS"
        "  (SELECT 1 FROM evidence_blob b WHERE b.content_hash=p.original_hash)"
        % DERIVED_STATES)
    m["provenance"] = {
        "acquired_objects": acquired,
        "acquired_tracing_to_bytes": traceable_acquired,
        "acquired_untraceable": acquired - traceable_acquired,
        "traceable_pct_of_acquired": round(
            100.0 * traceable_acquired / max(acquired, 1), 2),
        "derived_objects": derived,
        "derived_that_also_cite_bytes": derived_traceable,
        "note": "derived objects legitimately have no bytes of their own; "
                "they are traced through their parents (see `cite`).",
    }

    # growth
    m["acquired_by_month"] = {r["m"]: r["n"] for r in rows(
        "SELECT substr(acquired_at,1,7) m, COUNT(*) n FROM source_object"
        " WHERE acquired_at IS NOT NULL GROUP BY 1 ORDER BY 1")}
    m["authored_by_year"] = {r["y"]: r["n"] for r in rows(
        "SELECT substr(source_created_at,1,4) y, COUNT(*) n FROM source_object"
        " WHERE source_created_at IS NOT NULL AND length(source_created_at)>=4"
        " GROUP BY 1 ORDER BY 1")}

    # read vs write: how much of this has ever been surfaced by a question
    surfaced = set()
    inquiries = with_ids = 0
    for r in conn.execute(
            "SELECT detail FROM audit_event WHERE action='inquiry'"):
        inquiries += 1
        try:
            d = json.loads(r["detail"] or "{}")
        except ValueError:
            continue
        ids = d.get("result_ids") or []
        if ids:
            with_ids += 1
        for oid in ids:
            surfaced.add(oid)
    m["read_vs_write"] = {
        "inquiries_recorded": inquiries,
        "inquiries_with_ids_logged": with_ids,
        "distinct_objects_ever_surfaced": len(surfaced),
        "pct_of_store_ever_surfaced": round(100.0 * len(surfaced) / total, 3),
        "note": ("A store is written far more than it is read. This is the "
                 "number that says whether it is being USED or merely filled. "
                 "Only inquiries made through `ask` count."
                 + ("" if with_ids == inquiries else
                    " %d of %d recorded inquiries predate result-id logging, so "
                    "this undercounts." % (inquiries - with_ids, inquiries))),
    }
    return m
