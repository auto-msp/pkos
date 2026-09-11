-- ===========================================================================
-- PKOS CANONICAL KNOWLEDGE SCHEMA
-- schema_name: pkos.canonical   schema_version: 1.0.0
--
-- AUTHORITY MODEL (SOW 6):   RAW EVIDENCE -> CANONICAL KNOWLEDGE -> DERIVED
-- This file defines the CANONICAL plane only. Nothing here is derived; every
-- table in this file must be reconstructible only from raw evidence + events,
-- never from an index. Derived artefacts live in a separate database that may
-- be deleted and rebuilt at any time (SOW 25, 88).
--
-- PORTABILITY (SOW 7, 124): SQLite is the operational canonical store, but it
-- is NOT the authority of last resort. Every canonical table mirrors to JSONL
-- via `secondbrain export`. If SQLite vanished tomorrow, the JSONL mirror plus
-- the content-addressed evidence blobs fully reconstitute the system.
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------------------
-- SCHEMA REGISTRY (SOW 90) + ID ALLOCATION (SOW 8)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
  schema_name        TEXT NOT NULL,
  schema_version     TEXT NOT NULL,
  applied_at         TEXT NOT NULL,
  migration_path     TEXT,
  compatibility_rules TEXT,
  PRIMARY KEY (schema_name, schema_version)
);

-- Identity is allocated here and NOWHERE else. An object_id must not derive
-- from a path, filename, provider, rowid, vector id or URL (SOW 8), so the
-- sequence is the single allocation point and survives storage migration.
CREATE TABLE IF NOT EXISTS id_sequence (
  prefix   TEXT PRIMARY KEY,
  next_val INTEGER NOT NULL
);

-- --------------------------------------------------------------------------
-- SOURCE IDENTITY (SOW 12, 45, 46)
-- source -> account -> profile/workspace -> source_object -> canonical object
-- Account boundaries are NEVER collapsed, even when content is identical.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source (
  source_id         TEXT PRIMARY KEY,       -- e.g. SRC-google-drive
  vendor            TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  category          TEXT,
  acquisition_method TEXT,                  -- api | export | connector | filesystem | manual
  auth_method       TEXT,
  incremental_sync  TEXT,                   -- supported | unsupported | UNVERIFIED
  privacy_default   TEXT NOT NULL DEFAULT 'PRIVATE',
  licensing_default TEXT NOT NULL DEFAULT 'MY_CONTENT',
  complexity        TEXT,
  state             TEXT NOT NULL DEFAULT 'NOT_STARTED',  -- SOW 96 state machine
  state_reason      TEXT,
  capability_verified INTEGER NOT NULL DEFAULT 0,  -- 0 = UNVERIFIED (SOW 107)
  notes             TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  CHECK (state IN ('NOT_STARTED','DISCOVERED','AWAITING_CREDENTIALS','READY',
                   'ACQUIRING','ACQUIRED','NORMALIZING','ENRICHING','INDEXING',
                   'VALIDATING','COMPLETED','FAILED','BLOCKED',
                   'PARTIALLY_COMPLETED','SKIPPED','REQUIRES_HUMAN_REVIEW')),
  CHECK (privacy_default IN ('PUBLIC','INTERNAL','PRIVATE','SENSITIVE','HIGHLY_SENSITIVE','RESTRICTED'))
);

CREATE TABLE IF NOT EXISTS account (
  account_id     TEXT PRIMARY KEY,
  source_id      TEXT NOT NULL REFERENCES source(source_id),
  identifier     TEXT NOT NULL,             -- email / handle / org slug
  display_name   TEXT,
  discovered_via TEXT NOT NULL,             -- evidence for HOW we know this exists
  verified       INTEGER NOT NULL DEFAULT 0,
  state          TEXT NOT NULL DEFAULT 'DISCOVERED',
  notes          TEXT,
  created_at     TEXT NOT NULL,
  UNIQUE (source_id, identifier)
);

