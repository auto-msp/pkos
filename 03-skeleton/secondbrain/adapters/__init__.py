from .filesystem import FilesystemAdapter
from .bookmarks import BookmarksAdapter
from .server_audit import ServerAuditAdapter
from .claude_export import ClaudeExportAdapter
from .takeout import TakeoutAdapter
from .mbox import MboxAdapter
from .notion import NotionAdapter
from .github_stars import GithubStarsAdapter
from .chatgpt import ChatgptExportAdapter
from .airtable import AirtableAdapter
from .meta_export import InstagramAdapter, FacebookAdapter
from .tabular import LinkedinAdapter, GumroadAdapter
from .obsidian import ObsidianAdapter
from .n8n import N8nAdapter

REGISTRY = {
    "filesystem":    FilesystemAdapter,
    "bookmarks":     BookmarksAdapter,
    "server-audit":  ServerAuditAdapter,
    "claude-export": ClaudeExportAdapter,
    "takeout":       TakeoutAdapter,
    "mbox":          MboxAdapter,
    "notion":        NotionAdapter,
    "github-stars":  GithubStarsAdapter,
    "chatgpt":       ChatgptExportAdapter,
    "airtable":      AirtableAdapter,
    "instagram":     InstagramAdapter,
    "facebook":      FacebookAdapter,
    "linkedin":      LinkedinAdapter,
    "gumroad":       GumroadAdapter,
    "obsidian":      ObsidianAdapter,
    "n8n":           N8nAdapter,
}

# Adapters whose account identity must be stated by the operator (SOW 45/46).
# Being on this list is not a formality: for every one of these, the export
# itself carries no trustworthy marker of which account produced it.
NEEDS_IDENTITY = {"takeout", "mbox", "notion", "github-stars", "chatgpt",
                  "airtable", "instagram", "facebook", "linkedin", "gumroad", "obsidian", "n8n"}

# Which SOW phase each adapter closes, so `secondbrain inventory` and the
# roadmap cannot drift apart silently.
PHASE = {
    "filesystem": "3/6", "bookmarks": "8", "server-audit": "1/2",
    "claude-export": "14", "github-stars": "9", "takeout": "10",
    "notion": "11", "airtable": "12", "mbox": "13", "chatgpt": "15",
    "gumroad": "16", "instagram": "17", "facebook": "18", "linkedin": "19",
    "obsidian": "3", "n8n": "3",
}
