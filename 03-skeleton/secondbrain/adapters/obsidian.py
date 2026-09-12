"""Obsidian vault adapter (SOW 22 graph, 110 Phase 3).

The filesystem adapter can already ingest a vault: it will happily store 61,512
markdown files and every byte will be there. What it cannot do is see that the
vault is a GRAPH. Every `[[wikilink]]` is an edge the author drew by hand
between two ideas, and a vault's value is mostly in those edges -- the notes
are the nodes, the links are the thinking. Ingesting a vault as loose files
keeps the sentences and throws away the reasoning.

So this adapter reads what Obsidian actually means:

  [[Note]] [[Note|alias]] [[Note#heading]] ![[embed]]   -> LINKS_TO / EMBEDS
  #tag  #nested/tag                                      -> Tag entities
  --- YAML frontmatter ---                               -> typed metadata
  2026-09-11.md and friends                              -> dated daily notes
  .canvas                                                -> Obsidian canvases

Two Obsidian-specific rules that are easy to get wrong:

1. **Links resolve by NAME, not path.** `[[Meeting Notes]]` finds
   `any/depth/Meeting Notes.md`. Resolving links by path would silently drop
   almost every edge in a vault with folders. Where two files share a name the
   link is genuinely ambiguous; this records the ambiguity instead of picking
   one and pretending.

2. **Identity IS the path here, and that is correct** -- unlike Notion, where
   keying on the filename was a bug. Obsidian has no per-note id; renaming a
   note rewrites every link to it, so the name is the durable handle the vault
   itself uses. Saying so explicitly matters, because the opposite rule applies
   one module over.

Frontmatter is parsed by a small YAML subset reader rather than PyYAML: the
SOW forbids dependencies, and Obsidian frontmatter is overwhelmingly flat
`key: value` and simple lists. Anything it cannot parse is kept verbatim and
flagged, never silently dropped.
"""
import re
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids
from ..util import now_iso

WIKILINK = re.compile(r"(!?)\[\[([^\]\[|#^]+)(?:[#^][^\]\[|]*)?(?:\|([^\]\[]*))?\]\]")
# Obsidian has a "Use [[Wikilinks]]" setting, and with it OFF - which is the
# default for anyone who wants their vault to stay portable markdown - it
# writes ordinary links instead: [Note](Note.md) and ![img](assets/img.png).
# A vault authored that way is fully linked and shows ZERO wikilinks, so an
# adapter that only reads [[...]] reports an unlinked vault and is believed.
# 3,637 notes yielding 343 links was the tell.
MDLINK = re.compile(
    r'(!?)\[([^\]\[]*)\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)')
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.I)
TAG = re.compile(r"(?:(?<=\s)|^)#([A-Za-z][\w/-]*)")
# `#ef4444` is a colour, not a tag - and every CSS hex colour begins with one
# of a-f, so "must start with a letter" lets all of them through. The first
# real vault ingest produced a tag list whose top entries were ef4444, f59e0b,
# f8fafc, FFFFFF: the store had learned that Moiz's most important topic was
# the colour of his buttons. Obsidian itself rejects an all-digit tag for the
# same family of reason; this rejects the hex shapes too.
HEX_COLOUR = re.compile(r"^(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}"
                        r"|[0-9a-fA-F]{8})$")