CREATE TABLE IF NOT EXISTS profile_workspace (
  workspace_id  TEXT PRIMARY KEY,
  account_id    TEXT NOT NULL REFERENCES account(account_id),
  kind          TEXT NOT NULL,              -- profile | workspace | base | drive | vault
  identifier    TEXT NOT NULL,
  display_name  TEXT,
  permission_level TEXT,
  created_at    TEXT NOT NULL,
  UNIQUE (account_id, kind, identifier)
);

-- --------------------------------------------------------------------------
-- EVIDENCE PLANE POINTERS (SOW 5.1, 18)
-- The bytes live content-addressed on disk; this table is the index into them.
-- Rows are APPEND-ONLY. A blob is never mutated or deleted by any pipeline.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_blob (
  content_hash   TEXT PRIMARY KEY,          -- sha256 hex - the address
  byte_size      INTEGER NOT NULL,
  storage_path   TEXT NOT NULL,             -- relative to evidence root
  mime_type      TEXT,
  first_seen_at  TEXT NOT NULL,
  acquired_by_job TEXT,
  original_filename TEXT,
  CHECK (length(content_hash) = 64)
);

-- What the source actually handed us, before any interpretation (SOW 4, 12).
CREATE TABLE IF NOT EXISTS source_object (
  source_object_id TEXT PRIMARY KEY,
  source_id      TEXT NOT NULL REFERENCES source(source_id),
  account_id     TEXT REFERENCES account(account_id),
  workspace_id   TEXT REFERENCES profile_workspace(workspace_id),
  native_id      TEXT NOT NULL,             -- the id the SOURCE uses
  native_path    TEXT,
  native_url     TEXT,
  -- content_hash: hash of THIS record's canonical form. Deliberately NOT a
  -- foreign key: a record may be extracted from a larger blob (one bookmark
  -- inside a bookmarks.html) and therefore have no blob of its own.
  content_hash   TEXT,
  -- evidence_hash: WHICH raw blob this record was extracted from. This is the
  -- link back to the evidence plane (SOW 17 provenance chain).
  evidence_hash  TEXT REFERENCES evidence_blob(content_hash),
  source_created_at  TEXT,
  source_modified_at TEXT,
  acquired_at    TEXT NOT NULL,
  acquisition_job_id TEXT,
  raw_metadata   TEXT,                      -- JSON, verbatim from source
  UNIQUE (source_id, account_id, native_id)
);

-- --------------------------------------------------------------------------
-- CANONICAL OBJECT + VERSION (SOW 8, 9, 10, 14, 15, 16)
-- object identity is stable; state changes create VERSIONS, never new ids.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS object (
  object_id       TEXT PRIMARY KEY,         -- KB-00000001
  uuid            TEXT NOT NULL UNIQUE,     -- merge-safe across machines
  object_class    TEXT NOT NULL,            -- SOW 14 vocabulary
  current_version TEXT,                     -- -> object_version.version_id
  title           TEXT,
  memory_type     TEXT,                     -- SOW 15: FACT|BELIEF|HYPOTHESIS|...
  knowledge_state TEXT NOT NULL DEFAULT 'ORIGINAL',  -- SOW 16
  decay_status    TEXT NOT NULL DEFAULT 'CURRENT',   -- SOW 67
  authority       TEXT,                     -- SOW 65
  classification  TEXT NOT NULL DEFAULT 'PRIVATE',   -- SOW 31
  license         TEXT NOT NULL DEFAULT 'MY_CONTENT',-- SOW 85
  retention_class TEXT NOT NULL DEFAULT 'LONG_TERM', -- SOW 118
  lifecycle_state TEXT NOT NULL DEFAULT 'DISCOVERED',-- SOW 117
  is_duplicate_of TEXT REFERENCES object(object_id), -- SOW 19: alias, not deleted
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  CHECK (knowledge_state IN ('ORIGINAL','TRANSFORMED','DERIVED','SYNTHESIZED','INFERRED','HUMAN_VALIDATED')),
  CHECK (decay_status IN ('CURRENT','HISTORICAL','OUTDATED','DEPRECATED','SUPERSEDED','UNVERIFIED','DISPUTED')),
  CHECK (classification IN ('PUBLIC','INTERNAL','PRIVATE','SENSITIVE','HIGHLY_SENSITIVE','RESTRICTED')),
  CHECK (license IN ('MY_CONTENT','LICENSED','PURCHASED','THIRD_PARTY','PUBLIC','DERIVED')),
  CHECK (retention_class IN ('PERMANENT','LONG_TERM','ARCHIVAL','TEMPORARY','REBUILDABLE','EPHEMERAL')),
  CHECK (memory_type IS NULL OR memory_type IN
        ('FACT','BELIEF','HYPOTHESIS','ASSUMPTION','DECISION','PLAN','OBSERVATION',
         'LESSON','IDEA','REFERENCE','PROCEDURE','TEMPLATE'))
);
CREATE INDEX IF NOT EXISTS idx_object_class ON object(object_class);
CREATE INDEX IF NOT EXISTS idx_object_dup   ON object(is_duplicate_of);
CREATE INDEX IF NOT EXISTS idx_object_state ON object(lifecycle_state);

