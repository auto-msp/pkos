"""Shared harness for the adapter suites."""
import json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent

# A suite that does an in-process `import secondbrain` (rather than only
# shelling out through sb()) must not depend on the caller having exported
# PYTHONPATH or on cwd happening to be the skeleton root. Setting it for
# subprocesses alone is what made test_smoke and test_adapters_graph pass
# on my machine and fail on Perceptor. Put SKEL on THIS process's path too,
# at harness import, so every suite runs identically from any directory.
if str(SKEL) not in sys.path:
    sys.path.insert(0, str(SKEL))


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
    # Scrub ambient PKOS_* rather than layering over it: the runbook tells the
    # operator to export PKOS_ROOT and PKOS_DERIVED, and an inherited
    # PKOS_DERIVED silently points every test store's derived plane at the real
    # store's. dict(os.environ, ...) looks like it overrides both, and does -
    # but any OTHER PKOS_ var the operator has set still rides along.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PKOS_")}
    env.update(PKOS_ROOT=str(root), PKOS_DERIVED=str(Path(root) / "derived"),
               PYTHONPATH=str(SKEL))
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
