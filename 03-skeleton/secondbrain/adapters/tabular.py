"""CSV-export adapter for LinkedIn and Gumroad (SOW 110 Phases 19 and 16).

Both products hand you a folder of CSVs, so the work is the same: decide what
one ROW is, and give it an identity that survives the next export.

Identity is the whole problem. These exports have no ids in them. LinkedIn's
`Connections.csv` has no connection id; Gumroad's `sales.csv` has an order
number but only sometimes. Keying on row position is the trap -- both products
re-sort and re-paginate between exports, so a position-keyed ingest duplicates
the entire file on the second run while reporting a clean one (SOW 39 says
re-ingesting identical content must create nothing at all). So each known file
declares the COLUMNS that identify a row, and identity is the hash of those
values. A file this adapter does not recognise still gets ingested, keyed on
the hash of the whole row, and is named in `unrecognised_files` so a new export
shape shows up as a finding instead of a silence.

LinkedIn also prefixes several CSVs with a "Notes:" preamble before the real
header, and Gumroad writes a UTF-8 BOM. Both are handled in
`_archive.read_csv_rows`; both otherwise produce one garbage column that then
sits on every object for the next ten years.
"""
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, urls

# file pattern -> (object_class, identity columns, title columns, date column,
#                  classification, memory_type)
SPEC = {
    # ---- LinkedIn -------------------------------------------------------
    "connections":      ("Contact",      ["URL", "First Name", "Last Name", "Company"],
                         ["First Name", "Last Name"], "Connected On", "SENSITIVE", "REFERENCE"),
    "positions":        ("Employment",   ["Company Name", "Title", "Started On"],
                         ["Title", "Company Name"], "Started On", "PRIVATE", "FACT"),
    "education":        ("Education",    ["School Name", "Start Date"],
                         ["School Name", "Degree Name"], "Start Date", "PRIVATE", "FACT"),
    "skills":           ("Skill",        ["Name"], ["Name"], None, "PRIVATE", "FACT"),
    "messages":         ("Message",      ["CONVERSATION ID", "DATE", "FROM", "CONTENT"],
                         ["SUBJECT", "FROM"], "DATE", "SENSITIVE", "OBSERVATION"),
    "shares":           ("Post",         ["Date", "ShareLink", "ShareCommentary"],
                         ["ShareCommentary"], "Date", "PRIVATE", "OBSERVATION"),
    "comments":         ("Comment",      ["Date", "Link", "Message"],
                         ["Message"], "Date", "PRIVATE", "OBSERVATION"),
    "reactions":        ("Reaction",     ["Date", "Link", "Type"],
                         ["Type", "Link"], "Date", "PRIVATE", "OBSERVATION"),
    "invitations":      ("Invitation",   ["From", "To", "Sent At"],
                         ["From", "To"], "Sent At", "SENSITIVE", "OBSERVATION"),
    "company follows":  ("SocialLink",   ["Organization"], ["Organization"],
                         "Followed On", "PRIVATE", "REFERENCE"),
    "recommendations":  ("Recommendation", ["First Name", "Last Name", "Creation Date"],
                         ["First Name", "Last Name"], "Creation Date", "PRIVATE", "OBSERVATION"),
    "saved_items":      ("Bookmark",     ["savedItem"], ["savedItem"], None,
                         "PRIVATE", "REFERENCE"),
    "profile":          ("ProfileFact",  ["First Name", "Last Name", "Headline"],
                         ["Headline"], None, "PRIVATE", "FACT"),
    "learning":         ("Course",       ["Content Title", "Content Completed At"],
                         ["Content Title"], "Content Completed At", "PRIVATE", "REFERENCE"),
    # ---- Gumroad --------------------------------------------------------
    "sales":            ("Sale",         ["Order Number", "Purchase Date", "Buyer Email", "Item Name"],
                         ["Item Name", "Buyer Name"], "Purchase Date", "SENSITIVE", "FACT"),
    "products":         ("Product",      ["Name", "Permalink"], ["Name"],
                         "Published At", "PRIVATE", "FACT"),
    "customers":        ("Contact",      ["Email", "Name"], ["Name", "Email"],
                         "Created At", "SENSITIVE", "REFERENCE"),
    "subscribers":      ("Contact",      ["Email"], ["Email"], "Created At",
                         "SENSITIVE", "REFERENCE"),
}
URL_COLUMNS = ("URL", "Link", "ShareLink", "SharedUrl", "Permalink",
               "SENDER PROFILE URL", "Profile Url", "savedItem")
DATE_FALLBACKS = ("Date", "date", "Created At", "Purchase Date", "Sent At",
                  "Connected On", "Started On")