CREATE TABLE IF NOT EXISTS object_version (
  version_id        TEXT PRIMARY KEY,       -- KB-00000001:v01
  object_id         TEXT NOT NULL REFERENCES object(object_id),
  version_num       INTEGER NOT NULL,
  parent_version_id TEXT REFERENCES object_version(version_id),
  created_at        TEXT NOT NULL,
  effective_at      TEXT,
  source_timestamp  TEXT,
  change_type       TEXT NOT NULL,
  changed_by        TEXT NOT NULL,          -- human:moiz | job:<id> | model:<id>
  change_reason     TEXT,
  content_hash      TEXT,                   -- hash of the canonical body
  body              TEXT,                   -- canonical text (NULL for binaries)
  body_ref          TEXT REFERENCES evidence_blob(content_hash),
  schema_version    TEXT NOT NULL,
  validation_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
  UNIQUE (object_id, version_num),
  CHECK (change_type IN ('imported','normalized','corrected','enriched','superseded',
                         'merged','split','archived','restored')),
  CHECK (validation_status IN ('UNVALIDATED','PASSED','PASSED_WITH_EXCEPTIONS','FAILED','REQUIRES_HUMAN_REVIEW'))
);
CREATE INDEX IF NOT EXISTS idx_version_object ON object_version(object_id);

-- --------------------------------------------------------------------------
-- PROVENANCE (SOW 17) - one row per version. This is what makes an ANSWER
-- traceable back to RAW EVIDENCE.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provenance (
  provenance_id     TEXT PRIMARY KEY,
  object_id         TEXT NOT NULL REFERENCES object(object_id),
  version_id        TEXT NOT NULL REFERENCES object_version(version_id),
  source_system     TEXT,
  source_account    TEXT,
  source_profile    TEXT,
  source_workspace  TEXT,
  source_object_id  TEXT REFERENCES source_object(source_object_id),
  source_url        TEXT,
  original_filename TEXT,
  original_path     TEXT,
  source_created_at TEXT,
  source_modified_at TEXT,
  acquired_at       TEXT,
  original_hash     TEXT,
  canonical_hash    TEXT,
  parent_object_id  TEXT,
  parent_version_id TEXT,
  transformation_id TEXT,
  model             TEXT,
  model_version     TEXT,
  prompt_reference  TEXT,
  confidence        REAL,
  validation_status TEXT,
  license           TEXT,
  privacy_classification TEXT
);
CREATE INDEX IF NOT EXISTS idx_prov_object ON provenance(object_id);

