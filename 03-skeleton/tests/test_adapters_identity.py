"""Account identity is explicit, never inferred (SOW 45/46) - enforced by code.

The account-boundary near-miss (post-mortem 12.1) was not caught by a test. It
was caught by reading the code, after the fact, because nothing had errored.
The fix was to make the code RAISE rather than guess, and the lesson that
generalises is this: every adapter whose export carries no trustworthy account
marker must refuse to run without being told the account.

That property is easy to lose. Someone adds an adapter, forgets the guard,
and the store silently acquires a second person's Notion workspace under the
first person's account. So this suite walks the registry itself rather than a
hand-written list: a new adapter added to NEEDS_IDENTITY is tested
automatically, and an adapter added WITHOUT the guard fails here.
"""
import shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import Suite, sb, sbj, SKEL                      # noqa: E402

sys.path.insert(0, str(SKEL))
from secondbrain.adapters import REGISTRY, NEEDS_IDENTITY, PHASE   # noqa: E402


def main():
    s = Suite("IDENTITY-GUARD")
    tmp = Path(tempfile.mkdtemp(prefix="pkos-ident-"))
    root = tmp / "store"
    sb(root, "init")

    # A target that exists, so the refusal cannot be blamed on a missing path.
    target = tmp / "some-export"
    target.mkdir()
    (target / "placeholder.json").write_text("[]", encoding="utf-8")
    (target / "placeholder.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    print("\nregistry coverage")
    s.check("every adapter has a declared phase",
            set(REGISTRY) == set(PHASE),
            "missing: %s" % (set(REGISTRY) - set(PHASE)))
    s.check("identity-required set is non-empty and a subset of the registry",
            NEEDS_IDENTITY and NEEDS_IDENTITY <= set(REGISTRY),
            "%d adapters" % len(NEEDS_IDENTITY))

    print("\nrefusal without --identity")
    for name in sorted(NEEDS_IDENTITY):
        r = sb(root, "ingest", name, str(target))
        blob = (r.stdout + r.stderr).lower()
        s.check("%s refuses without --identity" % name,
                r.returncode != 0 and "identity" in blob,
                "exit=%d" % r.returncode)

    print("\nnothing was written by any refusal")
    d, _ = sbj(root, "status")
    objects = (d or {}).get("counts", {}).get("objects", None)
    if objects is None:
        from _harness import one
        objects = one(root, "SELECT COUNT(*) FROM object")
    s.check("store still holds zero objects after %d refusals"
            % len(NEEDS_IDENTITY), objects == 0, "objects=%s" % objects)

    rc = s.finish()
    if rc == 0:
        shutil.rmtree(tmp, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
