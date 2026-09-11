"""GitHub Stars adapter (SOW 110 Phase 9).

A starred repository is a dated bookmark with unusually rich metadata: it
records that on a specific day this person found a specific tool worth keeping,
and it carries the language, topics and description that say what kind of
problem they were solving at the time. Against the corpus that is a strong
temporal signal (SOW 60/62) and a cheap one to acquire.

Two JSON shapes are accepted, because the interesting one is not the default:

    gh api --paginate user/starred > stars.json
        -> [ {full_name, html_url, ...}, ... ]        no star date at all

    gh api --paginate -H "Accept: application/vnd.github.star+json" \\
        user/starred > stars.json
        -> [ {starred_at, repo:{...}}, ... ]          WITH the star date

The second form is the one worth having, and an ingest of the first is told so
in plain terms rather than quietly producing a corpus with no dates in it --
undated stars are a link list, and this project already has one of those.
"""
import json
from pathlib import Path

from . import _archive as A
from .base import BaseAdapter
from .. import canonical, evidence, urls


class GithubStarsAdapter(BaseAdapter):
    source_id = "SRC-github-stars"
    vendor = "github"
    display_name = "GitHub starred repositories"
    acquisition_method = "api"
    auth_method = "human_token"

    def __init__(self, *a, identity=None, **kw):
        super().__init__(*a, **kw)
        self.identity = identity
        self.stats = {"repos": 0, "with_star_date": 0, "without_star_date": 0,
                      "archived": 0, "forks": 0, "languages": {},
                      "files_read": 0, "empty_globs": []}

    def discover(self, target):
        if not self.identity:
            raise SystemExit(
                "github-stars adapter requires --identity <your GitHub "
                "login>.\nSOW 45/46: account identity is explicit, never "
                "inferred. `gh api user/starred` output contains the starred "
                "repositories but never names the account that starred them, "
                "so two GitHub accounts' stars would merge with no error.")

        root = Path(target).expanduser().resolve()
        files = [root] if root.is_file() else A.loud_glob(
            root, "*star*.json", "GitHub stars JSON", self.stats, required=True)
        self._account = self.ensure_account(
            self.identity, discovered_via="operator-declared on `ingest github-stars`",
            display_name=self.identity, verified=False)
        self._workspace = self.ensure_workspace(
            self._account, "github", "starred", display_name="Starred repositories")

        total = 0
        for f in files:
            evidence.store_file(self.conn, self.paths.blobs, f,
                                mime="application/json")
            self.stats["files_read"] += 1
            data = A.read_json(f)
            # --paginate concatenates pages; accept a list, or a dict wrapping one
            if isinstance(data, dict):
                data = data.get("items") or data.get("starred") or [data]
            if not isinstance(data, list):
                raise SystemExit(
                    "%s does not contain a JSON array of repositories. Expected "
                    "the output of `gh api --paginate user/starred`." % f.name)
            for entry in data:
                total += 1
                yield (f, entry)

        if total and not self.stats["with_star_date"]:
            # Reported at the end, when the count is known and honest.
            self.stats["star_date_warning"] = (
                "none of the %d entries carried `starred_at`. Re-export with "
                "-H \"Accept: application/vnd.github.star+json\" to get the "
                "date you starred each repo; without it these are undated "
                "bookmarks and contribute nothing to temporal clustering."
                % total)

    def acquire_one(self, item, job_id):
        src, entry = item
        if isinstance(entry, dict) and "repo" in entry and isinstance(entry["repo"], dict):
            starred_at = A.ts_iso(entry.get("starred_at"))
            repo = entry["repo"]
            self.stats["with_star_date"] += 1
        else:
            starred_at = None
            repo = entry
            self.stats["without_star_date"] += 1

        full = repo.get("full_name") or repo.get("name")
        if not full:
            raise ValueError("entry has no full_name: %s" % str(repo)[:160])
        self.stats["repos"] += 1
        if repo.get("archived"):
            self.stats["archived"] += 1
        if repo.get("fork"):
            self.stats["forks"] += 1
        lang = repo.get("language") or "(none)"
        self.stats["languages"][lang] = self.stats["languages"].get(lang, 0) + 1

        html = repo.get("html_url") or ("https://github.com/%s" % full)
        c = urls.canonicalize(html)
        if c["normalized_url"]:
            A.record_url(self.conn, c, starred_at, full,
                         {"kind": "referenced", "source_file": str(src),
                          "raw": {"why": "starred on GitHub"}})

        body = "\n".join(x for x in [
            repo.get("description") or "",
            ("Topics: " + ", ".join(repo.get("topics") or [])) if repo.get("topics") else "",
            ("Language: %s" % repo["language"]) if repo.get("language") else "",
            ("Homepage: %s" % repo["homepage"]) if repo.get("homepage") else "",
        ] if x).strip()

        return canonical.ingest_item(
            self.conn, source_id=self.source_id, account_id=self._account,
            workspace_id=self._workspace, native_id="github:repo:%s" % full.lower(),
            object_class="Repository",
            content_hash=evidence.hash_bytes(
                ("%s\n%s\n%s" % (full, body, starred_at or "")).encode()),
            title=full, body=body or None, native_url=html,
            source_created_at=starred_at or A.ts_iso(repo.get("created_at")),
            source_modified_at=A.ts_iso(repo.get("pushed_at")
                                        or repo.get("updated_at")),
            job_id=job_id,
            raw_metadata={
                "starred_at": starred_at,
                "star_date_present": starred_at is not None,
                "owner": (repo.get("owner") or {}).get("login"),
                "language": repo.get("language"),
                "topics": repo.get("topics") or [],
                "stargazers": repo.get("stargazers_count"),
                "forks": repo.get("forks_count"),
                "archived": bool(repo.get("archived")),
                "is_fork": bool(repo.get("fork")),
                "license": ((repo.get("license") or {}) or {}).get("spdx_id"),
                "repo_created_at": A.ts_iso(repo.get("created_at")),
                "repo_pushed_at": A.ts_iso(repo.get("pushed_at")),
                "default_branch": repo.get("default_branch"),
            },
            classification="PRIVATE", license="THIRD_PARTY",
            memory_type="REFERENCE", authority="UNKNOWN",
            actor="job:%s" % job_id)[1]