# A tag also has to look like a word. Obsidian requires at least one
# non-numeric character; single letters and pure punctuation are noise.
TAG_MIN_LEN = 2
FENCE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]+`", re.S)
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
DAILY = re.compile(r"^(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})$")
# The canonical record of a note is a function of TWO things: the bytes on
# disk, and the parser that read them. Hashing only the bytes means a parser
# fix can never reach a vault that has already been ingested - re-running
# reports "unchanged" and the store keeps serving the old interpretation,
# which after the hex-colour bug meant keeping a tag list that said the
# vault's central topics were #ef4444 and #f8fafc. Bumping this forces exactly
# one new version per NOTE (not per attachment, whose parsing has not changed)
# with change_type=normalized, which is what SOW 9 asks for when the
# interpretation changes rather than the source.
#   1 - initial
#   2 - markdown links read as links; hex colours are no longer tags;
#       frontmatter keeps what parses instead of discarding the block
PARSE_VERSION = 2

NOTE_EXT = {".md", ".markdown"}
CANVAS_EXT = {".canvas"}
SKIP_DIRS = {".obsidian", ".trash", ".git", ".smart-env", ".space"}


class ObsidianAdapter(BaseAdapter):
    source_id = "SRC-obsidian"
    vendor = "obsidian"
    display_name = "Obsidian vault"
    acquisition_method = "filesystem"
    auth_method = "none"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"notes": 0, "canvases": 0, "attachments": 0,
                      "wikilinks_found": 0, "markdown_links_found": 0,
                      "external_links": 0, "links_resolved": 0,
                      "links_to_missing_notes": 0, "ambiguous_links": 0,
                      "embeds": 0, "tags_found": 0, "distinct_tags": 0,
                      "daily_notes": 0, "frontmatter_parsed": 0,
                      "frontmatter_unparseable": 0, "empty_globs": []}
        self._by_name = {}
        self._by_path = {}
        self._by_file = {}
        self._pending = []
        self._oids = {}
        self._tags = {}

    # -- discovery ----------------------------------------------------------
    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "obsidian adapter requires --identity <vault name>.\n"
                "SOW 45/46: identity is explicit, never inferred. Two vaults "
                "ingested without it merge into one graph, and a merged graph "
                "is worse than no graph -- it asserts connections between "
                "notes that were never linked.")

        root = Path(target).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit("vault path is not a directory: %s" % root)
        if (root / "HEAD").is_file() and (root / "objects").is_dir():
            raise SystemExit(
                "%s is a bare git repository, not a vault. Check out a working "
                "tree first:\n    git clone \"%s\" \"%s-worktree\"" % (root, root, root))
        self._root = root
        marker = root / ".obsidian"
        self.stats["has_obsidian_config"] = marker.is_dir()

        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest obsidian`",
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, "obsidian_vault", root.name, display_name=self.identity)

        files = []
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
                continue
            if p.name.startswith("."):
                continue
            files.append(p)
        if not files:
            raise SystemExit("no files found under %s - is this a vault?" % root)

        notes = [p for p in files if p.suffix.lower() in NOTE_EXT]
        if not notes:
            self.stats["empty_globs"].append(
                "no .md files anywhere under the vault root")
        # Index FIRST, and index THREE ways, because Obsidian accepts three
        # spellings of the same link and a stem-only index silently drops two
        # of them:
        #     [[Note]]              bare name, resolved vault-wide
        #     [[folder/Note]]       path-qualified, used whenever names collide
        #     ![[diagram.png]]      an attachment embed, which is a FILE not a note
        # Indexing only note stems loses every path-qualified link and every
        # embedded image in the vault - and loses them quietly, as unresolved
        # links, which look exactly like the author linking to something they
        # have not written yet.
        for p in notes:
            self._by_name.setdefault(p.stem.lower(), []).append(p)
        for p in files:
            rel = str(p.relative_to(root)).replace("\\", "/")
            self._by_path.setdefault(rel.lower(), p)
            stem_path = rel.rsplit(".", 1)[0].lower() if "." in p.name else rel.lower()
            self._by_path.setdefault(stem_path, p)
            self._by_file.setdefault(p.name.lower(), []).append(p)
        self.stats["notes_on_disk"] = len(notes)
        self.stats["files_on_disk"] = len(files)
        self.stats["name_collisions"] = sum(
            1 for v in self._by_name.values() if len(v) > 1)

        for p in files:
            yield p

    # -- frontmatter --------------------------------------------------------
    def _frontmatter(self, text):
        m = FRONTMATTER.match(text)
        if not m:
            return {}, text
        raw = m.group(1)
        body = text[m.end():]
        try:
            return self._mini_yaml(raw), body
        except Exception:
            self.stats["frontmatter_unparseable"] += 1
            return {"_unparsed_frontmatter": raw[:4000]}, body

    @staticmethod
    def _mini_yaml(raw):
        """A deliberately small YAML subset: flat keys, scalars, and lists.

        Obsidian frontmatter is almost always `tags:`, `aliases:`, `date:`,
        `status:` and similar. Supporting the whole YAML spec without a
        dependency is not possible, and pretending otherwise would be the
        invented capability SOW 107 forbids -- so anything richer is preserved
        verbatim under _unparsed_frontmatter rather than half-parsed.
        """
        out, key, nested = {}, None, {}
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if re.match(r"^\s*-\s+", line):
                if key is None:
                    raise ValueError("list item before any key")
                out.setdefault(key, [])
                if not isinstance(out[key], list):
                    out[key] = [out[key]] if out[key] else []
                out[key].append(_scalar(re.sub(r"^\s*-\s+", "", line)))
                continue
            if line[0] in " \t":
                # A nested map or a block scalar. Raising here threw away the
                # WHOLE frontmatter block - 166 of 1,198 notes in the real
                # vault lost every field they had because one key happened to
                # be nested. Keep what parsed, collect the rest verbatim.
                if key is not None:
                    nested.setdefault(key, []).append(line.strip())
                continue
            if ":" not in line:
                raise ValueError("line is neither key nor list item")
            k, _, v = line.partition(":")
            key = k.strip()
            v = v.strip()
            if v == "":
                out[key] = []
            elif v.startswith("[") and v.endswith("]"):
                out[key] = [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
            elif v in ("|", ">", "|-", ">-", "|+", ">+"):
                out[key] = []          # block scalar; body arrives indented
            else:
                out[key] = _scalar(v)
        for k, lines in nested.items():
            if isinstance(out.get(k), list) and not out[k]:
                out[k] = [re.sub(r"^-\s*", "", x) for x in lines]
            else:
                out["%s__raw" % k] = "\n".join(lines)
        return out

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, path, job_id):
        rel = str(path.relative_to(self._root)).replace("\\", "/")
        ext = path.suffix.lower()
        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime=_mime(ext), job_id=job_id)
        native = "obsidian:%s" % rel

        if ext in CANVAS_EXT:
            self.stats["canvases"] += 1
            return self._ingest(path, native, "Canvas", None, digest, rel,
                                job_id, {"parsed": False,
                                         "note": "canvas JSON stored as evidence; "
                                                 "node/edge extraction not implemented"})
        if ext not in NOTE_EXT:
            self.stats["attachments"] += 1
            return self._ingest(path, native, "File", None, digest, rel, job_id,
                                {"bytes": path.stat().st_size})

        self.stats["notes"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, body = self._frontmatter(text)
        if fm and "_unparsed_frontmatter" not in fm:
            self.stats["frontmatter_parsed"] += 1

        stripped = FENCE.sub(" ", body)     # never read links/tags out of code
        links, embeds = [], []
        for bang, target, alias in WIKILINK.findall(stripped):
            self.stats["wikilinks_found"] += 1
            t = target.strip()
            (embeds if bang else links).append({"target": t, "alias": alias or None})
            if bang:
                self.stats["embeds"] += 1
            self._pending.append((native, t, "EMBEDS" if bang else "LINKS_TO"))

        for bang, text, href in MDLINK.findall(stripped):
            if EXTERNAL.match(href):
                self.stats["external_links"] = self.stats.get("external_links", 0) + 1
                continue
            from urllib.parse import unquote
            t = unquote(href.split("#")[0]).strip()
            if not t:
                continue
            self.stats["markdown_links_found"] += 1
            (embeds if bang else links).append({"target": t, "alias": text or None})
            if bang:
                self.stats["embeds"] += 1
            self._pending.append((native, t, "EMBEDS" if bang else "LINKS_TO"))

        tags = sorted({t for t in TAG.findall(stripped)
                       if len(t) >= TAG_MIN_LEN and not HEX_COLOUR.match(t)})
        for t in tags:
            self._tags[t] = self._tags.get(t, 0) + 1
        self.stats["tags_found"] += len(tags)
        fm_tags = fm.get("tags") or fm.get("tag") or []
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        all_tags = sorted(set(tags) | {str(x).lstrip("#") for x in fm_tags})

        daily = DAILY.match(path.stem)
        when = None
        if daily:
            self.stats["daily_notes"] += 1
            when = "%s-%s-%sT00:00:00Z" % daily.groups()
        when = when or A.ts_iso(fm.get("date") or fm.get("created"))

        meta = {
            "relative_path": rel, "folder": str(Path(rel).parent)
            if str(Path(rel).parent) != "." else None,
            "frontmatter": fm or None,
            "tags": all_tags, "inline_tags": tags,
            "wikilinks": [l["target"] for l in links],
            "embeds": [e["target"] for e in embeds],
            "aliases": fm.get("aliases") or fm.get("alias") or [],
            "is_daily_note": bool(daily),
            "word_count": len(body.split()),
            "identity_basis": "vault-relative path - correct for Obsidian, which "
                              "has no note id and rewrites links on rename, so "
                              "the name IS the durable handle",
        }
        return self._ingest(path, native, "Note", body.strip()[:400000], digest,
                            rel, job_id, meta,
                            title=(fm.get("title") or path.stem), when=when,
                            memory_type="REFERENCE")

    def _ingest(self, path, native, cls, body, digest, rel, job_id, meta,
                title=None, when=None, memory_type=None):
        st = path.stat()
        title = str(title or path.stem)[:500]
        basis = "%s|%s" % (digest, title)
        if cls == "Note":
            basis += "|parse%d" % PARSE_VERSION
        content_hash = evidence.hash_bytes(basis.encode())
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native, object_class=cls,
            content_hash=content_hash, evidence_hash=digest, title=title,
            body=body, native_path=str(path),
            source_created_at=when,
            source_modified_at=when or A.ts_iso(st.st_mtime), job_id=job_id,
            raw_metadata=meta, classification="PRIVATE", license="MY_CONTENT",
            memory_type=memory_type, authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        return outcome

    # -- link resolution ----------------------------------------------------
    def run(self, target, limit=None, dry_run=False):
        job_id, res, status = super().run(target, limit=limit, dry_run=dry_run)
        if not dry_run:
            self._write_links(job_id)
            self.stats["distinct_tags"] = len(self._tags)
            self.stats["top_tags"] = dict(
                sorted(self._tags.items(), key=lambda x: -x[1])[:25])
        return job_id, res, status

    def _resolve(self, target):
        """Resolve a wikilink the way Obsidian does: path, then filename, then
        bare name. Returns a Path, None for unresolved, or "AMBIGUOUS"."""
        t = target.lower().strip().strip("/")
        if not t:
            return None
        if "/" in t:
            # Path-qualified. The path index is consulted ONLY here: a
            # root-level note's path key is identical to its bare stem, so
            # letting bare names fall through to it would quietly resolve
            # [[Ambiguous]] to whichever of two same-named notes sorted first -
            # a confident wrong edge, which is worse than no edge.
            return self._by_path.get(t) or self._by_path.get(t + ".md")
        cands = self._by_file.get(t)          # ![[diagram.png]] - has an extension
        if cands:
            return cands[0] if len(cands) == 1 else "AMBIGUOUS"
        cands = self._by_name.get(t)          # [[Perceptor]] - a bare note name
        if cands:
            return cands[0] if len(cands) == 1 else "AMBIGUOUS"
        return None

    def _write_links(self, job_id):
        written = 0
        for src_native, target, rtype in self._pending:
            hit = self._resolve(target)
            if hit == "AMBIGUOUS":
                self.stats["ambiguous_links"] += 1
                continue
            if hit is None:
                # Obsidian happily links to notes that do not exist yet - the
                # famous "unresolved link". That is a real signal about intent,
                # not an error, so it is counted rather than discarded.
                self.stats["links_to_missing_notes"] += 1
                continue
            tgt_native = "obsidian:%s" % str(
                hit.relative_to(self._root)).replace("\\", "/")
            s, t = self._oids.get(src_native), self._oids.get(tgt_native)
            if not s or not t or s == t:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
                "target_object,relationship_type,confidence,created_at,provenance,"
                "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
                (ids.scoped("REL", 1), s, t, rtype, 1.0, now_iso(),
                 "structural: a wikilink the author wrote in the note itself",
                 "job:%s" % job_id, "PASSED"))
            written += 1
        self.stats["links_resolved"] = written
        self.conn.commit()


def _scalar(v):
    v = v.strip().strip('"').strip("'")
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def _mime(ext):
    return {".md": "text/markdown", ".markdown": "text/markdown",
            ".canvas": "application/json", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".pdf": "application/pdf", ".svg": "image/svg+xml",
            ".webp": "image/webp", ".excalidraw": "application/json"
            }.get(ext, "application/octet-stream")
