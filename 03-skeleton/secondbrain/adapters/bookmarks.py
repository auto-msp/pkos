"""Netscape bookmarks adapter (SOW 53-64, 110 Phase 7/8).

Parses the Netscape bookmark HTML that every browser exports, using only
html.parser from the stdlib. Produces THREE distinct object types, deliberately
not collapsed into one (SOW 58):

    url_visit  - the temporal event: this was bookmarked, at this time, in this
                 folder. This is the research signal.
    url        - the resource identity, with deterministic canonicalization.
    object     - the canonical knowledge object (class Bookmark).

ADD_DATE is the whole point of ingesting bookmarks rather than a plain URL
list: it is what makes SOW 60/62 temporal clustering possible. A bookmark file
with ADD_DATE stripped is a derived re-foldering, not a source, and is flagged
as such.
"""
from html.parser import HTMLParser
from pathlib import Path
from .base import BaseAdapter
from .. import evidence, canonical, ids, urls
from ..util import iso, now_iso


class _NetscapeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []; self.folders = []; self._pending = None; self._in_h3 = False
        self.folder_count = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h3":
            self._in_h3 = True; self._h3_text = ""
        elif tag == "dl":
            pass
        elif tag == "a" and a.get("href"):
            self._pending = {
                "href": a["href"],
                "add_date": a.get("add_date"),
                "last_modified": a.get("last_modified"),
                "icon_uri": a.get("icon_uri"),
                "tags": a.get("tags"),
                "folder": "/".join(self.folders) if self.folders else "",
                "title": "",
            }

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False
            self.folders.append(getattr(self, "_h3_text", "").strip() or "(unnamed)")
            self.folder_count += 1
        elif tag == "dl" and self.folders:
            self.folders.pop()
        elif tag == "a" and self._pending is not None:
            self.items.append(self._pending); self._pending = None

    def handle_data(self, data):
        if self._in_h3:
            self._h3_text = getattr(self, "_h3_text", "") + data
        elif self._pending is not None:
            self._pending["title"] += data


class BookmarksAdapter(BaseAdapter):
    source_id = "SRC-browser-bookmarks"
    vendor = "browser"
    display_name = "Browser bookmarks (Netscape export)"
    acquisition_method = "export"
    auth_method = "none"

    def __init__(self, *a, browser=None, **kw):
        super().__init__(*a, **kw)
        self.browser = browser or "unknown"
        self.stats = {"with_add_date": 0, "without_add_date": 0,
                      "unparseable_urls": 0, "folders": 0, "new_urls": 0,
                      "repeat_urls": 0}

    def discover(self, target):
        path = Path(target).expanduser().resolve()
        if not path.exists():
            raise SystemExit("bookmark file not found: %s" % path)
        raw = path.read_bytes()
        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime="web", job_id=None)
        self._source_file = str(path)
        self._source_hash = digest
        p = _NetscapeParser()
        p.feed(raw.decode("utf-8", errors="replace"))
        self.stats["folders"] = p.folder_count
        for it in p.items:
            yield it

    def acquire_one(self, item, job_id):
        c = urls.canonicalize(item["href"])
        if not c["normalized_url"]:
            self.stats["unparseable_urls"] += 1
            raise ValueError("unparseable url: %r" % item["href"][:120])

        added = iso(item["add_date"]) if item.get("add_date") else None
        if added: self.stats["with_add_date"] += 1
        else:     self.stats["without_add_date"] += 1

        # --- URL identity (deduplicated on normalized form, SOW 19 url-dedup)
        row = self.conn.execute("SELECT url_id,visit_count,first_seen,last_seen"
                                " FROM url WHERE normalized_url=?",
                                (c["normalized_url"],)).fetchone()
        if row:
            url_id = row["url_id"]; self.stats["repeat_urls"] += 1
            first = min(x for x in [row["first_seen"], added] if x) if (row["first_seen"] or added) else None
            last  = max(x for x in [row["last_seen"], added] if x) if (row["last_seen"] or added) else None
            self.conn.execute("UPDATE url SET visit_count=visit_count+1,"
                              "first_seen=?,last_seen=? WHERE url_id=?",
                              (first, last, url_id))
        else:
            url_id = ids.scoped("URL", 1); self.stats["new_urls"] += 1
            self.conn.execute(
                "INSERT INTO url(url_id,original_url,normalized_url,canonical_url,"
                "canonicalization_rules,domain,registrable_domain,scheme,first_seen,"
                "last_seen,visit_count,fetch_status,title)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (url_id, c["original_url"], c["normalized_url"], None,
                 ";".join(c["rules"]), c["domain"], urls.registrable(c["domain"]),
                 c["scheme"], added, added, 1, "NOT_FETCHED",
                 item["title"].strip() or None))

        # --- the temporal event, kept separate from the URL (SOW 58)
        self.conn.execute(
            "INSERT INTO url_visit(history_event_id,url_id,timestamp,browser,profile,"
            "source_file,visit_kind,folder_path,raw_metadata) VALUES(?,?,?,?,?,?,?,?,?)",
            (ids.scoped("VIS", 1), url_id, added, self.browser, None,
             self._source_file, "bookmark", item.get("folder") or None,
             None))

        # --- canonical knowledge object
        oid, outcome = canonical.ingest_item(
            self.conn,
            source_id=self.source_id, account_id=self.account_id,
            workspace_id=self.workspace_id,
            native_id=c["normalized_url"],
            object_class="Bookmark",
            content_hash=evidence.hash_bytes(
                ("%s\n%s\n%s" % (c["normalized_url"], item["title"].strip(),
                                  item.get("folder") or "")).encode()),
            evidence_hash=self._source_hash,   # the bookmarks.html blob it came from
            title=item["title"].strip() or c["normalized_url"],
            body=None, native_url=c["original_url"],
            source_created_at=added, source_modified_at=iso(item.get("last_modified")),
            job_id=job_id,
            raw_metadata={"folder": item.get("folder"), "tags": item.get("tags"),
                          "source_file_hash": self._source_hash,
                          "canonicalization_rules": c["rules"]},
            classification="PRIVATE", license="THIRD_PARTY",
            authority="UNKNOWN", memory_type="REFERENCE",
            actor="job:%s" % job_id)
        self.conn.execute("UPDATE url SET object_id=? WHERE url_id=? AND object_id IS NULL",
                          (oid, url_id))
        return outcome
