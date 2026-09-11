"""The agent boundary (SOW 3, 17, 24 - Phase 24).

THE RULE THIS MODULE EXISTS TO ENFORCE
======================================
The deterministic core retrieves, assembles and cites. An agent interprets.
Neither does the other's job, and the store can always tell which did what.

So `ask` deliberately produces NO PROSE. It gathers the evidence, traces every
item back to the bytes it came from, states plainly what it could not find, and
stops. Answering is a separate, recorded act - and an answer enters the store
as SYNTHESIZED, attributed to the model that wrote it, linked to every source
it used. A model's paraphrase must never be retrievable as though the user had
said it.

That separation is what makes the SOW 17 chain executable end to end:

    ANSWER -> object -> object_version -> provenance -> evidence_blob -> bytes

`cite` walks it. If any link is missing the answer is not trustworthy, and the
command says so instead of printing something plausible.
"""
from pathlib import Path

from . import ids, search, evidence
from .canonical import create_object, add_version, add_provenance
from .events import record_event, audit
from .util import now_iso, jdump

EXCERPT = 1200
KNOWN_SOURCES = {
    "SRC-laptop-filesystem": "laptop files",
    "SRC-browser-bookmarks": "browser bookmarks",
    "SRC-claude-ai": "Claude conversations",
    "SRC-oci-servers": "server audits",
}
DECLARED_BUT_ABSENT = {
    "notion": "Phase 11", "airtable": "Phase 12", "gmail/outlook/zoho": "Phase 13",
    "chatgpt": "Phase 15", "gumroad": "Phase 16", "instagram": "Phase 17",
    "facebook": "Phase 18", "linkedin": "Phase 19", "github-stars": "Phase 9",
    "google-takeout": "Phase 10",
}


def provenance_chain(conn, object_id):
    """Every hop from a knowledge object back to raw bytes, or the gap."""
    o = conn.execute(
        "SELECT o.object_id, o.object_class, o.title, o.knowledge_state,"
        "       o.classification, o.authority, o.current_version"
        "  FROM object o WHERE o.object_id=?", (object_id,)).fetchone()
    if not o:
        return None
    v = conn.execute(
        "SELECT version_id, version_num, change_type, changed_by, created_at,"
        "       content_hash, body_ref FROM object_version WHERE version_id=?",
        (o["current_version"],)).fetchone()
    p = conn.execute(
        "SELECT source_system, source_account, source_object_id, original_path,"
        "       original_filename, original_hash, canonical_hash, acquired_at,"
        "       transformation_id, model, model_version, prompt_reference,"
        "       parent_object_id, confidence, validation_status"
        "  FROM provenance WHERE version_id=? ORDER BY rowid DESC LIMIT 1",
        (o["current_version"],)).fetchone()
    blob = None
    if p and p["original_hash"]:
        blob = conn.execute(
            "SELECT content_hash, byte_size, storage_path, mime_type,"
            "       original_filename FROM evidence_blob WHERE content_hash=?",
            (p["original_hash"],)).fetchone()
    chain = {"object": dict(o), "version": dict(v) if v else None,
             "provenance": dict(p) if p else None,
             "evidence_blob": dict(blob) if blob else None}
    breaks = []
    if not v:
        breaks.append("object has no current version")
    if not p:
        breaks.append("version has no provenance row")
    if p and not p["original_hash"]:
        breaks.append("provenance records no original hash "
                      "(derived object - trace its parents instead)")
    elif p and not blob:
        breaks.append("provenance names hash %s but no evidence blob is "
                      "registered under it" % (p["original_hash"] or "?")[:16])
    chain["complete"] = not breaks
    chain["breaks"] = breaks
    return chain


def coverage_gaps(conn):
    """What this store cannot answer from. Stated before any answer is given.

    An answer built on a corpus with known holes is not wrong, but presenting
    it without the holes IS. SOW 43: completion is never inferred from the
    absence of an error, and neither is coverage.
    """
    present = {r["source_id"] for r in conn.execute(
        "SELECT DISTINCT source_id FROM source_object")}
    gaps = {
        "sources_ingested": sorted(KNOWN_SOURCES[s] for s in present if s in KNOWN_SOURCES),
        "sources_declared_but_absent": DECLARED_BUT_ABSENT,
        "ranking_signals_off": [k for k, v in search.RANK_COMPONENTS.items()
                                if v.startswith("NOT")],
    }
    r = conn.execute(
        "SELECT MIN(source_created_at) a, MAX(source_created_at) b"
        "  FROM source_object WHERE source_created_at IS NOT NULL").fetchone()
    gaps["corpus_spans"] = {"from": r["a"], "to": r["b"]}
    gaps["redacted_objects"] = conn.execute(
        "SELECT COUNT(*) c FROM object WHERE classification='RESTRICTED'").fetchone()["c"]
    gaps["items_in_dead_letter"] = conn.execute(
        "SELECT COUNT(*) c FROM dead_letter").fetchone()["c"]
    url_total = conn.execute("SELECT COUNT(*) c FROM url").fetchone()["c"]
    gaps["urls_ingested"] = url_total
    return gaps


