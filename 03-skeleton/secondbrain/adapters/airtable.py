"""Airtable adapter (SOW 110 Phase 12).

Airtable is an API source, not a download, so acquisition and interpretation
are split the way SOW 4 requires: something with credentials pulls the bases
into JSON snapshots on disk, and THIS reads those snapshots. The split is not
ceremony. It means a parsing mistake is fixed by re-running the adapter over
bytes already held, instead of hitting a rate-limited API again; and it means
the snapshot is the evidence, hashed and immutable, rather than a memory of
what an API said once.

Snapshot shape (one file per base, or one file holding a list of them):

    {"captured_at": "...", "base": {"id": "app...", "name": "..."},
     "tables": [{"id": "tbl...", "name": "...", "fields": [...],
                 "records": [{"id": "rec...", "createdTime": "...",
                              "fields": {...}}]}]}

Two things are deliberately NOT claimed:

  Attachment URLs expire. Airtable serves attachments from signed URLs with a
  short life, so a stored URL is a dangling pointer within hours. Attachments
  are therefore recorded as FileReference objects -- named, countable, and
  visible in `gaps` -- rather than as files the store can open. Writing them
  down as though they were retrievable would be exactly the invented
  capability SOW 107 forbids.

  Formulas, rollups and lookups arrive as computed VALUES. The API does not
  return the expression. That is the same loss the Google Drive connector has,
  and it is named here for the same reason.
"""
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids
from ..util import now_iso

COMPUTED = {"formula", "rollup", "lookup", "count", "autoNumber",
            "createdTime", "lastModifiedTime", "createdBy", "lastModifiedBy"}


