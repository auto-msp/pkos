"""Email adapter, mbox format (SOW 110 Phase 13).

Phase 13 is the one acquisition in this project where a mistake is genuinely
expensive to undo, and the mistake is always the same one: filing mail under
the wrong identity. A person has a work address, a personal address, an old
address they still receive on, and an alias that forwards to another. Ingest
100,000 messages under a merged identity and the damage is not one bad row --
it is that every thread, every counterparty and every date range is now
attributed to a person who did not send it, and unpicking that means
re-deriving identity for every row from headers that were already ambiguous.

So this adapter refuses to run without `--identity`, exactly as the account
boundary near-miss (12.1) taught: the code raises rather than guess. It also
refuses a mailbox whose messages are overwhelmingly *not* addressed to the
declared identity, because that is the signature of pointing it at the wrong
export, and catching it before the write is far cheaper than after.

mbox is the format Google Takeout, Thunderbird and most migration tools emit.
Outlook .pst is deliberately NOT handled here: parsing it needs a dependency,
and the SOW forbids one. Converting .pst to mbox is a step the operator takes,
and is named as such rather than silently unsupported (SOW 107).
"""
import mailbox, re
from email import policy
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, ids
from ..events import audit
from ..util import now_iso

ADDR_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
TEXT_PREF = ("text/plain", "text/html")
# Phrases a text/plain part uses when it is a placeholder for an HTML body.
STUB_RE = re.compile(
    r"(requires?\s+(an?\s+)?html|view\s+(this|the)\s+(e-?mail|message)\s+in|"
    r"plain[\s-]?text\s+version|if\s+you\s+(cannot|can't)\s+(see|read|view)|"
    r"enable\s+html|html[\s-]?capable)", re.I)


