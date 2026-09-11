"""Notion export adapter (SOW 110 Phase 11).

Notion's "Export all" produces `Export-<uuid>.zip`, and over a certain size it
produces several of them, each containing more zips. Every exported filename
carries the block's real Notion id as a 32-hex suffix:

    Meeting Notes 1a2b3c4d5e6f7890abcdef1234567890.md
                  ^------------- the page id -------^

That suffix is the only durable identity in the whole export. The visible part
is the page *title*, which the user renames freely, and the directory path is
the *current* nesting, which they reorganise freely. SOW 9 is explicit that
identity is never derived from a path or a filename, and Notion is the source
that punishes it hardest: re-export after a tidy-up and a path-keyed ingest
duplicates the entire workspace while reporting a clean run. Key on the id;
treat the title and the path as content that can change.

The export also loses things, and they are named rather than glossed:
  - Comments are not exported at all.
  - Database *views*, filters and sorts are not exported; the CSV is one
    flattened view of the rows.
  - Formula columns export as computed values, not as formulas.
  - Synced blocks export as static copies.
"""
import re
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids
from ..util import now_iso

ID_RE = re.compile(r"[ _-]([0-9a-f]{32})(?:_all)?$", re.I)
LINK_RE = re.compile(r"\]\(([^)]+?\.(?:md|csv|html))\)", re.I)
PAGE_EXT = {".md", ".html"}
DB_EXT = {".csv"}
TEXTUAL = PAGE_EXT | DB_EXT
LOSSES = {
    "comments": "not present in any Notion export",
    "database_views": "only one flattened view per database is exported",
    "formulas": "formula columns export as computed values, not formulas",
    "synced_blocks": "exported as static copies of their content",
}


