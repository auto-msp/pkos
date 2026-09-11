"""n8n workflow adapter (SOW 28 secrets, 110 Phase 3 adjacent).

Three n8n instances run across this fleet and not one workflow is in the store.
That is the automation itself -- the actual operating logic of the business,
expressed as nodes and the wires between them. It is also, uniquely among the
sources here, the one most likely to contain live credentials in plain text.

So this adapter does two jobs, and the second one is not optional.

**It reads the graph.** A workflow is not a document; it is nodes plus the
connections between them. Ingesting the JSON as one blob would store the
automation as an opaque string and lose every "this feeds that". Nodes become
objects, connections become FLOWS_TO edges, and the store can then answer "what
touches Mautic?" -- which is the whole reason to have it.

**It refuses to carry secrets.** n8n puts credential *references* in
`node.credentials` (an id and a name, safe), but node `parameters` routinely
hold hard-coded API keys, bearer tokens, basic-auth URLs and webhook secrets
that someone typed in during a hurry. Those are stripped BEFORE anything is
written to the canonical layer, by key name and by the same pattern set
`secrets.py` uses, and what was stripped is recorded by KEY, never by value.
SOW 28 exists for this, and the earlier Airtable ingest proved the store will
happily swallow a token nobody looked at.

A `n8n export:credentials` dump is refused outright. Encrypted or decrypted, a
credentials file has no business in a knowledge store, and the polite version
of this adapter -- ingest it and redact afterwards -- still means the bytes land
in the immutable evidence plane, where nothing can ever remove them.
"""
import json
import re
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids, secrets
from ..util import now_iso

SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|apikey|access[_-]?token|auth[_-]?token|bearer|password|passwd|"
    r"secret|private[_-]?key|client[_-]?secret|webhook[_-]?secret|signature|"
    r"authorization|credential|session[_-]?id|refresh[_-]?token)", re.I)
CRED_MARKERS = ("encryptedData", "oauthTokenData", "credentials_entity")


