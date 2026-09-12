"""Secret detection and redaction (SOW 28, 31, 32, 125.14).

Hard rule: a secret VALUE must never live in the canonical knowledge layer.
Canonical content is what gets indexed, searched, and eventually handed to a
model — so a credential sitting in an object body is one query away from a log,
a prompt, or a screen.

This is NOT evidence destruction. The redaction applies only to the canonical
BODY. The raw bytes stay untouched in the evidence plane, content-addressed by
their original hash (SOW 5.1), and the redaction itself is recorded as a new
version with change_type='corrected' plus an event, so the change is auditable
and reversible rather than silent (SOW 10, 11, 125.10).
"""
import re
from .util import now_iso

PATTERNS = [
    ("private_key",  re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("putty_key",    re.compile(r"PuTTY-User-Key-File")),
    ("anthropic",    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai",       re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("aws_akid",     re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github",       re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("google_api",   re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("gcp_service",  re.compile(r'"private_key_id"\s*:')),
    ("slack",        re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("telegram_bot", re.compile(r"\b\d{9,10}:AA[A-Za-z0-9_\-]{30,}")),
    ("bearer",       re.compile(r"[Bb]earer\s+[A-Za-z0-9_\-\.]{30,}")),
    ("pem_block",    re.compile(r"-----BEGIN (?:CERTIFICATE|RSA|OPENSSH|EC|DSA)")),

    # Added after GitHub's push protection caught two secrets in a server audit
    # that THIS scanner had passed as clean. One of them - an Anthropic key -
    # we could see and correctly found nowhere in a canonical body. The other,
    # a Notion token, we could not see at all, because there was no Notion
    # pattern: the clean result was true for the patterns that existed and
    # silent about the one that did not. A vendor list is only as good as its
    # last audit, so these come straight off what GitHub detected and what this
    # fleet actually uses.
    ("notion",       re.compile(r"\b(?:secret_[A-Za-z0-9]{43}|ntn_[A-Za-z0-9]{36,})\b")),
    ("airtable_pat", re.compile(r"\bpat[A-Za-z0-9]{14}\.[a-f0-9]{64}\b")),
    ("stripe",       re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("sendgrid",     re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b")),
    ("twilio",       re.compile(r"\bSK[0-9a-f]{32}\b")),
    ("huggingface",  re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("jwt",          re.compile(
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),

    # The patterns above all recognise a VENDOR's key format. That covers the
    # hosted services and misses the self-hosted ones entirely: a bare 48-hex
    # access token sitting next to its own URL is the most common credential
    # shape in this fleet, and it matched nothing at all until an Airtable
    # ingest walked one straight through a passing `no_secret_values_in_bodies`
    # check. These three are deliberately high-precision -- a secret beside its
    # own URL, or named as a secret in a query string -- rather than a general
    # "long hex string" rule. A general rule is untenable HERE specifically:
    # this store is content-addressed, so 64-character hex strings ARE its
    # evidence addresses, and a scanner that flagged them would propose
    # redacting the provenance chain itself.
    ("url_credentials", re.compile(r"://[^/\s:@]{1,64}:[^/\s@]{3,}@")),
    ("query_secret",    re.compile(
        r"[?&](?:token|api[_-]?key|access[_-]?token|auth[_-]?token|secret|"
        r"password|passwd|pwd|signature)=[A-Za-z0-9_\-\.~%]{8,}", re.I)),
    ("token_beside_url", re.compile(
        r"https?://\S{4,}[\s]*[\(\[][\s]*[A-Za-z0-9_\-]{24,}[\s]*[\)\]]")),
    # A data-export download URL is a bearer token for an entire account's
    # history. Single-use and short-lived, but live until claimed - and an
    # export manifest sitting in Downloads gets ingested like any other file.
    ("export_url",   re.compile(r"https://claude\.ai/export/[0-9a-f\-]{8,}/download/[0-9a-f]{16,}")),
]

MARKER = ("[REDACTED BY PKOS — this object contained credential material.\n"
          " The original bytes are preserved in the evidence plane under the\n"
          " content hash recorded in this object's provenance. Retrieve them\n"
          " deliberately; they are deliberately absent from search and from\n"
          " anything a model can read (SOW 28, 32).]\n")


def scan_body(body):
    """Return the list of secret types found in a body, or []."""
    if not body:
        return []
    return [name for name, rx in PATTERNS if rx.search(body)]


def find_all(conn, limit=None):
    """Every current-version object whose body carries secret material."""
    out = []
    q = ("SELECT o.object_id, o.title, o.classification, v.version_id, v.body,"
         "       p.original_path"
         "  FROM object o"
         "  JOIN object_version v ON v.version_id = o.current_version"
         "  LEFT JOIN provenance p ON p.version_id = o.current_version"
         " WHERE v.body IS NOT NULL")
    for r in conn.execute(q):
        kinds = scan_body(r["body"])
        if kinds:
            out.append({"object_id": r["object_id"], "title": r["title"],
                        "path": r["original_path"], "kinds": kinds,
                        "classification": r["classification"],
                        "bytes": len(r["body"])})
            if limit and len(out) >= limit:
                break
    return out


def sample(conn, per_pattern=8, window=44):
    """Show WHAT matched, before anything is redacted (SOW 97: dry run and
    impact report precede the destructive act).

    `redact` rewrites canonical bodies and reclassifies objects RESTRICTED. On
    a corpus of bookmarks and chat logs that is a large, if reversible, act -
    a pattern like `?token=` matches a Google Drive share link exactly as
    happily as it matches a live credential, and a store whose bookmark bodies
    have all been replaced by a redaction marker has lost real knowledge to
    protect nothing. So: look first. This returns the matched span in context,
    with the middle of the match masked, plus the distribution by object class
    and source - which is what actually distinguishes "152 real secrets" from
    "152 URLs in my bookmarks".
    """
    from collections import defaultdict
    examples = defaultdict(list)
    by_class = defaultdict(lambda: defaultdict(int))
    by_source = defaultdict(lambda: defaultdict(int))
    q = ("SELECT o.object_id, o.object_class, v.body, so.source_id"
         "  FROM object o"
         "  JOIN object_version v ON v.version_id = o.current_version"
         "  LEFT JOIN provenance pr ON pr.version_id = o.current_version"
         "  LEFT JOIN source_object so ON so.source_object_id = pr.source_object_id"
         " WHERE v.body IS NOT NULL")
    for r in conn.execute(q):
        body = r["body"]
        for name, rx in PATTERNS:
            m = rx.search(body)
            if not m:
                continue
            by_class[name][r["object_class"] or "?"] += 1
            by_source[name][r["source_id"] or "(none)"] += 1
            if len(examples[name]) < per_pattern:
                a, b = m.span()
                hit = m.group(0)
                masked = (hit[:6] + "\u2026" + hit[-4:]) if len(hit) > 14 else hit
                left = body[max(0, a - window):a].replace("\n", " ")
                right = body[b:b + window].replace("\n", " ")
                examples[name].append({
                    "object_id": r["object_id"],
                    "object_class": r["object_class"],
                    "source_id": r["source_id"],
                    "context": "%s>>%s<<%s" % (left, masked, right)})
    return {"examples": dict(examples),
            "by_class": {k: dict(v) for k, v in by_class.items()},
            "by_source": {k: dict(v) for k, v in by_source.items()}}
def redact(conn, findings, actor="human:moiz"):
    """Replace each body with the marker, reclassify RESTRICTED, version + log.

    Evidence blobs are never touched.
    """
    from .canonical import add_version, add_provenance
    from .events import record_event, audit
    n = 0
    for f in findings:
        oid = f["object_id"]
        prov = conn.execute(
            "SELECT * FROM provenance WHERE object_id=? ORDER BY rowid DESC LIMIT 1",
            (oid,)).fetchone()
        vid = add_version(
            conn, oid, "corrected", actor,
            content_hash=(prov["canonical_hash"] if prov else None),
            body=MARKER + "\ndetected: " + ", ".join(f["kinds"]) + "\n",
            change_reason="credential material removed from canonical body "
                          "(SOW 28); raw bytes retained in the evidence plane",
            validation_status="PASSED")
        add_provenance(conn, oid, vid,
                       source_system=(prov["source_system"] if prov else None),
                       source_object_id=(prov["source_object_id"] if prov else None),
                       original_path=(prov["original_path"] if prov else None),
                       original_hash=(prov["original_hash"] if prov else None),
                       canonical_hash=(prov["canonical_hash"] if prov else None),
                       acquired_at=now_iso(), validation_status="PASSED",
                       privacy_classification="RESTRICTED")
        conn.execute("UPDATE object SET classification='RESTRICTED',"
                     " retention_class='PERMANENT', updated_at=? WHERE object_id=?",
                     (now_iso(), oid))
        record_event(conn, "MODIFIED", oid, actor=actor,
                     previous_state=f["classification"], new_state="RESTRICTED",
                     reason="secret redaction: " + ",".join(f["kinds"]))
        n += 1
    audit(conn, "security", "redact_secrets", "OK",
          actor=actor, detail={"objects": n})
    conn.commit()
    return n
