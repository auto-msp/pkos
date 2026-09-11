"""Filesystem adapter (SOW 75, 110 Phase 3/6).

Ingests documents from a directory tree. Implements the SOW 75 include/exclude
policy, but exclusion is a CLASSIFICATION, not a deletion or an omission: every
excluded file is still counted and reported so the corpus total reconciles.
"""
import os
from pathlib import Path
from .base import BaseAdapter
from .. import evidence, canonical
from ..util import iso

# SOW 75 INCLUDE
INCLUDE_EXT = {
    ".pdf":"pdf", ".doc":"doc", ".docx":"doc", ".odt":"doc", ".rtf":"doc",
    ".txt":"text", ".md":"text", ".markdown":"text", ".org":"text", ".tex":"text",
    ".xls":"sheet", ".xlsx":"sheet", ".xlsm":"sheet", ".ods":"sheet", ".csv":"sheet", ".tsv":"sheet",
    ".ppt":"slides", ".pptx":"slides", ".odp":"slides", ".key":"slides",
    ".epub":"ebook", ".mobi":"ebook", ".azw3":"ebook",
    ".png":"image", ".jpg":"image", ".jpeg":"image", ".gif":"image", ".webp":"image",
    ".svg":"image", ".bmp":"image", ".tiff":"image", ".heic":"image",
    ".html":"web", ".htm":"web", ".mhtml":"web", ".har":"web",
    ".json":"data", ".jsonl":"data", ".xml":"data", ".yaml":"data", ".yml":"data",
    ".vcf":"contact", ".ics":"calendar",
    ".mp3":"media", ".wav":"media", ".m4a":"media", ".mp4":"media", ".mov":"media",
    ".zip":"archive", ".tar":"archive", ".gz":"archive", ".7z":"archive",
}
# SOW 75 EXCLUDE (code + build artefacts)
EXCLUDE_EXT = {
    ".py",".js",".jsx",".ts",".tsx",".java",".c",".h",".cpp",".hpp",".cs",".go",
    ".rs",".rb",".php",".swift",".kt",".scala",".sh",".bash",".zsh",".ps1",".bat",
    ".lock",".map",".pyc",".pyo",".class",".o",".so",".dll",".dylib",".a",".obj",
    ".exe",".msi",".deb",".rpm",".appimage",".dmg",".pkg",".jar",".war",
}
EXCLUDE_DIRS = {
    "node_modules",".git",".svn","__pycache__",".next",".nuxt","dist","build",
    "target","vendor",".venv","venv","env",".tox",".gradle",".idea",".vscode",
    ".pytest_cache",".mypy_cache","site-packages",".cache","bower_components",
    ".terraform","coverage",".nyc_output",".parcel-cache",".turbo",
}
TEXT_KINDS = {"text", "web", "data"}
MAX_INLINE_BODY = 512 * 1024      # larger bodies stay in the evidence plane only


def is_bare_git_repo(path):
    """True for a directory that IS a git repository's internals.

    EXCLUDE_DIRS catches a directory literally named ".git". It does not catch
    `automsp-obsidian-vault.git`, which is the same thing under a different
    name -- a BARE repository, the shape `git clone --bare` and every git host
    produces. Walking one yields thousands of zlib-compressed loose objects and
    packfiles, and the adapter would dutifully ingest each as an opaque binary
    File: thousands of objects, gigabytes of evidence, and not one readable
    sentence, because the readable content only exists once a working tree is
    checked out. Detect it by structure (HEAD + objects/ + refs/), not by the
    ".git" suffix, so a repo under any name is recognised.
    """
    path = Path(path)
    try:
        return ((path / "HEAD").is_file()
                and (path / "objects").is_dir()
                and (path / "refs").is_dir())
    except OSError:
        return False


