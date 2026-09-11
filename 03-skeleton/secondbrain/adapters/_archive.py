"""Shared helpers for export-archive adapters (SOW 36, 40).

Every "download your data" archive has the same four problems, and this module
solves each exactly once so eight adapters do not solve it eight ways:

  1. It arrives as a zip, sometimes zips inside zips.
  2. Its filenames are not identity (bug 12.2: two accounts, same filenames,
     one landing directory, a silent cross-account read).
  3. Its timestamps come in six different encodings.
  4. A glob that matches nothing must be LOUD (bug 12.3: `memories.json`
     became `memories/<uuid>.json`, the old glob matched zero files, and all
     15 memory documents vanished with no error at all).

Stdlib only. Nothing here may ever import a third-party package.
"""
import csv, datetime, email.utils, io, json, re, zipfile
from pathlib import Path
from .. import evidence
from ..events import audit


# --------------------------------------------------------------------------
# 1 + 2. Unpacking, keyed on CONTENT
# --------------------------------------------------------------------------

def unpack(conn, paths, zips, prefix, stats=None, nested=True):
    """Extract archive parts into the evidence landing area.

    The landing directory name is derived from the sha256 of the parts, never
    from their filenames. Meta, LinkedIn and Notion all ship exports whose
    top-level filename is identical for every user and every download
    (`facebook-<handle>.zip`, `Basic_LinkedInDataExport.zip`,
    `Export-<uuid>.zip`), so a name-derived key would route two different
    archives to one directory and silently read the first in place of the
    second. Hash first, then choose where to unpack.

    Returns the landing Path. Each zip is stored as a blob BEFORE extraction:
    the archive is the artefact that was actually acquired, and it stays
    byte-exact even if this extraction logic is later found to be wrong.
    """
    stats = stats if stats is not None else {}
    zips = [Path(z) for z in zips]
    part_hashes = {}
    for z in zips:
        digest, _ = evidence.store_file(conn, paths.blobs, z,
                                        mime="application/zip")
        part_hashes[z.name] = digest
    tag = evidence.hash_bytes(
        "|".join("%s:%s" % (n, part_hashes[n])
                 for n in sorted(part_hashes)).encode())[:12]
    work = Path(paths.landing) / ("%s-%s" % (prefix, tag))
    work.mkdir(parents=True, exist_ok=True)

    for z in zips:
        marker = work / (".unpacked-%s-%s" % (z.name, part_hashes[z.name][:12]))
        if marker.exists():
            continue
        _extract_one(z, work, stats)
        marker.write_text("unpacked from %s\n" % z, encoding="utf-8")

    # Notion (and Google Takeout, over ~2 GB) nest zips inside the outer zip.
    # One pass is enough in practice; a second is cheap insurance and the
    # `seen` set makes it terminate.
    if nested:
        seen = set()
        for _round in range(3):
            inner = [p for p in sorted(work.rglob("*.zip")) if p not in seen]
            if not inner:
                break
            for p in inner:
                seen.add(p)
                evidence.store_file(conn, paths.blobs, p, mime="application/zip")
                _extract_one(p, p.parent, stats)
                stats["nested_zips"] = stats.get("nested_zips", 0) + 1

    audit(conn, "ingestion", "archive_unpacked", "OK",
          target=str(zips[0].parent if zips else work),
          detail={"prefix": prefix, "part_hashes": part_hashes,
                  "unpacked_to": str(work), "stats": dict(stats)})
    conn.commit()
    return work


def _extract_one(zpath, dest, stats):
    try:
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    stats["unsafe_zip_entries"] = stats.get("unsafe_zip_entries", 0) + 1
                    continue
                zf.extract(info, str(dest))
    except zipfile.BadZipFile as e:
        raise SystemExit(
            "%s is not a readable zip (%s). The download was probably "
            "truncated. Re-request the export rather than ingesting a "
            "partial archive." % (zpath.name, e))


def parts(target, *patterns):
    """Resolve a target into (root, [zip parts]). Accepts a directory, a single
    zip, or a directory containing multipart zips."""
    root = Path(target).expanduser().resolve()
    if root.is_file() and root.suffix.lower() == ".zip":
        return root.parent, [root]
    if not root.exists():
        raise SystemExit("export path does not exist: %s" % root)
    found = []
    for pat in patterns or ("*.zip",):
        found.extend(sorted(root.glob(pat)))
    return root, sorted(set(found))


