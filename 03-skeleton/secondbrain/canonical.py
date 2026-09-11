"""Creating and versioning canonical objects (SOW 8-11, 17).

The one rule this module exists to enforce: an object's identity is allocated
once and never reallocated. Re-ingesting changed content creates a new VERSION
under the same object_id (SOW 9). Re-ingesting identical content creates
nothing at all (SOW 39 idempotency).
"""
from . import ids
from .events import record_event
from .util import now_iso, jdump
from . import SCHEMA_VERSION


def find_by_source(conn, source_id, account_id, native_id):
    r = conn.execute(
        "SELECT so.source_object_id, so.content_hash, p.object_id"
        "  FROM source_object so"
        "  LEFT JOIN provenance p ON p.source_object_id = so.source_object_id"
        " WHERE so.source_id=? AND (so.account_id IS ? OR so.account_id=?)"
        "   AND so.native_id=? LIMIT 1",
        (source_id, account_id, account_id, native_id)).fetchone()
    return r


def upsert_source_object(conn, source_id, account_id, workspace_id, native_id,
                         content_hash, native_path=None, native_url=None,
                         source_created_at=None, source_modified_at=None,
                         job_id=None, raw_metadata=None, evidence_hash=None):
    soid = ids.scoped("SO", 1)
    conn.execute(
        "INSERT INTO source_object(source_object_id,source_id,account_id,workspace_id,"
        "native_id,native_path,native_url,content_hash,evidence_hash,source_created_at,"
        "source_modified_at,acquired_at,acquisition_job_id,raw_metadata)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(source_id,account_id,native_id) DO UPDATE SET"
        "   content_hash=excluded.content_hash,"
        "   evidence_hash=excluded.evidence_hash,"
        "   source_modified_at=excluded.source_modified_at,"
        "   acquired_at=excluded.acquired_at,"
        "   acquisition_job_id=excluded.acquisition_job_id,"
        "   raw_metadata=excluded.raw_metadata",
        (soid, source_id, account_id, workspace_id, native_id, native_path,
         native_url, content_hash, evidence_hash, source_created_at,
         source_modified_at, now_iso(), job_id,
         jdump(raw_metadata) if raw_metadata is not None else None))
    r = conn.execute(
        "SELECT source_object_id FROM source_object WHERE source_id=?"
        " AND (account_id IS ? OR account_id=?) AND native_id=?",
        (source_id, account_id, account_id, native_id)).fetchone()
    return r["source_object_id"]


def create_object(conn, object_class, title=None, memory_type=None,
                  knowledge_state="ORIGINAL", classification="PRIVATE",
                  license="MY_CONTENT", retention_class="LONG_TERM",
                  authority=None):
    oid = ids.one(conn)
    ts = now_iso()
    conn.execute(
        "INSERT INTO object(object_id,uuid,object_class,title,memory_type,"
        "knowledge_state,classification,license,retention_class,authority,"
        "lifecycle_state,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (oid, ids.new_uuid(), object_class, title, memory_type, knowledge_state,
         classification, license, retention_class, authority, "ACQUIRED", ts, ts))
    return oid


def add_version(conn, object_id, change_type, changed_by, content_hash=None,
                body=None, body_ref=None, change_reason=None,
                source_timestamp=None, effective_at=None,
                validation_status="UNVALIDATED"):
    r = conn.execute("SELECT MAX(version_num) n, "
                     "(SELECT version_id FROM object_version WHERE object_id=? "
                     " ORDER BY version_num DESC LIMIT 1) parent"
                     " FROM object_version WHERE object_id=?",
                     (object_id, object_id)).fetchone()
    n = (r["n"] or 0) + 1
    vid = ids.version_id(object_id, n)
    conn.execute(
        "INSERT INTO object_version(version_id,object_id,version_num,parent_version_id,"
        "created_at,effective_at,source_timestamp,change_type,changed_by,change_reason,"
        "content_hash,body,body_ref,schema_version,validation_status)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (vid, object_id, n, r["parent"], now_iso(), effective_at, source_timestamp,
         change_type, changed_by, change_reason, content_hash, body, body_ref,
         SCHEMA_VERSION, validation_status))
    conn.execute("UPDATE object SET current_version=?, updated_at=? WHERE object_id=?",
                 (vid, now_iso(), object_id))
    return vid


