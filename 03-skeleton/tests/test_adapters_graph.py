"""Obsidian and n8n: the two sources whose value IS their graph.

Both of these can be "successfully" ingested while losing everything that
matters. A vault ingested as loose files keeps every sentence and drops every
link the author drew by hand. A workflow ingested as one JSON blob keeps the
automation as an opaque string and answers no question about what feeds what.
Neither failure raises. So the tests here assert EDGES, not bytes.

The n8n half additionally asserts what must NOT be in the store. n8n
parameters routinely hold hard-coded tokens, and the Airtable ingest earlier in
this project proved the store will swallow a credential nobody looked at and
report a clean run.
"""
import json, shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import Suite, sb, sbj, ingest, q, one            # noqa: E402


def make_vault(d):
    v = d / "vault"; (v / "projects").mkdir(parents=True)
    (v / "daily").mkdir()
    (v / ".obsidian").mkdir()
    (v / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")

    (v / "PKOS.md").write_text(
        "---\n"
        "title: Personal Knowledge OS\n"
        "tags:\n"
        "  - architecture\n"
        "  - secondbrain\n"
        "status: active\n"
        "date: 2026-09-01\n"
        "---\n"
        "# PKOS\n\n"
        "Depends on [[Perceptor]] and links to [[projects/Second Brain|the build]].\n"
        "Also embeds ![[diagram.png]].\n"
        "Tagged #architecture and #ops/infra inline.\n\n"
        "```python\n"
        "# not a tag: [[NotALink]] and #notatag live in a fence\n"
        "```\n", encoding="utf-8")
    (v / "Perceptor.md").write_text(
        "# Perceptor\n\nThe master. Back to [[PKOS]].\n#ops/infra\n", encoding="utf-8")
    (v / "projects" / "Second Brain.md").write_text(
        "# Second Brain\n\nSee [[PKOS]] and [[Ghost Note]] which does not exist.\n",
        encoding="utf-8")
    # deliberate name collision: two files called "Ambiguous"
    (v / "Ambiguous.md").write_text("# A\n[[PKOS]]\n", encoding="utf-8")
    (v / "projects" / "Ambiguous.md").write_text("# B\n", encoding="utf-8")
    (v / "Collide.md").write_text("Links to [[Ambiguous]].\n", encoding="utf-8")
    # A vault with "Use [[Wikilinks]]" OFF writes portable markdown links.
    # Obsidian supports both; an adapter that reads only [[...]] reports such
    # a vault as unlinked and is believed, because nothing errors.
    (v / "Portable.md").write_text(
        "# Portable\n\nLinks to [Perceptor](Perceptor.md) and "
        "[the build](projects/Second%20Brain.md).\n"
        "Embeds ![diagram](diagram.png).\n"
        "External [docs](https://example.com) is not a vault link.\n"
        "Colours here are not tags: #ef4444 #f8fafc #FFFFFF\n",
        encoding="utf-8")
    (v / "daily" / "2026-09-11.md").write_text(
        "# Today\n\nShipped part 2. [[PKOS]]\n", encoding="utf-8")
    (v / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (v / "board.canvas").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    return v


def make_n8n(d):
    n = d / "n8n"; n.mkdir(parents=True)
    wf = {
        "id": "wf-42", "name": "Lead Router", "active": True,
        "createdAt": "2026-05-01T10:00:00.000Z",
        "updatedAt": "2026-08-20T12:00:00.000Z",
        "tags": [{"name": "outbound"}],
        "nodes": [
            {"id": "n1", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 1, "position": [0, 0], "webhookId": "abc",
             "parameters": {"path": "lead-in", "httpMethod": "POST"}},
            {"id": "n2", "name": "Enrich", "type": "n8n-nodes-base.httpRequest",
             "typeVersion": 3, "position": [200, 0],
             "credentials": {"httpHeaderAuth": {"id": "7", "name": "Clay key"}},
             "parameters": {
                 "url": "https://api.clay.com/v1/enrich",
                 "apiKey": "live_9f8e7d6c5b4a39281706fedcba098765",
                 "headerParameters": {"parameters": [
                     {"name": "Authorization",
                      "value": "Bearer eyJhbGciOiJIUzI1NiJ9.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}}},
            {"id": "n3", "name": "Mautic", "type": "n8n-nodes-base.mautic",
             "typeVersion": 1, "position": [400, 0],
             "parameters": {"resource": "contact", "operation": "create"}},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Enrich", "type": "main", "index": 0}]]},
            "Enrich":  {"main": [[{"node": "Mautic", "type": "main", "index": 0}]]},
        },
    }
    (n / "workflows.json").write_text(json.dumps([wf]), encoding="utf-8")
    return n


def main():
    s = Suite("GRAPH-ADAPTER")
    tmp = Path(tempfile.mkdtemp(prefix="pkos-graph-"))
    root = tmp / "store"
    sb(root, "init")
    fx = tmp / "fx"; fx.mkdir()

    # ------------------------------------------------------------ Obsidian
    print("\nOBSIDIAN VAULT")
    v = make_vault(fx)
    d, r = ingest(root, "obsidian", v, "--identity", "automsp-vault")
    s.check("ingest completes", d and d["status"] == "COMPLETED",
            (r.stdout + r.stderr)[-400:] if not d else "")
    st = (d or {}).get("adapter_stats", {})
    s.check("8 notes, 1 canvas, 1 attachment",
            (st.get("notes"), st.get("canvases"), st.get("attachments")) == (8, 1, 1),
            "%s" % [st.get("notes"), st.get("canvases"), st.get("attachments")])
    s.check(".obsidian config directory not ingested as content",
            one(root, "SELECT COUNT(*) FROM source_object"
                      " WHERE native_id LIKE '%.obsidian%'") == 0)

    s.check("wikilinks became real edges", st.get("links_resolved", 0) >= 4,
            "resolved=%s of %s found" % (st.get("links_resolved"),
                                         st.get("wikilinks_found")))
    # BOTH embed syntaxes - ![[diagram.png]] and ![alt](diagram.png) - must
    # land on the same attachment object. Two notes embed it, so two edges.
    s.check("both embed syntaxes resolve to the same FILE, typed EMBEDS",
            one(root, "SELECT COUNT(*) FROM relationship r JOIN object o"
                      " ON o.object_id=r.target_object"
                      " WHERE r.relationship_type='EMBEDS'"
                      " AND o.title='diagram'") == 2,
            "embeds found=%s" % st.get("embeds"))
    s.check("and they came from two different notes",
            one(root, "SELECT COUNT(DISTINCT r.source_object) FROM relationship r"
                      " JOIN object o ON o.object_id=r.target_object"
                      " WHERE r.relationship_type='EMBEDS' AND o.title='diagram'") == 2)
    s.check("a path-qualified link [[folder/Note]] resolves too",
            one(root, "SELECT COUNT(*) FROM relationship r"
                      " JOIN object src ON src.object_id=r.source_object"
                      " JOIN object tgt ON tgt.object_id=r.target_object"
                      " WHERE src.title='Personal Knowledge OS'"
                      " AND tgt.title='Second Brain'") == 1)
    s.check("a link to a note that does not exist is counted, not dropped "
            "silently", st.get("links_to_missing_notes") == 1,
            "got %s" % st.get("links_to_missing_notes"))
    s.check("an ambiguous link is refused rather than guessed",
            st.get("ambiguous_links") == 1 and st.get("name_collisions") == 1,
            "ambiguous=%s collisions=%s" % (st.get("ambiguous_links"),
                                            st.get("name_collisions")))

    meta = json.loads(one(root, "SELECT raw_metadata FROM source_object"
                                " WHERE native_id='obsidian:PKOS.md'"))
    s.check("YAML frontmatter parsed into real fields",
            meta["frontmatter"].get("status") == "active"
            and "architecture" in (meta["frontmatter"].get("tags") or []),
            "fm=%s" % meta["frontmatter"])
    s.check("frontmatter title wins over the filename",
            one(root, "SELECT COUNT(*) FROM object"
                      " WHERE title='Personal Knowledge OS'") == 1)
    s.check("inline and frontmatter tags merged",
            set(meta["tags"]) >= {"architecture", "ops/infra", "secondbrain"},
            "tags=%s" % meta["tags"])
    s.check("a link inside a code fence is NOT a link",
            "NotALink" not in meta["wikilinks"], "links=%s" % meta["wikilinks"])
    s.check("a #hash inside a code fence is NOT a tag",
            "notatag" not in meta["tags"], "tags=%s" % meta["tags"])

    daily = json.loads(one(root, "SELECT raw_metadata FROM source_object"
                                 " WHERE native_id='obsidian:daily/2026-09-11.md'"))
    s.check("a daily note is dated from its filename",
            daily["is_daily_note"] and (one(
                root, "SELECT source_created_at FROM source_object"
                      " WHERE native_id='obsidian:daily/2026-09-11.md'") or ""
                ).startswith("2026-09-11"))

    print("\n  portable markdown links, hex colours, parser versioning")
    s.check("markdown links were read as links",
            st.get("markdown_links_found", 0) >= 3,
            "got %s" % st.get("markdown_links_found"))
    s.check("an external https link is not counted as a vault link",
            st.get("external_links", 0) >= 1, "got %s" % st.get("external_links"))
    pm = json.loads(one(root, "SELECT raw_metadata FROM source_object"
                              " WHERE native_id='obsidian:Portable.md'"))
    s.check("CSS hex colours are NOT tags",
            not any(t.lower() in ("ef4444", "f8fafc", "ffffff") for t in pm["tags"]),
            "tags=%s" % pm["tags"])
    s.check("a markdown link resolved to a real edge",
            one(root, "SELECT COUNT(*) FROM relationship r"
                      " JOIN object src ON src.object_id=r.source_object"
                      " JOIN object tgt ON tgt.object_id=r.target_object"
                      " WHERE src.title='Portable' AND tgt.title='Perceptor'") == 1)

    d2, _ = ingest(root, "obsidian", v, "--identity", "automsp-vault")
    s.check("re-ingest of an unchanged vault creates nothing",
            (d2 or {}).get("created") == 0 and (d2 or {}).get("unchanged", 0) > 0,
            "created=%s" % (d2 or {}).get("created"))

    # ---------------------------------------------------------------- n8n
    print("\nN8N WORKFLOWS")
    n = make_n8n(fx)
    d, r = ingest(root, "n8n", n, "--identity", "n8n.automsp.us")
    s.check("ingest completes", d and d["status"] == "COMPLETED",
            (r.stdout + r.stderr)[-400:] if not d else "")
    st = (d or {}).get("adapter_stats", {})
    s.check("1 workflow, 3 nodes", st.get("workflows") == 1 and st.get("nodes") == 3,
            "%s / %s" % (st.get("workflows"), st.get("nodes")))
    s.check("the wiring became FLOWS_TO edges, not a JSON string",
            st.get("flow_edges_written") == 2,
            "got %s" % st.get("flow_edges_written"))
    s.check("nodes are PART_OF their workflow",
            one(root, "SELECT COUNT(*) FROM relationship r JOIN object o"
                      " ON o.object_id=r.target_object"
                      " WHERE r.relationship_type='PART_OF'"
                      " AND o.object_class='Workflow'") == 3)

    print("\n  the part that matters: no credential reaches the store")
    leaked = one(root, "SELECT COUNT(*) FROM object_version"
                       " WHERE body LIKE '%live_9f8e7d6c%'"
                       "    OR body LIKE '%eyJhbGciOiJIUzI1NiJ9%'")
    s.check("the hard-coded API key and bearer token are NOT in any body",
            leaked == 0, "leaked=%s" % leaked)
    s.check("redaction happened by key name and by pattern",
            st.get("parameters_redacted_by_key", 0) >= 1
            and st.get("parameters_redacted_by_pattern", 0) >= 1,
            "by_key=%s by_pattern=%s" % (st.get("parameters_redacted_by_key"),
                                         st.get("parameters_redacted_by_pattern")))
    s.check("what was redacted is recorded by KEY, never by value",
            "apiKey" in (st.get("redacted_keys") or []),
            "keys=%s" % st.get("redacted_keys"))
    s.check("the credential REFERENCE is kept (it is not a secret)",
            st.get("credential_refs") == 1
            and "Clay key" in (one(root, "SELECT raw_metadata FROM source_object"
                                         " WHERE native_id LIKE '%node:wf-42:Enrich'") or ""))
    s.check("useful non-secret parameters survive redaction",
            "lead-in" in (one(root, "SELECT v.body FROM object o JOIN object_version v"
                                    " ON o.current_version=v.version_id"
                                    " WHERE o.title LIKE 'Webhook%'") or ""))

    print("\n  a credentials export is refused outright")
    bad = fx / "n8n-creds"; bad.mkdir()
    (bad / "credentials.json").write_text(json.dumps(
        [{"id": "7", "name": "Clay key", "type": "httpHeaderAuth",
          "encryptedData": "U2FsdGVkX1+abcdef=="}]), encoding="utf-8")
    rc = sb(root, "ingest", "n8n", str(bad), "--identity", "n8n.automsp.us")
    blob = (rc.stdout + rc.stderr).lower()
    s.check("credentials file refused with the reason named",
            rc.returncode != 0 and "credential" in blob and "evidence plane" in blob,
            "exit=%d" % rc.returncode)
    s.check("and nothing from it was written",
            one(root, "SELECT COUNT(*) FROM evidence_blob"
                      " WHERE original_filename='credentials.json'") == 0)

    # ------------------------------------ a vault is not a filesystem
    # The first real ingest pulled 21,204 .js, 9,814 source maps and 3,626
    # .pyc into an append-only evidence plane, because this adapter skipped
    # only Obsidian's metadata folders while the filesystem adapter has
    # carried SOW 75's exclusion lists since Phase 6. A vault containing a
    # code project is normal; storing that project's node_modules as personal
    # knowledge is not, and evidence cannot be un-written.
    print("\nSOW 75 EXCLUSIONS APPLY TO VAULTS TOO")
    cv = fx / "code-vault"
    (cv / "notes").mkdir(parents=True)
    (cv / "app" / "node_modules" / "react").mkdir(parents=True)
    (cv / "app" / "dist").mkdir(parents=True)
    (cv / "notes" / "Real.md").write_text(
        "# Real\n\nSee [Other](Other.md).\n#MSP\n", encoding="utf-8")
    (cv / "notes" / "Other.md").write_text("# Other\n", encoding="utf-8")
    (cv / "pic.png").write_bytes(b"\x89PNGfake")
    for i in range(40):
        (cv / "app" / "node_modules" / "react" / ("m%d.js" % i)).write_text(
            "module.exports=%d" % i, encoding="utf-8")
    for i in range(15):
        (cv / "app" / "dist" / ("b%d.js.map" % i)).write_text("{}", encoding="utf-8")
    (cv / "app" / "main.py").write_text("print(1)\n", encoding="utf-8")
    (cv / "app" / "main.pyc").write_bytes(b"fakebytecode")

    dcv, _ = ingest(root, "obsidian", cv, "--identity", "code-vault")
    stv = (dcv or {}).get("adapter_stats", {})
    s.check("58 files on disk, only the 3 knowledge files ingested",
            dcv and dcv["discovered"] == 3,
            "discovered=%s" % (dcv or {}).get("discovered"))
    s.check("node_modules and dist were skipped wholesale",
            stv.get("skipped_excluded_dirs", 0) >= 55,
            "got %s" % stv.get("skipped_excluded_dirs"))
    s.check("loose .py and .pyc excluded by extension",
            stv.get("skipped_code_files") == 2
            and set(stv.get("skipped_by_extension", {})) == {".py", ".pyc"},
            "%s" % stv.get("skipped_by_extension"))
    s.check("no build artefact reached the evidence plane",
            one(root, "SELECT COUNT(*) FROM evidence_blob"
                      " WHERE original_filename LIKE '%.js'"
                      "    OR original_filename LIKE '%.map'"
                      "    OR original_filename LIKE '%.pyc'") == 0)
    s.check("and the real notes still linked to each other",
            stv.get("links_resolved", 0) >= 1,
            "resolved=%s" % stv.get("links_resolved"))

    # ------------------------------------------- placeholders vs secrets
    # The first real scan of the live store returned 370 findings across
    # 39,766 objects. Reading them showed the list was two populations mixed
    # together: live third-party keys, and documentation that merely LOOKS
    # like keys - `postgresql://user:pass@localhost`, `api_key=YOUR_KEY_HERE`.
    # A finding list nobody can read is a finding list nobody acts on, so the
    # distinction is load-bearing and pinned here.
    print("\nPLACEHOLDERS ARE NOT SECRETS")
    from secondbrain import secrets as S
    for text, expect_secret, why in [
        ("postgresql://your_user:your_password@your_db_host", False, "docs template"),
        ("postgresql://user:pass@localhost:5432/churn", False, "generic pair"),
        ("postgresql://postgres:postgres@postgres:5432/tax", False, "compose default"),
        ("DATABASE_URL: postgresql://wf:${DB_PASSWORD}@db:5432/x", False, "env var"),
        ("?apiKey=YOUR_API_KEY_HERE&number=1", False, "placeholder value"),
        ("[w95](https://github.com/w95/awesome-claude)", False, "markdown link"),
        ("NOTION_API_KEY=ntn_590212562958bjcIgpZpmVFpQwErTyUiOpAsDfGh", True, "live notion token"),
        ("postgresql://postgres.abc:Rx8kLm2QpVn4Zdli1@db.xyz.supabase.co:5432/postgres", True, "live connection string"),
    ]:
        got = bool(S.scan_body(text))
        s.check("%-22s %s" % (why, "-> secret" if expect_secret else "-> ignored"),
                got == expect_secret, "" if got == expect_secret else "got %s" % got)

    print("\nSURGICAL REDACTION KEEPS THE DOCUMENT")
    doc = ("# Deploy notes\nRelay on Ratchet behind Caddy.\n"
           "remote.sendgrid.auth.secret = \"SG.ONQabcdefghijklmnopqrst."
           "uvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVW\"\n"
           "Restart with: systemctl restart stalwart\n"
           "Example for docs: postgresql://user:pass@localhost/db\n")
    spans = S.scan_spans(doc)
    s.check("exactly one span is redactable", len(spans) == 1,
            "spans=%d" % len(spans))
    out, last = [], 0
    for a, b, k in spans:
        out.append(doc[last:a]); out.append("[REDACTED:%s]" % k); last = b
    out.append(doc[last:])
    red = "".join(out)
    s.check("the key is gone", "SG.ONQ" not in red)
    s.check("every other line survives",
            "systemctl restart stalwart" in red and "Relay on Ratchet" in red
            and "postgresql://user:pass@localhost/db" in red,
            "len %d -> %d" % (len(doc), len(red)))

    # --------------------------------- redaction must reach the DERIVED plane
    # Redaction rewrites canonical bodies. The FTS index was built from the
    # OLD bodies, so until it is rebuilt it still serves every secret that was
    # just removed - and `no_secret_values_in_bodies` cannot see that, because
    # it only reads bodies. Canonical spotless, validate green, index leaking.
    # Exactly the silent shape this project keeps hitting, so it gets a test.
    print("\nREDACTION REACHES THE DERIVED PLANE")
    leak = fx / "leak"; leak.mkdir()
    (leak / "cfg.md").write_text(
        "# service config\nNOTION_API_KEY=ntn_590212562958bjcIgpZpmVFpQwErTyUiOpAsDfGh\n"
        "the rest of this document is ordinary prose worth keeping\n",
        encoding="utf-8")
    ingest(root, "filesystem", leak)
    sb(root, "rebuild-index", "--quiet")
    pre, _ = sbj(root, "search", "ntn", "--limit", "3")
    s.check("before redaction the index really does serve the secret",
            pre is not None and len(pre.get("results", [])) >= 1,
            "hits=%s" % (len(pre.get("results", [])) if pre else "n/a"))

    sb(root, "secrets", "--redact")
    v3, _ = sbj(root, "validate")
    names = {c["check"]: c["status"] for c in (v3 or {}).get("checks", [])}
    s.check("canonical is clean immediately",
            names.get("no_secret_values_in_bodies") == "PASS")
    # validate emits "ERROR" for a failed check, not "FAIL" - assert the
    # string the tool actually produces, not the one that reads nicely.
    s.check("but validate FAILS until the index is rebuilt",
            names.get("derived_index_rebuilt_since_redaction") in ("ERROR", "FAIL")
            and v3["status"] == "FAILED",
            "check=%s status=%s" % (names.get("derived_index_rebuilt_since_redaction"),
                                    (v3 or {}).get("status")))

    sb(root, "rebuild-index", "--quiet")
    v4, _ = sbj(root, "validate")
    names4 = {c["check"]: c["status"] for c in (v4 or {}).get("checks", [])}
    s.check("after rebuild-index the store is valid again",
            names4.get("derived_index_rebuilt_since_redaction") == "PASS"
            and v4["status"] == "PASSED",
            "status=%s" % (v4 or {}).get("status"))
    s.check("and the prose around the key survived the redaction",
            "ordinary prose worth keeping" in (one(
                root, "SELECT v.body FROM object o JOIN object_version v"
                      " ON v.version_id=o.current_version"
                      " WHERE o.title='cfg.md'") or ""))

    # -------------------------------------------------------- invariants
    print("\nINVARIANTS")
    v2, _ = sbj(root, "validate")
    s.check("validate passes", v2 and v2["status"] == "PASSED",
            "failed=%s" % (v2 or {}).get("failed_checks"))
    sc, _ = sbj(root, "secrets")
    s.check("the secret scanner finds nothing left to redact",
            sc is not None and sc.get("objects_with_credentials", 0) == 0,
            "found=%s" % (sc or {}).get("objects_with_credentials"))

    rc2 = sb(root, "rebuild-index", "--quiet")
    s.check("index rebuilds", rc2.returncode == 0)
    sr, _ = sbj(root, "search", "Perceptor")
    s.check("vault content is searchable", sr and len(sr.get("results", [])) >= 1,
            "hits=%s" % (len(sr.get("results", [])) if sr else "n/a"))

    rc3 = s.finish()
    if rc3 == 0:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("store kept: %s" % root)
    return rc3


if __name__ == "__main__":
    sys.exit(main())
