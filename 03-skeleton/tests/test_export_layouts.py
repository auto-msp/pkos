"""The Claude export ships in more than one shape. Handle both, prove neither
is silently truncated.

Old shape: one unpacked folder (conversations.json, users.json, memories.json,
projects/). New shape: a manifest json plus one zip per category, each with a
SINGLE-USE download URL.

The single-use URLs are why the missing-part check matters. If one download
fails, that part is gone until a whole new export is requested - and an
ingester that just globs whatever zips it finds would report a clean,
successful, quietly incomplete run.
"""
import json, os, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent
FAILED = []


def check(name, ok, detail=""):
    print("  [%s] %-54s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def sb(root, *args):
    env = dict(os.environ, PKOS_ROOT=str(root), PKOS_DERIVED=str(root / "derived"),
               PYTHONPATH=str(SKEL))
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


ACCT = "cccccccc-0000-4000-8000-000000000003"

CONVS = [{
    "uuid": "33333333-0000-4000-8000-000000000003", "name": "second account chat",
    "summary": "", "created_at": "2026-02-01T00:00:00Z",
    "updated_at": "2026-02-01T00:00:00Z", "account": {"uuid": ACCT},
    "chat_messages": [{
        "uuid": "33333333-0000-4000-8000-0000000000c3",
        "text": "hello from the second account", "content": [], "sender": "human",
        "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z",
        "attachments": [], "files": [],
        "parent_message_uuid": "00000000-0000-4000-8000-000000000000"}],
}]
USERS = [{"uuid": ACCT, "full_name": "Person Two",
          "email_address": "second@example.com"}]
MEMS = [{"account_uuid": ACCT, "conversations_memory": "second account memory"}]
PROJ = {"uuid": "44444444-0000-4000-8000-000000000004", "name": "P2",
        "description": "second account project", "is_private": True,
        "prompt_template": "", "created_at": "2026-02-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "docs": [{"uuid": "55555555-0000-4000-8000-000000000005",
                  "filename": "brief.md", "content": "the brief",
                  "created_at": "2026-02-01T00:00:00Z"}]}

LOGINS = {"login_events": [
    {"account_uuid": ACCT, "timestamp": "2026-02-01T09:00:00+00:00",
     "ip_address": "203.0.113.9", "method": "magic_link",
     "user_agent": {"browser_family": "Chrome", "browser_version": "148.0",
                    "os_family": "Windows", "os_version": "10"},
     "location_info": {"country": "IN", "region": None, "city": None}},
    # an event belonging to somebody else must never be filed under this account
    {"account_uuid": "dddddddd-0000-4000-8000-000000000009",
     "timestamp": "2026-02-01T10:00:00+00:00", "ip_address": "198.51.100.7",
     "method": "magic_link", "user_agent": {}, "location_info": {"country": "US"}},
]}

# The 2026-09 export shape: memories live in memories/<account-uuid>.json,
# and light_metadata carries login_history.json alongside users.json.
PARTS = {
    "conversations-000.zip":  [("conversations.json", json.dumps(CONVS))],
    "light_metadata-000.zip": [("users.json", json.dumps(USERS)),
                               ("login_history.json", json.dumps(LOGINS))],
    "memories-000.zip":       [("memories/%s.json" % ACCT, json.dumps(MEMS[0])),
                               ("memories/dddddddd-0000-4000-8000-000000000009.json",
                                json.dumps({"conversations_memory": "somebody else"}))],
    "projects-000.zip":       [("projects/%s.json" % PROJ["uuid"], json.dumps(PROJ))],
    "design_chats-000.zip":   [("design_chats/README.txt", "no design chats")],
}


