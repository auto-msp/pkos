"""Meta "Download Your Information" adapter - Instagram and Facebook
(SOW 110 Phases 17 and 18).

One adapter for two products because Meta ships them in one format. Both write
JSON in the DYI layout, both wrap their records under a single key whose name
changes between exports (`ig_stories`, `likes_media_likes`, `comments_v2`,
`saved_saved_media`, ...), both use the `string_map_data` idiom for labelled
fields, and both have the same encoding bug.

That bug is worth stating plainly because it is silent and total. Meta writes
UTF-8 bytes and then JSON-escapes each BYTE as if it were a codepoint. So a
post containing "café" arrives as "cafÃ©" and an emoji arrives as four
mojibake characters. Nothing raises. The JSON is valid. Every non-ASCII
character in years of posts and messages is simply wrong, and no search will
ever match them again. `_archive.meta_text` reverses it, and it is applied to
every string on the way in, not at read time -- the canonical layer should hold
what was actually written.

The other decision here is to find records STRUCTURALLY rather than by a table
of filenames. Meta renames these files between exports; a filename table would
go stale silently, which is bug 12.3 all over again. Instead: parse the JSON,
find the list of record-shaped dicts wherever it is, and report any file where
none was found rather than skipping it quietly.
"""
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids, urls
from ..util import now_iso

TS_KEYS = ("timestamp", "creation_timestamp", "timestamp_ms", "taken_at",
           "time", "date")
TEXT_KEYS = ("title", "post", "content", "text", "caption", "name", "value",
             "description")
SKIP_FILES = {"autofill_information.json", "ads_information.json"}


