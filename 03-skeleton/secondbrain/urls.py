"""Deterministic URL canonicalization (SOW 55).

Produces original_url / normalized_url / canonical_url plus the exact list of
rules applied, so the transformation is auditable and reversible in intent.

Deliberately conservative: normalizing away something that changes resource
identity is worse than leaving a duplicate. We do NOT strip arbitrary query
parameters - only a known tracking allowlist - and we never touch path case.

Two deliberate non-normalizations, both required by SOW 55 ("do not
over-normalize in ways that change resource identity"):
  * http:// and https:// stay DISTINCT urls. They are different URLs. Variants
    are linked afterwards as url-kind duplicates (SOW 19) rather than merged,
    so both identities and the evidence for the link survive.
  * path case is never altered. Many servers are case-sensitive.

KNOWN LIMITATION: a schemeless "host:port/path" string (e.g. "localhost:8080/x")
is rejected as INVALID_HOST, because urlsplit reads "localhost" as the scheme
and the result is genuinely ambiguous. Browser bookmark exports always carry a
scheme, so this does not affect the bookmark pipeline. Recorded here rather
than silently coerced.
"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
    "utm_name","utm_cid","utm_reader","utm_place","utm_brand","utm_social",
    "gclid","gclsrc","dclid","fbclid","msclkid","twclid","igshid","mc_cid",
    "mc_eid","_hsenc","_hsmi","hsCtaTracking","vero_id","vero_conv","yclid",
    "ref_src","ref_url","spm","scm","trk","trkCampaign","sc_channel","sc_campaign",
    "s_kwcid","ei","ved","usg","sa","oi","ct","cd","cad","source",
}
DEFAULT_PORTS = {"http": "80", "https": "443", "ftp": "21"}
INDEX_SUFFIX = re.compile(r"/(index|default)\.(html?|php|aspx?)$", re.I)


def canonicalize(raw):
    rules = []
    original = (raw or "").strip()
    if not original:
        return {"original_url": raw, "normalized_url": None, "canonical_url": None,
                "domain": None, "scheme": None, "rules": ["EMPTY"]}

    u = original
    if u.startswith("//"):
        u = "https:" + u; rules.append("protocol_relative->https")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", u):
        u = "http://" + u; rules.append("added_missing_scheme:http")

    try:
        parts = urlsplit(u)
    except ValueError:
        return {"original_url": original, "normalized_url": None, "canonical_url": None,
                "domain": None, "scheme": None, "rules": ["UNPARSEABLE"]}

    # Reject non-URLs rather than manufacturing one by prepending a scheme.
    # SOW 57: a malformed string is not evidence of a resource.
    raw_host = parts.hostname or ""
    if (not raw_host or " " in raw_host or "\t" in raw_host
            or ("." not in raw_host and raw_host not in ("localhost",))
            or raw_host.startswith(".") or raw_host.endswith(".")
            or ".." in raw_host):
        return {"original_url": original, "normalized_url": None,
                "canonical_url": None, "domain": None, "scheme": None,
                "rules": ["INVALID_HOST"]}

    scheme = (parts.scheme or "").lower()
    if scheme != parts.scheme: rules.append("lowercased_scheme")

    host = (parts.hostname or "").lower()
    if parts.hostname and parts.hostname != host: rules.append("lowercased_host")
    try:
        host_ascii = host.encode("idna").decode("ascii") if host else host
        if host_ascii != host: rules.append("idna_encoded_host"); host = host_ascii
    except (UnicodeError, UnicodeDecodeError):
        pass
    if host.startswith("www.") and host.count(".") > 1:
        host = host[4:]; rules.append("stripped_www")

    netloc = host
    port = parts.port
    if port and str(port) != DEFAULT_PORTS.get(scheme):
        netloc = "%s:%d" % (host, port)
    elif port:
        rules.append("dropped_default_port")
    if parts.username:
        # keep userinfo OUT of the normalized form: it is a credential (SOW 28)
        rules.append("stripped_userinfo")

    path = parts.path or "/"
    if INDEX_SUFFIX.search(path):
        path = INDEX_SUFFIX.sub("/", path); rules.append("stripped_index_suffix")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/"); rules.append("stripped_trailing_slash")
    if not path:
        path = "/"

    kept, dropped = [], []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        (dropped if k.lower() in TRACKING_PARAMS else kept).append((k, v))
    if dropped:
        rules.append("dropped_tracking_params:" + ",".join(sorted({k for k, _ in dropped})))
    kept.sort()
    if kept and [k for k, _ in kept] != [k for k, _ in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]:
        rules.append("sorted_query_params")
    query = urlencode(kept, doseq=True)

    # Fragments are dropped EXCEPT hashbang routes, where the fragment is the
    # resource identity, not a within-page anchor.
    frag = ""
    if parts.fragment:
        if parts.fragment.startswith("!"):
            frag = parts.fragment; rules.append("kept_hashbang_fragment")
        else:
            rules.append("dropped_fragment")

    normalized = urlunsplit((scheme, netloc, path, query, frag))
    return {"original_url": original, "normalized_url": normalized,
            "canonical_url": None,          # only set after a real fetch (SOW 56)
            "domain": host, "scheme": scheme, "rules": rules}


def registrable(domain):
    """Best-effort eTLD+1 WITHOUT the public suffix list (no dependencies).
    Deliberately approximate; flagged as such so nothing downstream treats it
    as authoritative (SOW 107)."""
    if not domain:
        return None
    parts = domain.split(".")
    if len(parts) <= 2:
        return domain
    two = {"co","com","org","net","gov","edu","ac","or","ne","go"}
    if len(parts) >= 3 and parts[-2] in two and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])
