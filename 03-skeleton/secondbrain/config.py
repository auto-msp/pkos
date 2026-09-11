"""Configuration and the three-plane layout (SOW 5).

  evidence/   EVIDENCE PLANE   immutable, content-addressed, append-only
  canonical/  KNOWLEDGE PLANE  the authority: SQLite + JSONL mirror
  derived/    DERIVED PLANE    rebuildable; safe to delete entirely

The separation is physical, not just logical, so that "rm -rf derived/" is a
recoverable operation by construction (SOW 25, 88).
"""
import os
from pathlib import Path

ENV_ROOT = "PKOS_ROOT"
ENV_DERIVED = "PKOS_DERIVED"
DEFAULT_ROOT = Path.home() / ".pkos"


class Paths:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get(ENV_ROOT) or DEFAULT_ROOT).expanduser().resolve()

    @property
    def evidence(self):  return self.root / "evidence"
    @property
    def blobs(self):     return self.evidence / "blobs"
    @property
    def landing(self):   return self.evidence / "landing"
    @property
    def canonical(self): return self.root / "canonical"
    @property
    def db(self):        return self.canonical / "canonical.sqlite3"
    @property
    def mirror(self):    return self.canonical / "mirror"
    @property
    def derived(self):
        """The derived plane may live anywhere (SOW 22 class D: never synced,
        always regenerated). Overriding it via PKOS_DERIVED is not a workaround
        but the intended shape: canonical data belongs on durable, synced,
        possibly restricted storage, while indexes want fast local scratch.

        This mattered in practice. The canonical store here sits on a mount that
        forbids unlink; SQLite cannot create a NEW database there at all, because
        its first commit must delete a rollback journal. Canonical survives
        because it is already in WAL. Rather than weaken the canonical layer to
        suit an index, the index moves. Nothing is lost: `secondbrain
        rebuild-index` reconstructs it from canonical content."""
        import os as _os
        v = _os.environ.get(ENV_DERIVED)
        return Path(v).expanduser().resolve() if v else self.root / "derived"
    @property
    def fts_db(self):    return self.derived / "fts.sqlite3"
    @property
    def logs(self):      return self.root / "logs"
    @property
    def reports(self):   return self.root / "reports"

    def ensure(self):
        for p in (self.evidence, self.blobs, self.landing, self.canonical,
                  self.mirror, self.derived, self.logs, self.reports):
            p.mkdir(parents=True, exist_ok=True)
        # A plain-text marker so the plane boundary is obvious to a human
        # wandering the filesystem in 2036 with no tooling.
        (self.derived / "REBUILDABLE.txt").write_text(
            "Everything under derived/ is a DERIVED ARTEFACT (SOW 25, 88).\n"
            "It can be deleted at any time and rebuilt with:\n"
            "    secondbrain rebuild-index\n"
            "Nothing here is authoritative. Never edit an index as if it were\n"
            "the source of truth.\n", encoding="utf-8")
        # Self-ingestion guard: the filesystem adapter refuses to descend into
        # any directory tree marked by this file, so a store living inside an
        # ingested folder can never ingest itself.
        (self.root / ".pkos-root").write_text(
            "This directory is a PKOS store root. The filesystem adapter will not\n"
            "descend into it. Do not delete this marker.\n", encoding="utf-8")
        (self.evidence / "IMMUTABLE.txt").write_text(
            "Everything under evidence/ is RAW EVIDENCE (SOW 5.1).\n"
            "Append-only. Never modify or delete a blob: canonical knowledge\n"
            "and every derived index trace back to these bytes. Blobs are\n"
            "content-addressed by sha256; the path IS the hash.\n", encoding="utf-8")
        return self