class MboxAdapter(BaseAdapter):
    source_id = "SRC-email"
    vendor = "email"
    display_name = "Email (mbox)"
    acquisition_method = "export"
    auth_method = "human_download"

    def __init__(self, *a, identity=None, min_match=0.05, **kw):
        super().__init__(*a, **kw)
        self.identity = (identity or "").strip().lower()
        self.min_match = min_match
        self.stats = {"messages": 0, "with_message_id": 0,
                      "synthesised_ids": 0, "attachments": 0,
                      "attachment_bytes": 0, "threads": 0,
                      "undated": 0, "identity_match_ratio": None,
                      "mailboxes": 0, "empty_globs": []}
        self._oid = {}

    # -- discovery ----------------------------------------------------------
    def discover(self, target):
        if not self.identity or "@" not in self.identity:
            raise SystemExit(
                "mbox adapter requires --identity <your email address>.\n"
                "SOW 45/46: account identity is explicit, never inferred. Mail "
                "is the corpus where an inferred identity is most expensive to "
                "undo -- every thread and counterparty would be attributed to "
                "the wrong person. Name the address this mailbox belongs to.")

        root = Path(target).expanduser().resolve()
        if root.is_file():
            boxes = [root]
        else:
            boxes = A.loud_glob(root, "*.mbox", "mbox mailboxes", self.stats,
                                required=True)
        self.stats["mailboxes"] = len(boxes)

        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest mbox`",
            display_name=self.identity, verified=False)

        for box in boxes:
            evidence.store_file(self.conn, self.paths.blobs, box,
                                mime="application/mbox")
            wsid = self.ensure_workspace(self._account, "mailbox", box.name,
                                         display_name=box.stem)
            mb = mailbox.mbox(str(box), factory=None)

            # Two passes, on purpose. The guard has to decide BEFORE anything is
            # written: a generator that yields as it counts has already handed
            # every message to the framework by the time it works out the
            # mailbox was the wrong one, so the "refusal" refuses nothing and
            # the store is left holding someone else's mail with a non-zero
            # exit code as the only clue. Counting first costs one extra header
            # pass over the file and makes the refusal mean what it says.
            keys = list(mb.keys())
            hits = total = 0
            for key in keys:
                try:
                    msg = mb.get_message(key)
                except Exception:
                    continue
                total += 1
                if self.identity in self._addr_blob(msg):
                    hits += 1
            ratio = (hits / total) if total else 0.0
            self.stats["identity_match_ratio"] = round(ratio, 4)
            self._guard_identity(box, ratio, total, hits)

            for key in keys:
                try:
                    msg = mb.get_message(key)
                except Exception:
                    continue
                self.stats["messages"] += 1
                yield (box, wsid, key, msg)

    def _addr_blob(self, msg):
        return " ".join(str(msg.get(h, "")) for h in
                        ("From", "To", "Cc", "Bcc", "Delivered-To",
                         "X-Original-To", "Return-Path")).lower()

    def _guard_identity(self, box, ratio, total, hits):
        """Refuse a mailbox that plainly is not this person's.

        A real mailbox has the owner's address on nearly every message, as
        sender or recipient. A ratio near zero means the wrong file was named,
        and writing it costs far more than stopping. The threshold is
        deliberately generous: the check exists to catch the obvious mistake,
        not to second-guess an unusual mailbox.
        """
        audit(self.conn, "ingestion", "identity_guard",
              "OK" if ratio >= self.min_match else "REFUSED",
              target=str(box),
              detail={"identity": self.identity, "messages": total,
                      "messages_naming_identity": hits,
                      "ratio": round(ratio, 4), "threshold": self.min_match})
        self.conn.commit()
        if total and ratio < self.min_match:
            raise SystemExit(
                "refusing %s: only %d of %d messages (%.2f%%) name %s in any "
                "address header.\nThat is the signature of the wrong export or "
                "the wrong --identity. Nothing was written. If this mailbox is "
                "genuinely yours (a shared or archived box, say), re-run with "
                "--min-identity-match 0."
                % (box.name, hits, total, ratio * 100, self.identity))

    # -- acquisition --------------------------------------------------------
    def acquire_one(self, item, job_id):
        box, wsid, key, msg = item
        mid = self._header(msg, "Message-ID").strip()
        if mid:
            self.stats["with_message_id"] += 1
            native = "msg:%s" % mid
        else:
            # No Message-ID: synthesise one from content so re-ingest is still
            # idempotent. Keyed on headers + body, never on the mbox offset --
            # offsets shift the moment a message is added or removed, and an
            # offset-keyed identity would duplicate the entire mailbox on the
            # next ingest while reporting a clean run.
            self.stats["synthesised_ids"] += 1
            native = "msg:sha256:%s" % evidence.hash_bytes(
                ("%s|%s|%s|%s" % (self._header(msg, "From"),
                                  self._header(msg, "Subject"),
                                  self._header(msg, "Date"),
                                  self._body(msg)[:4000])).encode())[:32]

        when = self._date(msg)
        if not when:
            self.stats["undated"] += 1
        body = self._body(msg)
        subject = self._header(msg, "Subject") or "(no subject)"
        frm = getaddresses([self._header(msg, "From")])
        to = getaddresses([self._header(msg, "To")])
        cc = getaddresses([self._header(msg, "Cc")])
        atts = self._attachments(msg, job_id)

        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=wsid, native_id=native, object_class="EmailMessage",
            content_hash=evidence.hash_bytes(
                ("%s\n%s\n%s" % (subject, self._header(msg, "From"), body)).encode()),
            title=subject[:500], body=body or None,
            source_created_at=when, source_modified_at=when, job_id=job_id,
            raw_metadata={
                "from": [{"name": n, "address": a} for n, a in frm],
                "to": [a for _n, a in to], "cc": [a for _n, a in cc],
                "message_id": mid or None,
                "in_reply_to": self._header(msg, "In-Reply-To") or None,
                "references": self._header(msg, "References").split() or None,
                "list_id": self._header(msg, "List-Id") or None,
                "mailbox": box.name,
                "direction": ("sent" if any(
                    self.identity == (a or "").lower() for _n, a in frm)
                    else "received"),
                "attachments": atts,
                "body_source": getattr(self, "_body_source", None),
            },
            classification="SENSITIVE", license="MY_CONTENT",
            memory_type="OBSERVATION", authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)

        self._oid[native] = oid
        irt = self._header(msg, "In-Reply-To").strip()
        if irt:
            self._link(oid, "msg:%s" % irt, "REPLY_TO", job_id)
        return outcome

    def _link(self, src_oid, tgt_native, rtype, job_id):
        """Link to a parent that may not be ingested yet.

        Threads arrive out of order, so the parent of a reply is frequently
        later in the mbox or in a different mailbox entirely. Resolving through
        source_object rather than an in-memory map means the edge is written
        whenever both ends exist, in either order, and a genuinely missing
        parent simply produces no edge instead of a false one.
        """
        r = self.conn.execute(
            "SELECT p.object_id FROM source_object so"
            " JOIN provenance p ON p.source_object_id = so.source_object_id"
            " WHERE so.source_id=? AND so.account_id IS ? AND so.native_id=?"
            " LIMIT 1", (self.source_id, self._account, tgt_native)).fetchone()
        if not r or not r["object_id"] or r["object_id"] == src_oid:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO relationship(relationship_id,source_object,"
            "target_object,relationship_type,confidence,created_at,provenance,"
            "created_by,validation_status) VALUES(?,?,?,?,?,?,?,?,?)",
            (ids.scoped("REL", 1), src_oid, r["object_id"], rtype, 1.0,
             now_iso(), "structural: In-Reply-To header, not inferred",
             "job:%s" % job_id, "PASSED"))
        self.stats["threads"] += 1

    # -- header / body helpers ---------------------------------------------
    @staticmethod
    def _header(msg, name):
        raw = msg.get(name)
        if raw is None:
            return ""
        try:
            return str(make_header(decode_header(str(raw))))
        except (UnicodeDecodeError, LookupError, ValueError):
            return str(raw)

    @staticmethod
    def _date(msg):
        raw = msg.get("Date")
        if not raw:
            return None
        try:
            d = parsedate_to_datetime(str(raw))
        except (TypeError, ValueError):
            return None
        if d is None:
            return None
        return A.ts_iso(d.isoformat())

    def _body(self, msg):
        """Return the message text, preferring text/plain -- but not blindly.

        A large share of real mail is HTML with a text/plain part that says
        "This message requires an HTML-capable client" or repeats the subject.
        Preferring text/plain unconditionally stores that stub as the body of
        the message, forever, and the actual content is never indexed and never
        found. Nothing errors; the message is simply empty of meaning.

        So: take text/plain when it is substantive, and fall back to de-tagged
        HTML when the plain part is a stub next to a much richer HTML part.
        Which one was used is recorded on the object, so the choice is
        inspectable rather than a silent guess.
        """
        plain = html = None
        parts = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get_filename():
                    continue
                if part.get_content_type() in TEXT_PREF:
                    parts.append(part)
        else:
            parts = [msg]
        for part in parts:
            text = self._decode(part)
            if text is None:
                continue
            if part.get_content_type() == "text/plain" and plain is None:
                plain = text
            elif part.get_content_type() == "text/html" and html is None:
                html = self._detag(text)

        pw = len((plain or "").split())
        hw = len((html or "").split())
        # A stub is short AND out-weighed by the HTML, or it says outright that
        # it is a stub. Length alone is a bad test: plenty of real mail is four
        # words long, and preferring HTML for those would store a de-tagged,
        # whitespace-mangled copy of a message that was already fine.
        use_html = bool(html) and (
            pw == 0
            or bool(STUB_RE.search(plain or ""))
            or (pw < 40 and hw > pw * 1.5))
        if use_html:
            self._body_source = (
                "text/html (text/plain part was a %d-word stub)" % pw if pw
                else "text/html (no usable text/plain part)")
            return html.strip()[:400000]
        self._body_source = "text/plain" if plain else "none"
        return (plain or "").strip()[:400000]

    @staticmethod
    def _decode(part):
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            return None
        if payload is None:
            return None
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return payload.decode("utf-8", errors="replace")

    @staticmethod
    def _detag(text):
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text,
                      flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;?", " ", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text)

    def _attachments(self, msg, job_id):
        """Store attachment BYTES as evidence. Unlike the Claude export, an
        mbox genuinely carries them, so these are real blobs rather than
        FileReference gaps."""
        out = []
        if not msg.is_multipart():
            return out
        for part in msg.walk():
            name = part.get_filename()
            if not name:
                continue
            try:
                name = str(make_header(decode_header(name)))
            except (UnicodeDecodeError, LookupError, ValueError):
                pass
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                payload = None
            if payload is None:
                out.append({"name": name, "bytes": None, "hash": None,
                            "stored": False,
                            "reason": "part could not be decoded"})
                continue
            digest, _ = evidence.store_bytes(
                self.conn, self.paths.blobs, payload, name=name,
                mime=part.get_content_type(), job_id=job_id)
            self.stats["attachments"] += 1
            self.stats["attachment_bytes"] += len(payload)
            out.append({"name": name, "bytes": len(payload), "hash": digest,
                        "stored": True, "mime": part.get_content_type()})
        return out