# --------------------------------------------------------------------------
# 3. Timestamps
# --------------------------------------------------------------------------

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ts_iso(v):
    """Coerce whatever an export calls a timestamp into ISO 8601 UTC.

    Returns None rather than guessing. Handles: epoch seconds, epoch
    milliseconds, epoch microseconds (Chrome/Takeout uses microseconds since
    1601 in some files and since 1970 in others -- only the 1970 ones reach
    here, `chrome_ts` below handles the other), ISO strings with or without
    a zone, bare dates, and RFC 2822 mail headers.
    """
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
        if n > 1e17:        # microseconds since 1601 leaked in
            return None
        if n > 1e14:        # microseconds since epoch
            n /= 1e6
        elif n > 1e11:      # milliseconds since epoch
            n /= 1e3
        try:
            return datetime.datetime.fromtimestamp(n, datetime.timezone.utc)\
                           .strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError, OverflowError):
            return None
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return ts_iso(int(s))
    if _DATE_RE.match(s):
        return s + "T00:00:00Z"
    if _ISO_RE.match(s):
        t = s.replace(" ", "T")
        t = re.sub(r"\.\d+", "", t)
        if t.endswith("Z"):
            return t
        m = re.search(r"([+-]\d{2}):?(\d{2})$", t)
        if m:
            try:
                d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
                return d.astimezone(datetime.timezone.utc)\
                        .strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                return None
        return t + "Z"
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d is not None:
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return d.astimezone(datetime.timezone.utc)\
                    .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    return None


def chrome_ts(v):
    """Chrome/Edge history timestamps: microseconds since 1601-01-01 UTC.

    Google Takeout's BrowserHistory.json uses this encoding, and treating it
    as epoch seconds silently dates every URL to the year 54000-odd. That is
    exactly the class of error SOW 43 exists for: nothing raises, the numbers
    are simply wrong forever.
    """
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    try:
        base = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
        return (base + datetime.timedelta(microseconds=n))\
            .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# 4. Loud globs
# --------------------------------------------------------------------------

def loud_glob(root, pattern, what, stats=None, required=False):
    """rglob that records a zero-match instead of shrugging at it.

    Bug 12.3 in this project: the Claude export moved `memories.json` to
    `memories/<account-uuid>.json`, the old glob matched nothing, and fifteen
    memory documents were dropped with no error and no warning. A glob is a
    contract with a format that can change underneath you; when it matches
    zero, that is a finding, not a non-event.
    """
    hits = sorted(Path(root).rglob(pattern))
    if not hits:
        if stats is not None:
            stats.setdefault("empty_globs", []).append("%s (%s)" % (pattern, what))
        if required:
            raise SystemExit(
                "expected %s at %s/%s and found none.\n"
                "Either this export does not contain it, or the format has "
                "changed since this adapter was written. Not ingesting "
                "something silently." % (what, root, pattern))
    return hits


# --------------------------------------------------------------------------
# Meta's encoding bug, and CSV reading
# --------------------------------------------------------------------------

def meta_text(s):
    """Undo Meta's double-encoding of UTF-8 in Facebook/Instagram JSON exports.

    Both products write UTF-8 bytes and then JSON-escape each BYTE as though
    it were a codepoint, so "café" arrives as "cafÃ©" and an emoji arrives as
    four mojibake characters. Ingesting it uncorrected means every non-ASCII
    character in years of posts is wrong, and no search will ever match them.
    The fix is to re-interpret the string's codepoints as latin-1 bytes and
    decode them as UTF-8; if that fails, the string was genuinely fine and is
    returned unchanged.
    """
    if not isinstance(s, str):
        return s
    if s.isascii():
        return s
    # Two flavours occur in the wild, depending on which single-byte codec the
    # bytes were misread through before being re-escaped. latin-1 is the common
    # one; cp1252 shows up wherever a Windows tool touched the file, and it is
    # the only one that can carry the curly quotes and em-dashes that are
    # everywhere in real posts. Trying only latin-1 leaves every em-dash
    # mojibake intact while appearing to work, because latin-1 simply refuses
    # those codepoints and the string is returned unchanged.
    for codec in ("latin-1", "cp1252"):
        try:
            fixed = s.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        return fixed
    return s


