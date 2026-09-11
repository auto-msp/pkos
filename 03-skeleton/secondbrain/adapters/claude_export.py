"""Claude.ai account export adapter (SOW 110 Phase 14).

The export is a self-describing archive, so this adapter needs no API, no
token and no network: it is a pure filesystem read of an artefact the user
already owns. That matters for SOW 21 (provider independence) - the knowledge
survives whether or not the account still exists.

FOUR object classes, deliberately not collapsed into one (cf. SOW 58):

    Conversation      the container: title, dates, participants, the opening
                      ask. What a person actually remembers ("that chat where
                      we designed the voice agent").
    Message           the retrievable unit. 15k of them; this is what search
                      returns and what a citation points at.
    Attachment        a document pasted INTO a conversation. Its text is real
                      knowledge with a different origin from the chat around
                      it, so it gets its own identity and its own authority
                      tier rather than being smeared into the message body.
    ProjectDocument   a file attached to a Claude Project.
    AssistantMemory   what the assistant had synthesised about the user.
                      knowledge_state=SYNTHESIZED, authority=AI-GENERATED:
                      useful, but never confusable with something he said.

WHAT THE EXPORT DOES NOT CONTAIN (SOW 107 - never invent platform capability):
  * files[] entries carry a uuid and a name only. The BYTES of uploaded files
    are not in the export. Those objects are recorded as references with
    fetch_status UNAVAILABLE rather than silently dropped.
  * conversations carry no project id, so conversation->project membership
    CANNOT be reconstructed from this archive. No such relationship is
    written. Projects are registered as workspaces; their docs are ingested.
  * tool_result payloads are summarised in the canonical body, not inlined.
    The full JSON is in the evidence plane, addressed by the export's hash.
"""
import json
import zipfile
from pathlib import Path

from .base import BaseAdapter
from .. import evidence, canonical, ids, secrets
from ..events import audit
from ..util import now_iso, jdump

# body render markers -------------------------------------------------------
THINK = "[assistant reasoning]"
MAX_TOOL_SUMMARY = 400


def _norm(s):
    return "".join((s or "").split())


def render_message(m):
    """Canonical text of one message.

    Content blocks are the superset and win. Top-level `text` is appended only
    when it is genuinely different from the blocks (1,494 of 15,908 messages in
    the July-2026 export), so nothing the export carries is silently lost.
    """
    parts = []
    text_only = []
    for blk in (m.get("content") or []):
        t = blk.get("type")
        if t == "text":
            if blk.get("text"):
                parts.append(blk["text"]); text_only.append(blk["text"])
        elif t == "thinking":
            if blk.get("thinking"):
                parts.append("%s\n%s" % (THINK, blk["thinking"]))
        elif t == "tool_use":
            nm = blk.get("name") or "tool"
            via = blk.get("integration_name")
            inp = blk.get("input")
            brief = ""
            if inp is not None:
                brief = jdump(inp)[:MAX_TOOL_SUMMARY]
            parts.append("[tool_use: %s%s] %s" % (nm, " via %s" % via if via else "", brief))
        elif t == "tool_result":
            nm = blk.get("name") or "tool"
            body = blk.get("content")
            size = len(jdump(body)) if body is not None else 0
            parts.append("[tool_result: %s%s, %d chars - full payload in evidence]"
                         % (nm, " ERROR" if blk.get("is_error") else "", size))
        elif t == "token_budget":
            continue
        else:
            parts.append("[%s block]" % t)

    top = (m.get("text") or "").strip()
    if top and _norm(top) != _norm("\n\n".join(text_only)):
        parts.append(top if not text_only else "[export top-level text]\n" + top)
    return "\n\n".join(p for p in parts if p).strip() or None


