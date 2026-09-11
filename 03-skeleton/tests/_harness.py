"""Shared harness for the adapter suites."""
import json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent


class Suite:
    def __init__(self, name):
        self.name = name
        self.failed = []

    def check(self, label, ok, detail=""):
        print("  [%s] %-56s %s" % ("PASS" if ok else "FAIL", label, detail))
        if not ok:
            self.failed.append("%s: %s" % (label, detail))
        return ok

    def finish(self):
        print("=" * 78)
        if self.failed:
            print("%s FAILED (%d)" % (self.name, len(self.failed)))
            for f in self.failed:
                print("  -", f)
            return 1
        print("ALL %s TESTS PASSED" % self.name)
        return 0


def sb(root, *args):
    env = dict(os.environ, PKOS_ROOT=str(root),
               PKOS_DERIVED=str(root / "derived"), PYTHONPATH=str(SKEL))
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


def sbj(root, *args):
    r = sb(root, "--json", *args)
    try:
        return json.loads(r.stdout), r
    except json.JSONDecodeError:
        return None, r


def ingest(root, adapter, target, *extra):
    return sbj(root, "ingest", adapter, str(target), *extra)


def q(root, sql, *params):
    import sqlite3
    c = sqlite3.connect(str(Path(root) / "canonical" / "canonical.sqlite3"))
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(sql, params)]
    finally:
        c.close()


def one(root, sql, *params):
    rows = q(root, sql, *params)
    return list(rows[0].values())[0] if rows else None
