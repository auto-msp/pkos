"""Knowledge graph (SOW 22, Phase 22).

WHAT AN ENTITY IS HERE, AND WHY IT IS NOT GUESSED
=================================================
The tempting way to build this is to run text through a model, pull out things
that look like names, and call them entities. That produces a graph that is
80% right, cannot be re-derived, and quietly rots: nobody can ever say why a
node exists or whether it still should.

Every entity here comes from STRUCTURED evidence the store already holds and
already trusts:

    Domain      <- url.registrable_domain            (parsed, not inferred)
    Server      <- profile_workspace kind='server'   (from a real audit)
    Account     <- account                           (from the export's own users.json)
    Workspace   <- profile_workspace kind='project'  (from the platform)
    Folder      <- the directory a file was actually acquired from

Edges follow the same rule. `HOSTED_AT` exists because a URL's host IS that
domain - a fact, not a similarity. Nothing is created from resemblance.

The one probabilistic step is MENTIONS, and it is deliberately fenced:
  * matching is a literal phrase search over canonical bodies via FTS
  * an entity that appears in more than SATURATION of the corpus produces NO
    mention edges at all. A term in a third of your documents does not tell you
    which document you want; it is noise wearing a graph edge's clothes.
  * the true match count is recorded on the entity either way, so the decision
    is visible rather than silently applied.

Entities are DERIVED objects (SOW 16). They carry knowledge_state='DERIVED' and
a provenance row naming the exact rule that produced them, so `graph --rebuild`
is reproducible and a wrong rule is correctable rather than permanent.
"""
import sqlite3
from pathlib import Path

from . import ids
from .canonical import create_object, add_version, add_provenance
from .events import record_event, audit
from .util import now_iso, jdump
from . import evidence

SATURATION = 0.05          # an entity in >5% of objects earns no MENTIONS edges
MAX_MENTIONS = 500         # per entity, most-relevant first
ENTITY_CLASSES = ("Domain", "Server", "Account", "Workspace", "Folder")


# -- entity identity --------------------------------------------------------
def find_entity(conn, cls, key):
    r = conn.execute(
        "SELECT object_id FROM object WHERE object_class=? AND title=?"
        "   AND knowledge_state='DERIVED' LIMIT 1", (cls, key)).fetchone()
    return r["object_id"] if r else None


def upsert_entity(conn, cls, key, rule, body=None, authority="DIRECT PROJECT ARTIFACT"):
    """Create the entity if absent. Returns (object_id, created?)."""
    oid = find_entity(conn, cls, key)
    if oid:
        return oid, False
    oid = create_object(conn, cls, title=key, memory_type="REFERENCE",
                        knowledge_state="DERIVED", classification="PRIVATE",
                        license="MY_CONTENT", authority=authority)
    vid = add_version(conn, oid, "enriched", "rule:%s" % rule,
                      content_hash=evidence.hash_bytes(("%s\x00%s" % (cls, key)).encode()),
                      body=body or key,
                      change_reason="derived by graph rule %s from canonical data" % rule,
                      validation_status="PASSED")
    add_provenance(conn, oid, vid, transformation_id="graph:%s" % rule,
                   acquired_at=now_iso(), confidence=1.0,
                   validation_status="PASSED", privacy_classification="PRIVATE",
                   license="MY_CONTENT")
    record_event(conn, "ENRICHED", oid, actor="rule:%s" % rule,
                 new_state="ACQUIRED", reason="entity derived from structured evidence")
    return oid, True


def link(conn, src, tgt, rtype, rule, confidence=1.0):
    if not src or not tgt or src == tgt:
        return 0
    cur = conn.execute(
        "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
        "target_object,relationship_type,confidence,created_at,provenance,"
        "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
        (ids.scoped("REL", 1), src, tgt, rtype, confidence, now_iso(),
         "graph rule %s" % rule, "rule:%s" % rule, "PASSED"))
    return cur.rowcount or 0


# -- the deterministic passes ----------------------------------------------
def build_domains(conn, st):
    """A URL's host IS a domain. Not a similarity - a parse."""
    rows = conn.execute(
        "SELECT registrable_domain d, COUNT(*) n FROM url"
        " WHERE registrable_domain IS NOT NULL AND registrable_domain<>''"
        " GROUP BY 1").fetchall()
    for r in rows:
        oid, new = upsert_entity(
            conn, "Domain", r["d"], "domain-from-url",
            body="%s\n%d URL(s) in the corpus resolve to this registrable domain."
                 % (r["d"], r["n"]),
            authority="PRIMARY SOURCE")
        st["domains"] += new
        for u in conn.execute(
                "SELECT object_id FROM url WHERE registrable_domain=?"
                " AND object_id IS NOT NULL", (r["d"],)):
            st["edges_hosted_at"] += link(conn, u["object_id"], oid,
                                          "HOSTED_AT", "domain-from-url")


