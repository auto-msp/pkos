"""ChatGPT / OpenAI export adapter (SOW 110 Phase 15).

OpenAI's export ships `conversations.json`, and its shape is not a list of
messages. Each conversation holds a `mapping`: a dict of node-id -> node, where
every node has a parent and a list of children. It is a TREE, because every
edit and every regenerate forks it. Reading the dict in insertion order and
calling that "the conversation" produces a transcript that includes abandoned
branches interleaved with the real one -- text the person never saw in that
order, presented as though they did.

So this walks the tree from the root and follows the LAST child at each step,
which is the branch the interface leaves you on and the one the conversation
actually ended as. Every other branch is still ingested, as a message with
`on_current_branch: false`, because SOW 5.1 does not delete things -- the
abandoned drafts are real history, they are just not the transcript.

The Claude adapter next door solves the same problem for a different vendor;
they stay separate because the two formats agree on nothing except that they
both contain conversations, and a merged adapter would be a pile of branches.
"""
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids
from ..util import now_iso

ROLE_AUTHORITY = {"user": "DIRECT PROJECT ARTIFACT", "assistant": "UNKNOWN",
                  "system": "UNKNOWN", "tool": "UNKNOWN"}


class ChatgptExportAdapter(BaseAdapter):
    source_id = "SRC-chatgpt"
    vendor = "openai"
    display_name = "ChatGPT export"
    acquisition_method = "export"
    auth_method = "human_download"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"conversations": 0, "messages": 0,
                      "messages_on_current_branch": 0,
                      "messages_on_abandoned_branches": 0,
                      "empty_messages_skipped": 0, "models_seen": {},
                      "nested_zips": 0, "empty_globs": []}
        self._oids = {}

    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "chatgpt adapter requires --identity <the OpenAI account "
                "email>.\nSOW 45/46: account identity is explicit, never "
                "inferred. This store already keeps two Claude accounts "
                "strictly apart; the same rule applies here.")

        root, zips = A.parts(target, "*.zip")
        if zips:
            root = A.unpack(self.conn, self.paths, zips, "chatgpt-export",
                            self.stats)
        convs = A.loud_glob(root, "conversations.json", "ChatGPT conversations",
                            self.stats, required=True)
        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest chatgpt`",
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, "chatgpt", "default", display_name="ChatGPT")

        for f in convs:
            evidence.store_file(self.conn, self.paths.blobs, f,
                                mime="application/json")
            data = A.read_json(f)
            if not isinstance(data, list):
                raise SystemExit(
                    "%s is not a JSON array of conversations. The export "
                    "format has changed; not guessing at it." % f)
            for conv in data:
                self.stats["conversations"] += 1
                yield ("conversation", conv, str(f))
                for node, on_branch in self._walk(conv):
                    yield ("message", (conv, node, on_branch), str(f))

    # -- tree walk ----------------------------------------------------------
    def _walk(self, conv):
        """Yield (node, on_current_branch) for every message in the tree."""
        mapping = conv.get("mapping") or {}
        current = set()
        node_id = conv.get("current_node")
        # Walk UP from current_node: that is the branch the user was left on,
        # and it is exact, unlike guessing downwards from the root.
        guard = 0
        while node_id and node_id in mapping and guard < 100000:
            guard += 1
            current.add(node_id)
            node_id = (mapping[node_id] or {}).get("parent")
        if not current:      # older exports omit current_node
            nid = self._root_of(mapping)
            while nid and guard < 100000:
                guard += 1
                current.add(nid)
                kids = (mapping.get(nid) or {}).get("children") or []
                nid = kids[-1] if kids else None
        for nid, node in mapping.items():
            if not isinstance(node, dict) or not node.get("message"):
                continue
            yield (dict(node, _id=nid), nid in current)

    @staticmethod
    def _root_of(mapping):
        for nid, node in mapping.items():
            if isinstance(node, dict) and not node.get("parent"):
                return nid
        return None

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, item, job_id):
        kind, payload, origin = item
        if kind == "conversation":
            return self._conversation(payload, origin, job_id)
        return self._message(payload, origin, job_id)

    def _conversation(self, conv, origin, job_id):
        cid = conv.get("conversation_id") or conv.get("id")
        if not cid:
            raise ValueError("conversation has no id")
        title = conv.get("title") or "(untitled conversation)"
        native = "chatgpt:conversation:%s" % cid
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Conversation",
            content_hash=evidence.hash_bytes(
                ("%s|%s|%s" % (cid, title, conv.get("update_time"))).encode()),
            title=title[:500], body=None,
            source_created_at=A.ts_iso(conv.get("create_time")),
            source_modified_at=A.ts_iso(conv.get("update_time")),
            job_id=job_id,
            raw_metadata={"conversation_id": cid,
                          "node_count": len(conv.get("mapping") or {}),
                          "is_archived": conv.get("is_archived"),
                          "default_model": conv.get("default_model_slug"),
                          "source_file": origin},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="OBSERVATION", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        return outcome

    def _message(self, payload, origin, job_id):
        conv, node, on_branch = payload
        msg = node["message"]
        author = (msg.get("author") or {}).get("role") or "unknown"
        parts = ((msg.get("content") or {}).get("parts")) or []
        text = "\n".join(p for p in parts if isinstance(p, str)).strip()
        if not text:
            # Tool calls and image parts have no text. Skipping them silently
            # would make the message count wrong, so it is counted.
            self.stats["empty_messages_skipped"] += 1
        self.stats["messages"] += 1
        if on_branch:
            self.stats["messages_on_current_branch"] += 1
        else:
            self.stats["messages_on_abandoned_branches"] += 1
        model = (msg.get("metadata") or {}).get("model_slug")
        if model:
            self.stats["models_seen"][model] = \
                self.stats["models_seen"].get(model, 0) + 1

        cid = conv.get("conversation_id") or conv.get("id")
        native = "chatgpt:message:%s" % msg.get("id", node["_id"])
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Message",
            content_hash=evidence.hash_bytes(("%s|%s" % (author, text)).encode()),
            title=("%s: %s" % (author, text[:120].replace("\n", " ")))[:500],
            body=text or None,
            source_created_at=A.ts_iso(msg.get("create_time")),
            source_modified_at=A.ts_iso(msg.get("update_time")
                                        or msg.get("create_time")),
            job_id=job_id,
            raw_metadata={"role": author, "model": model,
                          "conversation_id": cid,
                          "on_current_branch": on_branch,
                          "branch_note": None if on_branch else
                          "this message is on a branch the conversation moved "
                          "off (an edit or regenerate); it is real history but "
                          "was not part of the final transcript",
                          "parent_node": node.get("parent"),
                          "content_type": (msg.get("content") or {}).get("content_type"),
                          "source_file": origin},
            classification="PRIVATE", license="MY_CONTENT",
            memory_type="OBSERVATION",
            authority=ROLE_AUTHORITY.get(author, "UNKNOWN"),
            actor="job:%s" % job_id)
        self._oids[native] = oid
        parent = self._oids.get("chatgpt:conversation:%s" % cid)
        if parent and parent != oid:
            self.conn.execute(
                "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
                "target_object,relationship_type,confidence,created_at,provenance,"
                "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
                (ids.scoped("REL", 1), oid, parent, "PART_OF", 1.0, now_iso(),
                 "structural: the export's own conversation mapping",
                 "job:%s" % job_id, "PASSED"))
        return outcome