-- --------------------------------------------------------------------------
-- EVENT LOG (SOW 11) - append-only. The reproducible history of the system.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
  event_id       TEXT PRIMARY KEY,
  timestamp      TEXT NOT NULL,
  object_id      TEXT,
  actor          TEXT NOT NULL,
  operation      TEXT NOT NULL,
  source         TEXT,
  previous_state TEXT,
  new_state      TEXT,
  reason         TEXT,
  job_id         TEXT,
  model_id       TEXT,
  confidence     REAL,
  CHECK (operation IN ('ACQUIRED','IMPORTED','NORMALIZED','CLASSIFIED','ENRICHED',
                       'REVIEWED','VALIDATED','MODIFIED','MERGED','SPLIT',
                       'SUPERSEDED','ARCHIVED','RESTORED','DELETED'))
);
CREATE INDEX IF NOT EXISTS idx_event_object ON event(object_id);
CREATE INDEX IF NOT EXISTS idx_event_time   ON event(timestamp);

-- --------------------------------------------------------------------------
-- RELATIONSHIPS AS FIRST-CLASS OBJECTS (SOW 13, 70)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS relationship (
  relationship_id   TEXT PRIMARY KEY,
  source_object     TEXT NOT NULL REFERENCES object(object_id),
  target_object     TEXT NOT NULL REFERENCES object(object_id),
  relationship_type TEXT NOT NULL,
  confidence        REAL,
  created_at        TEXT NOT NULL,
  provenance        TEXT,
  created_by        TEXT NOT NULL,
  validation_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
  UNIQUE (source_object, target_object, relationship_type)
);
CREATE INDEX IF NOT EXISTS idx_rel_src ON relationship(source_object);
CREATE INDEX IF NOT EXISTS idx_rel_tgt ON relationship(target_object);

