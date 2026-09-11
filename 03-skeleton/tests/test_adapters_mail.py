"""Email ingest (SOW 110 Phase 13) - identity, threading, encodings, attachments.

Phase 13 is the acquisition the SOW singles out as expensive to get wrong, and
the expense is always the same: mail filed under the wrong identity. The guard
tested here is deliberately blunt -- if almost no message in a mailbox names
the declared address in any header, the wrong file or the wrong address was
given, and refusing costs a re-run while accepting costs a re-derivation of
identity across every row.

The other four tests are the quiet corruptions: an RFC 2047 encoded subject
stored as raw `=?UTF-8?B?...?=`, an HTML-only message stored as an empty body,
a message with no Message-ID duplicating itself on every re-ingest, and an
attachment whose bytes are dropped while the store reports success.
"""
import base64, shutil, sys, tempfile
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import Suite, sb, sbj, ingest, q, one            # noqa: E402

ME = "moiz@example.com"


def _msg(frm, to, subject, body, mid=None, irt=None, date=None,
         html=None, attach=None):
    m = EmailMessage()
    m["From"] = frm
    m["To"] = to
    m["Subject"] = subject
    if mid:
        m["Message-ID"] = mid
    if irt:
        m["In-Reply-To"] = irt
    m["Date"] = date or "Mon, 15 Jan 2024 10:00:00 +0000"
    if html is not None:
        m.set_content(body or "This message requires HTML.")
        m.add_alternative(html, subtype="html")
    else:
        m.set_content(body)
    if attach:
        name, data = attach
        m.add_attachment(data, maintype="application", subtype="pdf",
                         filename=name)
    return m


def write_mbox(path, messages):
    with open(path, "wb") as f:
        for m in messages:
            f.write(b"From MAILER-DAEMON Mon Jan 15 10:00:00 2024\n")
            raw = m.as_bytes()
            # mbox escaping: a body line starting with "From " must be quoted
            f.write(raw.replace(b"\nFrom ", b"\n>From "))
            f.write(b"\n\n")


def make_mine(d):
    p = d / "mine"; p.mkdir(parents=True, exist_ok=True)
    box = p / "All mail.mbox"
    write_mbox(box, [
        _msg("amir@acme.test", ME, "Contract for the voice agent pilot",
             "Attaching the MSA.", mid="<a1@acme.test>",
             attach=("msa.pdf", b"%PDF-1.4 fake contract bytes")),
        _msg(ME, "amir@acme.test", "Re: Contract for the voice agent pilot",
             "Signed and returned.", mid="<a2@example.com>",
             irt="<a1@acme.test>",
             date="Mon, 15 Jan 2024 12:00:00 +0000"),
        # RFC 2047 encoded subject - stored raw it is unreadable and unsearchable
        _msg("priya@globex.test", ME,
             "=?UTF-8?B?UsOpc3Vtw6kgZm9yIHRoZSBTdXJhdCByb2xl?=",
             "CV attached separately.", mid="<a3@globex.test>"),
        # HTML-only in practice: text/plain is a stub, the content is in HTML
        _msg("news@vendor.test", ME, "Release notes", "",
             mid="<a4@vendor.test>",
             html="<html><body><h1>v3 shipped</h1>"
                  "<p>VACUUM INTO is now default.</p>"
                  "<script>evil()</script></body></html>"),
        # no Message-ID at all
        _msg("legacy@old.test", ME, "No message id here", "Body of the orphan."),
    ])
    return p


def make_not_mine(d):
    p = d / "someone-else"; p.mkdir(parents=True, exist_ok=True)
    write_mbox(p / "other.mbox", [
        _msg("a@x.test", "b@y.test", "Nothing to do with Moiz", "one",
             mid="<z1@x.test>"),
        _msg("c@x.test", "d@y.test", "Also not his", "two", mid="<z2@x.test>"),
        _msg("e@x.test", "f@y.test", "Nor this", "three", mid="<z3@x.test>"),
    ])
    return p