class N8nAdapter(BaseAdapter):
    source_id = "SRC-n8n"
    vendor = "n8n"
    display_name = "n8n workflow automation"
    acquisition_method = "export"
    auth_method = "none"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"files": 0, "workflows": 0, "nodes": 0, "connections": 0,
                      "active_workflows": 0, "node_types": {},
                      "parameters_redacted_by_key": 0,
                      "parameters_redacted_by_pattern": 0,
                      "redacted_keys": [], "credential_refs": 0,
                      "credential_files_refused": [], "empty_globs": []}
        self._oids = {}
        self._pending = []

    # -- discovery ----------------------------------------------------------
    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "n8n adapter requires --identity <instance host or name>, e.g. "
                "n8n.automsp.us.\nThree n8n instances run on this fleet and "
                "their workflows overlap by name. SOW 45/46: identity is "
                "explicit, never inferred -- otherwise two instances' copies of "
                "'Lead Router' become one object and the store starts lying "
                "about which server runs what.")

        root = Path(target).expanduser().resolve()
        files = [root] if root.is_file() else A.loud_glob(
            root, "*.json", "n8n workflow exports", self.stats, required=True)

        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest n8n`",
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, "n8n_instance", self.identity, display_name=self.identity)

        found = 0
        for f in files:
            raw = f.read_text(encoding="utf-8", errors="replace")
            if any(m in raw for m in CRED_MARKERS):
                self.stats["credential_files_refused"].append(f.name)
                continue
            try:
                data = json.loads(raw)
            except ValueError as e:
                self.stats["empty_globs"].append("%s (not JSON: %s)" % (f.name, e))
                continue
            self.stats["files"] += 1
            evidence.store_file(self.conn, self.paths.blobs, f,
                                mime="application/json")
            for wf in (data if isinstance(data, list) else [data]):
                if not isinstance(wf, dict) or "nodes" not in wf:
                    continue
                found += 1
                self.stats["workflows"] += 1
                if wf.get("active"):
                    self.stats["active_workflows"] += 1
                yield ("workflow", (wf, str(f)), str(f))
                for node in wf.get("nodes") or []:
                    self.stats["nodes"] += 1
                    t = node.get("type", "unknown")
                    self.stats["node_types"][t] = self.stats["node_types"].get(t, 0) + 1
                    yield ("node", (wf, node, str(f)), str(f))

        if self.stats["credential_files_refused"]:
            raise SystemExit(
                "refusing %d file(s) that look like an n8n CREDENTIALS export: "
                "%s\n\nA credentials dump does not belong in a knowledge store. "
                "Encrypted or decrypted, ingesting it writes the bytes into the "
                "immutable evidence plane, where by design nothing can ever "
                "remove them again. Move those files out of the target folder "
                "and re-run; the workflow exports will ingest normally."
                % (len(self.stats["credential_files_refused"]),
                   ", ".join(self.stats["credential_files_refused"])))
        if not found:
            raise SystemExit(
                "no n8n workflows found at %s. Expected JSON with a `nodes` key "
                "-- produce it with `n8n export:workflow --all --output=...` or "
                "Download from the workflow menu." % root)

    # -- redaction ----------------------------------------------------------
    def _clean(self, obj, trail=""):
        """Strip credential material from node parameters before it is stored."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if SENSITIVE_KEY.search(str(k)):
                    self.stats["parameters_redacted_by_key"] += 1
                    if k not in self.stats["redacted_keys"]:
                        self.stats["redacted_keys"].append(k)
                    out[k] = "[REDACTED BY PKOS: parameter name matches a "
                    out[k] += "credential pattern; value never left the export]"
                    continue
                out[k] = self._clean(v, "%s.%s" % (trail, k))
            return out
        if isinstance(obj, list):
            return [self._clean(x, trail) for x in obj]
        if isinstance(obj, str):
            if secrets.scan_body(obj):
                self.stats["parameters_redacted_by_pattern"] += 1
                return ("[REDACTED BY PKOS: value matched a credential pattern "
                        "(%s)]" % ",".join(secrets.scan_body(obj)))
            return obj
        return obj

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, item, job_id):
        kind, payload, _origin = item
        return getattr(self, "_acq_" + kind)(payload, job_id)

    def _acq_workflow(self, payload, job_id):
        wf, src = payload
        wid = str(wf.get("id") or wf.get("versionId") or wf.get("name"))
        nodes = wf.get("nodes") or []
        conns = wf.get("connections") or {}
        n_conn = sum(len(b) for groups in conns.values()
                     for b in groups.values() for b in [b] for b in b)
        self.stats["connections"] += n_conn

        # queue the wiring; node objects may not exist yet
        for src_name, groups in conns.items():
            for _out_type, branches in (groups or {}).items():
                for branch in (branches or []):
                    for c in (branch or []):
                        if isinstance(c, dict) and c.get("node"):
                            self._pending.append((wid, src_name, c["node"]))

        body = "\n".join(
            "%s  [%s]" % (n.get("name"), n.get("type")) for n in nodes)
        native = "n8n:%s:workflow:%s" % (self.identity, wid)
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="Workflow",
            content_hash=evidence.hash_bytes(
                json.dumps(self._clean(wf), sort_keys=True, default=str).encode()),
            title=str(wf.get("name") or wid)[:500], body=body or None,
            source_created_at=A.ts_iso(wf.get("createdAt")),
            source_modified_at=A.ts_iso(wf.get("updatedAt")), job_id=job_id,
            raw_metadata={
                "workflow_id": wid, "instance": self.identity,
                "active": bool(wf.get("active")),
                "node_count": len(nodes), "connection_count": n_conn,
                "tags": [t.get("name") if isinstance(t, dict) else t
                         for t in (wf.get("tags") or [])],
                "node_types": sorted({n.get("type") for n in nodes if n.get("type")}),
                "trigger_nodes": [n.get("name") for n in nodes
                                  if "trigger" in str(n.get("type", "")).lower()
                                  or "webhook" in str(n.get("type", "")).lower()],
                "source_file": src,
                "credentials_policy": "references kept, values never ingested"},
            classification="SENSITIVE", license="MY_CONTENT",
            memory_type="PROCEDURE", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        return outcome

    def _acq_node(self, payload, job_id):
        wf, node, src = payload
        wid = str(wf.get("id") or wf.get("versionId") or wf.get("name"))
        name = node.get("name") or node.get("id") or "(unnamed node)"
        params = self._clean(node.get("parameters") or {})
        creds = node.get("credentials") or {}
        if creds:
            self.stats["credential_refs"] += len(creds)

        body = json.dumps(params, indent=1, ensure_ascii=False, default=str)[:200000]
        native = "n8n:%s:node:%s:%s" % (self.identity, wid, name)
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id=native,
            object_class="WorkflowNode",
            content_hash=evidence.hash_bytes(
                ("%s|%s|%s" % (name, node.get("type"), body)).encode()),
            title=("%s [%s]" % (name, node.get("type", "?")))[:500], body=body,
            job_id=job_id,
            raw_metadata={
                "node_name": name, "node_type": node.get("type"),
                "type_version": node.get("typeVersion"),
                "workflow_id": wid, "instance": self.identity,
                "disabled": bool(node.get("disabled")),
                "position": node.get("position"),
                # references only: an id and a display name, never a value
                "credential_refs": {k: (v or {}).get("name")
                                    for k, v in creds.items()},
                "webhook_id": node.get("webhookId"),
                "source_file": src},
            classification="SENSITIVE", license="MY_CONTENT",
            memory_type="PROCEDURE", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)
        self._oids[native] = oid
        parent = self._oids.get("n8n:%s:workflow:%s" % (self.identity, wid))
        if parent and parent != oid:
            self._edge(oid, parent, "PART_OF",
                       "structural: the node belongs to this workflow", job_id)
        return outcome

    def _edge(self, s, t, rtype, why, job_id):
        self.conn.execute(
            "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
            "target_object,relationship_type,confidence,created_at,provenance,"
            "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
            (ids.scoped("REL", 1), s, t, rtype, 1.0, now_iso(), why,
             "job:%s" % job_id, "PASSED"))

    def run(self, target, limit=None, dry_run=False):
        job_id, res, status = super().run(target, limit=limit, dry_run=dry_run)
        if not dry_run:
            wired = 0
            for wid, a, b in self._pending:
                s = self._oids.get("n8n:%s:node:%s:%s" % (self.identity, wid, a))
                t = self._oids.get("n8n:%s:node:%s:%s" % (self.identity, wid, b))
                if s and t and s != t:
                    self._edge(s, t, "FLOWS_TO",
                               "structural: the workflow's own connection map",
                               job_id)
                    wired += 1
            self.stats["flow_edges_written"] = wired
            self.conn.commit()
        return job_id, res, status
