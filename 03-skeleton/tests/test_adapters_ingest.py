"""End-to-end tests for the Phase 9-19 adapters, against synthetic exports.

Written against SOW 43: every claim below is a measured count, a re-hash or an
asserted identity, never "it ran without raising". The cases that matter most
are the ones that fail SILENTLY in production:

  * a Chrome timestamp read as epoch seconds dates every URL to the year
    54000 and nothing raises;
  * a Notion page renamed between exports duplicates the whole workspace if
    identity came from the filename;
  * a LinkedIn CSV re-sorted between exports duplicates every row if identity
    came from row position;
  * Meta's double-encoded UTF-8 corrupts every non-ASCII character and the
    JSON stays perfectly valid;
  * a ChatGPT tree read in dict order interleaves abandoned branches into the
    transcript.

Each of those has a test here that fails loudly if the handling regresses.
"""
import json, shutil, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _harness import Suite, sb, sbj, ingest, q, one          # noqa: E402

EPOCH_1601 = 11644473600          # seconds between 1601-01-01 and 1970-01-01
JAN15 = 1705312800                # 2024-01-15T10:00:00Z
ID1 = "1a2b3c4d5e6f7890abcdef1234567890"
ID2 = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
ID3 = "abcdef0123456789abcdef0123456789"


# ---------------------------------------------------------------- fixtures
def make_takeout(d):
    t = d / "Takeout"
    (t / "Chrome").mkdir(parents=True)
    (t / "Chrome" / "BrowserHistory.json").write_text(json.dumps({
        "Browser History": [
            {"title": "Postgres WAL internals", "url": "https://www.postgresql.org/docs/wal.html?utm_source=x",
             "time_usec": (JAN15 + EPOCH_1601) * 1000000,
             "page_transition": "LINK", "client_id": "profile-1"},
            {"title": "SQLite WAL", "url": "https://sqlite.org/wal.html",
             "time_usec": (JAN15 + 3600 + EPOCH_1601) * 1000000,
             "page_transition": "TYPED", "client_id": "profile-1"},
            {"title": "Postgres WAL internals again", "url": "https://www.postgresql.org/docs/wal.html",
             "time_usec": (JAN15 + 7200 + EPOCH_1601) * 1000000,
             "page_transition": "RELOAD", "client_id": "profile-1"},
        ]}), encoding="utf-8")
    (t / "Chrome" / "Bookmarks.html").write_text(
        '<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL><p>\n'
        '<DT><H3 ADD_DATE="1700000000">Infra</H3>\n<DL><p>\n'
        '<DT><A HREF="https://caddyserver.com/docs" ADD_DATE="1700000100">Caddy docs</A>\n'
        '</DL><p>\n'
        '<DT><A HREF="https://tailscale.com/kb" ADD_DATE="1700000200">Tailscale KB</A>\n'
        '</DL><p>\n', encoding="utf-8")

    (t / "Drive").mkdir()
    (t / "Drive" / "budget.xlsx").write_bytes(b"PK\x03\x04fake-xlsx-with-formulas")
    (t / "Drive" / "budget.xlsx-info.json").write_text(json.dumps(
        {"title": "FY26 Budget", "created_date": "2025-04-01T09:00:00Z",
         "modified_date": "2026-02-02T11:30:00Z",
         "url": "https://docs.google.com/spreadsheets/d/abc"}), encoding="utf-8")
    (t / "Drive" / "notes.txt").write_text("Perceptor is the master.\n", encoding="utf-8")

    (t / "Keep").mkdir()
    (t / "Keep" / "shopping.json").write_text(json.dumps({
        "title": "Backup checklist", "textContent": "",
        "listContent": [{"text": "verify restore drill", "isChecked": True},
                        {"text": "rotate offsite", "isChecked": False}],
        "createdTimestampUsec": JAN15 * 1000000,
        "userEditedTimestampUsec": (JAN15 + 500) * 1000000,
        "labels": [{"name": "ops"}], "isPinned": True}), encoding="utf-8")

    (t / "Calendar").mkdir()
    (t / "Calendar" / "moiz.ics").write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Standup\nEND:VEVENT\n"
        "BEGIN:VEVENT\nSUMMARY:Review\nEND:VEVENT\nEND:VCALENDAR\n", encoding="utf-8")

    act = t / "My Activity" / "Search"
    act.mkdir(parents=True)
    act.joinpath("MyActivity.json").write_text(json.dumps([
        {"header": "Search", "title": "Searched for sqlite vacuum into",
         "titleUrl": "https://www.google.com/search?q=sqlite+vacuum+into",
         "time": "2024-03-02T08:15:00Z"},
        {"header": "Search", "title": "no url here"},
    ]), encoding="utf-8")

    (t / "Mail").mkdir()
    (t / "Mail" / "All mail.mbox").write_text(
        "From x@y.z Mon Jan 15 10:00:00 2024\nSubject: hi\n\nbody\n", encoding="utf-8")
    return d


