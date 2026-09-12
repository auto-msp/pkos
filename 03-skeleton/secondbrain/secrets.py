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
    # The [text](url) form of markdown reads as "a URL followed by a bracketed
    # blob" and matched every markdown link in the corpus. Require the bracket
    # to hold ONLY the token - no scheme, no slashes, no spaces.
    ("token_beside_url", re.compile(
        r"https?://[^\s()\[\]]{4,}[ \t]*[\(\[][ \t]*"
        r"(?![a-z]+://)[A-Za-z0-9_\-]{24,}[ \t]*[\)\]]")),
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


# --------------------------------------------------------------------------
# Placeholders are not secrets
# --------------------------------------------------------------------------
# A knowledge store that ingests chat logs and config files is full of
# documentation: `postgresql://user:pass@localhost`, `api_key=YOUR_KEY_HERE`,
# `${DB_PASSWORD}`. Those match every credential pattern ever written, and
# treating them as findings buries the real ones - 87 connection-string
# examples hid one live Supabase URL in this store's first real scan. The
# point of filtering them is not tidiness; it is that a finding list nobody
# can read is a finding list nobody acts on.
PLACEHOLDER = re.compile(
    r"(your[_-]?\w*|my[_-]?(user|pass|key|token|secret)|example|sample|dummy|"
    r"placeholder|change[_-]?me|replace[_-]?me|insert[_-]?\w+|xxx+|"
    r"<[^>]{1,40}>|\$\{[^}]{1,40}\}|\$[A-Z_]{3,}|_here\b|here$|"
    r"^(user|username|admin|root|postgres|mysql|redis|test|demo|foo|bar)"
    r"[:/]?(pass|password|passwd|secret|admin|root|postgres|mysql|test|123)?$)",
    re.I)


def looks_placeholder(value):
    """True when a matched span is documentation rather than a credential."""
    v = (value or "").strip()
    if not v:
        return True
    # strip the surrounding syntax so the test sees the value itself
    core = re.sub(r"^[?&]?[A-Za-z_\-]{1,24}=", "", v)
    core = re.sub(r"^://", "", core).rstrip("@")
    if PLACEHOLDER.search(core):
        return True
    # user:pass style pairs where BOTH halves are generic words
    if ":" in core:
        left, _, right = core.partition(":")
        generic = {"user", "username", "pass", "password", "passwd", "admin",
                   "root", "postgres", "mysql", "redis", "test", "demo",
                   "secret", "changeme", "guest", "dbuser", "dbpass"}
        if left.lower() in generic and right.lower().rstrip("@") in generic:
            return True
    return False
def scan_body(body):
    """Credential kinds present in a body, placeholders excluded."""
    if not body:
        return []
    out = []
    for name, rx in PATTERNS:
        for m in rx.finditer(body):
            if looks_placeholder(m.group(0)):
                continue
            out.append(name)
            break
    return out


def scan_spans(body):
    """Every non-placeholder match as (start, end, kind), earliest first.

    Surgical redaction needs the spans, not just the kinds: replacing a whole
    5,000-line config file because one line held an API key removes the key and
    the other 4,999 lines of knowledge with it.
    """
    if not body:
        return []
    spans = []
    for name, rx in PATTERNS:
        for m in rx.finditer(body):
            if not looks_placeholder(m.group(0)):
                spans.append((m.start(), m.end(), name))
    spans.sort()
    merged = []
    for a, b, k in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b), merged[-1][2])
        else:
            merged.append((a, b, k))
    return merged


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
            # Show the first match that is actually a FINDING. Using plain
            # .search() here meant the triage output could display a
            # placeholder as the example for an object that was flagged
            # because of a real secret elsewhere in the same body - the
            # evidence and the verdict disagreeing, which is worse than no
            # evidence at all.
            m = next((x for x in rx.finditer(body)
                      if not looks_placeholder(x.group(0))), None)
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
def redact(conn, findings, actor="human:moiz", surgical=True):
    """Remove credential material from canonical bodies. Evidence never touched.

    Two modes, and the default changed for a reason.

    SURGICAL (default) replaces only the matched spans, leaving the rest of the
    body intact. WHOLE-BODY replaces everything with a marker. The original
    implementation only did whole-body, which is the right instrument when a
    body IS a credential and the wrong one everywhere else: this store's first
    real scan found keys inside deployment notes, docker-compose files and
    long Claude conversations, and blanking those would have destroyed
    thousands of lines of knowledge to remove forty characters. Protecting a
    secret by deleting the document that explains it is not a good trade.

    Either way the object is reclassified RESTRICTED, the change is a new
    version with change_type=corrected, an event is recorded, and the evidence
    blob keeps the original bytes - so the redaction is auditable and
    reversible, never silent (SOW 10, 11, 125.10).
    """
    from .canonical import add_version, add_provenance
    from .events import record_event, audit
    n = 0
    for f in findings:
        oid = f["object_id"]
        prov = conn.execute(
            "SELECT * FROM provenance WHERE object_id=? ORDER BY rowid DESC LIMIT 1",
            (oid,)).fetchone()
        new_body = MARKER + "\ndetected: " + ", ".join(f["kinds"]) + "\n"
        if surgical:
            row = conn.execute(
                "SELECT v.body FROM object o JOIN object_version v"
                " ON v.version_id=o.current_version WHERE o.object_id=?",
                (oid,)).fetchone()
            if row and row["body"]:
                body, out, last = row["body"], [], 0
                for a, b, kind in scan_spans(body):
                    out.append(body[last:a])
                    out.append("[REDACTED:%s]" % kind)
                    last = b
                out.append(body[last:])
                new_body = "".join(out)
        vid = add_version(
            conn, oid, "corrected", actor,
            content_hash=(prov["canonical_hash"] if prov else None),
            body=new_body,
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
    # The derived plane still holds what was just removed from canonical.
    # Redaction rewrites bodies; the FTS index was built from the OLD bodies
    # and keeps every redacted secret fully searchable until it is rebuilt.
    # Nothing errored, canonical was clean, and `validate` passed - which is
    # this project's exact signature failure mode. Mark the indexes stale so
    # the gap is a recorded state rather than something only a person who
    # happened to read the closing line of the redact output would know.
    stale = conn.execute(
        "UPDATE derived_index_registry SET status='STALE'"
        " WHERE status <> 'STALE'").rowcount
    audit(conn, "security", "redact_secrets", "OK",
          actor=actor, detail={"objects": n,
                               "mode": "surgical" if surgical else "whole_body",
                               "derived_indexes_marked_stale": stale,
                               "warning": "the FTS index still contains the "
                                          "redacted text until `rebuild-index` "
                                          "runs"})
    conn.commit()
    return n