class TabularExportAdapter(BaseAdapter):
    vendor = "tabular"
    acquisition_method = "export"
    auth_method = "human_download"
    product = "tabular"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"csv_files": 0, "rows": 0, "recognised_files": [],
                      "unrecognised_files": [], "empty_files": [],
                      "urls_recorded": 0, "nested_zips": 0, "empty_globs": []}

    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "%s adapter requires --identity <your account email or "
                "handle>.\nSOW 45/46: account identity is explicit, never "
                "inferred." % self.product)

        root, zips = A.parts(target, "*.zip")
        if zips:
            root = A.unpack(self.conn, self.paths, zips,
                            "%s-export" % self.product, self.stats)
        self._root = root

        self._account = self.ensure_account(
            self.identity,
            discovered_via="operator-declared on `ingest %s`" % self.product,
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, self.product, root.name,
            display_name="%s export" % self.display_name)

        files = A.loud_glob(root, "*.csv", "%s CSVs" % self.product,
                            self.stats, required=True)
        for f in files:
            self.stats["csv_files"] += 1
            evidence.store_file(self.conn, self.paths.blobs, f, mime="text/csv")
            spec = self._spec_for(f)
            (self.stats["recognised_files"] if spec
             else self.stats["unrecognised_files"]).append(f.name)
            rows = A.read_csv_rows(f, self.stats)
            if not rows:
                self.stats["empty_files"].append(f.name)
                continue
            for r in rows:
                self.stats["rows"] += 1
                yield (f, spec, r)

    @staticmethod
    def _spec_for(path):
        stem = path.stem.lower().replace("-", "_").replace(" ", "_")
        for key, spec in SPEC.items():
            k = key.replace(" ", "_")
            if stem == k or stem.startswith(k) or k in stem:
                return spec
        return None

    def acquire_one(self, item, job_id):
        f, spec, row = item
        row = {(k or "").strip(): (v or "").strip()
               for k, v in row.items() if k is not None}
        rel = str(f.relative_to(self._root)).replace("\\", "/")

        if spec:
            cls, id_cols, title_cols, date_col, classification, mtype = spec
            id_basis = [c for c in id_cols if row.get(c)]
            key = "|".join("%s=%s" % (c, row[c]) for c in id_basis)
            title = " ".join(row.get(c, "") for c in title_cols).strip()
            when = A.ts_iso(row.get(date_col)) if date_col else None
        else:
            cls, classification, mtype = "TabularRecord", "PRIVATE", "REFERENCE"
            id_basis = sorted(row)
            key = "|".join("%s=%s" % (c, row[c]) for c in id_basis)
            title = next((v for v in row.values() if v), "")
            when = None

        if not when:
            for c in DATE_FALLBACKS:
                if row.get(c):
                    when = A.ts_iso(row[c])
                    if when:
                        break
        if not key:
            key = "|".join("%s=%s" % (k, row[k]) for k in sorted(row))

        for c in URL_COLUMNS:
            v = row.get(c)
            if v and v.lower().startswith("http"):
                cu = urls.canonicalize(v)
                if cu["normalized_url"]:
                    A.record_url(self.conn, cu, when, title[:200] or None,
                                 {"kind": "referenced", "source_file": str(f),
                                  "raw": {"product": self.product, "column": c}})
                    self.stats["urls_recorded"] += 1

        body = "\n".join("%s: %s" % (k, v) for k, v in row.items() if v)
        return canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace,
            native_id="%s:%s:%s" % (self.product, Path(rel).stem.lower(),
                                    evidence.hash_bytes(key.encode())[:24]),
            object_class=cls,
            content_hash=evidence.hash_bytes(body.encode()),
            title=(title or Path(rel).stem)[:500], body=body or None,
            source_created_at=when, source_modified_at=when, job_id=job_id,
            raw_metadata={"source_file": rel, "product": self.product,
                          "columns": sorted(row),
                          "identity_columns": id_basis,
                          "identity_basis": "declared key columns" if spec
                          else "whole row (file shape not recognised - if this "
                               "export is re-downloaded with different columns, "
                               "these rows will not match)",
                          "row": row},
            classification=classification, license="MY_CONTENT",
            memory_type=mtype, authority="DIRECT PROJECT ARTIFACT",
            actor="job:%s" % job_id)[1]


class LinkedinAdapter(TabularExportAdapter):
    source_id = "SRC-linkedin"
    display_name = "LinkedIn"
    vendor = "linkedin"
    product = "linkedin"


class GumroadAdapter(TabularExportAdapter):
    source_id = "SRC-gumroad"
    display_name = "Gumroad"
    vendor = "gumroad"
    product = "gumroad"