def build_workspaces(conn, st):
    for w in conn.execute(
            "SELECT workspace_id, kind, identifier, display_name,"
            "       (SELECT identifier FROM account a WHERE a.account_id=pw.account_id) acct"
            "  FROM profile_workspace pw").fetchall():
        name = (w["display_name"] or w["identifier"] or "").strip()
        if not name:
            continue
        cls = "Server" if w["kind"] == "server" else "Workspace"
        oid, new = upsert_entity(
            conn, cls, name, "workspace-from-registry",
            body="%s (%s)\naccount: %s" % (name, w["kind"], w["acct"] or "-"),
            authority="DIRECT PROJECT ARTIFACT")
        st["workspaces"] += new
        n = 0
        for so in conn.execute(
                "SELECT DISTINCT p.object_id FROM source_object so"
                "  JOIN provenance p ON p.source_object_id=so.source_object_id"
                " WHERE so.workspace_id=?", (w["workspace_id"],)):
            n += link(conn, so["object_id"], oid, "BELONGS_TO",
                      "workspace-from-registry")
        st["edges_belongs_to"] += n


def build_accounts(conn, st):
    for a in conn.execute("SELECT account_id, identifier, display_name, source_id"
                          "  FROM account").fetchall():
        name = a["display_name"] or a["identifier"]
        oid, new = upsert_entity(
            conn, "Account", name, "account-from-registry",
            body="%s\nsource: %s\nidentifier: %s"
                 % (name, a["source_id"], a["identifier"]),
            authority="PRIMARY SOURCE")
        st["accounts"] += new
        # Only container objects get an account edge. Attaching all 17k messages
        # would bury the graph in edges that say nothing a JOIN cannot.
        for o in conn.execute(
                "SELECT DISTINCT p.object_id FROM source_object so"
                "  JOIN provenance p ON p.source_object_id=so.source_object_id"
                "  JOIN object ob ON ob.object_id=p.object_id"
                " WHERE so.account_id=? AND ob.object_class IN"
                "       ('Conversation','Project','AssistantMemory','Source')",
                (a["account_id"],)):
            st["edges_account"] += link(conn, o["object_id"], oid, "BELONGS_TO",
                                        "account-from-registry")


def build_folders(conn, st):
    """The directory a file came from is real organisational intent.

    The first version of this hardcoded "/mnt/" and took the segment after it.
    That worked on exactly one machine: run it anywhere else and every file
    collapsed into a single meaningless entity, with no error. A derivation
    rule that depends on the operator's mount layout is not a rule, it is a
    coincidence.

    The layout-independent version: find the deepest directory ALL acquired
    files share, then take the first segment below it. If that segment holds
    almost everything (a plain container like "Downloads"), descend one more
    level - a path component that every file shares tells you nothing about
    any of them. Same reasoning as the saturation rule for mentions.
    """
    DESCEND_IF_ABOVE = 0.95
    rows = [(r["p"], r["o"]) for r in conn.execute(
        "SELECT so.native_path p, pr.object_id o FROM source_object so"
        "  JOIN provenance pr ON pr.source_object_id=so.source_object_id"
        " WHERE so.source_id='SRC-laptop-filesystem' AND so.native_path IS NOT NULL")]
    if not rows:
        return
    split = [([x for x in path.split("/") if x], oid) for path, oid in rows]

    # deepest shared directory
    common = 0
    shortest = min(len(parts) for parts, _ in split)
    while common < shortest - 1:
        seg = split[0][0][common]
        if all(parts[common] == seg for parts, _ in split):
            common += 1
        else:
            break

    def bucket(parts, depth):
        return parts[depth] if len(parts) > depth + 1 else None

    depth = common
    for _ in range(3):                      # never descend forever
        counts = {}
        for parts, _oid in split:
            b = bucket(parts, depth)
            if b:
                counts[b] = counts.get(b, 0) + 1
        if not counts:
            return
        total = sum(counts.values())
        top = max(counts.values())
        if len(counts) == 1 or top / total > DESCEND_IF_ABOVE:
            st["folder_levels_descended"] += 1
            depth += 1
            continue
        break

    # A path segment carrying a file extension is an extraction artefact - an
    # unzipped archive, a directory named after the file it came from. It is a
    # true path component but not organisational intent, and as an entity it is
    # pure noise: "...-2026-08-23-13_05_16.png" is nobody's filing system.
    ARTEFACT = (".zip", ".tar", ".gz", ".rar", ".7z", ".png", ".jpg", ".jpeg",
                ".pdf", ".json", ".csv", ".txt", ".md", ".html", ".docx", ".xlsx")
    seen = {}
    for parts, oid in split:
        b = bucket(parts, depth)
        if not b or b.startswith("."):
            continue
        if b.lower().endswith(ARTEFACT):
            st["folders_skipped_artefact"] += 1
            continue
        seen.setdefault(b, []).append(oid)
    for folder, objs in seen.items():
        eid, new = upsert_entity(
            conn, "Folder", folder, "folder-from-path",
            body="%s\n%d acquired file(s) came from this folder.\n"
                 "derived at path depth %d, below the shared ancestor"
                 % (folder, len(objs), depth),
            authority="DIRECT PROJECT ARTIFACT")
        st["folders"] += new
        for o in objs:
            st["edges_stored_in"] += link(conn, o, eid, "STORED_IN", "folder-from-path")


