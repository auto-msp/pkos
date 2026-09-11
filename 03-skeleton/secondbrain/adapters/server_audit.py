"""Server audit adapter (SOW 47-52, 102, 110 Phase 1/2).

Consumes the JSON produced by 99-runbooks/pkos-server-audit.sh. The audit
script deliberately emits raw command output; parsing happens HERE so it can be
corrected and re-run without touching production again (SOW 4).
"""
import json
from pathlib import Path
from .base import BaseAdapter
from .. import evidence, canonical
from ..util import now_iso

EXPECTED = ["identity","storage","heatmap","docker","archives","databases",
            "services","scheduled","age_profile","backups","security_surface"]


class ServerAuditAdapter(BaseAdapter):
    source_id = "SRC-oci-servers"
    vendor = "oracle-cloud"
    display_name = "OCI Ubuntu servers"
    acquisition_method = "operator_executed_script"
    auth_method = "human_ssh"

    def discover(self, target):
        p = Path(target).expanduser().resolve()
        files = sorted(p.glob("*.json")) if p.is_dir() else [p]
        if not files:
            raise SystemExit(
                "no audit JSON found at %s\n"
                "Run pkos/99-runbooks/pkos-server-audit.sh on each server and drop the\n"
                "output into pkos/90-evidence/servers/ first. Phase 1 is BLOCKED until then."
                % p)
        for f in files:
            yield f

    def acquire_one(self, path, job_id):
        data = json.loads(path.read_text(encoding="utf-8"))
        host = data.get("host") or path.stem
        digest, _ = evidence.store_file(self.conn, self.paths.blobs, path,
                                        mime="data", job_id=job_id)
        # SOW 45/46: each server is its own workspace under the tenancy account,
        # registered properly rather than referenced by an invented id.
        acct = self.ensure_account(
            "oci-tenancy", discovered_via="server audit script output", verified=False)
        wsid = self.ensure_workspace(acct, "server", host, display_name=host)
        missing = [s for s in EXPECTED if s not in data]
        summary = {
            "host": host,
            "ran_as_root": data.get("ran_as_root"),
            "generated_at_utc": data.get("generated_at_utc"),
            "schema_version": data.get("schema_version"),
            "error_count": data.get("error_count"),
            "missing_sections": missing,
            "low_free_filesystems": _lines(data, "storage", "low_free_filesystems"),
            "df": _lines(data, "storage", "df_bytes"),
            "df_inodes": _lines(data, "storage", "df_inodes"),
            "docker_status": (data.get("docker") or {}).get("status", "present"),
            "scheduled_root_crontab": _lines(data, "scheduled", "root_crontab"),
            "systemd_timers": _lines(data, "scheduled", "systemd_timers"),
        }
        oid, outcome = canonical.ingest_item(
            self.conn, source_id=self.source_id,
            account_id=acct, workspace_id=wsid,
            native_id="server:%s" % host, object_class="Source",
            content_hash=digest, title="Server audit: %s" % host,
            body=json.dumps(summary, indent=2, ensure_ascii=False),
            native_path=str(path),
            source_created_at=data.get("generated_at_utc"),
            source_modified_at=data.get("generated_at_utc"),
            job_id=job_id, raw_metadata=summary, evidence_hash=digest,
            classification="SENSITIVE",       # infra detail is not ordinary PRIVATE
            license="MY_CONTENT", memory_type="OBSERVATION",
            authority="DIRECT PROJECT ARTIFACT", actor="job:%s" % job_id)
        return outcome


def _lines(data, section, key):
    try:
        return (data[section][key] or {}).get("lines", [])[:200]
    except (KeyError, TypeError, AttributeError):
        return []