def add_provenance(conn, object_id, version_id, **kw):
    cols = ["source_system","source_account","source_profile","source_workspace",
            "source_object_id","source_url","original_filename","original_path",
            "source_created_at","source_modified_at","acquired_at","original_hash",
            "canonical_hash","parent_object_id","parent_version_id","transformation_id",
            "model","model_version","prompt_reference","confidence","validation_status",
            "license","privacy_classification"]
    pid = ids.scoped("PRV", 1)
    vals = [kw.get(c) for c in cols]
    conn.execute(
        "INSERT INTO provenance(provenance_id,object_id,version_id,%s)"
        " VALUES(?,?,?%s)" % (",".join(cols), ",?" * len(cols)),
        [pid, object_id, version_id] + vals)
    return pid


def ingest_item(conn, *, source_id, account_id, workspace_id, native_id,
                object_class, content_hash, title=None, body=None,
                native_path=None, native_url=None, source_created_at=None,
                source_modified_at=None, job_id=None, raw_metadata=None,
                classification="PRIVATE", license="MY_CONTENT",
                actor="job", memory_type=None, authority=None,
                evidence_hash=None):
    """Idempotent ingest of one source item (SOW 39).

    Returns (object_id, outcome) where outcome is one of:
      created   - new canonical object
      versioned - content changed, new version under the SAME object_id
      unchanged - identical hash, nothing written
    """
    existing = find_by_source(conn, source_id, account_id, native_id)
    if existing and existing["object_id"]:
        if existing["content_hash"] == content_hash:
            return existing["object_id"], "unchanged"
        oid = existing["object_id"]
        soid = upsert_source_object(conn, source_id, account_id, workspace_id,
                                    native_id, content_hash, native_path, native_url,
                                    source_created_at, source_modified_at, job_id,
                                    raw_metadata, evidence_hash)
        vid = add_version(conn, oid, "normalized", actor,
                          content_hash=content_hash, body=body,
                          change_reason="source content changed since last acquisition",
                          source_timestamp=source_modified_at)
        add_provenance(conn, oid, vid, source_system=source_id,
                       source_account=account_id, source_workspace=workspace_id,
                       source_object_id=soid, source_url=native_url,
                       original_filename=title, original_path=native_path,
                       source_created_at=source_created_at,
                       source_modified_at=source_modified_at,
                       acquired_at=now_iso(), original_hash=evidence_hash or content_hash,
                       canonical_hash=content_hash, license=license,
                       privacy_classification=classification)
        record_event(conn, "MODIFIED", oid, actor=actor, source=source_id,
                     previous_state="ACQUIRED", new_state="ACQUIRED",
                     reason="content hash changed", job_id=job_id)
        return oid, "versioned"

    soid = upsert_source_object(conn, source_id, account_id, workspace_id, native_id,
                                content_hash, native_path, native_url,
                                source_created_at, source_modified_at, job_id,
                                raw_metadata, evidence_hash)
    oid = create_object(conn, object_class, title=title, memory_type=memory_type,
                        classification=classification, license=license,
                        authority=authority)
    vid = add_version(conn, oid, "imported", actor, content_hash=content_hash,
                      body=body, change_reason="initial acquisition",
                      source_timestamp=source_modified_at)
    add_provenance(conn, oid, vid, source_system=source_id, source_account=account_id,
                   source_workspace=workspace_id, source_object_id=soid,
                   source_url=native_url, original_filename=title,
                   original_path=native_path, source_created_at=source_created_at,
                   source_modified_at=source_modified_at, acquired_at=now_iso(),
                   original_hash=evidence_hash or content_hash, canonical_hash=content_hash,
                   license=license, privacy_classification=classification)
    record_event(conn, "ACQUIRED", oid, actor=actor, source=source_id,
                 new_state="ACQUIRED", job_id=job_id)
    return oid, "created"
