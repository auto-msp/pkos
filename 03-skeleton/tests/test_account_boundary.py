"""Regression test: two Claude accounts must never collapse into one object.

Several native ids in a Claude export are NOT globally unique. Every export
ever produced contains `memory:conversations_memory:0`, and memory files are
keyed by path, so `memory_file:/areas/gtm.md` is the same string in two
different people's archives. If the resume map is not scoped by account, the
second account's document matches the first account's object, comes back
"unchanged", and two accounts silently become one - with no error raised and
nothing in the dead-letter queue.

That is the failure this test exists to make impossible. It is not a
hypothetical: the unscoped version of the query is what shipped first.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent
FAILED = []


def check(name, ok, detail=""):
    print("  [%s] %-52s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def sb(root, *args):
    env = dict(os.environ, PKOS_ROOT=str(root), PKOS_DERIVED=str(root / "derived"),
               PYTHONPATH=str(SKEL))
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


def make_export(d, account_uuid, email, conv_uuid, msg_uuid, body):
    """An export whose memory ids collide with every other export by design."""
    d.mkdir(parents=True)
    (d / "users.json").write_text(json.dumps(
        [{"uuid": account_uuid, "full_name": "Person", "email_address": email}]))
    (d / "memories.json").write_text(json.dumps([{
        "account_uuid": account_uuid,
        "conversations_memory": "narrative memory for %s" % email,
        # identical PATH in both exports - this is the collision
        "memory_files": [{"path": "/areas/gtm.md",
                          "content": "go-to-market notes for %s" % email,
                          "updated_at": "2026-01-01T00:00:00Z"}],
    }]))
    (d / "conversations.json").write_text(json.dumps([{
        "uuid": conv_uuid, "name": "chat", "summary": "",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        "account": {"uuid": account_uuid},
        "chat_messages": [{"uuid": msg_uuid, "text": body, "content": [],
                           "sender": "human", "created_at": "2026-01-01T00:00:00Z",
                           "updated_at": "2026-01-01T00:00:00Z",
                           "attachments": [], "files": [],
                           "parent_message_uuid": "00000000-0000-4000-8000-000000000000"}],
    }]))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-acct-"))
    root = tmp / "store"
    a = tmp / "export-a"; b = tmp / "export-b"
    make_export(a, "aaaaaaaa-0000-4000-8000-000000000001", "one@example.com",
                "11111111-0000-4000-8000-000000000001",
                "11111111-0000-4000-8000-0000000000a1", "first account body")
    make_export(b, "bbbbbbbb-0000-4000-8000-000000000002", "two@example.com",
                "22222222-0000-4000-8000-000000000002",
                "22222222-0000-4000-8000-0000000000b2", "second account body")

    print("ACCOUNT BOUNDARY TEST"); print("=" * 66)
    sb(root, "init")
    r1 = sb(root, "--json", "ingest", "claude-export", str(a))
    r2 = sb(root, "--json", "ingest", "claude-export", str(b))
    check("both exports ingested without error",
          r1.returncode == 0 and r2.returncode == 0,
          "rc=%s,%s %s" % (r1.returncode, r2.returncode, (r2.stderr or "")[:120]))

    d2 = json.loads(r2.stdout) if r2.stdout.strip().startswith("{") else {}
    check("second account created its own objects, none reported unchanged",
          d2.get("created", 0) > 0 and d2.get("unchanged", 0) == 0,
          "created=%s unchanged=%s" % (d2.get("created"), d2.get("unchanged")))

    import sqlite3
    c = sqlite3.connect(str(root / "canonical" / "canonical.sqlite3"))
    c.row_factory = sqlite3.Row
    accts = c.execute("SELECT account_id, identifier FROM account"
                      " WHERE source_id='SRC-claude-ai'").fetchall()
    check("two distinct accounts registered", len(accts) == 2,
          "%d account(s)" % len(accts))

    rows = c.execute(
        "SELECT so.account_id, p.object_id, v.body FROM source_object so"
        "  JOIN provenance p ON p.source_object_id = so.source_object_id"
        "  JOIN object o ON o.object_id = p.object_id"
        "  JOIN object_version v ON v.version_id = o.current_version"
        " WHERE so.native_id='memory_file:/areas/gtm.md'").fetchall()
    check("the colliding native id produced TWO objects, not one",
          len({r["object_id"] for r in rows}) == 2,
          "object_ids=%s" % sorted({r["object_id"] for r in rows}))
    check("each object kept its own account's content",
          len({(r["body"] or "")[:60] for r in rows}) == 2,
          "%d distinct bodies" % len({(r["body"] or "")[:60] for r in rows}))

    shared = c.execute(
        "SELECT COUNT(*) FROM (SELECT p.object_id,"
        " COUNT(DISTINCT COALESCE(so.account_id,'~')) a FROM provenance p"
        " JOIN source_object so ON so.source_object_id=p.source_object_id"
        " GROUP BY p.object_id HAVING a>1)").fetchone()[0]
    check("no object carries provenance from two accounts", shared == 0,
          "%d shared object(s)" % shared)

    # re-ingesting account A must still be a no-op, not a cross-account rewrite
    r3 = sb(root, "--json", "ingest", "claude-export", str(a))
    d3 = json.loads(r3.stdout) if r3.stdout.strip().startswith("{") else {}
    check("re-ingesting the first account is still idempotent",
          d3.get("created", 1) == 0 and d3.get("unchanged", 0) > 0,
          "created=%s unchanged=%s" % (d3.get("created"), d3.get("unchanged")))

    rv = sb(root, "--json", "validate")
    v = json.loads(rv.stdout)
    names = {x["check"]: x["status"] == "PASS" for x in v["checks"]}
    check("validate: account_boundaries_preserved",
          names.get("account_boundaries_preserved") is True)
    check("validate: objects_not_shared_across_accounts",
          names.get("objects_not_shared_across_accounts") is True)
    check("validate: all invariants pass", v["status"] == "PASSED",
          "failed=%d" % v["failed_checks"])

    print("=" * 66)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED:
            print("  -", f)
        return 1
    print("ALL ACCOUNT BOUNDARY TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