def build_mentions(conn, fts_path, st):
    """The one inexact pass, fenced by saturation."""
    fts_path = Path(fts_path)
    if not fts_path.exists():
        st["mentions_skipped_no_index"] = True
        return
    f = sqlite3.connect(str(fts_path))
    total = conn.execute("SELECT COUNT(*) c FROM object").fetchone()["c"]
    cap = max(int(total * SATURATION), 1)
    ents = conn.execute(
        "SELECT object_id, object_class, title FROM object"
        " WHERE knowledge_state='DERIVED' AND object_class IN ('Domain','Server','Workspace')"
    ).fetchall()
    for e in ents:
        term = (e["title"] or "").strip()
        if len(term) < 4:
            st["entities_too_short"] += 1
            continue
        phrase = '"%s"' % term.replace('"', '""')
        try:
            n = f.execute("SELECT COUNT(*) FROM doc WHERE doc MATCH ?", (phrase,)).fetchone()[0]
        except sqlite3.OperationalError:
            st["entities_unqueryable"] += 1
            continue
        conn.execute("UPDATE object SET updated_at=? WHERE object_id=?",
                     (now_iso(), e["object_id"]))
        if n == 0:
            st["entities_no_match"] += 1
            continue
        if n > cap:
            # Recorded, not silently dropped: the number is why there are no edges.
            st["entities_saturated"] += 1
            vid = add_version(
                conn, e["object_id"], "enriched", "rule:mention-saturation",
                body="%s\nAppears in %d of %d objects (>%.0f%%). No MENTIONS "
                     "edges were created: a term this common cannot "
                     "discriminate between documents."
                     % (term, n, total, SATURATION * 100),
                change_reason="saturated term, mention edges withheld",
                validation_status="PASSED")
            # Every version needs a provenance row (SOW 17, and the
            # every_version_has_provenance invariant). This branch had none:
            # it never fired on the current corpus, so the omission was
            # invisible. An invariant you only satisfy by luck is not satisfied.
            add_provenance(conn, e["object_id"], vid,
                           transformation_id="graph:mention-saturation",
                           acquired_at=now_iso(), confidence=1.0,
                           validation_status="PASSED",
                           privacy_classification="PRIVATE", license="MY_CONTENT")
            continue
        rows = f.execute("SELECT object_id FROM doc WHERE doc MATCH ?"
                         " ORDER BY bm25(doc) LIMIT ?", (phrase, MAX_MENTIONS)).fetchall()
        made = 0
        for (oid,) in rows:
            made += link(conn, oid, e["object_id"], "MENTIONS", "mention-fts",
                         confidence=0.8)
        st["edges_mentions"] += made
        st["entities_with_mentions"] += 1
    f.close()


def rebuild(conn, paths):
    st = {k: 0 for k in (
        "domains", "workspaces", "accounts", "folders",
        "edges_hosted_at", "edges_belongs_to", "edges_account", "edges_stored_in",
        "edges_mentions", "entities_with_mentions", "entities_saturated",
        "entities_no_match", "entities_too_short", "entities_unqueryable",
        "folder_levels_descended", "stale_rule_edges_cleared",
        "folders_skipped_artefact",
        "entities_superseded", "entities_revived")}
    # A rebuild must REPLACE what the rules previously produced, not add to it.
    # Change a rule (as the folder rule just changed) and the old edges would
    # otherwise survive alongside the new ones - a file "stored in" two folders,
    # one of them from a rule that no longer exists. Only rule-generated edges
    # go: adapter edges carry created_by='job:...' and are acquired facts.
    st["stale_rule_edges_cleared"] = conn.execute(
        "DELETE FROM relationship WHERE created_by LIKE 'rule:%'").rowcount
    conn.commit()
    build_domains(conn, st)
    build_workspaces(conn, st)
    build_accounts(conn, st)
    build_folders(conn, st)
    conn.commit()
    build_mentions(conn, paths.fts_db, st)
    st["entities_superseded"], st["entities_revived"] = retire_orphans(conn)
    audit(conn, "derived", "graph_rebuild", "OK", detail=st)
    conn.commit()
    return st