class AirtableAdapter(BaseAdapter):
    source_id = "SRC-airtable"
    vendor = "airtable"
    display_name = "Airtable"
    acquisition_method = "connector"
    auth_method = "oauth_connector"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"snapshots": 0, "bases": 0, "tables": 0, "records": 0,
                      "fields": 0, "computed_fields": 0,
                      "attachments_referenced": 0, "attachment_bytes_held": 0,
                      "linked_record_edges": 0, "unresolved_links": 0,
                      "empty_globs": []}
        self._oids = {}
        self._pending = []

    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "airtable adapter requires --identity <your Airtable account "
                "email>.\nSOW 45/46: account identity is explicit, never "
                "inferred. A snapshot names its bases and tables but not the "
                "login whose connector produced it, and this store already "
                "keeps two accounts of one vendor strictly apart.")

        root = Path(target).expanduser().resolve()
        files = [root] if root.is_file() else A.loud_glob(
            root, "*.json", "Airtable snapshots", self.stats, required=True)

        self._account = self.ensure_account(
            self.identity, discovered_via="Airtable connector snapshot",
            display_name=self.identity, verified=True)

        for f in files:
            digest, _ = evidence.store_file(self.conn, self.paths.blobs, f,
                                            mime="application/json")
            data = A.read_json(f)
            for snap in (data if isinstance(data, list) else [data]):
                if not isinstance(snap, dict) or "tables" not in snap:
                    continue
                self.stats["snapshots"] += 1
                base = snap.get("base") or {}
                bid = base.get("id") or f.stem
                self.stats["bases"] += 1
                yield ("base", (snap, base, bid, digest, str(f)), str(f))
                for t in snap.get("tables") or []:
                    self.stats["tables"] += 1
                    self.stats["fields"] += len(t.get("fields") or [])
                    self.stats["computed_fields"] += sum(
                        1 for fl in (t.get("fields") or [])
                        if (fl or {}).get("type") in COMPUTED)
                    yield ("table", (t, bid, digest, str(f)), str(f))
                    for r in t.get("records") or []:
                        self.stats["records"] += 1
                        yield ("record", (r, t, bid, digest, str(f)), str(f))
        if not self.stats["snapshots"]:
            raise SystemExit(
                "no Airtable snapshot found at %s.\nExpected JSON containing a "
                "`tables` key. Produce one with the Airtable connector first; "
                "this adapter reads snapshots, it does not call the API." % root)

    def acquire_one(self, item, job_id):
        kind, payload, _origin = item
        return getattr(self, "_acq_" + kind)(payload, job_id)

    def _acq_base(self, payload, job_id):
        snap, base, bid, digest, src = payload
        self._workspace = self.ensure_workspace(
            self._account, "airtable_base", bid,
            display_name=base.get("name"),
            permission_level=base.get("permissionLevel"))
        native = "airtable:base:%s" % bid
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Database", content_hash=evidence.hash_bytes(
                ("%s|%s|%s" % (bid, base.get("name"),
                               len(snap.get("tables") or []))).encode()),
            evidence_hash=digest, title=base.get("name") or bid, body=None,
            source_modified_at=A.ts_iso(snap.get("captured_at")), job_id=job_id,
            raw_metadata={"base_id": bid,
                          "permission_level": base.get("permissionLevel"),
                          "table_count": len(snap.get("tables") or []),
                          "captured_at": snap.get("captured_at"),
                          "snapshot_file": src},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="REFERENCE", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        return outcome

    def _acq_table(self, payload, job_id):
        t, bid, digest, src = payload
        tid = t.get("id") or t.get("name")
        fields = t.get("fields") or []
        computed = [f.get("name") for f in fields
                    if (f or {}).get("type") in COMPUTED]
        native = "airtable:table:%s" % tid
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Table",
            content_hash=evidence.hash_bytes(
                ("%s|%s" % (tid, "|".join(sorted(
                    "%s:%s" % (f.get("name"), f.get("type")) for f in fields
                )))).encode()),
            evidence_hash=digest, title=t.get("name") or tid, body=None,
            job_id=job_id,
            raw_metadata={"table_id": tid, "base_id": bid,
                          "record_count": len(t.get("records") or []),
                          "fields": [{"name": f.get("name"), "type": f.get("type")}
                                     for f in fields],
                          "computed_fields": computed,
                          "computed_fields_note":
                              "values only - the Airtable API does not return "
                              "formula, rollup or lookup expressions (SOW 107)",
                          "views_note":
                              "views, filters and sorts are not captured",
                          "snapshot_file": src},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="REFERENCE", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        self._link_now(oid, "airtable:base:%s" % bid, "PART_OF", job_id)
        return outcome

    def _acq_record(self, payload, job_id):
        r, t, bid, digest, src = payload
        rid = r.get("id")
        if not rid:
            raise ValueError("record with no id in table %s" % t.get("name"))
        fields = r.get("fields") or {}
        tid = t.get("id") or t.get("name")

        atts = []
        for fname, val in fields.items():
            if isinstance(val, list) and val and isinstance(val[0], dict) \
                    and "filename" in val[0] and "url" in val[0]:
                for a in val:
                    atts.append({"field": fname, "filename": a.get("filename"),
                                 "size": a.get("size"), "type": a.get("type"),
                                 "airtable_id": a.get("id")})
            if isinstance(val, list) and val and isinstance(val[0], str) \
                    and val[0].startswith("rec"):
                for linked in val:
                    self._pending.append(
                        ("airtable:record:%s" % rid,
                         "airtable:record:%s" % linked))

        body = "\n".join("%s: %s" % (k, _flat(v)) for k, v in fields.items()
                         if v not in (None, "", [], {}))
        title = _title_of(fields) or rid
        native = "airtable:record:%s" % rid
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Record",
            content_hash=evidence.hash_bytes(body.encode()),
            evidence_hash=digest, title=str(title)[:500], body=body or None,
            source_created_at=A.ts_iso(r.get("createdTime")),
            source_modified_at=A.ts_iso(r.get("createdTime")), job_id=job_id,
            raw_metadata={"record_id": rid, "table_id": tid, "base_id": bid,
                          "fields": fields, "attachments": atts,
                          "snapshot_file": src},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="FACT", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        self._link_now(oid, "airtable:table:%s" % tid, "PART_OF", job_id)

        for a in atts:
            self.stats["attachments_referenced"] += 1
            canonical.ingest_item(
                self.conn, source_id=self.source_id, account_id=self._account,
                workspace_id=self._workspace,
                native_id="airtable:attachment:%s" % (a.get("airtable_id")
                                                      or "%s:%s" % (rid, a["filename"])),
                object_class="FileReference",
                content_hash=evidence.hash_bytes(
                    ("%s|%s" % (rid, a.get("filename"))).encode()),
                title=a.get("filename") or "(attachment)", body=None,
                job_id=job_id,
                raw_metadata=dict(a, record_id=rid, bytes_available=False,
                                  reason="Airtable serves attachments from "
                                         "short-lived signed URLs; the URL is "
                                         "not durable and the bytes were not "
                                         "downloaded"),
                classification="PRIVATE", license="MY_CONTENT",
                memory_type="REFERENCE", authority="UNKNOWN",
                actor="job:%s" % job_id)
        return outcome

    def _link_now(self, src_oid, tgt_native, rtype, job_id):
        t = self._oids.get(tgt_native)
        if not t or t == src_oid:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
            "target_object,relationship_type,confidence,created_at,provenance,"
            "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
            (ids.scoped("REL", 1), src_oid, t, rtype, 1.0, now_iso(),
             "structural: the snapshot's own base/table/record nesting",
             "job:%s" % job_id, "PASSED"))

    def run(self, target, limit=None, dry_run=False):
        job_id, res, status = super().run(target, limit=limit, dry_run=dry_run)
        if not dry_run:
            for src, tgt in self._pending:
                s, t = self._oids.get(src), self._oids.get(tgt)
                if not s or not t or s == t:
                    self.stats["unresolved_links"] += 1
                    continue
                self.conn.execute(
                    "INSERT OR IGNORE INTO relationship(relationship_id,"
                    "source_object,target_object,relationship_type,confidence,"
                    "created_at,provenance,created_by,validation_status)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (ids.scoped("REL", 1), s, t, "LINKS_TO", 1.0, now_iso(),
                     "structural: linked-record field in the snapshot",
                     "job:%s" % job_id, "PASSED"))
                self.stats["linked_record_edges"] += 1
            self.conn.commit()
        return job_id, res, status


def _flat(v):
    if isinstance(v, list):
        return ", ".join(_flat(x) for x in v)
    if isinstance(v, dict):
        return v.get("name") or v.get("filename") or v.get("email") or str(v)
    return str(v)


def _title_of(fields):
    for k in ("Name", "name", "Title", "title", "Subject", "Company", "Email"):
        if fields.get(k):
            return _flat(fields[k])
    for _k, v in fields.items():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None