def meta_walk(o):
    """Apply meta_text to every string in a nested structure."""
    if isinstance(o, str):
        return meta_text(o)
    if isinstance(o, list):
        return [meta_walk(x) for x in o]
    if isinstance(o, dict):
        return {meta_text(k): meta_walk(v) for k, v in o.items()}
    return o


def read_json(path, meta=False):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    data = json.loads(raw.decode("utf-8", errors="replace"))
    return meta_walk(data) if meta else data


def read_csv_rows(path, stats=None):
    """Read a CSV export as dicts, tolerating the preambles real exports ship.

    LinkedIn prefixes several of its CSVs with a "Notes:" block before the
    real header row, and Gumroad writes UTF-8 with a BOM. Both make a naive
    DictReader produce one garbage column, which then becomes a garbage field
    on every object for the next ten years.
    """
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")

    lines = text.splitlines()

    # Find the header by asking which candidate line makes the REST of the file
    # rectangular, rather than by looking for known preamble text. LinkedIn's
    # preamble is a quoted sentence that contains commas, so "the first line
    # with a comma" picks the note and every object then carries one garbage
    # column called "When exporting your connection data...". Rectangularity is
    # a property of a real CSV and does not depend on knowing the vendor.
    start, best = 0, (-1.0, 0)
    for i in range(min(12, len(lines))):
        if not lines[i].strip():
            continue
        try:
            rows = list(csv.reader(io.StringIO("\n".join(lines[i:]))))
        except csv.Error:
            continue
        if not rows:
            continue
        ncol = len(rows[0])
        if ncol < 2 or not any(c.strip() for c in rows[0]):
            continue
        data = [r for r in rows[1:] if any(c.strip() for c in r)]
        score = 1.0 if not data else \
            sum(1 for r in data if len(r) == ncol) / float(len(data))
        if (score, ncol) > best:
            best, start = (score, ncol), i
    if best[0] < 0.5:
        start = 0

    body = "\n".join(lines[start:])
    if not body.strip():
        return []
    rows = list(csv.DictReader(io.StringIO(body)))
    if stats is not None and start:
        stats["csv_preamble_lines_skipped"] = \
            stats.get("csv_preamble_lines_skipped", 0) + start
    return rows


# --------------------------------------------------------------------------
# URL identity, shared by every adapter that carries links
# --------------------------------------------------------------------------

def record_url(conn, canon, when=None, title=None, visit=None):
    """Upsert a URL identity and optionally record one temporal visit.

    SOW 58 keeps three things apart that every browser export collapses into
    one row: the URL as a resource, the visit as an event, and the canonical
    knowledge object. Merging them loses the ability to ask "when did I first
    care about this?" -- which is the entire point of ingesting history rather
    than a link list. Returns (url_id, was_new).
    """
    from .. import ids
    row = conn.execute(
        "SELECT url_id,visit_count,first_seen,last_seen FROM url"
        " WHERE normalized_url=?", (canon["normalized_url"],)).fetchone()
    if row:
        url_id = row["url_id"]; was_new = False
        seen = [x for x in (row["first_seen"], row["last_seen"], when) if x]
        conn.execute("UPDATE url SET visit_count=visit_count+1,first_seen=?,"
                     "last_seen=?,title=COALESCE(title,?) WHERE url_id=?",
                     (min(seen) if seen else None, max(seen) if seen else None,
                      title, url_id))
    else:
        url_id = ids.scoped("URL", 1); was_new = True
        conn.execute(
            "INSERT INTO url(url_id,original_url,normalized_url,canonical_url,"
            "canonicalization_rules,domain,registrable_domain,scheme,first_seen,"
            "last_seen,visit_count,fetch_status,title) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (url_id, canon["original_url"], canon["normalized_url"], None,
             ";".join(canon["rules"]), canon["domain"],
             registrable_domain(canon["domain"]), canon["scheme"],
             when, when, 1, "NOT_FETCHED", title))
    if visit:
        conn.execute(
            "INSERT INTO url_visit(history_event_id,url_id,timestamp,browser,"
            "profile,source_file,visit_kind,folder_path,raw_metadata)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (ids.scoped("VIS", 1), url_id, when, visit.get("browser"),
             visit.get("profile"), visit.get("source_file"),
             visit.get("kind", "history"), visit.get("folder"),
             json.dumps(visit.get("raw"), ensure_ascii=False)
             if visit.get("raw") is not None else None))
    return url_id, was_new


def registrable_domain(domain):
    from .. import urls as _u
    return _u.registrable(domain)