def make_new_shape(d, omit=()):
    d.mkdir(parents=True)
    for name, entries in PARTS.items():
        if name in omit:
            continue
        with zipfile.ZipFile(d / name, "w") as z:
            for inner, body in entries:
                z.writestr(inner, body)
    (d / "manifest-abc.json").write_text(json.dumps({
        "instructions": "Download each file using the export_url. Note: Each "
                        "export URL can only be used once.",
        "created_at": "2026-02-01T00:00:00Z", "total_files": len(PARTS),
        "version": "1.0",
        "data_files": [{"batch_index": i, "filename": n, "part": 0,
                        "category": n.split("-")[0],
                        "export_url": "https://claude.ai/export/6514f07f-b0e7-449a"
                                      "-a8dc-57615ea8088b/download/%032x" % i}
                       for i, n in enumerate(PARTS)],
    }))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-layout-"))
    print("EXPORT LAYOUT TEST"); print("=" * 70)

    # ---- 1. incomplete set is refused ---------------------------------
    root = tmp / "store"; sb(root, "init")
    bad = tmp / "partial"
    make_new_shape(bad, omit=("memories-000.zip", "projects-000.zip"))
    r = sb(root, "ingest", "claude-export", str(bad))
    out = (r.stdout or "") + (r.stderr or "")
    check("incomplete export is refused, not quietly ingested",
          r.returncode != 0 and "missing" in out.lower(), "rc=%d" % r.returncode)
    check("the refusal names the missing parts",
          "memories-000.zip" in out and "projects-000.zip" in out)
    check("the refusal explains the single-use consequence",
          "single-use" in out.lower())

    # ---- 2. --allow-partial proceeds and records the gap ---------------
    r = sb(root, "--json", "ingest", "claude-export", str(bad), "--allow-partial")
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("--allow-partial ingests what is there",
          r.returncode == 0 and d.get("created", 0) > 0,
          "created=%s" % d.get("created"))
    st = d.get("adapter_stats", {})
    check("the gap is recorded in the run's own stats",
          st.get("export_parts_missing") and
          len(st["export_parts_missing"]) == 2,
          "missing=%s" % st.get("export_parts_missing"))

    # ---- 3. the complete set ingests cleanly ---------------------------
    root2 = tmp / "store2"; sb(root2, "init")
    good = tmp / "full"; make_new_shape(good)
    r = sb(root2, "--json", "ingest", "claude-export", str(good))
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("complete multi-zip export ingests", r.returncode == 0,
          "rc=%d %s" % (r.returncode, (r.stderr or "")[:100]))
    st = d.get("adapter_stats", {})
    check("all 5 parts seen, none missing",
          st.get("export_parts_present") == 5 and not st.get("export_parts_missing"),
          "present=%s" % st.get("export_parts_present"))
    check("account resolved from the zipped users.json",
          st.get("conversations") == 1 and st.get("messages") == 1)
    check("project doc found inside the projects zip",
          st.get("project_documents") == 1, "docs=%s" % st.get("project_documents"))
    # memories/<account-uuid>.json is the 2026-09 layout. Globbing
    # "memories*.json" does not match it, and missing it is SILENT.
    check("memories found in the memories/<account-uuid>.json layout",
          st.get("assistant_memories", 0) >= 1,
          "memories=%s" % st.get("assistant_memories"))
    check("another account's memory file is skipped, not ingested",
          st.get("foreign_memory_files_skipped", 0) >= 1,
          "skipped=%s" % st.get("foreign_memory_files_skipped"))
    check("login history ingested", st.get("login_events") == 1,
          "events=%s" % st.get("login_events"))
    check("another account's login event is skipped",
          st.get("foreign_login_events_skipped") == 1,
          "skipped=%s" % st.get("foreign_login_events_skipped"))

    import sqlite3
    c = sqlite3.connect(str(root2 / "canonical" / "canonical.sqlite3"))
    c.row_factory = sqlite3.Row
    acc = c.execute("SELECT identifier, display_name FROM account"
                    " WHERE source_id='SRC-claude-ai'").fetchone()
    check("account identity came from users.json, not inferred",
          acc and acc["identifier"] == ACCT and "second@example.com" in (acc["display_name"] or ""),
          acc["display_name"] if acc else "none")
    lg = c.execute("SELECT o.title, o.classification, v.body FROM object o"
                   " JOIN object_version v ON v.version_id=o.current_version"
                   " WHERE o.object_class='LoginEvent'").fetchone()
    check("a sign-in record is classified SENSITIVE and keeps its origin",
          lg and lg["classification"] == "SENSITIVE" and "203.0.113.9" in (lg["body"] or ""),
          lg["title"] if lg else "none")
    zipped = c.execute("SELECT COUNT(*) FROM evidence_blob"
                       " WHERE mime_type='application/zip'").fetchone()[0]
    check("every zip is kept as evidence, byte-exact", zipped == 5,
          "%d zip blob(s)" % zipped)
    aud = c.execute("SELECT detail FROM audit_event"
                    " WHERE action='export_parts_acquired'"
                    " ORDER BY rowid DESC LIMIT 1").fetchone()
    check("part fingerprints are auditable after the fact",
          aud and len(json.loads(aud["detail"])["part_hashes"]) == 5)

    # ---- 4. the single-use URL never reaches a searchable body ---------
    sys.path.insert(0, str(SKEL))
    from secondbrain import secrets as _s
    check("an export download URL is treated as credential material",
          _s.scan_body("see https://claude.ai/export/6514f07f-b0e7-449a-a8dc-"
                       "57615ea8088b/download/fa8da19460fe33c91cddd833308f10fe"),
          "matched")

    # ---- 5. zip traversal is refused -----------------------------------
    root3 = tmp / "store3"; sb(root3, "init")
    evil = tmp / "evil"; make_new_shape(evil)
    with zipfile.ZipFile(evil / "design_chats-000.zip", "w") as z:
        z.writestr("../../escaped.txt", "should never be written")
        z.writestr("design_chats/ok.txt", "fine")
    r = sb(root3, "--json", "ingest", "claude-export", str(evil))
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("path traversal inside a zip is refused",
          d.get("adapter_stats", {}).get("unsafe_zip_entries") == 1,
          "unsafe=%s" % d.get("adapter_stats", {}).get("unsafe_zip_entries"))
    check("nothing escaped the landing directory",
          not (tmp / "escaped.txt").exists() and not (root3 / "escaped.txt").exists())

    # ---- 5b. two DIFFERENT exports, identical filenames -----------------
    # Every Claude export ships conversations-000.zip, memories-000.zip and so
    # on. If the unpack directory is keyed on those names, a second account's
    # export lands on top of the first one's, the ".unpacked" markers say the
    # work is already done, nothing is extracted, and the FIRST account's
    # users.json is read as though it were the second's. Silent, and wrong in
    # the worst possible way: a confident answer about the wrong identity.
    root5 = tmp / "store5"; sb(root5, "init")
    exp_a = tmp / "acct-a"; make_new_shape(exp_a)

    ACCT_B = "eeeeeeee-0000-4000-8000-00000000000b"
    exp_b = tmp / "acct-b"; exp_b.mkdir()
    parts_b = {
        "conversations-000.zip": [("conversations.json", json.dumps([{
            "uuid": "66666666-0000-4000-8000-000000000006", "name": "B chat",
            "summary": "", "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-01T00:00:00Z", "account": {"uuid": ACCT_B},
            "chat_messages": [{"uuid": "66666666-0000-4000-8000-0000000000d6",
                               "text": "belongs to account B", "content": [],
                               "sender": "human",
                               "created_at": "2026-03-01T00:00:00Z",
                               "updated_at": "2026-03-01T00:00:00Z",
                               "attachments": [], "files": [],
                               "parent_message_uuid":
                                   "00000000-0000-4000-8000-000000000000"}]}]))],
        "light_metadata-000.zip": [("users.json", json.dumps(
            [{"uuid": ACCT_B, "full_name": "Person B",
              "email_address": "b@example.com"}]))],
        "memories-000.zip": [("memories/%s.json" % ACCT_B,
                              json.dumps({"conversations_memory": "B memory"}))],
        "projects-000.zip": [("projects/x.json", json.dumps(
            {"uuid": "77777777-0000-4000-8000-000000000007", "name": "PB",
             "description": "", "docs": []}))],
        "design_chats-000.zip": [("design_chats/README.txt", "b")],
    }
    for name, entries in parts_b.items():
        with zipfile.ZipFile(exp_b / name, "w") as z:
            for inner, body in entries:
                z.writestr(inner, body)
    (exp_b / "manifest-b.json").write_text(json.dumps({
        "total_files": len(parts_b), "version": "1.0",
        "data_files": [{"filename": n, "category": n.split("-")[0], "part": 0,
                        "batch_index": i, "export_url": "https://example.invalid/%d" % i}
                       for i, n in enumerate(parts_b)]}))

    sb(root5, "ingest", "claude-export", str(exp_a))
    r = sb(root5, "--json", "ingest", "claude-export", str(exp_b))
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("a second export with the SAME filenames is really unpacked",
          d.get("created", 0) > 0 and d.get("unchanged", 0) == 0,
          "created=%s unchanged=%s" % (d.get("created"), d.get("unchanged")))

    c5 = sqlite3.connect(str(root5 / "canonical" / "canonical.sqlite3"))
    c5.row_factory = sqlite3.Row
    ids = [r["identifier"] for r in c5.execute(
        "SELECT identifier FROM account WHERE source_id='SRC-claude-ai'")]
    check("both accounts registered from identically-named zips",
          sorted(ids) == sorted([ACCT, ACCT_B]), str(sorted(ids)))
    lands = sorted(pp.name for pp in (root5 / "evidence" / "landing").iterdir()
                   if pp.is_dir())
    check("each export unpacked to its own content-keyed directory",
          len(lands) == 2, str(lands))

    # ---- 6. the OLD unpacked shape still works -------------------------
    root4 = tmp / "store4"; sb(root4, "init")
    old = tmp / "old"; (old / "projects").mkdir(parents=True)
    (old / "conversations.json").write_text(json.dumps(CONVS))
    (old / "users.json").write_text(json.dumps(USERS))
    (old / "memories.json").write_text(json.dumps(MEMS))
    (old / "projects" / (PROJ["uuid"] + ".json")).write_text(json.dumps(PROJ))
    r = sb(root4, "--json", "ingest", "claude-export", str(old))
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("the original unpacked folder shape still ingests",
          r.returncode == 0 and d.get("created", 0) > 0,
          "created=%s" % d.get("created"))

    print("=" * 70)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED:
            print("  -", f)
        return 1
    print("ALL EXPORT LAYOUT TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
