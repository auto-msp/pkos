"""Shared adapter framework (SOW 36, 40, 99).

Every source adapter gets, for free: manifests, checkpointing, idempotency,
failure isolation, a dead-letter queue and provenance. Adapters implement
discover() and acquire_one(); the framework owns the rest.

Acquisition and processing are separated by construction (SOW 4): the
acquisition manifest is written and committed BEFORE any normalization runs,
so a parser crash can never make it look as though nothing was acquired.
"""
import traceback
from .. import ids
from ..events import audit, record_event
from ..util import now_iso, jdump


class AdapterResult:
    def __init__(self):
        self.discovered = 0; self.acquired = 0; self.failed = 0
        self.skipped = 0; self.created = 0; self.versioned = 0; self.unchanged = 0
        self.errors = []

    def as_dict(self):
        return {"discovered": self.discovered, "acquired": self.acquired,
                "failed": self.failed, "skipped": self.skipped,
                "created": self.created, "versioned": self.versioned,
                "unchanged": self.unchanged, "errors": self.errors[:50]}


class BaseAdapter:
    source_id = None
    vendor = None
    display_name = None
    acquisition_method = "filesystem"
    auth_method = "none"

    def __init__(self, conn, paths, account_id=None, workspace_id=None):
        self.conn = conn; self.paths = paths
        self.account_id = account_id; self.workspace_id = workspace_id

    # -- to implement -------------------------------------------------------
    def discover(self, target):
        raise NotImplementedError
    def acquire_one(self, item, job_id):
        raise NotImplementedError

    # -- framework ----------------------------------------------------------
    def ensure_source(self, **kw):
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO source(source_id,vendor,display_name,acquisition_method,"
            "auth_method,state,created_at,updated_at,capability_verified,"
            "privacy_default,licensing_default)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET"
            " updated_at=excluded.updated_at",
            (self.source_id, self.vendor, self.display_name, self.acquisition_method,
             self.auth_method, "DISCOVERED", ts, ts, kw.get("capability_verified", 1),
             kw.get("privacy_default", "PRIVATE"),
             kw.get("licensing_default", "MY_CONTENT")))

    def ensure_account(self, identifier, discovered_via, display_name=None,
                       verified=False):
        """Register an account under this source. SOW 45/46: account identity
        is explicit and never inferred, and boundaries are never collapsed."""
        row = self.conn.execute(
            "SELECT account_id FROM account WHERE source_id=? AND identifier=?",
            (self.source_id, identifier)).fetchone()
        if row:
            return row["account_id"]
        aid = ids.scoped("ACC", 1)
        self.conn.execute(
            "INSERT INTO account(account_id,source_id,identifier,display_name,"
            "discovered_via,verified,state,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (aid, self.source_id, identifier, display_name, discovered_via,
             1 if verified else 0, "DISCOVERED", now_iso()))
        return aid

    def ensure_workspace(self, account_id, kind, identifier, display_name=None,
                         permission_level=None):
        row = self.conn.execute(
            "SELECT workspace_id FROM profile_workspace"
            " WHERE account_id=? AND kind=? AND identifier=?",
            (account_id, kind, identifier)).fetchone()
        if row:
            return row["workspace_id"]
        wid = ids.scoped("WS", 1)
        self.conn.execute(
            "INSERT INTO profile_workspace(workspace_id,account_id,kind,identifier,"
            "display_name,permission_level,created_at) VALUES(?,?,?,?,?,?,?)",
            (wid, account_id, kind, identifier, display_name, permission_level,
             now_iso()))
        return wid

    def set_state(self, state, reason=None):
        self.conn.execute("UPDATE source SET state=?,state_reason=?,updated_at=?"
                          " WHERE source_id=?",
                          (state, reason, now_iso(), self.source_id))

    def dead_letter(self, job_id, item_ref, stage, error):
        self.conn.execute(
            "INSERT INTO dead_letter(dl_id,job_id,item_ref,stage,error,"
            "first_failed_at,last_failed_at) VALUES(?,?,?,?,?,?,?)",
            (ids.scoped("DL", 1), job_id, str(item_ref)[:500], stage,
             str(error)[:2000], now_iso(), now_iso()))

    def run(self, target, limit=None, dry_run=False):
        self.ensure_source()
        job_id = ids.scoped("JOB", 1)
        res = AdapterResult()
        self.conn.execute(
            "INSERT INTO acquisition_manifest(job_id,source_id,account_id,workspace_id,"
            "started_at,raw_location,authentication_method,status)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (job_id, self.source_id, self.account_id, self.workspace_id, now_iso(),
             str(target), self.auth_method, "ACQUIRING"))
        self.set_state("ACQUIRING")
        audit(self.conn, "ingestion", "acquisition_started",
              "OK" if not dry_run else "DRY_RUN", target=str(target), job_id=job_id)
        self.conn.commit()

        try:
            for item in self.discover(target):
                res.discovered += 1
                if limit and res.acquired >= limit:
                    res.skipped += 1; continue
                if dry_run:
                    res.skipped += 1; continue
                try:
                    outcome = self.acquire_one(item, job_id)
                    res.acquired += 1
                    setattr(res, outcome, getattr(res, outcome) + 1)
                    # checkpoint every 200 items so a kill loses at most 200
                    if res.acquired % 200 == 0:
                        self._checkpoint(job_id, res); self.conn.commit()
                except Exception as e:          # SOW 40: isolate, never abort
                    res.failed += 1
                    res.errors.append({"item": str(item)[:200], "error": repr(e)})
                    self.dead_letter(job_id, item, "acquire", traceback.format_exc(limit=3))
            status = ("COMPLETED" if res.failed == 0 else "PARTIALLY_COMPLETED")
            if dry_run:
                status = "SKIPPED"
        except Exception as e:
            status = "FAILED"
            res.errors.append({"item": "<discover>", "error": repr(e)})
            self.dead_letter(job_id, target, "discover", traceback.format_exc(limit=5))

        self._checkpoint(job_id, res, completed=True, status=status)
        self.set_state(status, "%d acquired / %d failed" % (res.acquired, res.failed))
        audit(self.conn, "ingestion", "acquisition_finished", status,
              target=str(target), detail=res.as_dict(), job_id=job_id)
        self.conn.commit()
        return job_id, res, status

    def _checkpoint(self, job_id, res, completed=False, status=None):
        self.conn.execute(
            "UPDATE acquisition_manifest SET items_discovered=?,items_acquired=?,"
            "items_failed=?,items_skipped=?,errors=?,completed_at=?,status=COALESCE(?,status)"
            " WHERE job_id=?",
            (res.discovered, res.acquired, res.failed, res.skipped,
             jdump(res.errors[:50]), now_iso() if completed else None,
             status, job_id))
