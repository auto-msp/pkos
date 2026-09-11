"""Google Takeout adapter (SOW 110 Phase 10, and the unblock for Phase 7).

Takeout is chosen over the Google Drive connector deliberately, not for
convenience. The connector reads a spreadsheet's *values*; Takeout exports the
*.xlsx*, so formulas, named ranges and cell notes survive. A knowledge store
that kept only the numbers would have silently thrown away how they were
computed, and there is no way to recover that later from the values alone.
This is SOW 107 in practice: the connector's limitation is named, not papered
over.

What this adapter reads, and why each one earns its place:

  Chrome/BrowserHistory.json   The real browsing history. Phase 7 has 1,448
                               URLs from bookmark exports against an estimated
                               ~20,000 actually visited; bookmarks are the
                               handful a person stopped to save, history is
                               what they actually read. Timestamps here are
                               microseconds since 1601, not epoch seconds.
  Chrome/Bookmarks.html        Folder structure + ADD_DATE (SOW 60/62).
  Drive/                       The faithful copies, with sidecar metadata.
  Keep/                        Notes, with their labels and timestamps.
  Calendar/*.ics               Temporal spine; useful for dating everything else.
  My Activity/*/MyActivity.json Search and product activity as visits.
  Mail/*.mbox                  DELIBERATELY NOT INGESTED HERE. See below.

Mail is refused on purpose. SOW 45/46 says account identity is explicit and
never inferred, and mail is the one corpus where getting that wrong is
genuinely expensive to undo -- every message, thread and contact would be
filed under a merged identity, and unpicking it afterwards means re-deriving
identity for hundreds of thousands of rows. The mbox is registered as a known,
named, unacquired source so `gaps` reports it, and the operator is told the
exact command. A gap you can see is worth more than an ingest you cannot trust.
"""
import json
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .bookmarks import _NetscapeParser
from .. import canonical, evidence, urls
from ..events import audit

SIDECAR_SUFFIXES = ("-info.json", "-metadata.json")
DRIVE_SKIP = {".DS_Store", "archive_browser.html"}