-- --------------------------------------------------------------------------
-- CLAIMS (SOW 66) and CONFLICTS (SOW 20)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim (
  claim_id        TEXT PRIMARY KEY,
  claim_text      TEXT NOT NULL,
  observed_at     TEXT,
  verified_at     TEXT,
  confidence      REAL,
  authority_score REAL,
  status          TEXT NOT NULL DEFAULT 'UNVERIFIED',
  created_by      TEXT NOT NULL,
  created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_evidence (
  claim_id  TEXT NOT NULL REFERENCES claim(claim_id),
  object_id TEXT NOT NULL REFERENCES object(object_id),
  stance    TEXT NOT NULL,        -- supports | contradicts | context
  PRIMARY KEY (claim_id, object_id, stance)
);

-- Conflicts are RECORDED, never silently resolved (SOW 20, 125.12).
CREATE TABLE IF NOT EXISTS conflict (
  conflict_id    TEXT PRIMARY KEY,
  conflict_type  TEXT NOT NULL,
  object_a       TEXT,
  object_b       TEXT,
  detected_at    TEXT NOT NULL,
  detected_by    TEXT NOT NULL,
  description    TEXT,
  resolution_rule TEXT,
  resolved_at    TEXT,
  resolved_by    TEXT,
  resolution_event_id TEXT REFERENCES event(event_id),
  status         TEXT NOT NULL DEFAULT 'OPEN',
  CHECK (status IN ('OPEN','RESOLVED','ACCEPTED_BOTH','REQUIRES_HUMAN_REVIEW'))
);

-- Duplicates are LINKED, never deleted (SOW 19, 125.10).
CREATE TABLE IF NOT EXISTS duplicate_link (
  duplicate_id   TEXT PRIMARY KEY,
  canonical_object TEXT NOT NULL REFERENCES object(object_id),
  alias_object   TEXT NOT NULL REFERENCES object(object_id),
  dedup_kind     TEXT NOT NULL,   -- exact|structural|semantic|version|url|conversation|derived
  evidence       TEXT,
  confidence     REAL,
  detected_at    TEXT NOT NULL,
  detected_by    TEXT NOT NULL,
  UNIQUE (canonical_object, alias_object, dedup_kind)
);

-- --------------------------------------------------------------------------
-- MANIFESTS (SOW 37, 38) - acquisition history is kept SEPARATE from
-- interpretation history, so a bad parse never obscures what was acquired.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acquisition_manifest (
  job_id            TEXT PRIMARY KEY,
  source_id         TEXT NOT NULL REFERENCES source(source_id),
  account_id        TEXT REFERENCES account(account_id),
  workspace_id      TEXT,
  started_at        TEXT NOT NULL,
  completed_at      TEXT,
  items_discovered  INTEGER NOT NULL DEFAULT 0,
  items_acquired    INTEGER NOT NULL DEFAULT 0,
  items_failed      INTEGER NOT NULL DEFAULT 0,
  items_skipped     INTEGER NOT NULL DEFAULT 0,
  raw_location      TEXT,
  checksums         TEXT,
  authentication_method TEXT,
  rate_limit_events INTEGER NOT NULL DEFAULT 0,
  errors            TEXT,
  status            TEXT NOT NULL DEFAULT 'ACQUIRING'
);

CREATE TABLE IF NOT EXISTS processing_manifest (
  processing_job_id TEXT PRIMARY KEY,
  acquisition_job_id TEXT REFERENCES acquisition_manifest(job_id),
  transformations   TEXT,
  model             TEXT,
  model_version     TEXT,
  started_at        TEXT NOT NULL,
  completed_at      TEXT,
  input_count       INTEGER NOT NULL DEFAULT 0,
  output_count      INTEGER NOT NULL DEFAULT 0,
  success_count     INTEGER NOT NULL DEFAULT 0,
  failure_count     INTEGER NOT NULL DEFAULT 0,
  validation_result TEXT,
  status            TEXT NOT NULL DEFAULT 'NORMALIZING'
);

-- Dead-letter queue (SOW 40): a failed item never kills the batch.
CREATE TABLE IF NOT EXISTS dead_letter (
  dl_id       TEXT PRIMARY KEY,
  job_id      TEXT,
  item_ref    TEXT NOT NULL,
  stage       TEXT NOT NULL,
  error       TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 1,
  first_failed_at TEXT NOT NULL,
  last_failed_at  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'PENDING_REVIEW'
);

-- --------------------------------------------------------------------------
-- AUDIT (SOW 35, 95) - separate from `event`: event tracks KNOWLEDGE change,
-- audit tracks SYSTEM action, including actions that touch no object.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_event (
  audit_id    TEXT PRIMARY KEY,
  timestamp   TEXT NOT NULL,
  actor       TEXT NOT NULL,
  category    TEXT NOT NULL,
  action      TEXT NOT NULL,
  target      TEXT,
  outcome     TEXT NOT NULL,
  detail      TEXT,
  job_id      TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_event(timestamp);

-- Credential LIFECYCLE only. Secret VALUES are never stored here (SOW 28, 30).
CREATE TABLE IF NOT EXISTS credential_registry (
  credential_id TEXT PRIMARY KEY,
  label         TEXT NOT NULL,
  owner         TEXT NOT NULL,
  source_id     TEXT REFERENCES source(source_id),
  kind          TEXT NOT NULL,
  storage_location TEXT NOT NULL,   -- WHERE it lives, never WHAT it is
  created_at    TEXT,
  last_rotated  TEXT,
  expiration    TEXT,
  status        TEXT NOT NULL DEFAULT 'ACTIVE',
  notes         TEXT
);

-- --------------------------------------------------------------------------
-- SYNC STATE (SOW 24) - canonical authority is the Ubuntu server; the laptop
-- is a first-class replica. Neither side is silently overwritten (SOW 23).
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_state (
  path          TEXT PRIMARY KEY,
  sync_class    TEXT NOT NULL,     -- A_canonical_text | B_structured_db | C_binary | D_derived | E_secrets
  state         TEXT NOT NULL,
  local_hash    TEXT,
  remote_hash   TEXT,
  base_hash     TEXT,
  last_synced_at TEXT,
  CHECK (state IN ('LOCAL_ONLY','REMOTE_ONLY','SYNCED','MODIFIED_LOCAL','MODIFIED_REMOTE',
                   'CONFLICT','PENDING_UPLOAD','PENDING_DOWNLOAD','VALIDATING','FAILED')),
  CHECK (sync_class IN ('A_canonical_text','B_structured_db','C_binary','D_derived','E_secrets'))
);

-- --------------------------------------------------------------------------
-- HISTORICAL WEB PIPELINE (SOW 53-64)
-- Three distinct objects: the VISIT EVENT, the URL, and the SNAPSHOT.
-- Collapsing them loses the temporal research signal, which is the point.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS url (
  url_id          TEXT PRIMARY KEY,
  original_url    TEXT NOT NULL,
  normalized_url  TEXT NOT NULL,
  canonical_url   TEXT,
  canonicalization_rules TEXT,
  domain          TEXT NOT NULL,
  registrable_domain TEXT,
  scheme          TEXT,
  first_seen      TEXT,
  last_seen       TEXT,
  visit_count     INTEGER NOT NULL DEFAULT 0,
  fetch_status    TEXT NOT NULL DEFAULT 'NOT_FETCHED',
  http_status     INTEGER,
  redirect_chain  TEXT,
  availability    TEXT,
  title           TEXT,
  object_id       TEXT REFERENCES object(object_id),
  CHECK (fetch_status IN ('NOT_FETCHED','FETCHED','SUCCESS','REDIRECTED','NOT_FOUND',
                          'FORBIDDEN','PAYWALLED','AUTH_REQUIRED','RATE_LIMITED',
                          'SERVER_ERROR','TIMEOUT','CONTENT_CHANGED','CONTENT_UNAVAILABLE'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_url_norm ON url(normalized_url);
CREATE INDEX IF NOT EXISTS idx_url_domain ON url(domain);

CREATE TABLE IF NOT EXISTS url_visit (
  history_event_id TEXT PRIMARY KEY,
  url_id        TEXT NOT NULL REFERENCES url(url_id),
  timestamp     TEXT,
  browser       TEXT,
  profile       TEXT,
  source_file   TEXT,
  source_object_id TEXT REFERENCES source_object(source_object_id),
  visit_kind    TEXT NOT NULL DEFAULT 'bookmark',  -- bookmark | history | referenced
  folder_path   TEXT,
  raw_metadata  TEXT
);
CREATE INDEX IF NOT EXISTS idx_visit_url  ON url_visit(url_id);
CREATE INDEX IF NOT EXISTS idx_visit_time ON url_visit(timestamp);

CREATE TABLE IF NOT EXISTS web_snapshot (
  snapshot_id   TEXT PRIMARY KEY,
  url_id        TEXT NOT NULL REFERENCES url(url_id),
  retrieved_at  TEXT NOT NULL,
  final_url     TEXT,
  http_status   INTEGER,
  content_hash  TEXT REFERENCES evidence_blob(content_hash),
  title         TEXT,
  extracted_text_ref TEXT,
  -- SOW 59: never imply we archived a page we merely linked to
  archive_provider  TEXT,
  archive_url       TEXT,
  archive_timestamp TEXT,
  attribution   TEXT NOT NULL DEFAULT 'self'
);

-- --------------------------------------------------------------------------
-- DERIVED-INDEX REGISTRY (SOW 25, 88, 89)
-- The canonical DB records only that a derived artefact EXISTS and whether it
-- is stale. The artefact itself lives elsewhere and is always rebuildable.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS derived_index_registry (
  index_name    TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,     -- fts | vector | graph | rerank | summary
  backend       TEXT NOT NULL,
  model         TEXT,
  model_version TEXT,
  built_at      TEXT,
  source_watermark TEXT,
  object_count  INTEGER,
  status        TEXT NOT NULL DEFAULT 'STALE',
  rebuild_command TEXT NOT NULL,
  CHECK (status IN ('FRESH','STALE','BUILDING','FAILED'))
);