def retire_orphans(conn):
    """An entity no current rule still produces is SUPERSEDED, never deleted.

    Changing the folder rule left 88 entities behind - Folder nodes named after
    .mp4 and .zip files, from a rule that no longer exists. Deleting them would
    be the tidy option and the wrong one: they carry KB- ids that may already
    be cited in an answer, and SOW 10/11 say history is append-only. So they
    are marked SUPERSEDED, excluded from lookup and ranking, and revived
    automatically if a future rule produces them again.
    """
    sup = rev = 0
    orphans = conn.execute(
        "SELECT object_id, title, decay_status FROM object o"
        " WHERE o.knowledge_state='DERIVED' AND o.is_duplicate_of IS NULL"
        "   AND NOT EXISTS"
        "   (SELECT 1 FROM relationship r WHERE r.target_object=o.object_id)"
    ).fetchall()
    for o in orphans:
        if o["decay_status"] == "SUPERSEDED":
            continue
        vid = add_version(conn, o["object_id"], "superseded", "rule:retire-orphan",
                          body="%s\nNo current graph rule produces this entity and "
                               "nothing links to it. Retained with its identity and "
                               "history intact; excluded from lookup and ranking "
                               "until a rule produces it again." % o["title"],
                          change_reason="orphaned by a graph rule change",
                          validation_status="PASSED")
        add_provenance(conn, o["object_id"], vid,
                       transformation_id="graph:retire-orphan",
                       acquired_at=now_iso(), confidence=1.0,
                       validation_status="PASSED",
                       privacy_classification="PRIVATE", license="MY_CONTENT")
        conn.execute("UPDATE object SET decay_status='SUPERSEDED', updated_at=?"
                     " WHERE object_id=?", (now_iso(), o["object_id"]))
        record_event(conn, "SUPERSEDED", o["object_id"], actor="rule:retire-orphan",
                     previous_state="CURRENT", new_state="SUPERSEDED",
                     reason="no current rule produces this entity")
        sup += 1
    # Anything SUPERSEDED that has edges again comes back - EXCEPT a merged
    # alias. An alias keeps its own edges by design (SOW 19: linked, never
    # deleted), so without this exclusion the next rebuild would "revive" it
    # and silently undo a merge a human confirmed. A rebuild must never
    # overturn a human decision.
    for o in conn.execute(
            "SELECT object_id FROM object o WHERE o.knowledge_state='DERIVED'"
            "   AND o.decay_status='SUPERSEDED' AND o.is_duplicate_of IS NULL"
            "   AND EXISTS"
            "   (SELECT 1 FROM relationship r WHERE r.target_object=o.object_id)"):
        conn.execute("UPDATE object SET decay_status='CURRENT', updated_at=?"
                     " WHERE object_id=?", (now_iso(), o["object_id"]))
        record_event(conn, "RESTORED", o["object_id"], actor="rule:retire-orphan",
                     previous_state="SUPERSEDED", new_state="CURRENT",
                     reason="a current rule produces this entity again")
        rev += 1
    return sup, rev


# -- reading the graph ------------------------------------------------------
def stats(conn):
    ent = {r["object_class"]: r["n"] for r in conn.execute(
        "SELECT object_class, COUNT(*) n FROM object"
        " WHERE knowledge_state='DERIVED' GROUP BY 1")}
    rel = {r["relationship_type"]: r["n"] for r in conn.execute(
        "SELECT relationship_type, COUNT(*) n FROM relationship GROUP BY 1 ORDER BY 2 DESC")}
    return {"entities": ent, "entity_total": sum(ent.values()),
            "relationships": rel, "relationship_total": sum(rel.values())}