def main():
    s = Suite("MAIL")
    tmp = Path(tempfile.mkdtemp(prefix="pkos-mail-"))
    root = tmp / "store"
    sb(root, "init")
    fx = tmp / "fx"; fx.mkdir()

    print("\nthe identity guard")
    other = make_not_mine(fx)
    r = sb(root, "ingest", "mbox", str(other), "--identity", ME)
    blob = r.stdout + r.stderr
    s.check("a mailbox that names nobody is refused", r.returncode != 0,
            "exit=%d" % r.returncode)
    s.check("the refusal says how many messages matched",
            "0 of 3" in blob or "0.00%" in blob, blob.strip()[-160:])
    s.check("nothing at all was written by the refusal",
            one(root, "SELECT COUNT(*) FROM object WHERE object_class='EmailMessage'") == 0)
    s.check("the refusal is on the audit trail, not just stderr",
            one(root, "SELECT COUNT(*) FROM audit_event WHERE action='identity_guard'"
                      " AND outcome='REFUSED'") == 1)

    r2 = sb(root, "ingest", "mbox", str(other), "--identity", ME,
            "--min-identity-match", "0")
    s.check("the guard can be overridden deliberately for a shared mailbox",
            r2.returncode == 0,
            (r2.stdout + r2.stderr)[-200:] if r2.returncode else "")

    print("\nhis own mailbox")
    mine = make_mine(fx)
    d, r = ingest(root, "mbox", mine, "--identity", ME)
    s.check("ingest completes", d and d["status"] == "COMPLETED",
            (r.stdout + r.stderr)[-400:] if not d else "")
    st = (d or {}).get("adapter_stats", {})
    s.check("5 messages read", st.get("messages") == 5,
            "got %s" % st.get("messages"))
    s.check("4 had a Message-ID, 1 was given a content-derived id",
            st.get("with_message_id") == 4 and st.get("synthesised_ids") == 1,
            "%s / %s" % (st.get("with_message_id"), st.get("synthesised_ids")))

    print("\nthe quiet corruptions")
    subj = one(root, "SELECT title FROM object WHERE title LIKE '%Surat%'")
    s.check("RFC 2047 encoded subject decoded, not stored as =?UTF-8?B?...",
            subj is not None and "Résumé" in subj, "title=%r" % subj)

    html_body = one(root, "SELECT v.body FROM object o JOIN object_version v"
                          " ON o.current_version=v.version_id"
                          " WHERE o.title LIKE '%Release notes%'")
    s.check("HTML-only message yielded readable text, not an empty body",
            html_body and "VACUUM INTO is now default" in html_body,
            "body=%r" % (html_body or "")[:80])
    s.check("<script> contents stripped rather than stored as text",
            html_body is not None and "evil()" not in html_body)
    src = one(root, "SELECT raw_metadata FROM source_object"
                    " WHERE native_id='msg:<a4@vendor.test>'")
    s.check("the store records WHICH part the body came from",
            src is not None and "text/html" in src, "meta=%r" % (src or "")[:120])
    plain_src = one(root, "SELECT raw_metadata FROM source_object"
                          " WHERE native_id='msg:<a2@example.com>'")
    s.check("an ordinary plain-text message still uses text/plain",
            plain_src is not None and '"body_source": "text/plain"' in plain_src)

    atts = one(root, "SELECT COUNT(*) FROM evidence_blob WHERE original_filename='msa.pdf'")
    s.check("attachment BYTES stored in the evidence plane",
            atts == 1 and st.get("attachments") == 1,
            "blobs=%s stat=%s" % (atts, st.get("attachments")))

    s.check("In-Reply-To became a REPLY_TO edge",
            one(root, "SELECT COUNT(*) FROM relationship"
                      " WHERE relationship_type='REPLY_TO'") == 1)
    s.check("sent vs received derived from the declared identity",
            one(root, "SELECT COUNT(*) FROM source_object"
                      " WHERE raw_metadata LIKE '%\"direction\": \"sent\"%'") == 1)

    print("\nidempotency")
    before = one(root, "SELECT COUNT(*) FROM object WHERE object_class='EmailMessage'")
    d2, _ = ingest(root, "mbox", mine, "--identity", ME)
    after = one(root, "SELECT COUNT(*) FROM object WHERE object_class='EmailMessage'")
    s.check("re-ingest creates nothing, including the message with no "
            "Message-ID", before == after and (d2 or {}).get("created") == 0,
            "before=%s after=%s created=%s"
            % (before, after, (d2 or {}).get("created")))

    print("\ninvariants")
    v, _ = sbj(root, "validate")
    s.check("validate passes", v and v["status"] == "PASSED",
            "failed=%s" % (v or {}).get("failed_checks"))
    s.check("mail is classified SENSITIVE, not ordinary PRIVATE",
            one(root, "SELECT COUNT(*) FROM object WHERE object_class='EmailMessage'"
                      " AND classification<>'SENSITIVE'") == 0)

    rc = s.finish()
    if rc == 0:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("store kept: %s" % root)
    return rc


if __name__ == "__main__":
    sys.exit(main())