class NotionAdapter(BaseAdapter):
    source_id = "SRC-notion"
    vendor = "notion"
    display_name = "Notion workspace export"
    acquisition_method = "export"
    auth_method = "human_download"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"pages": 0, "databases": 0, "assets": 0,
                      "with_notion_id": 0, "without_notion_id": 0,
                      "internal_links": 0, "unresolved_links": 0,
                      "nested_zips": 0, "empty_globs": [],
                      "known_export_losses": LOSSES}
        self._by_id = {}
        self._pending_links = []

    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "notion adapter requires --identity <your Notion account email "
                "or workspace name>.\nSOW 45/46: account identity is explicit, "
                "never inferred. A Notion export carries no marker of which "
                "workspace or account produced it - the filenames are page "
                "titles and the ids are block ids, neither of which names an "
                "owner. Two workspaces ingested without this are merged, "
                "silently, with no error.")

        root, zips = A.parts(target, "Export-*.zip", "*.zip")
        if zips:
            root = A.unpack(self.conn, self.paths, zips, "notion-export",
                            self.stats)
        self._root = root

        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest notion`",
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, "notion_workspace", root.name,
            display_name="Notion export %s" % root.name)

        files = [p for p in sorted(root.rglob("*")) if p.is_file()
                 and not p.name.startswith(".unpacked-")
                 and p.suffix.lower() != ".zip"]
        if not files:
            raise SystemExit(
                "no files found under %s.\nA Notion export should contain .md "
                "or .html pages and .csv databases. Either this is not a Notion "
                "export, or the zip did not unpack." % root)

        pages = [p for p in files if p.suffix.lower() in TEXTUAL]
        if not pages:
            self.stats["empty_globs"].append(
                "no .md/.html/.csv anywhere in the export - format may have changed")

        # Two passes on purpose: every page id must be known before any link is
        # resolved, otherwise a link to a page later in the walk resolves to
        # nothing and is quietly dropped.
        for p in pages:
            nid = self._notion_id(p)
            if nid:
                self._by_id[nid] = p
        for p in files:
            yield p

    @staticmethod
    def _notion_id(path):
        m = ID_RE.search(path.stem)
        return m.group(1).lower() if m else None

    @staticmethod
    def _clean_title(path):
        return ID_RE.sub("", path.stem).strip() or path.stem

    def acquire_one(self, path, job_id):
        ext = path.suffix.lower()
        nid = self._notion_id(path)
        rel = str(path.relative_to(self._root)).replace("\\", "/")
        if nid:
            self.stats["with_notion_id"] += 1
            native = "notion:%s" % nid
        else:
            # No id in the name: an attachment, or an export shape this adapter
            # has not seen. Fall back to the relative path but SAY SO, so the
            # weaker identity is visible in the store rather than assumed.
            self.stats["without_notion_id"] += 1
            native = "notion:path:%s" % rel

        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime=_mime(ext), job_id=job_id)

        if ext not in TEXTUAL:
            self.stats["assets"] += 1
            return self._ingest(path, native, "File", None, digest, rel, nid,
                                job_id, memory_type="REFERENCE")

        text = path.read_text(encoding="utf-8", errors="replace")
        if ext in DB_EXT:
            self.stats["databases"] += 1
            rows = A.read_csv_rows(path, self.stats)
            body = text[:400000]
            return self._ingest(
                path, native, "Database", body, digest, rel, nid, job_id,
                memory_type="REFERENCE",
                extra={"row_count": len(rows),
                       "columns": list(rows[0].keys()) if rows else [],
                       "export_losses": ["database_views", "formulas"]})

        self.stats["pages"] += 1
        for m in LINK_RE.finditer(text):
            target = m.group(1)
            tid = self._link_id(target)
            if tid:
                self.stats["internal_links"] += 1
                self._pending_links.append((native, "notion:%s" % tid))
            else:
                self.stats["unresolved_links"] += 1
        return self._ingest(path, native, "Page", text[:400000], digest, rel,
                            nid, job_id, memory_type="REFERENCE")

    @staticmethod
    def _link_id(href):
        from urllib.parse import unquote
        m = re.search(r"([0-9a-f]{32})", unquote(href), re.I)
        return m.group(1).lower() if m else None

    def _ingest(self, path, native, cls, body, digest, rel, nid, job_id,
                memory_type=None, extra=None):
        st = path.stat()
        # The blob digest alone is NOT the content hash. A Notion page's title
        # lives in its filename, not in the file, so renaming a page changes
        # nothing about the bytes -- and an ingest keyed on the digest reports
        # "unchanged" while the store keeps serving the old title forever. The
        # title is part of what the page IS; fold it in, and a rename becomes a
        # new version under the same object, which is what SOW 9 asks for.
        title = self._clean_title(path)[:500]
        content_hash = evidence.hash_bytes(
            ("%s|%s" % (digest, title)).encode())
        meta = {"relative_path": rel, "bytes": st.st_size,
                "notion_id": nid,
                "identity_basis": "notion block id" if nid else
                                  "relative path (no id in filename - weaker "
                                  "identity, will duplicate if the page is "
                                  "moved or renamed)",
                "parent_path": str(Path(rel).parent) if Path(rel).parent != Path(".") else None}
        meta.update(extra or {})
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native, object_class=cls,
            content_hash=content_hash, evidence_hash=digest,
            title=title, body=body,
            native_path=str(path),
            source_modified_at=A.ts_iso(st.st_mtime), job_id=job_id,
            raw_metadata=meta, classification="PRIVATE", license="MY_CONTENT",
            memory_type=memory_type, authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oid_cache_set(native, oid)
        return outcome

    # -- link resolution ----------------------------------------------------
    def _oid_cache_set(self, native, oid):
        if not hasattr(self, "_oids"):
            self._oids = {}
        self._oids[native] = oid

    def run(self, target, limit=None, dry_run=False):
        job_id, res, status = super().run(target, limit=limit, dry_run=dry_run)
        if not dry_run:
            self._write_links(job_id)
        return job_id, res, status

    def _write_links(self, job_id):
        """Write LINKS_TO edges once every page has an object_id.

        Deferred to the end deliberately: Notion pages link forwards as often
        as backwards, and resolving during the walk would silently drop every
        link to a page that had not been reached yet.
        """
        oids = getattr(self, "_oids", {})
        written = dropped = 0
        for src, tgt in self._pending_links:
            s, t = oids.get(src), oids.get(tgt)
            if not s or not t or s == t:
                dropped += 1
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
                "target_object,relationship_type,confidence,created_at,provenance,"
                "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
                (ids.scoped("REL", 1), s, t, "LINKS_TO", 1.0, now_iso(),
                 "structural: inline link in the exported page, not inferred",
                 "job:%s" % job_id, "PASSED"))
            written += 1
        self.stats["links_written"] = written
        self.stats["links_to_pages_outside_export"] = dropped
        self.conn.commit()


def _mime(ext):
    return {".md": "text/markdown", ".csv": "text/csv", ".html": "text/html",
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".pdf": "application/pdf",
            ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