def neighbours(conn, object_id, limit=25):
    out = []
    for r in conn.execute(
            "SELECT r.relationship_type t, r.confidence c, o.object_id id,"
            "       o.title, o.object_class k, 'out' dir"
            "  FROM relationship r JOIN object o ON o.object_id=r.target_object"
            " WHERE r.source_object=? UNION ALL "
            "SELECT r.relationship_type, r.confidence, o.object_id, o.title,"
            "       o.object_class, 'in'"
            "  FROM relationship r JOIN object o ON o.object_id=r.source_object"
            " WHERE r.target_object=? LIMIT ?", (object_id, object_id, limit)):
        out.append(dict(r))
    return out


def find(conn, term, limit=15):
    like = "%" + term + "%"
    return [dict(r) for r in conn.execute(
        "SELECT object_id, object_class, title,"
        "  (SELECT COUNT(*) FROM relationship WHERE target_object=object.object_id) in_degree"
        "  FROM object WHERE knowledge_state='DERIVED' AND decay_status<>'SUPERSEDED'"
        "   AND is_duplicate_of IS NULL AND title LIKE ?"
        "  ORDER BY in_degree DESC LIMIT ?", (like, limit))]


def top_entities(conn, cls=None, limit=20):
    q = ("SELECT o.object_id, o.object_class, o.title,"
         "  (SELECT COUNT(*) FROM relationship r WHERE r.target_object=o.object_id) deg"
         "  FROM object o WHERE o.knowledge_state='DERIVED'"
         "   AND o.decay_status<>'SUPERSEDED' AND o.is_duplicate_of IS NULL")
    a = []
    if cls:
        q += " AND o.object_class=?"; a.append(cls)
    q += " ORDER BY deg DESC LIMIT ?"; a.append(limit)
    return [dict(r) for r in conn.execute(q, a)]


def merge_entities(conn, canonical_id, alias_id, confirmed_by, reason=None):
    """Record that two entities are the same thing. A HUMAN decides this.

    SOW 19: duplicates are LINKED, never deleted. The alias keeps its id, its
    history and its own edges - anything that already cited it stays valid.
    What changes is that the canonical entity inherits the alias's edges, so
    retrieval sees one thing, and the alias drops out of lookup and ranking.

    This is deliberately not automated. "AutoMSP", "automsp.us" and "AutoMSP AI
    Automation Services" are the same thing to Moiz and would be three
    different things to any string-similarity rule worth trusting. Merging is
    judgement, so it needs a name attached to it - which is why confirmed_by is
    required and is written into the link as evidence.
    """
    if canonical_id == alias_id:
        raise ValueError("cannot merge an entity into itself")
    for oid in (canonical_id, alias_id):
        if not conn.execute("SELECT 1 FROM object WHERE object_id=?", (oid,)).fetchone():
            raise ValueError("no such object: %s" % oid)
    existing = conn.execute("SELECT is_duplicate_of d FROM object WHERE object_id=?",
                            (alias_id,)).fetchone()["d"]
    if existing == canonical_id:
        return {"already": True, "edges_inherited": 0}

    inherited = 0
    for r in conn.execute("SELECT source_object s, relationship_type t, confidence c"
                          "  FROM relationship WHERE target_object=?", (alias_id,)):
        inherited += link(conn, r["s"], canonical_id, r["t"], "entity-merge",
                          confidence=r["c"] or 1.0)
    conn.execute("UPDATE object SET is_duplicate_of=?, decay_status='SUPERSEDED',"
                 " updated_at=? WHERE object_id=?",
                 (canonical_id, now_iso(), alias_id))
    conn.execute(
        "INSERT OR IGNORE INTO duplicate_link(duplicate_id,canonical_object,"
        "alias_object,dedup_kind,evidence,confidence,detected_at,detected_by)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (ids.scoped("DUP", 1), canonical_id, alias_id, "semantic",
         reason or "confirmed identical by a human", 1.0, now_iso(), confirmed_by))
    vid = add_version(conn, alias_id, "merged", confirmed_by,
                      body="Merged into %s. Confirmed by %s.\n%s"
                           % (canonical_id, confirmed_by, reason or ""),
                      change_reason="human-confirmed entity merge",
                      validation_status="PASSED")
    add_provenance(conn, alias_id, vid, parent_object_id=canonical_id,
                   transformation_id="graph:entity-merge", acquired_at=now_iso(),
                   confidence=1.0, validation_status="PASSED")
    record_event(conn, "MERGED", alias_id, actor=confirmed_by,
                 previous_state="CURRENT", new_state="SUPERSEDED",
                 reason="merged into %s" % canonical_id)
    audit(conn, "graph", "entity_merge", "OK", actor=confirmed_by,
          detail={"canonical": canonical_id, "alias": alias_id,
                  "edges_inherited": inherited, "reason": reason})
    conn.commit()
    return {"already": False, "edges_inherited": inherited}