def ask(conn, paths, question, limit=8):
    """Assemble evidence for a question. Deliberately answers nothing."""
    res = search.query(conn, paths.fts_db, question, limit=limit)
    items = []
    for r in res["results"]:
        ch = provenance_chain(conn, r["object_id"])
        body = conn.execute(
            "SELECT body FROM object_version WHERE version_id="
            "  (SELECT current_version FROM object WHERE object_id=?)",
            (r["object_id"],)).fetchone()
        items.append({
            "object_id": r["object_id"], "title": r["title"],
            "object_class": r["object_class"], "score": r["score"],
            "signals": r["score_components"],
            "excerpt": ((body["body"] or "")[:EXCERPT] if body else None),
            "traceable_to_bytes": bool(ch and ch["complete"]),
            "chain_breaks": (ch or {}).get("breaks", []),
            "provenance": (ch or {}).get("provenance"),
        })
    inq = ids.scoped("INQ", 1)
    pack = {
        "inquiry_id": inq, "question": question, "asked_at": now_iso(),
        "retrieval": {"expansion_terms": res["expansion_terms"],
                      "graph_entities": res["graph_entities"],
                      "candidates_considered": res["pool_size"]},
        "evidence": items,
        "coverage_gaps": coverage_gaps(conn),
        "instruction_to_agent":
            "Answer ONLY from the excerpts above. Cite object_ids. If the "
            "evidence does not support an answer, say so and name what is "
            "missing - do not fill the gap from general knowledge. Items with "
            "traceable_to_bytes=false must not be cited as fact.",
    }
    # Record WHICH objects were surfaced, not just how many. Without the ids
    # there is no way to ever answer "what in here has never been read?" - and
    # a store that is only ever written to is a filing cabinet, not a brain.
    audit(conn, "retrieval", "inquiry", "OK", target=question[:200],
          detail={"inquiry_id": inq, "results": len(items),
                  "result_ids": [i["object_id"] for i in items],
                  "untraceable": sum(1 for i in items if not i["traceable_to_bytes"])})
    conn.commit()
    return pack


def record_answer(conn, question, answer_text, source_ids, model,
                  inquiry_id=None, actor="human:moiz"):
    """Store an agent's interpretation as an attributed, SYNTHESIZED object."""
    oid = create_object(conn, "Answer", title=question[:300],
                        memory_type="OBSERVATION", knowledge_state="SYNTHESIZED",
                        classification="PRIVATE", license="DERIVED",
                        authority="AI-GENERATED")
    conn.execute("UPDATE object SET decay_status='UNVERIFIED' WHERE object_id=?", (oid,))
    vid = add_version(conn, oid, "enriched", "model:%s" % model,
                      content_hash=evidence.hash_bytes(answer_text.encode()),
                      body=answer_text,
                      change_reason="interpretation of inquiry %s" % (inquiry_id or "-"),
                      validation_status="REQUIRES_HUMAN_REVIEW")
    add_provenance(conn, oid, vid, model=model, model_version=model,
                   prompt_reference=inquiry_id, acquired_at=now_iso(),
                   confidence=None, validation_status="REQUIRES_HUMAN_REVIEW",
                   license="DERIVED", privacy_classification="PRIVATE",
                   transformation_id="agent:answer")
    linked = 0
    for s in source_ids:
        if conn.execute("SELECT 1 FROM object WHERE object_id=?", (s,)).fetchone():
            conn.execute(
                "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
                "target_object,relationship_type,confidence,created_at,provenance,"
                "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
                (ids.scoped("REL", 1), oid, s, "DERIVED_FROM", 1.0, now_iso(),
                 "cited by the agent answering %s" % (inquiry_id or "-"),
                 "model:%s" % model, "REQUIRES_HUMAN_REVIEW"))
            linked += 1
    record_event(conn, "ENRICHED", oid, actor=actor, model_id=model,
                 new_state="ACQUIRED",
                 reason="agent answer recorded, awaiting human validation")
    audit(conn, "agent", "answer_recorded", "OK", actor=actor,
          detail={"object_id": oid, "model": model, "cited": linked,
                  "inquiry_id": inquiry_id})
    conn.commit()
    return oid, linked


def validate_answer(conn, object_id, verdict, actor="human:moiz", note=None):
    """A human accepting or rejecting an agent's answer. SOW 16: only this
    promotes SYNTHESIZED to HUMAN_VALIDATED."""
    if verdict not in ("accept", "reject"):
        raise ValueError("verdict must be accept or reject")
    state = "HUMAN_VALIDATED" if verdict == "accept" else "SYNTHESIZED"
    decay = "CURRENT" if verdict == "accept" else "DISPUTED"
    vid = add_version(conn, object_id, "corrected" if verdict == "reject" else "enriched",
                      actor, body=None,
                      change_reason="human %s: %s" % (verdict, note or "no note"),
                      validation_status="PASSED" if verdict == "accept" else "FAILED")
    add_provenance(conn, object_id, vid, acquired_at=now_iso(),
                   validation_status="PASSED" if verdict == "accept" else "FAILED",
                   transformation_id="human:validation")
    conn.execute("UPDATE object SET knowledge_state=?, decay_status=?, updated_at=?"
                 " WHERE object_id=?", (state, decay, now_iso(), object_id))
    record_event(conn, "VALIDATED" if verdict == "accept" else "REVIEWED",
                 object_id, actor=actor, new_state=state, reason=note)
    audit(conn, "agent", "answer_%sed" % verdict, "OK", actor=actor,
          detail={"object_id": object_id, "note": note})
    conn.commit()
    return state