class FilesystemAdapter(BaseAdapter):
    source_id = "SRC-laptop-filesystem"
    vendor = "local"
    display_name = "Laptop filesystem"
    acquisition_method = "filesystem"
    auth_method = "local_fs"

    def __init__(self, *a, include_excluded=False, max_bytes=None, recurse=True, **kw):
        super().__init__(*a, **kw)
        self.recurse = recurse
        self.include_excluded = include_excluded
        self.max_bytes = max_bytes
        self.stats = {"excluded_files": 0, "excluded_bytes": 0,
                      "excluded_by_dir": 0, "oversize": 0,
                      "skipped_store_roots": 0, "skipped_unchanged": 0}

    @staticmethod
    def classify(path):
        ext = path.suffix.lower()
        if ext in EXCLUDE_EXT:
            return None, "code_or_binary"
        kind = INCLUDE_EXT.get(ext)
        if kind is None:
            return None, ("no_extension" if not ext else "unknown_extension")
        return kind, None

    def discover(self, target):
        root = Path(target).expanduser().resolve()
        if not root.exists():
            raise SystemExit("path does not exist: %s" % root)
        if root.is_file():
            yield root; return
        if not self.recurse:
            # depth-1 only: the loose files directly under `root`
            for name in sorted(os.listdir(root)):
                p = root / name
                try:
                    if p.is_file() and not p.is_symlink():
                        yield p
                except OSError:
                    continue
            return
        if is_bare_git_repo(root):
            raise SystemExit(
                "%s is a bare git repository, not a folder of documents.\n"
                "Everything under it is zlib-compressed loose objects and "
                "packfiles; ingesting it would add thousands of unreadable "
                "binaries and no knowledge at all. Check out a working tree "
                "first:\n"
                "    git clone \"%s\" \"%s-worktree\"\n"
                "then ingest that." % (root, root, root))
        for dirpath, dirnames, filenames in os.walk(root):
            # never descend into a PKOS store (self-ingestion guard)
            keep = []
            for d in dirnames:
                if d in EXCLUDE_DIRS or d.startswith("."):
                    continue
                sub = Path(dirpath) / d
                if (sub / ".pkos-root").exists():
                    continue
                if is_bare_git_repo(sub):
                    self.stats.setdefault("skipped_git_repos", []).append(str(sub))
                    continue
                keep.append(d)
            dirnames[:] = keep
            if (Path(dirpath) / ".pkos-root").exists():
                self.stats["skipped_store_roots"] = self.stats.get("skipped_store_roots", 0) + 1
                dirnames[:] = []
                continue
            for fn in filenames:
                p = Path(dirpath) / fn
                try:
                    if p.is_symlink() or not p.is_file():
                        continue
                except OSError:
                    continue
                yield p

    def unchanged_fast(self, path, st):
        """True when this exact path was already ingested at this size+mtime."""
        row = self.conn.execute(
            "SELECT source_modified_at, raw_metadata FROM source_object"
            " WHERE source_id=? AND (account_id IS ? OR account_id=?) AND native_id=?",
            (self.source_id, self.account_id, self.account_id, str(path))).fetchone()
        if not row or row["source_modified_at"] != iso(st.st_mtime):
            return False
        try:
            import json as _json
            return _json.loads(row["raw_metadata"] or "{}").get("size") == st.st_size
        except (ValueError, TypeError):
            return False

    def acquire_one(self, path, job_id):
        st = path.stat()
        if self.unchanged_fast(path, st):
            self.stats["skipped_unchanged"] = self.stats.get("skipped_unchanged", 0) + 1
            return "unchanged"
        kind, exclude_reason = self.classify(path)
        if kind is None and not self.include_excluded:
            self.stats["excluded_files"] += 1
            self.stats["excluded_bytes"] += st.st_size
            return "unchanged"                     # counted, not silently dropped
        if self.max_bytes and st.st_size > self.max_bytes:
            self.stats["oversize"] += 1
            return "unchanged"

        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime=kind, job_id=job_id)
        body = None
        if kind in TEXT_KINDS and st.st_size <= MAX_INLINE_BODY:
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = None

        oid, outcome = canonical.ingest_item(
            self.conn,
            source_id=self.source_id, account_id=self.account_id,
            workspace_id=self.workspace_id,
            native_id=str(path),                   # stable per machine+path
            object_class="File",
            content_hash=digest, evidence_hash=digest,
            title=path.name, body=body,
            native_path=str(path),
            source_created_at=iso(getattr(st, "st_ctime", None)),
            source_modified_at=iso(st.st_mtime),
            job_id=job_id,
            raw_metadata={"size": st.st_size, "ext": path.suffix.lower(),
                          "kind": kind, "excluded_reason": exclude_reason},
            actor="job:%s" % job_id)
        return outcome