class ClaudeExportAdapter(BaseAdapter):
    source_id = "SRC-claude-ai"
    vendor = "anthropic"
    display_name = "Claude.ai account export"
    acquisition_method = "export"
    auth_method = "none"

    def __init__(self, *a, allow_partial=False, **kw):
        super().__init__(*a, **kw)
        self.stats = {
            "conversations": 0, "messages": 0, "attachments": 0,
            "project_documents": 0, "assistant_memories": 0,
            "empty_messages": 0, "file_references_without_bytes": 0,
            "projects_registered": 0, "secrets_redacted_at_ingest": 0,
            "export_generation": None, "superseded_snapshots": 0,
            "export_parts_expected": None, "export_parts_present": None,
            "export_parts_missing": None, "login_events": 0,
            "foreign_memory_files_skipped": 0, "foreign_login_events_skipped": 0,
        }
        self.allow_partial = allow_partial
        self._manifest_path = None
        self._part_hashes = {}
        self._seen = {}        # native_id -> (content_hash, object_id)
        self._oid = {}         # native_id -> object_id (this run)
        self._pending_links = []

    # -- helpers ------------------------------------------------------------
    def _prefetch(self):
        """Resume map for THIS account only (SOW 45/46).

        This must be scoped by account and must run only after the account is
        resolved. Several native ids are not globally unique across accounts -
        `memory:conversations_memory:0` and `memory_file:/areas/x.md` are the
        same string in every export ever produced. An unscoped resume map would
        match a second account's memory document against the FIRST account's
        object and report it "unchanged": two people's knowledge silently
        collapsed into one object, with no error and nothing in the dead-letter
        queue. Account boundaries are not a data-quality nicety; a merge here is
        the one class of corruption that cannot be undone by re-running.
        """
        if self.account_id is None:
            raise RuntimeError(
                "refusing to build a resume map before the account is known "
                "(SOW 45: account identity is explicit, never inferred)")
        q = ("SELECT so.native_id AS n, so.content_hash AS h,"
             "       MAX(p.object_id) AS o"
             "  FROM source_object so"
             "  LEFT JOIN provenance p ON p.source_object_id = so.source_object_id"
             " WHERE so.source_id=? AND so.account_id IS ?"
             " GROUP BY so.native_id")
        for r in self.conn.execute(q, (self.source_id, self.account_id)):
            self._seen[r["n"]] = (r["h"], r["o"])

    def _link(self, src_native, tgt_native, rtype, job_id):
        s = self._oid.get(src_native) or (self._seen.get(src_native) or (None, None))[1]
        t = self._oid.get(tgt_native) or (self._seen.get(tgt_native) or (None, None))[1]
        if not s or not t or s == t:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
            "target_object,relationship_type,confidence,created_at,provenance,"
            "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
            (ids.scoped("REL", 1), s, t, rtype, 1.0, now_iso(),
             "structural: present in the Claude export itself, not inferred",
             "job:%s" % job_id, "PASSED"))

    def _ingest(self, *, native_id, object_class, body, title, job_id,
                created=None, modified=None, meta=None, authority="UNKNOWN",
                license="MY_CONTENT", memory_type=None,
                classification="PRIVATE"):
        """Ingest with the resume fast path and ingest-time secret redaction."""
        raw = body or ""
        chash = evidence.hash_bytes(
            ("%s\x00%s\x00%s" % (native_id, title or "", raw)).encode("utf-8"))
        prev = self._seen.get(native_id)
        if prev and prev[0] == chash and prev[1]:
            # Defence in depth: never hand back an object that belongs to a
            # different account, whatever the resume map says.
            owner = self.conn.execute(
                "SELECT so.account_id a FROM provenance p"
                "  JOIN source_object so ON so.source_object_id = p.source_object_id"
                " WHERE p.object_id=? LIMIT 1", (prev[1],)).fetchone()
            if owner and owner["a"] != self.account_id:
                raise ValueError(
                    "account boundary violation: %s already belongs to account %s, "
                    "refusing to reuse it for %s (SOW 46)"
                    % (prev[1], owner["a"], self.account_id))
            self._oid[native_id] = prev[1]
            return "unchanged"

        # SOW 28: a credential value must never reach the canonical layer.
        # The export's raw bytes keep it; the searchable body does not.
        kinds = secrets.scan_body(body)
        if kinds:
            body = secrets.MARKER + "\ndetected: " + ", ".join(kinds) + "\n"
            classification = "RESTRICTED"
            self.stats["secrets_redacted_at_ingest"] += 1

        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self.account_id,
            workspace_id=self.workspace_id, native_id=native_id,
            object_class=object_class, content_hash=chash,
            evidence_hash=self._export_hash,
            title=(title or "")[:300] or None, body=body,
            native_path=self._export_path, native_url=None,
            source_created_at=created, source_modified_at=modified,
            job_id=job_id, raw_metadata=meta,
            classification=classification, license=license,
            authority=authority, memory_type=memory_type,
            actor="job:%s" % job_id)
        self._oid[native_id] = oid
        return outcome

    # -- export layout resolution -------------------------------------------
    def _resolve_export(self, target, allow_partial=False):
        """Find the export's files, whatever shape the platform handed you.

        There are two shapes in the wild and this must handle both without
        guessing:

          old  a single unpacked folder: conversations.json, users.json,
               memories.json, projects/
          new  a manifest json plus one zip per category
               (conversations-000.zip, light_metadata-000.zip, memories-000.zip,
               projects-000.zip, design_chats-000.zip)

        When a manifest is present it is treated as the AUTHORITY on what the
        export contains. Anything it lists and the folder does not have is a
        missing part, and a missing part stops the run. The download URLs are
        single-use: a part that failed to download is gone until a new export
        is requested, and the failure mode of not checking is a corpus that
        looks complete and is quietly short a category (SOW 43 - completion is
        proven against what was promised, never inferred from what happens to
        be on disk).
        """
        root = Path(target).expanduser().resolve()
        if root.is_file():
            if root.suffix.lower() == ".json" and "manifest" in root.name.lower():
                root = root.parent
            elif root.suffix.lower() == ".zip":
                root = root.parent
            else:
                root = root.parent

        manifests = sorted(root.glob("manifest*.json"))
        expected, missing, present = [], [], []
        for m in manifests:
            try:
                man = json.loads(m.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if not isinstance(man, dict) or "data_files" not in man:
                continue
            self._manifest_path = str(m)
            evidence.store_file(self.conn, self.paths.blobs, m,
                                mime="application/json")
            for d in man.get("data_files") or []:
                fn = d.get("filename")
                if not fn:
                    continue
                expected.append(fn)
                (present if (root / fn).exists() else missing).append(fn)
            break

        # Only ever touch zips this export actually named. A Downloads folder
        # can hold a hundred unrelated archives; globbing *.zip there would
        # ingest somebody else's data.
        zips = [root / f for f in present] if expected else []
        if not expected:
            known = ("conversations", "light_metadata", "memories", "projects",
                     "design_chats")
            zips = sorted(z for z in root.glob("*.zip")
                          if z.name.split("-")[0] in known)

        self.stats["export_parts_expected"] = len(expected) or None
        self.stats["export_parts_present"] = len(zips) or None
        self.stats["export_parts_missing"] = missing or None

        if missing and not allow_partial:
            raise SystemExit(
                "export is incomplete - %d of %d parts are missing:\n  %s\n\n"
                "Each export URL is single-use, so a missing part cannot be "
                "re-downloaded from the same manifest; request a fresh export.\n"
                "To ingest what you do have anyway, re-run with --allow-partial "
                "(the gap will be recorded in the manifest, not hidden)."
                % (len(missing), len(expected), "\n  ".join(missing)))

        if not zips:
            return root                      # old shape: already unpacked

        # Unpack into the evidence landing area, never back into the user's
        # folder. The zips themselves are stored as blobs first: they are the
        # artefact that was actually acquired, and they stay byte-exact even if
        # the extraction logic is later found to be wrong and has to be re-run.
        # The landing directory is keyed on the CONTENT of the parts, never on
        # their names. Every Claude export ships the same five filenames, so a
        # name-derived key sends two DIFFERENT accounts' exports to the SAME
        # directory - and because the ".unpacked" markers are already sitting
        # there, the second export is silently not extracted at all and the
        # first account's files are read in its place. Two accounts, one folder,
        # no error, no warning, and an ingest that confidently reports the wrong
        # identity. Hash first, then choose where to unpack.
        for z in zips:
            digest, _ = evidence.store_file(self.conn, self.paths.blobs, z,
                                            mime="application/zip")
            self._part_hashes[z.name] = digest
        tag = evidence.hash_bytes(
            "|".join("%s:%s" % (n, self._part_hashes[n])
                     for n in sorted(self._part_hashes)).encode())[:12]
        work = Path(self.paths.landing) / ("claude-export-%s" % tag)
        work.mkdir(parents=True, exist_ok=True)
        for z in zips:
            # the marker carries the part's own hash, so a re-download with
            # different content re-extracts instead of being skipped
            marker = work / (".unpacked-%s-%s" % (z.name, self._part_hashes[z.name][:12]))
            if marker.exists():
                continue
            try:
                with zipfile.ZipFile(z) as zf:
                    for info in zf.infolist():
                        name = info.filename.replace("\\", "/")
                        # refuse absolute paths and ../ traversal
                        if name.startswith("/") or ".." in Path(name).parts:
                            self.stats.setdefault("unsafe_zip_entries", 0)
                            self.stats["unsafe_zip_entries"] += 1
                            continue
                        zf.extract(info, str(work))
            except zipfile.BadZipFile as e:
                raise SystemExit(
                    "%s is not a readable zip (%s). The download was probably "
                    "truncated - and its URL is single-use, so this part needs a "
                    "fresh export request." % (z.name, e))
            marker.write_text("unpacked from %s\n" % z, encoding="utf-8")

        # What arrived, and the fingerprint of each part. This is what makes a
        # later "was the export complete?" answerable instead of a memory.
        audit(self.conn, "ingestion", "export_parts_acquired",
              "OK" if not missing else "PARTIAL",
              target=str(root),
              detail={"manifest": self._manifest_path,
                      "expected": expected or None,
                      "missing": missing or None,
                      "part_hashes": self._part_hashes,
                      "unpacked_to": str(work)})
        self.conn.commit()
        return work

    @staticmethod
    def _find_one(root, *patterns):
        for pat in patterns:
            hits = sorted(root.rglob(pat))
            if hits:
                # shallowest match wins - a top-level users.json beats one
                # nested inside a project folder
                hits.sort(key=lambda p: (len(p.parts), str(p)))
                return hits[0]
        return None

    # -- discovery ----------------------------------------------------------
    def discover(self, target):
        root = self._resolve_export(target, allow_partial=self.allow_partial)
        conv_file = self._find_one(root, "conversations.json", "conversations*.json")
        if conv_file is None:
            raise SystemExit(
                "no conversations file found under %s\n"
                "Expected either an unpacked export folder or the zip set the "
                "export manifest names." % root)

        # -- evidence: the export itself, content-addressed and never rewritten
        self._export_hash, _ = evidence.store_file(
            self.conn, self.paths.blobs, conv_file, mime="application/json")
        self._export_path = str(conv_file)

        # -- account (SOW 45/46: explicit, never inferred, never merged)
        users_file = self._find_one(root, "users.json", "user*.json")
        acct_uuid = None; acct_label = None
        if users_file is not None and users_file.exists():
            evidence.store_file(self.conn, self.paths.blobs, users_file,
                                mime="application/json")
            u = json.loads(users_file.read_text(encoding="utf-8"))
            if u:
                acct_uuid = u[0].get("uuid")
                acct_label = "%s <%s>" % (u[0].get("full_name") or "?",
                                          u[0].get("email_address") or "?")
        convs = json.loads(conv_file.read_text(encoding="utf-8"))
        if not acct_uuid and convs:
            acct_uuid = (convs[0].get("account") or {}).get("uuid")
        if not self.account_id and acct_uuid:
            self.account_id = self.ensure_account(
                acct_uuid, discovered_via="export:users.json",
                display_name=acct_label, verified=True)

        if self.account_id is None:
            raise SystemExit(
                "cannot determine which Claude account this export belongs to.\n"
                "users.json is missing and no conversation carries an account uuid.\n"
                "Ingesting it anyway would put it under an unknown account and risk\n"
                "merging it with another one (SOW 45/46). Pass --account explicitly\n"
                "if you know which account id this is.")
        # Only now is it safe to build the resume map: it is scoped per account.
        self._prefetch()

        dates = sorted(c["created_at"][:10] for c in convs if c.get("created_at"))
        self.stats["export_generation"] = "%s..%s (%d conversations)" % (
            dates[0] if dates else "?", dates[-1] if dates else "?", len(convs))

        # -- projects become workspaces; their docs become objects
        pdirs = [d for d in root.rglob("projects") if d.is_dir()]
        projects = []
        for pdir in pdirs:
            for pf in sorted(pdir.glob("*.json")):
                evidence.store_file(self.conn, self.paths.blobs, pf,
                                    mime="application/json")
                try:
                    projects.append((pf, json.loads(pf.read_text(encoding="utf-8"))))
                except ValueError:
                    continue
        for pf, pj in projects:
            wid = self.ensure_workspace(
                self.account_id, "project", pj.get("uuid") or pf.stem,
                display_name=pj.get("name"),
                permission_level="private" if pj.get("is_private") else "shared")
            self.stats["projects_registered"] += 1
            yield {"kind": "project", "project": pj, "workspace_id": wid,
                   "path": str(pf)}
            for d in (pj.get("docs") or []):
                yield {"kind": "project_doc", "doc": d, "project": pj,
                       "workspace_id": wid, "path": str(pf)}

        # -- assistant memory (synthesised, clearly labelled as such)
        # The newer export shape moves this to memories/<account-uuid>.json.
        # Globbing "memories*.json" does NOT match that, and the failure mode is
        # silent: the run reports success and every memory document is missing.
        # Look for the account's own file first, and refuse a file belonging to
        # a different account outright (SOW 46).
        mem_file = fallback = None
        for cand in sorted(root.rglob("memories/*.json")):
            stem = cand.stem
            if acct_uuid and stem == acct_uuid:
                mem_file = cand                       # ours, by name
            elif acct_uuid and len(stem) == len(acct_uuid) and stem.count("-") == 4:
                # a memory file named for a DIFFERENT account uuid. Do not read
                # it, and do not pass over it in silence - count it, so a shared
                # or mis-assembled export is visible in the run's own output.
                self.stats["foreign_memory_files_skipped"] += 1
            elif fallback is None:
                fallback = cand
        mem_file = mem_file or fallback
        if mem_file is None:
            mem_file = self._find_one(root, "memories.json", "memories*.json")
        if mem_file is not None and mem_file.exists():
            evidence.store_file(self.conn, self.paths.blobs, mem_file,
                                mime="application/json")
            try:
                mem = json.loads(mem_file.read_text(encoding="utf-8"))
            except ValueError:
                mem = []
            # The memory payload is not one blob: it is a narrative memory, a
            # per-project memory map, and a set of structured memory FILES that
            # each carry their own path and updated_at. Collapsing them would
            # throw away the only timestamps the assistant memory has.
            for i, entry in enumerate(mem if isinstance(mem, list) else [mem]):
                for k, v in (entry or {}).items():
                    if k == "account_uuid" or not v:
                        continue
                    if k == "memory_files" and isinstance(v, list):
                        for d in v:
                            if isinstance(d, dict) and d.get("content"):
                                yield {"kind": "memory_file", "doc": d,
                                       "path": str(mem_file)}
                        continue
                    if isinstance(v, dict):
                        for kk, vv in v.items():
                            if isinstance(vv, str) and vv.strip():
                                yield {"kind": "memory", "slot": "%s/%s" % (k, kk),
                                       "index": i, "text": vv, "path": str(mem_file)}
                            elif vv:
                                yield {"kind": "memory", "slot": "%s/%s" % (k, kk),
                                       "index": i, "text": jdump(vv),
                                       "path": str(mem_file)}
                        continue
                    if isinstance(v, str) and v.strip():
                        yield {"kind": "memory", "slot": k, "index": i, "text": v,
                               "path": str(mem_file)}

        # -- login history. New in the 2026-09 export shape, and not a
        # curiosity: it is the only first-party record of WHEN and FROM WHERE
        # this account was accessed. That is the evidence a "was this really
        # me?" question needs, and it is answerable only if it is kept.
        login_file = self._find_one(root, "login_history.json", "login*history*.json")
        if login_file is not None and login_file.exists():
            evidence.store_file(self.conn, self.paths.blobs, login_file,
                                mime="application/json")
            try:
                lh = json.loads(login_file.read_text(encoding="utf-8"))
            except ValueError:
                lh = {}
            for ev in (lh.get("login_events") or []):
                if acct_uuid and ev.get("account_uuid") not in (None, acct_uuid):
                    self.stats["foreign_login_events_skipped"] += 1
                    continue
                yield {"kind": "login", "event": ev, "path": str(login_file)}

        # -- conversations, then their messages, then their attachments
        for c in convs:
            yield {"kind": "conversation", "conv": c}
            for m in (c.get("chat_messages") or []):
                yield {"kind": "message", "conv": c, "msg": m}
                for j, at in enumerate(m.get("attachments") or []):
                    yield {"kind": "attachment", "conv": c, "msg": m,
                           "att": at, "index": j}
                for f in (m.get("files") or []):
                    yield {"kind": "file_ref", "conv": c, "msg": m, "file": f}

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, item, job_id):
        k = item["kind"]
        return getattr(self, "_do_" + k)(item, job_id)

    def _do_project(self, item, job_id):
        p = item["project"]
        nid = "project:%s" % p.get("uuid")
        body = "\n\n".join(x for x in [
            p.get("description") or "",
            ("Custom instructions:\n" + p["prompt_template"]) if p.get("prompt_template") else "",
        ] if x.strip()) or None
        out = self._ingest(native_id=nid, object_class="Project", body=body,
                           title=p.get("name") or nid, job_id=job_id,
                           created=p.get("created_at"), modified=p.get("updated_at"),
                           authority="DIRECT PROJECT ARTIFACT",
                           memory_type="REFERENCE",
                           meta={"is_private": p.get("is_private"),
                                 "is_starter_project": p.get("is_starter_project"),
                                 "docs": len(p.get("docs") or []),
                                 "export_file": item["path"]})
        return out

    def _do_project_doc(self, item, job_id):
        d = item["doc"]; p = item["project"]
        nid = "project_doc:%s" % (d.get("uuid") or d.get("filename"))
        out = self._ingest(native_id=nid, object_class="ProjectDocument",
                           body=d.get("content"), title=d.get("filename") or nid,
                           job_id=job_id, created=d.get("created_at"),
                           authority="DIRECT PROJECT ARTIFACT",
                           meta={"project": p.get("name"),
                                 "project_uuid": p.get("uuid"),
                                 "export_file": item["path"]})
        self._link(nid, "project:%s" % p.get("uuid"), "PART_OF", job_id)
        self.stats["project_documents"] += 1
        return out

    def _do_memory(self, item, job_id):
        nid = "memory:%s:%d" % (item["slot"], item["index"])
        out = self._ingest(native_id=nid, object_class="AssistantMemory",
                           body=item["text"], title="Assistant memory: %s" % item["slot"],
                           job_id=job_id, authority="AI-GENERATED",
                           memory_type="REFERENCE",
                           meta={"slot": item["slot"], "export_file": item["path"]})
        oid = self._oid.get(nid)
        if oid and out != "unchanged":
            # SOW 16: this was synthesised BY a model ABOUT the user. It is not
            # something he said, and must never be retrievable as if it were.
            self.conn.execute(
                "UPDATE object SET knowledge_state='SYNTHESIZED',"
                " decay_status='UNVERIFIED' WHERE object_id=?", (oid,))
        self.stats["assistant_memories"] += 1
        return out

    def _do_memory_file(self, item, job_id):
        """One structured assistant-memory document. Its `path` is the stable
        identity (that is what the memory system itself keys on) and its
        updated_at is the only mtime this class of knowledge ever gets."""
        d = item["doc"]
        nid = "memory_file:%s" % d.get("path")
        out = self._ingest(native_id=nid, object_class="AssistantMemory",
                           body=d.get("content"),
                           title="Assistant memory file %s" % d.get("path"),
                           job_id=job_id, modified=d.get("updated_at"),
                           authority="AI-GENERATED", memory_type="REFERENCE",
                           meta={"memory_path": d.get("path"),
                                 "export_file": item["path"]})
        oid = self._oid.get(nid)
        if oid and out != "unchanged":
            self.conn.execute(
                "UPDATE object SET knowledge_state='SYNTHESIZED',"
                " decay_status='UNVERIFIED' WHERE object_id=?", (oid,))
        self.stats["assistant_memories"] += 1
        return out

    def _do_login(self, item, job_id):
        ev = item["event"]
        ts = ev.get("timestamp")
        ua = ev.get("user_agent") or {}
        loc = ev.get("location_info") or {}
        where = ", ".join(x for x in [loc.get("city"), loc.get("region"),
                                      loc.get("country")] if x) or "unknown location"
        device = " ".join(x for x in [
            ua.get("browser_family"), ua.get("browser_version"),
            "on", ua.get("os_family"), ua.get("os_version")] if x).strip()
        body = ("Sign-in to Claude.ai\n"
                "when   : %s\n"
                "method : %s\n"
                "from   : %s (%s)\n"
                "device : %s\n" % (ts, ev.get("method") or "unknown",
                                    ev.get("ip_address") or "unknown ip",
                                    where, device or "unknown device"))
        out = self._ingest(
            native_id="login:%s" % ts, object_class="LoginEvent",
            body=body, title="Sign-in %s from %s" % ((ts or "?")[:19], where),
            job_id=job_id, created=ts, modified=ts,
            authority="PRIMARY SOURCE", memory_type="OBSERVATION",
            classification="SENSITIVE",     # access records are not ordinary PRIVATE
            meta={"ip_address": ev.get("ip_address"), "method": ev.get("method"),
                  "user_agent": ua, "location": loc, "export_file": item["path"]})
        self.stats["login_events"] += 1
        return out

    def _do_conversation(self, item, job_id):
        c = item["conv"]
        nid = "conversation:%s" % c["uuid"]
        msgs = c.get("chat_messages") or []
        opening = ""
        for m in msgs:
            if m.get("sender") == "human":
                opening = (render_message(m) or "")[:2000]
                break
        head = ["# %s" % (c.get("name") or "(untitled conversation)")]
        if c.get("summary"):
            head.append(c["summary"])
        head.append("%d messages, %s to %s" % (
            len(msgs), (c.get("created_at") or "?")[:10],
            (c.get("updated_at") or "?")[:10]))
        if opening:
            head.append("Opening request:\n%s" % opening)
        out = self._ingest(
            native_id=nid, object_class="Conversation",
            body="\n\n".join(head), title=c.get("name") or nid, job_id=job_id,
            created=c.get("created_at"), modified=c.get("updated_at"),
            authority="PRIMARY SOURCE",
            meta={"message_count": len(msgs), "summary": c.get("summary") or None,
                  "conversation_uuid": c["uuid"]})
        self.stats["conversations"] += 1
        return out

    def _do_message(self, item, job_id):
        m = item["msg"]; c = item["conv"]
        nid = "message:%s" % m["uuid"]
        body = render_message(m)
        if body is None:
            self.stats["empty_messages"] += 1
        sender = m.get("sender") or "unknown"
        title = "%s: %s" % (c.get("name") or "(untitled)",
                            (body or "(empty message)").strip().splitlines()[0][:90])
        out = self._ingest(
            native_id=nid, object_class="Message", body=body, title=title,
            job_id=job_id, created=m.get("created_at"),
            modified=m.get("updated_at"),
            authority="PRIMARY SOURCE" if sender == "human" else "AI-GENERATED",
            meta={"sender": sender, "conversation_uuid": c["uuid"],
                  "conversation_name": c.get("name") or None,
                  "parent_message_uuid": m.get("parent_message_uuid"),
                  "block_types": sorted({b.get("type") for b in (m.get("content") or [])}),
                  "attachments": len(m.get("attachments") or []),
                  "files": len(m.get("files") or [])})
        self._link(nid, "conversation:%s" % c["uuid"], "PART_OF", job_id)
        parent = m.get("parent_message_uuid")
        if parent and not parent.startswith("00000000-"):
            self._link(nid, "message:%s" % parent, "REPLIES_TO", job_id)
        self.stats["messages"] += 1
        return out

    def _do_attachment(self, item, job_id):
        at = item["att"]; m = item["msg"]; c = item["conv"]
        nid = "attachment:%s:%d" % (m["uuid"], item["index"])
        name = at.get("file_name") or "(unnamed attachment %d)" % item["index"]
        out = self._ingest(
            native_id=nid, object_class="Attachment",
            body=at.get("extracted_content"), title=name, job_id=job_id,
            created=m.get("created_at"),
            authority="UNKNOWN", license="THIRD_PARTY",
            meta={"file_size": at.get("file_size"), "file_type": at.get("file_type"),
                  "message_uuid": m["uuid"], "conversation_uuid": c["uuid"],
                  "extraction": "text extracted by the platform at upload time;"
                                " the original binary is not in the export"})
        self._link(nid, "message:%s" % m["uuid"], "ATTACHED_TO", job_id)
        self.stats["attachments"] += 1
        return out

    def _do_file_ref(self, item, job_id):
        """SOW 107: the export names uploaded files but does not carry their
        bytes. Record the reference so the gap is visible and countable rather
        than pretending the file was never there."""
        f = item["file"]; m = item["msg"]
        nid = "file_ref:%s" % f.get("file_uuid")
        out = self._ingest(
            native_id=nid, object_class="FileReference", body=None,
            title=f.get("file_name") or "(uploaded file, bytes not exported)",
            job_id=job_id, created=m.get("created_at"), authority="UNKNOWN",
            meta={"file_uuid": f.get("file_uuid"), "message_uuid": m["uuid"],
                  "bytes_available": False,
                  "reason": "Claude export contains file references only"})
        self._link(nid, "message:%s" % m["uuid"], "ATTACHED_TO", job_id)
        self.stats["file_references_without_bytes"] += 1
        return out
