"""Evidence plane (SOW 5.1, 18).

Content-addressed blob store. The path IS the sha256, two-level fanout to keep
directory sizes sane. Writes are atomic (temp + rename) and idempotent: storing
the same bytes twice is a no-op that returns the same address.

Nothing in this module can modify or remove an existing blob. That is the
whole point: a failure in AI processing must never destroy the acquired source
(SOW 4).
"""
import hashlib, os, shutil
from pathlib import Path
from .util import now_iso

CHUNK = 1024 * 1024


def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def hash_bytes(b):
    return hashlib.sha256(b).hexdigest()


def blob_path(blobs_root, digest):
    return Path(blobs_root) / digest[:2] / digest[2:4] / digest


def store_file(conn, blobs_root, src, mime=None, job_id=None, copy=True):
    """Put a file into the evidence plane. Returns (content_hash, was_new)."""
    src = Path(src)
    digest = hash_file(src)
    dest = blob_path(blobs_root, digest)
    was_new = not dest.exists()
    if was_new:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp-%d" % os.getpid())
        if copy:
            shutil.copy2(str(src), str(tmp))
        else:
            tmp.write_bytes(src.read_bytes())
        os.replace(str(tmp), str(dest))
        try:
            os.chmod(str(dest), 0o444)      # advisory immutability
        except OSError:
            pass
    conn.execute(
        "INSERT OR IGNORE INTO evidence_blob"
        "(content_hash,byte_size,storage_path,mime_type,first_seen_at,"
        " acquired_by_job,original_filename) VALUES(?,?,?,?,?,?,?)",
        (digest, src.stat().st_size,
         str(dest.relative_to(Path(blobs_root).parent)), mime, now_iso(),
         job_id, src.name))
    return digest, was_new


def store_bytes(conn, blobs_root, data, name=None, mime=None, job_id=None):
    digest = hash_bytes(data)
    dest = blob_path(blobs_root, digest)
    was_new = not dest.exists()
    if was_new:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp-%d" % os.getpid())
        tmp.write_bytes(data)
        os.replace(str(tmp), str(dest))
    conn.execute(
        "INSERT OR IGNORE INTO evidence_blob"
        "(content_hash,byte_size,storage_path,mime_type,first_seen_at,"
        " acquired_by_job,original_filename) VALUES(?,?,?,?,?,?,?)",
        (digest, len(data), str(dest.relative_to(Path(blobs_root).parent)),
         mime, now_iso(), job_id, name))
    return digest, was_new


def verify(conn, blobs_root):
    """Re-hash every blob and report drift. Integrity is checkable, not assumed."""
    ok = missing = corrupt = 0
    problems = []
    for r in conn.execute("SELECT content_hash,byte_size FROM evidence_blob"):
        p = blob_path(blobs_root, r["content_hash"])
        if not p.exists():
            missing += 1; problems.append(("MISSING", r["content_hash"])); continue
        if hash_file(p) != r["content_hash"]:
            corrupt += 1; problems.append(("CORRUPT", r["content_hash"])); continue
        ok += 1
    return {"ok": ok, "missing": missing, "corrupt": corrupt, "problems": problems[:50]}


def find_interrupted_writes(conn, blobs_root):
    """Locate `<hash>.tmp-<pid>` fragments left by processes killed mid-write.

    store_file writes to a temp name and renames, which is what makes the
    evidence plane atomic. The cost is that a SIGKILL - a shell wall-clock
    limit, a closed laptop, an OOM - leaves the fragment behind. No `finally`
    can help: the process is simply gone.

    A fragment is only safe to remove once the blob it was BECOMING exists and
    still hashes correctly. If that blob is absent, the fragment may be the
    only copy of something acquired and must be examined by a human, not swept
    up by a cleanup job. Both cases are reported; only the first is prunable.
    """
    blobs_root = Path(blobs_root)
    known = {r["content_hash"] for r in
             conn.execute("SELECT content_hash FROM evidence_blob")}
    out = []
    if not blobs_root.exists():
        return out
    for root, _dirs, files in os.walk(str(blobs_root)):
        for name in files:
            if ".tmp-" not in name:
                continue
            p = Path(root) / name
            intended = name.split(".tmp-", 1)[0]
            final = blob_path(blobs_root, intended) if len(intended) == 64 else None
            final_ok = False
            if final is not None and final.exists():
                final_ok = (hash_file(final) == intended)
            out.append({
                "path": str(p),
                "bytes": p.stat().st_size,
                "intended_hash": intended,
                "final_blob_present": bool(final is not None and final.exists()),
                "final_blob_verified": final_ok,
                "in_database": intended in known,
                "prunable": bool(final_ok and intended in known),
            })
    return out


def prune_interrupted_writes(conn, blobs_root, findings, actor="human:moiz"):
    """Delete ONLY the fragments proven redundant. Everything is audited."""
    from .events import audit
    removed, freed, refused = [], 0, []
    for f in findings:
        if not f["prunable"]:
            refused.append(f["path"]); continue
        try:
            os.chmod(f["path"], 0o644)
        except OSError:
            pass
        try:
            os.remove(f["path"])
        except OSError as exc:
            refused.append("%s (%s)" % (f["path"], exc)); continue
        removed.append(f["path"]); freed += f["bytes"]
    audit(conn, "storage", "prune_interrupted_writes",
          "OK" if not refused else "PARTIAL", actor=actor,
          detail={"removed": len(removed), "bytes_freed": freed,
                  "refused": refused[:50],
                  "rule": "a fragment is removed only when the blob it was "
                          "becoming exists, re-hashes to its own name, and is "
                          "registered in evidence_blob"})
    conn.commit()
    return removed, freed, refused