class TakeoutAdapter(BaseAdapter):
    source_id = "SRC-google-takeout"
    vendor = "google"
    display_name = "Google Takeout"
    acquisition_method = "export"
    auth_method = "human_download"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"history_rows": 0, "history_new_urls": 0,
                      "bookmarks": 0, "drive_files": 0, "drive_sidecars": 0,
                      "keep_notes": 0, "calendar_files": 0, "activity_rows": 0,
                      "mail_mboxes_declared": 0, "products_seen": [],
                      "empty_globs": []}

    # -- discovery ----------------------------------------------------------
    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "takeout adapter requires --identity <google account email>.\n"
                "SOW 45/46: account identity is explicit, never inferred. A "
                "Takeout archive carries no reliable marker of which Google "
                "account produced it, and filing one account's Drive and "
                "history under another is not a mistake this store can undo "
                "cheaply. Name the account.")

        root, zips = A.parts(target, "takeout*.zip", "Takeout*.zip", "*.zip")
        if zips:
            root = A.unpack(self.conn, self.paths, zips, "google-takeout",
                            self.stats)
        root = self._takeout_root(root)

        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest takeout`",
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, "takeout", str(root.name), display_name="Google Takeout")
        self._root = root
        self.stats["products_seen"] = sorted(
            p.name for p in root.iterdir() if p.is_dir())

        self._declare_mail(root)
        yield from self._history(root)
        yield from self._bookmarks(root)
        yield from self._drive(root)
        yield from self._keep(root)
        yield from self._calendar(root)
        yield from self._activity(root)

    def _takeout_root(self, root):
        if (root / "Takeout").is_dir():
            return root / "Takeout"
        inner = sorted(root.glob("*/Takeout"))
        if inner:
            return inner[0]
        return root

    # -- product handlers ---------------------------------------------------
    def _history(self, root):
        for f in A.loud_glob(root, "BrowserHistory.json", "Chrome history",
                             self.stats):
            data = A.read_json(f)
            rows = data.get("Browser History") or data.get("browser_history") or []
            if not rows:
                self.stats["empty_globs"].append(
                    "BrowserHistory.json present but its 'Browser History' key "
                    "is empty or renamed")
            for r in rows:
                self.stats["history_rows"] += 1
                yield ("history", r, str(f))

    def _bookmarks(self, root):
        for f in A.loud_glob(root, "Bookmarks.html", "Chrome bookmarks",
                             self.stats):
            evidence.store_file(self.conn, self.paths.blobs, f, mime="web")
            p = _NetscapeParser()
            p.feed(f.read_bytes().decode("utf-8", errors="replace"))
            for item in p.items:
                self.stats["bookmarks"] += 1
                yield ("bookmark", item, str(f))

    def _drive(self, root):
        d = root / "Drive"
        if not d.is_dir():
            self.stats["empty_globs"].append("Drive/ (not in this export)")
            return
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name in DRIVE_SKIP:
                continue
            if any(f.name.endswith(s) for s in SIDECAR_SUFFIXES):
                self.stats["drive_sidecars"] += 1
                continue
            self.stats["drive_files"] += 1
            yield ("drive", f, str(f))

    def _keep(self, root):
        d = root / "Keep"
        if not d.is_dir():
            self.stats["empty_globs"].append("Keep/ (not in this export)")
            return
        for f in sorted(d.glob("*.json")):
            self.stats["keep_notes"] += 1
            yield ("keep", f, str(f))

    def _calendar(self, root):
        for f in A.loud_glob(root, "*.ics", "Calendar", self.stats):
            self.stats["calendar_files"] += 1
            yield ("calendar", f, str(f))

    def _activity(self, root):
        for f in A.loud_glob(root, "MyActivity.json", "My Activity", self.stats):
            product = f.parent.name
            try:
                rows = A.read_json(f)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not r.get("titleUrl"):
                    continue
                self.stats["activity_rows"] += 1
                r["_product"] = product
                yield ("activity", r, str(f))

    def _declare_mail(self, root):
        """Acquire the mbox BYTES, refuse to interpret them, and say so.

        This is the SOW 107 shape: the archive is real evidence and is stored
        content-addressed like everything else, so nothing is lost and nothing
        has to be re-downloaded. What is withheld is the *interpretation* --
        turning it into threads, messages and contacts -- because that step
        binds every row to an account identity, and Takeout does not carry one
        that can be trusted. The object minted here is what makes the deferral
        countable in `gaps` instead of a note in a chat log nobody reads.
        """
        mboxes = sorted(root.rglob("*.mbox"))
        if not mboxes:
            return
        self.stats["mail_mboxes_declared"] = len(mboxes)
        for m in mboxes:
            digest, _ = evidence.store_file(self.conn, self.paths.blobs, m,
                                            mime="application/mbox",
                                            job_id=None)
            canonical.ingest_item(
                self.conn, source_id=self.source_id, account_id=self._account,
                workspace_id=self._workspace,
                native_id="mail_archive:%s" % m.name,
                object_class="MailArchive", content_hash=digest,
                evidence_hash=digest,
                title="Mail archive (acquired, not interpreted): %s" % m.name,
                body=None, native_path=str(m),
                source_modified_at=A.ts_iso(m.stat().st_mtime),
                job_id=None,
                raw_metadata={
                    "bytes": m.stat().st_size,
                    "interpreted": False,
                    "reason": "SOW 45/46 - messages are not filed under an "
                              "inferred account identity",
                    "unblock": "secondbrain ingest mbox '%s' --identity "
                               "<address>" % m},
                classification="SENSITIVE", license="MY_CONTENT",
                memory_type="REFERENCE", authority="DIRECT PROJECT ARTIFACT",
                actor="adapter:takeout")
        audit(self.conn, "ingestion", "mail_deferred", "DECLARED",
              target=str(root),
              detail={"mboxes": [str(m) for m in mboxes],
                      "bytes_acquired": True, "interpreted": False,
                      "reason": "account identity must be explicit (SOW 45/46)",
                      "next": "secondbrain ingest mbox <path> --identity <address>"})
        self.conn.commit()

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, item, job_id):
        kind, payload, origin = item
        return getattr(self, "_acq_" + kind)(payload, origin, job_id)

    def _acq_history(self, r, origin, job_id):
        c = urls.canonicalize(r.get("url") or "")
        if not c["normalized_url"]:
            raise ValueError("unparseable history url: %r" % str(r.get("url"))[:120])
        when = A.chrome_ts(r.get("time_usec"))
        _uid, was_new = A.record_url(
            self.conn, c, when, r.get("title"),
            {"kind": "history", "browser": "chrome",
             "source_file": origin, "profile": r.get("client_id"),
             "raw": {"page_transition": r.get("page_transition")}})
        if was_new:
            self.stats["history_new_urls"] += 1
        return self._url_object(c, r.get("title"), when, origin, job_id,
                                "history visit", {"page_transition":
                                                  r.get("page_transition")})

    def _acq_bookmark(self, item, origin, job_id):
        c = urls.canonicalize(item["href"])
        if not c["normalized_url"]:
            raise ValueError("unparseable bookmark url: %r" % item["href"][:120])
        when = A.ts_iso(item.get("add_date"))
        A.record_url(self.conn, c, when, item["title"].strip() or None,
                              {"kind": "bookmark", "browser": "chrome",
                               "source_file": origin,
                               "folder": item.get("folder") or None})
        return self._url_object(c, item["title"].strip(), when, origin, job_id,
                                "bookmark", {"folder": item.get("folder")})

    def _url_object(self, c, title, when, origin, job_id, why, extra):
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=c["normalized_url"],
            object_class="WebPage",
            content_hash=evidence.hash_bytes(
                ("%s\n%s" % (c["normalized_url"], title or "")).encode()),
            title=(title or c["normalized_url"])[:500], body=None,
            native_url=c["original_url"], source_created_at=when,
            source_modified_at=when, job_id=job_id,
            raw_metadata=dict(extra or {}, origin=origin, why=why),
            classification="PRIVATE", license="THIRD_PARTY",
            memory_type="REFERENCE", authority="UNKNOWN",
            actor="job:%s" % job_id)
        self.conn.execute(
            "UPDATE url SET object_id=? WHERE normalized_url=? AND object_id IS NULL",
            (oid, c["normalized_url"]))
        return outcome

    def _acq_drive(self, path, origin, job_id):
        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime=_mime(path), job_id=job_id)
        meta = self._sidecar(path)
        body = None
        if path.suffix.lower() in (".txt", ".md", ".csv", ".json", ".html"):
            try:
                body = path.read_text(encoding="utf-8", errors="replace")[:200000]
            except OSError:
                body = None
        rel = str(path.relative_to(self._root))
        return canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id="drive:%s" % rel,
            object_class="File", content_hash=digest, evidence_hash=digest,
            title=meta.get("title") or path.name, body=body,
            native_path=str(path), native_url=meta.get("url"),
            source_created_at=A.ts_iso(meta.get("created_date")),
            source_modified_at=A.ts_iso(meta.get("modified_date")
                                        or path.stat().st_mtime),
            job_id=job_id,
            raw_metadata={"relative_path": rel, "bytes": path.stat().st_size,
                          "sidecar": meta or None,
                          "faithful_export": path.suffix.lower() in
                          (".xlsx", ".docx", ".pptx", ".odt", ".ods")},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="REFERENCE", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)[1]

    def _sidecar(self, path):
        for suffix in SIDECAR_SUFFIXES:
            cand = path.with_name(path.name + suffix)
            if cand.exists():
                try:
                    return A.read_json(cand)
                except (ValueError, UnicodeDecodeError):
                    return {}
        return {}

    def _acq_keep(self, path, origin, job_id):
        data = A.read_json(path)
        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime="application/json", job_id=job_id)
        body = data.get("textContent") or ""
        if data.get("listContent"):
            body += "\n" + "\n".join(
                "[%s] %s" % ("x" if i.get("isChecked") else " ", i.get("text", ""))
                for i in data["listContent"])
        return canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id="keep:%s" % path.name,
            object_class="Note", content_hash=evidence.hash_bytes(body.encode()),
            evidence_hash=digest, title=data.get("title") or path.stem,
            body=body or None, native_path=str(path),
            source_created_at=A.ts_iso(data.get("createdTimestampUsec")),
            source_modified_at=A.ts_iso(data.get("userEditedTimestampUsec")),
            job_id=job_id,
            raw_metadata={"labels": [l.get("name") for l in
                                     (data.get("labels") or [])],
                          "pinned": data.get("isPinned"),
                          "archived": data.get("isArchived"),
                          "trashed": data.get("isTrashed")},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="OBSERVATION", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)[1]

    def _acq_calendar(self, path, origin, job_id):
        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime="text/calendar", job_id=job_id)
        text = path.read_text(encoding="utf-8", errors="replace")
        events = text.count("BEGIN:VEVENT")
        return canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id="calendar:%s" % path.name,
            object_class="Calendar", content_hash=digest, evidence_hash=digest,
            title="Calendar: %s" % path.stem, body=None, native_path=str(path),
            source_modified_at=A.ts_iso(path.stat().st_mtime), job_id=job_id,
            raw_metadata={"vevent_count": events, "bytes": len(text),
                          "parsed": False,
                          "note": "the .ics is stored byte-exact as evidence; "
                                  "per-event normalization is not implemented "
                                  "and is declared rather than faked (SOW 107)"},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="REFERENCE", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)[1]

    def _acq_activity(self, r, origin, job_id):
        c = urls.canonicalize(r.get("titleUrl") or "")
        if not c["normalized_url"]:
            raise ValueError("unparseable activity url")
        when = A.ts_iso(r.get("time"))
        _uid, was_new = A.record_url(
            self.conn, c, when, r.get("title"),
            {"kind": "activity", "browser": None, "source_file": origin,
             "raw": {"product": r.get("_product"), "header": r.get("header")}})
        # Activity is a visit, not a document. Minting one canonical object per
        # activity row would put hundreds of thousands of near-empty objects in
        # the store and drown everything that matters. The URL and its visit are
        # recorded; the object is not.
        return "created" if was_new else "unchanged"


def _mime(path):
    ext = path.suffix.lower()
    return {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pdf": "application/pdf", ".json": "application/json",
            ".csv": "text/csv", ".md": "text/markdown", ".txt": "text/plain",
            ".html": "text/html"}.get(ext, "application/octet-stream")