class MetaExportAdapter(BaseAdapter):
    vendor = "meta"
    acquisition_method = "export"
    auth_method = "human_download"
    product = "meta"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"json_files": 0, "records": 0, "messages": 0,
                      "threads": 0, "media_files": 0,
                      "files_with_no_records": [], "mojibake_fixed": 0,
                      "nested_zips": 0, "empty_globs": []}

    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "%s adapter requires --identity <your handle or account "
                "email>.\nSOW 45/46: account identity is explicit, never "
                "inferred." % self.product)

        root, zips = A.parts(target, "*.zip")
        if zips:
            root = A.unpack(self.conn, self.paths, zips,
                            "%s-export" % self.product, self.stats)
        self._root = root

        self._account = self.ensure_account(
            self.identity,
            discovered_via="operator-declared on `ingest %s`" % self.product,
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, self.product, root.name,
            display_name="%s export" % self.display_name)

        files = A.loud_glob(root, "*.json", "%s JSON" % self.product,
                            self.stats, required=True)
        for f in files:
            if f.name in SKIP_FILES:
                continue
            self.stats["json_files"] += 1
            try:
                data = A.read_json(f, meta=True)
            except (ValueError, UnicodeDecodeError) as e:
                self.stats["files_with_no_records"].append(
                    "%s (unparseable: %s)" % (f.name, e))
                continue

            if self._is_thread(data):
                self.stats["threads"] += 1
                yield ("thread", (f, data), str(f))
                for m in data.get("messages") or []:
                    self.stats["messages"] += 1
                    yield ("message", (f, data, m), str(f))
                continue

            records = self._records(data)
            if not records:
                self.stats["files_with_no_records"].append(f.name)
                continue
            for r in records:
                self.stats["records"] += 1
                yield ("record", (f, r), str(f))

    # -- structure discovery ------------------------------------------------
    @staticmethod
    def _is_thread(data):
        return (isinstance(data, dict) and "messages" in data
                and isinstance(data.get("messages"), list)
                and "participants" in data)

    @staticmethod
    def _records(data):
        """Find the list of records wherever Meta put it this time."""
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if not isinstance(data, dict):
            return []
        best = []
        for _k, v in data.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                if len(v) > len(best):
                    best = v
        if not best and any(k in data for k in TEXT_KEYS + TS_KEYS):
            return [data]           # a single-record file
        return best

    @staticmethod
    def _first(d, keys):
        for k in keys:
            if isinstance(d, dict) and d.get(k) not in (None, "", [], {}):
                return d[k]
        return None

    def _text_of(self, r):
        bits = []
        v = self._first(r, TEXT_KEYS)
        if isinstance(v, str):
            bits.append(v)
        for m in (r.get("media") or []):
            if isinstance(m, dict) and m.get("title"):
                bits.append(m["title"])
        smd = r.get("string_map_data")
        if isinstance(smd, dict):
            for label, val in smd.items():
                if isinstance(val, dict) and val.get("value"):
                    bits.append("%s: %s" % (label, val["value"]))
        for d in (r.get("data") or []):
            if isinstance(d, dict):
                for k in TEXT_KEYS:
                    if isinstance(d.get(k), str) and d[k]:
                        bits.append(d[k])
        return "\n".join(dict.fromkeys(b for b in bits if b)).strip()

    def _when_of(self, r):
        v = self._first(r, TS_KEYS)
        if v is None:
            smd = r.get("string_map_data") or {}
            for val in smd.values():
                if isinstance(val, dict) and val.get("timestamp"):
                    v = val["timestamp"]; break
        if v is None:
            for m in (r.get("media") or []):
                if isinstance(m, dict) and m.get("creation_timestamp"):
                    v = m["creation_timestamp"]; break
        return A.ts_iso(v)

    def _links_of(self, r):
        out = []
        smd = r.get("string_map_data") or {}
        for val in smd.values():
            if isinstance(val, dict) and val.get("href"):
                out.append(val["href"])
        for m in (r.get("media") or []):
            if isinstance(m, dict) and m.get("uri"):
                out.append(m["uri"])
        if isinstance(r.get("uri"), str):
            out.append(r["uri"])
        return out

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, item, job_id):
        kind, payload, origin = item
        return getattr(self, "_acq_" + kind)(payload, origin, job_id)

    def _acq_record(self, payload, origin, job_id):
        f, r = payload
        text = self._text_of(r)
        when = self._when_of(r)
        rel = str(f.relative_to(self._root)).replace("\\", "/")
        # Identity from CONTENT, never from position in the file: Meta reorders
        # and re-paginates these arrays between exports, so an index-keyed id
        # would duplicate the entire history on the next download.
        native = "%s:%s:%s" % (self.product, rel,
                               evidence.hash_bytes(
                                   ("%s|%s" % (when or "", text)).encode())[:24])
        for href in self._links_of(r):
            if not href.lower().startswith("http"):
                self.stats["media_files"] += 1
                continue
            c = urls.canonicalize(href)
            if c["normalized_url"]:
                A.record_url(self.conn, c, when, text[:200] or None,
                             {"kind": "referenced", "source_file": str(f),
                              "raw": {"product": self.product}})
        return canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class=_class_for(rel),
            content_hash=evidence.hash_bytes((text or rel).encode()),
            title=(text[:120].replace("\n", " ") or Path(rel).stem)[:500],
            body=text or None, source_created_at=when, source_modified_at=when,
            job_id=job_id,
            raw_metadata={"source_file": rel, "product": self.product,
                          "media_uris": self._links_of(r)[:20],
                          "encoding_corrected": True},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="OBSERVATION", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)[1]

    def _acq_thread(self, payload, origin, job_id):
        f, data = payload
        rel = str(f.relative_to(self._root)).replace("\\", "/")
        people = [p.get("name") for p in (data.get("participants") or [])
                  if isinstance(p, dict)]
        thread_key = data.get("thread_path") or str(Path(rel).parent)
        native = "%s:thread:%s" % (self.product, thread_key)
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Conversation",
            content_hash=evidence.hash_bytes(
                ("%s|%s" % (thread_key, "|".join(people))).encode()),
            title=(data.get("title") or " & ".join(people) or thread_key)[:500],
            body=None, job_id=job_id,
            raw_metadata={"participants": people, "thread_path": thread_key,
                          "message_count": len(data.get("messages") or []),
                          "is_still_participant": data.get("is_still_participant"),
                          "source_file": rel},
            classification="SENSITIVE", license="MY_CONTENT",
            memory_type="OBSERVATION", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        if not hasattr(self, "_threads"):
            self._threads = {}
        self._threads[thread_key] = oid
        return outcome

    def _acq_message(self, payload, origin, job_id):
        f, data, m = payload
        rel = str(f.relative_to(self._root)).replace("\\", "/")
        thread_key = data.get("thread_path") or str(Path(rel).parent)
        when = A.ts_iso(m.get("timestamp_ms") or m.get("timestamp"))
        sender = m.get("sender_name") or "(unknown)"
        text = m.get("content") or ""
        native = "%s:msg:%s:%s" % (
            self.product, thread_key,
            evidence.hash_bytes(("%s|%s|%s" % (when or "", sender, text)).encode())[:24])
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Message",
            content_hash=evidence.hash_bytes(("%s|%s" % (sender, text)).encode()),
            title=("%s: %s" % (sender, text[:120].replace("\n", " ")))[:500],
            body=text or None, source_created_at=when, source_modified_at=when,
            job_id=job_id,
            raw_metadata={"sender": sender, "thread_path": thread_key,
                          "product": self.product, "type": m.get("type"),
                          "is_unsent": m.get("is_unsent"),
                          "reactions": m.get("reactions"),
                          "share": (m.get("share") or {}).get("link"),
                          "encoding_corrected": True, "source_file": rel},
            classification="SENSITIVE", license="MY_CONTENT",
            memory_type="OBSERVATION", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        parent = getattr(self, "_threads", {}).get(thread_key)
        if parent and parent != oid:
            self.conn.execute(
                "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
                "target_object,relationship_type,confidence,created_at,provenance,"
                "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
                (ids.scoped("REL", 1), oid, parent, "PART_OF", 1.0, now_iso(),
                 "structural: the export's own thread folder", "job:%s" % job_id,
                 "PASSED"))
        return outcome


def _class_for(rel):
    low = rel.lower()
    for needle, cls in (("saved", "Bookmark"), ("like", "Reaction"),
                        ("reaction", "Reaction"), ("comment", "Comment"),
                        ("follow", "SocialLink"), ("connection", "SocialLink"),
                        ("stor", "Post"), ("post", "Post"), ("reel", "Post"),
                        ("profile", "ProfileFact"),
                        ("personal_information", "ProfileFact")):
        if needle in low:
            return cls
    return "SocialRecord"


class InstagramAdapter(MetaExportAdapter):
    source_id = "SRC-instagram"
    display_name = "Instagram"
    product = "instagram"


class FacebookAdapter(MetaExportAdapter):
    source_id = "SRC-facebook"
    display_name = "Facebook"
    product = "facebook"
