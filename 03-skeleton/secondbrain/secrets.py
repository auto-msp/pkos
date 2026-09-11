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