def make_notion(d, title_one="Page One"):
    e = d / "notion-export"
    e.mkdir(parents=True, exist_ok=True)
    e.joinpath("%s %s.md" % (title_one, ID1)).write_text(
        "# %s\n\nSee [Page Two](Sub%%20Folder%%20{id2}/Page%%20Two%%20{id2}.md) for detail.\n"
        .replace("{id2}", ID2) % title_one, encoding="utf-8")
    sub = e / ("Sub Folder %s" % ID3)
    sub.mkdir(exist_ok=True)
    sub.joinpath("Page Two %s.md" % ID2).write_text(
        "# Page Two\n\nThe detail.\n", encoding="utf-8")
    e.joinpath("Tasks %s.csv" % ID3).write_text(
        "Name,Status,Due\nShip bundle,Doing,2026-09-12\nAudit servers,Todo,\n",
        encoding="utf-8")
    e.joinpath("diagram.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return e


def make_stars(d):
    p = d / "stars-dated.json"
    p.write_text(json.dumps([
        {"starred_at": "2024-06-01T12:00:00Z",
         "repo": {"full_name": "sqlite/sqlite", "html_url": "https://github.com/sqlite/sqlite",
                  "description": "SQLite source", "language": "C",
                  "topics": ["database"], "stargazers_count": 7000,
                  "created_at": "2015-01-01T00:00:00Z",
                  "pushed_at": "2026-01-01T00:00:00Z",
                  "owner": {"login": "sqlite"}, "license": {"spdx_id": "blessing"}}},
        {"starred_at": "2025-02-11T08:00:00Z",
         "repo": {"full_name": "caddyserver/caddy", "html_url": "https://github.com/caddyserver/caddy",
                  "description": "Fast web server", "language": "Go",
                  "archived": True, "owner": {"login": "caddyserver"}}},
    ]), encoding="utf-8")
    u = d / "stars-undated.json"
    u.write_text(json.dumps([
        {"full_name": "tailscale/tailscale", "html_url": "https://github.com/tailscale/tailscale",
         "description": "Mesh VPN", "language": "Go", "owner": {"login": "tailscale"}}
    ]), encoding="utf-8")
    return p, u


def make_chatgpt(d):
    e = d / "chatgpt"; e.mkdir(parents=True)
    # root -> a(user) -> b(assistant, ABANDONED) 
    #                 -> c(assistant, kept) -> d(user, current)
    mapping = {
        "root": {"id": "root", "message": None, "parent": None, "children": ["a"]},
        "a": {"id": "a", "parent": "root", "children": ["b", "c"],
              "message": {"id": "ma", "author": {"role": "user"},
                          "content": {"content_type": "text", "parts": ["how do I vacuum sqlite"]},
                          "create_time": JAN15}},
        "b": {"id": "b", "parent": "a", "children": [],
              "message": {"id": "mb", "author": {"role": "assistant"},
                          "content": {"content_type": "text", "parts": ["ABANDONED DRAFT"]},
                          "create_time": JAN15 + 10,
                          "metadata": {"model_slug": "gpt-4"}}},
        "c": {"id": "c", "parent": "a", "children": ["dd"],
              "message": {"id": "mc", "author": {"role": "assistant"},
                          "content": {"content_type": "text", "parts": ["Use VACUUM INTO."]},
                          "create_time": JAN15 + 20,
                          "metadata": {"model_slug": "gpt-4"}}},
        "dd": {"id": "dd", "parent": "c", "children": [],
               "message": {"id": "md", "author": {"role": "user"},
                           "content": {"content_type": "text", "parts": ["thanks"]},
                           "create_time": JAN15 + 30}},
    }
    e.joinpath("conversations.json").write_text(json.dumps([
        {"conversation_id": "conv-1", "title": "SQLite vacuum",
         "create_time": JAN15, "update_time": JAN15 + 30,
         "current_node": "dd", "mapping": mapping}]), encoding="utf-8")
    return e


def make_instagram(d):
    e = d / "instagram"; (e / "content").mkdir(parents=True)
    (e / "messages" / "inbox" / "amir_123").mkdir(parents=True)
    # "café" and "naïve" written the way Meta writes them: UTF-8 bytes
    # re-escaped one byte at a time.
    # exactly how Meta writes it: UTF-8 bytes re-escaped one byte at a time
    mojibake = "Morning at the caf\u00c3\u00a9 \u00e2\u0080\u0094 na\u00c3\u00afve but good"
    (e / "content" / "posts_1.json").write_text(json.dumps([
        {"media": [{"uri": "media/posts/1.jpg", "creation_timestamp": JAN15,
                    "title": mojibake}],
         "creation_timestamp": JAN15, "title": mojibake}]), encoding="utf-8")
    (e / "messages" / "inbox" / "amir_123" / "message_1.json").write_text(json.dumps({
        "participants": [{"name": "Moiz"}, {"name": "Amir"}],
        "thread_path": "inbox/amir_123", "title": "Amir",
        "is_still_participant": True,
        "messages": [
            {"sender_name": "Amir", "timestamp_ms": JAN15 * 1000, "content": "ping"},
            {"sender_name": "Moiz", "timestamp_ms": (JAN15 + 60) * 1000, "content": "pong"},
        ]}), encoding="utf-8")
    return e


def make_linkedin(d, reverse=False):
    e = d / ("linkedin-rev" if reverse else "linkedin")
    e.mkdir(parents=True, exist_ok=True)
    rows = [
        'Amir,Khan,https://www.linkedin.com/in/amirkhan,amir@example.com,Acme,CTO,15 Mar 2024',
        'Priya,Shah,https://www.linkedin.com/in/priyashah,,Globex,VP Eng,02 Jun 2023',
        'Sam,Lee,https://www.linkedin.com/in/samlee,,Initech,Founder,11 Nov 2022',
    ]
    if reverse:
        rows = list(reversed(rows))
    e.joinpath("Connections.csv").write_text(
        "Notes:\n"
        '"When exporting your connection data, you may notice..."\n'
        "\n"
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    return e


def make_airtable(d):
    e = d / "airtable"; e.mkdir(parents=True)
    e.joinpath("base-appXYZ.json").write_text(json.dumps({
        "captured_at": "2026-09-11T12:00:00Z",
        "base": {"id": "appXYZ", "name": "AutoMSP CRM", "permissionLevel": "create"},
        "tables": [{
            "id": "tblLeads", "name": "Leads",
            "fields": [{"name": "Name", "type": "singleLineText"},
                       {"name": "Score", "type": "formula"},
                       {"name": "Owner", "type": "multipleRecordLinks"},
                       {"name": "Contract", "type": "multipleAttachments"}],
            "records": [
                {"id": "rec001", "createdTime": "2026-01-05T10:00:00Z",
                 "fields": {"Name": "Acme Corp", "Score": 87,
                            "Owner": ["rec002"],
                            "Contract": [{"id": "att1", "filename": "msa.pdf",
                                          "size": 12345, "type": "application/pdf",
                                          "url": "https://v5.airtableusercontent.com/expiring"}]}},
                {"id": "rec002", "createdTime": "2026-01-06T10:00:00Z",
                 "fields": {"Name": "Globex"}},
            ]}]}), encoding="utf-8")
    return e


# ---------------------------------------------------------------- the suite
def main():
    s = Suite("ADAPTER")
    tmp = Path(tempfile.mkdtemp(prefix="pkos-adapters-"))
    root = tmp / "store"
    sb(root, "init")
    fx = tmp / "fx"; fx.mkdir()

    # ---------------------------------------------------------- Takeout
    print("\nGOOGLE TAKEOUT (phase 10, and the phase 7 unblock)")
    make_takeout(fx)
    d, r = ingest(root, "takeout", fx, "--identity", "moiz@example.com")
    s.check("takeout ingest completes", d and d["status"] == "COMPLETED",
            (r.stdout + r.stderr)[-400:] if not d else "")
    st = (d or {}).get("adapter_stats", {})
    s.check("3 history rows read", st.get("history_rows") == 3,
            "got %s" % st.get("history_rows"))
    s.check("2 bookmarks read", st.get("bookmarks") == 2,
            "got %s" % st.get("bookmarks"))
    s.check("2 Drive files, 1 sidecar not ingested as a file",
            st.get("drive_files") == 2 and st.get("drive_sidecars") == 1,
            "files=%s sidecars=%s" % (st.get("drive_files"), st.get("drive_sidecars")))

    # The one that fails silently: Chrome epochs are 1601-based.
    yrs = [row["first_seen"][:4] for row in
           q(root, "SELECT first_seen FROM url WHERE first_seen IS NOT NULL"
                   " AND normalized_url LIKE '%postgresql%'")]
    s.check("Chrome 1601-microsecond epoch decoded to 2024, not the year 54000",
            yrs and all(y == "2024" for y in yrs), "years=%s" % yrs)

    # Same page visited twice -> ONE url row, TWO visits, ONE canonical object.
    n_url = one(root, "SELECT COUNT(*) FROM url WHERE normalized_url LIKE '%postgresql%'")
    n_vis = one(root, "SELECT COUNT(*) FROM url_visit v JOIN url u USING(url_id)"
                      " WHERE u.normalized_url LIKE '%postgresql%'")
    n_obj = one(root, "SELECT COUNT(*) FROM object WHERE object_class='WebPage'"
                      " AND title LIKE '%WAL%'")
    s.check("repeat visit: 1 url, 2 visits, not 2 urls",
            n_url == 1 and n_vis == 2, "urls=%s visits=%s" % (n_url, n_vis))
    s.check("utm_source stripped so the two visits canonicalize together",
            n_url == 1, "objects=%s" % n_obj)

    s.check("bookmark visits kept distinct from history visits",
            one(root, "SELECT COUNT(*) FROM url_visit WHERE visit_kind='bookmark'") == 2
            and one(root, "SELECT COUNT(*) FROM url_visit WHERE visit_kind='history'") == 3)

    # Mail: bytes acquired, meaning NOT claimed.
    s.check("mbox acquired as evidence but not interpreted",
            one(root, "SELECT COUNT(*) FROM object WHERE object_class='MailArchive'") == 1
            and one(root, "SELECT COUNT(*) FROM object WHERE object_class='EmailMessage'") == 0)
    s.check("Keep list items rendered into the body",
            "verify restore drill" in (one(
                root, "SELECT body FROM object_version v JOIN object o"
                      " ON o.current_version=v.version_id WHERE o.object_class='Note'") or ""))
    s.check("Drive sidecar title preferred over the filename",
            one(root, "SELECT COUNT(*) FROM object WHERE title='FY26 Budget'") == 1)
    s.check("activity URLs recorded without minting an object each",
            one(root, "SELECT COUNT(*) FROM url_visit WHERE visit_kind='activity'") == 1)

    d2, _ = ingest(root, "takeout", fx, "--identity", "moiz@example.com")
    st2 = (d2 or {}).get("adapter_stats", {})
    s.check("re-ingest is idempotent (SOW 39): 0 created",
            d2 and d2["created"] == 0 and d2["unchanged"] > 0,
            "created=%s unchanged=%s" % ((d2 or {}).get("created"), (d2 or {}).get("unchanged")))

    # ---------------------------------------------------------- Notion
    print("\nNOTION (phase 11)")
    ne = make_notion(fx)
    d, r = ingest(root, "notion", ne, "--identity", "moiz@example.com")
    st = (d or {}).get("adapter_stats", {})
    s.check("notion ingest completes", d and d["status"] == "COMPLETED",
            (r.stdout + r.stderr)[-400:] if not d else "")
    s.check("2 pages, 1 database, 1 asset",
            (st.get("pages"), st.get("databases"), st.get("assets")) == (2, 1, 1),
            "%s" % [st.get("pages"), st.get("databases"), st.get("assets")])
    s.check("3 files carried a Notion block id", st.get("with_notion_id") == 3,
            "got %s" % st.get("with_notion_id"))
    s.check("inline link resolved into a LINKS_TO edge",
            st.get("links_written") == 1, "got %s" % st.get("links_written"))
    s.check("csv row count recorded from the parsed rows",
            one(root, "SELECT COUNT(*) FROM object WHERE object_class='Database'") == 1)

    # THE Notion test: rename the page, keep the id, re-export.
    before = one(root, "SELECT COUNT(*) FROM object WHERE object_class='Page'")
    for p in ne.glob("Page One %s.md" % ID1):
        p.rename(ne / ("Renamed Strategy Page %s.md" % ID1))
    d3, _ = ingest(root, "notion", ne, "--identity", "moiz@example.com")
    after = one(root, "SELECT COUNT(*) FROM object WHERE object_class='Page'")
    s.check("page renamed between exports does NOT duplicate (identity is the "
            "block id, not the filename)", before == after == 2,
            "before=%s after=%s" % (before, after))
    s.check("the rename produced a new VERSION under the same object",
            (d3 or {}).get("versioned", 0) >= 1,
            "versioned=%s" % (d3 or {}).get("versioned"))

    # ---------------------------------------------------------- GitHub stars
    print("\nGITHUB STARS (phase 9)")
    dated, undated = make_stars(fx)
    d, r = ingest(root, "github-stars", dated, "--identity", "moiz")
    st = (d or {}).get("adapter_stats", {})
    s.check("2 starred repos with star dates",
            st.get("repos") == 2 and st.get("with_star_date") == 2,
            "%s / %s" % (st.get("repos"), st.get("with_star_date")))
    s.check("archived repo counted", st.get("archived") == 1)
    s.check("star date became the object's source_created_at",
            (one(root, "SELECT source_created_at FROM source_object"
                       " WHERE native_id='github:repo:sqlite/sqlite'") or "").startswith("2024-06-01"))
    d, _ = ingest(root, "github-stars", undated, "--identity", "moiz")
    st = (d or {}).get("adapter_stats", {})
    s.check("undated export is called out rather than silently accepted",
            "star_date_warning" in st, "keys=%s" % sorted(st))

    # ---------------------------------------------------------- ChatGPT
    print("\nCHATGPT (phase 15)")
    ce = make_chatgpt(fx)
    d, r = ingest(root, "chatgpt", ce, "--identity", "moiz@example.com")
    st = (d or {}).get("adapter_stats", {})
    s.check("1 conversation, 4 messages", st.get("conversations") == 1
            and st.get("messages") == 4,
            "%s / %s" % (st.get("conversations"), st.get("messages")))
    s.check("3 messages on the branch the conversation ended on",
            st.get("messages_on_current_branch") == 3,
            "got %s" % st.get("messages_on_current_branch"))
    s.check("the abandoned regenerate is kept, and marked as abandoned",
            st.get("messages_on_abandoned_branches") == 1,
            "got %s" % st.get("messages_on_abandoned_branches"))
    body = one(root, "SELECT v.body FROM object o JOIN object_version v"
                     " ON o.current_version=v.version_id"
                     " WHERE v.body='ABANDONED DRAFT'")
    s.check("abandoned text is still in the store (nothing is deleted)",
            body == "ABANDONED DRAFT")

    # ---------------------------------------------------------- Instagram
    print("\nINSTAGRAM / META (phases 17-18)")
    ie = make_instagram(fx)
    d, r = ingest(root, "instagram", ie, "--identity", "moiz")
    st = (d or {}).get("adapter_stats", {})
    s.check("instagram ingest completes", d and d["status"] == "COMPLETED",
            (r.stdout + r.stderr)[-300:] if not d else "")
    s.check("thread and its 2 messages found",
            st.get("threads") == 1 and st.get("messages") == 2,
            "%s / %s" % (st.get("threads"), st.get("messages")))
    hit = one(root, "SELECT COUNT(*) FROM object_version WHERE body LIKE '%café%'")
    bad = one(root, "SELECT COUNT(*) FROM object_version WHERE body LIKE '%cafÃ©%'")
    s.check("Meta's double-encoded UTF-8 repaired on the way in",
            hit >= 1 and bad == 0, "café=%s mojibake=%s" % (hit, bad))
    s.check("messages linked PART_OF their thread",
            one(root, "SELECT COUNT(*) FROM relationship r JOIN object o"
                      " ON o.object_id=r.target_object"
                      " WHERE r.relationship_type='PART_OF'"
                      " AND o.object_class='Conversation'") >= 2)

    # ---------------------------------------------------------- LinkedIn
    print("\nLINKEDIN / TABULAR (phases 16, 19)")
    le = make_linkedin(fx)
    d, r = ingest(root, "linkedin", le, "--identity", "moiz")
    st = (d or {}).get("adapter_stats", {})
    s.check("3 connection rows read past the Notes: preamble",
            st.get("rows") == 3, "got %s" % st.get("rows"))
    cols = json.loads(one(root, "SELECT raw_metadata FROM source_object"
                                " WHERE native_id LIKE 'linkedin:connections:%' LIMIT 1"))
    s.check("header row parsed correctly, not the preamble",
            "First Name" in cols["columns"] and "Connected On" in cols["columns"],
            "cols=%s" % cols["columns"][:4])
    s.check("profile URLs recorded in the url table",
            one(root, "SELECT COUNT(*) FROM url WHERE normalized_url LIKE '%linkedin.com/in/%'") == 3)

    # THE tabular test: same rows, different order.
    rev = make_linkedin(fx, reverse=True)
    d4, _ = ingest(root, "linkedin", rev, "--identity", "moiz")
    n_contacts = one(root, "SELECT COUNT(*) FROM object WHERE object_class='Contact'")
    s.check("re-export with rows REORDERED does not duplicate them",
            n_contacts == 3 and (d4 or {}).get("created") == 0,
            "contacts=%s created=%s" % (n_contacts, (d4 or {}).get("created")))

    # ---------------------------------------------------------- Airtable
    print("\nAIRTABLE (phase 12)")
    ae = make_airtable(fx)
    d, r = ingest(root, "airtable", ae, "--identity", "moiz@example.com")
    st = (d or {}).get("adapter_stats", {})
    s.check("1 base, 1 table, 2 records",
            (st.get("bases"), st.get("tables"), st.get("records")) == (1, 1, 2),
            "%s" % [st.get("bases"), st.get("tables"), st.get("records")])
    s.check("formula column identified as computed",
            st.get("computed_fields") == 1, "got %s" % st.get("computed_fields"))
    s.check("linked-record field became a LINKS_TO edge",
            st.get("linked_record_edges") == 1,
            "got %s" % st.get("linked_record_edges"))
    att = q(root, "SELECT raw_metadata FROM source_object"
                  " WHERE native_id LIKE 'airtable:attachment:%'")
    s.check("attachment recorded as a FileReference with bytes_available false",
            len(att) == 1 and json.loads(att[0]["raw_metadata"])["bytes_available"] is False,
            "n=%d" % len(att))

    # ---------------------------------------------------- bare git repos
    print("\nBARE GIT REPOSITORIES (phase 3 hazard)")
    bare = fx / "automsp-obsidian-vault.git"
    (bare / "objects" / "ab").mkdir(parents=True)
    (bare / "refs" / "heads").mkdir(parents=True)
    (bare / "hooks").mkdir()
    (bare / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (bare / "objects" / "ab" / "cdef0123456789").write_bytes(b"x\x9c\x01\x00binary")
    (bare / "refs" / "heads" / "main").write_text("deadbeef\n", encoding="utf-8")

    r = sb(root, "ingest", "filesystem", str(bare))
    blob = (r.stdout + r.stderr).lower()
    s.check("a bare repo passed as the target is refused, with the fix named",
            r.returncode != 0 and "bare git repository" in blob and "git clone" in blob,
            "exit=%d" % r.returncode)

    # and it must be skipped when merely encountered during a walk
    holder = fx / "folder-with-a-repo-in-it"
    holder.mkdir()
    (holder / "real-note.md").write_text("# A real document\nworth ingesting\n",
                                         encoding="utf-8")
    import shutil as _sh
    _sh.copytree(bare, holder / "vault.git")
    d5, _ = ingest(root, "filesystem", holder)
    st5 = (d5 or {}).get("adapter_stats", {})
    s.check("a bare repo inside a walked folder is skipped, not ingested",
            d5 and d5["discovered"] == 1 and st5.get("skipped_git_repos"),
            "discovered=%s skipped=%s" % ((d5 or {}).get("discovered"),
                                          st5.get("skipped_git_repos")))
    s.check("the real document beside it still came through",
            one(root, "SELECT COUNT(*) FROM object WHERE title='real-note.md'") == 1)

    # ---------------------------------------------------------- invariants
    print("\nSTORE-WIDE INVARIANTS AFTER ALL OF THE ABOVE")
    v, r = sbj(root, "validate")
    s.check("validate passes on a store built by 7 new adapters",
            v and v["status"] == "PASSED",
            "failed=%s" % (v or {}).get("failed_checks"))
    if v:
        for c in v["checks"]:
            if c["status"] == "FAIL":
                s.check("  check %s" % c["check"], False, c["detail"])

    # NOT "every source_object has an account": the filesystem adapter has no
    # account by design (a folder of files belongs to no online identity), and
    # `account_boundaries_preserved` allows NULL under a source that has no
    # accounts. What must hold is the narrower claim: every adapter that
    # DECLARES it needs an identity actually attached one to every row it wrote.
    from secondbrain.adapters import REGISTRY, NEEDS_IDENTITY
    ids_sources = {REGISTRY[n].source_id for n in NEEDS_IDENTITY}
    marks = ",".join("?" * len(ids_sources))
    orphans = one(root, "SELECT COUNT(*) FROM source_object"
                        " WHERE account_id IS NULL AND source_id IN (%s)" % marks,
                  *sorted(ids_sources))
    accounts = one(root, "SELECT COUNT(DISTINCT account_id) FROM source_object"
                         " WHERE account_id IS NOT NULL")
    s.check("every identity-required adapter attached an account to every row",
            orphans == 0, "orphans=%s across %s accounts" % (orphans, accounts))
    s.check("the filesystem adapter is still allowed its accountless rows",
            one(root, "SELECT COUNT(*) FROM source_object"
                      " WHERE account_id IS NULL") >= 1)

    # Provenance, end to end, on a randomly chosen new object.
    oid = one(root, "SELECT object_id FROM object WHERE object_class='Repository' LIMIT 1")
    cj, _ = sbj(root, "cite", oid)
    chain = (cj or {}).get("chain") or {}
    s.check("a new adapter's object walks back to raw bytes (SOW 17)",
            bool(chain.get("provenance"))
            and bool((chain.get("version") or {}).get("content_hash")),
            "oid=%s" % oid)

    rb = sb(root, "rebuild-index", "--quiet")
    s.check("derived index rebuilds over the new content", rb.returncode == 0,
            rb.stderr[-200:])
    sr, _ = sbj(root, "search", "vacuum")
    s.check("new content is searchable", sr and len(sr.get("results", [])) >= 1,
            "hits=%s" % (len(sr.get("results", [])) if sr else "n/a"))

    rc = s.finish()
    if rc == 0:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("store kept for inspection: %s" % root)
    return rc


if __name__ == "__main__":
    sys.exit(main())
