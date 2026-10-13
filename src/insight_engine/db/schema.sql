PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  source_id            TEXT PRIMARY KEY,
  source_name          TEXT NOT NULL,
  source_type          TEXT NOT NULL,
  original_url         TEXT,
  acquisition_method   TEXT NOT NULL,
  permission_status    TEXT NOT NULL,
  license_note         TEXT,
  allow_local_store    INTEGER NOT NULL DEFAULT 1,
  allow_model_process  INTEGER NOT NULL DEFAULT 0,
  allow_report_export  INTEGER NOT NULL DEFAULT 1,
  retention_policy     TEXT,
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
  batch_id             TEXT PRIMARY KEY,
  source_id            TEXT NOT NULL REFERENCES sources(source_id),
  filename             TEXT,
  content_type         TEXT,
  started_at           TEXT NOT NULL,
  finished_at          TEXT,
  status               TEXT NOT NULL,
  row_count_input      INTEGER,
  row_count_imported   INTEGER,
  row_count_dupes      INTEGER,
  error_summary        TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  document_id          TEXT PRIMARY KEY,
  source_id            TEXT NOT NULL REFERENCES sources(source_id),
  batch_id             TEXT REFERENCES import_batches(batch_id),
  source_type          TEXT,
  source_name          TEXT,
  original_url         TEXT,
  title                TEXT,
  published_at         TEXT,
  collected_at         TEXT NOT NULL,
  content_type         TEXT NOT NULL,
  raw_content          TEXT,
  normalized_content   TEXT,
  content_hash         TEXT NOT NULL,
  url_normalized       TEXT,
  permission_status    TEXT NOT NULL,
  processing_status    TEXT NOT NULL,
  provenance_metadata  TEXT,
  is_duplicate         INTEGER NOT NULL DEFAULT 0,
  duplicate_of         TEXT REFERENCES documents(document_id),
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_published ON documents(published_at);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_batch ON documents(batch_id);
CREATE INDEX IF NOT EXISTS idx_documents_duplicate ON documents(is_duplicate);

CREATE TABLE IF NOT EXISTS import_errors (
  error_id             TEXT PRIMARY KEY,
  batch_id             TEXT NOT NULL REFERENCES import_batches(batch_id),
  row_number           INTEGER,
  field_name           TEXT,
  message              TEXT NOT NULL,
  raw_snippet          TEXT,
  created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_import_errors_batch ON import_errors(batch_id);

-- Standalone FTS index (synced by application code after insert/update).
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
  document_id UNINDEXED,
  title,
  normalized_content,
  source_name
);

-- Phase 2: structured analysis entities
CREATE TABLE IF NOT EXISTS analysis_runs (
  run_id               TEXT PRIMARY KEY,
  started_at           TEXT NOT NULL,
  finished_at          TEXT,
  status               TEXT NOT NULL,
  analyzer_type        TEXT NOT NULL,
  model_name           TEXT,
  prompt_version       TEXT,
  document_count       INTEGER,
  error_summary        TEXT,
  config_json          TEXT
);

CREATE TABLE IF NOT EXISTS model_outputs (
  output_id            TEXT PRIMARY KEY,
  run_id               TEXT NOT NULL REFERENCES analysis_runs(run_id),
  document_id          TEXT REFERENCES documents(document_id),
  output_type          TEXT NOT NULL,
  raw_output           TEXT,
  validated_json       TEXT,
  validation_status    TEXT NOT NULL,
  error_message        TEXT,
  created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  event_id             TEXT PRIMARY KEY,
  event_key            TEXT,
  title                TEXT,
  topic                TEXT,
  event_time           TEXT,
  summary              TEXT,
  confidence           REAL,
  review_status        TEXT NOT NULL DEFAULT 'unreviewed',
  created_by           TEXT NOT NULL,
  run_id               TEXT REFERENCES analysis_runs(run_id),
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic);
CREATE INDEX IF NOT EXISTS idx_events_review ON events(review_status);
CREATE INDEX IF NOT EXISTS idx_events_key ON events(event_key);

CREATE TABLE IF NOT EXISTS claims (
  claim_id             TEXT PRIMARY KEY,
  event_id             TEXT REFERENCES events(event_id),
  document_id          TEXT NOT NULL REFERENCES documents(document_id),
  claim_type           TEXT NOT NULL,
  claim_value          TEXT NOT NULL,
  polarity             TEXT,
  confidence           REAL,
  is_inference         INTEGER NOT NULL DEFAULT 0,
  review_status        TEXT NOT NULL DEFAULT 'unreviewed',
  created_by           TEXT NOT NULL,
  run_id               TEXT REFERENCES analysis_runs(run_id),
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_document ON claims(document_id);
CREATE INDEX IF NOT EXISTS idx_claims_type ON claims(claim_type);
CREATE INDEX IF NOT EXISTS idx_claims_review ON claims(review_status);

CREATE TABLE IF NOT EXISTS evidence_links (
  link_id              TEXT PRIMARY KEY,
  claim_id             TEXT NOT NULL REFERENCES claims(claim_id),
  document_id          TEXT NOT NULL REFERENCES documents(document_id),
  segment_id           TEXT,
  excerpt              TEXT NOT NULL,
  char_start           INTEGER,
  char_end             INTEGER,
  created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_document ON evidence_links(document_id);

CREATE TABLE IF NOT EXISTS human_reviews (
  review_id            TEXT PRIMARY KEY,
  target_type          TEXT NOT NULL,
  target_id            TEXT NOT NULL,
  action               TEXT NOT NULL,
  previous_value       TEXT,
  new_value            TEXT,
  note                 TEXT,
  reviewer             TEXT,
  created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trend_snapshots (
  snapshot_id          TEXT PRIMARY KEY,
  window_days          INTEGER NOT NULL,
  as_of                TEXT NOT NULL,
  metrics_json         TEXT NOT NULL,
  warnings_json        TEXT,
  created_at           TEXT NOT NULL
);

-- Phase 3: media assets and multimodal segments
CREATE TABLE IF NOT EXISTS media_assets (
  media_id             TEXT PRIMARY KEY,
  source_id            TEXT NOT NULL REFERENCES sources(source_id),
  document_id          TEXT REFERENCES documents(document_id),
  file_type            TEXT NOT NULL,
  original_filename    TEXT,
  local_path           TEXT NOT NULL,
  file_hash            TEXT NOT NULL,
  file_size_bytes      INTEGER,
  duration_seconds     REAL,
  width                INTEGER,
  height               INTEGER,
  permission_status    TEXT NOT NULL,
  allowed_processing   TEXT,
  retention_policy     TEXT,
  processing_status    TEXT NOT NULL,
  duplicate_of         TEXT REFERENCES media_assets(media_id),
  is_duplicate         INTEGER NOT NULL DEFAULT 0,
  error_message        TEXT,
  imported_at          TEXT NOT NULL,
  updated_at           TEXT NOT NULL,
  provenance_metadata  TEXT
);

CREATE INDEX IF NOT EXISTS idx_media_hash ON media_assets(file_hash);
CREATE INDEX IF NOT EXISTS idx_media_status ON media_assets(processing_status);

CREATE TABLE IF NOT EXISTS media_processing_runs (
  processing_run_id    TEXT PRIMARY KEY,
  media_id             TEXT NOT NULL REFERENCES media_assets(media_id),
  started_at           TEXT NOT NULL,
  finished_at          TEXT,
  status               TEXT NOT NULL,
  steps_json           TEXT,
  model_name           TEXT,
  model_version        TEXT,
  params_json          TEXT,
  error_summary        TEXT,
  duration_ms          INTEGER
);

CREATE TABLE IF NOT EXISTS media_segments (
  segment_id           TEXT PRIMARY KEY,
  media_id             TEXT NOT NULL REFERENCES media_assets(media_id),
  modality             TEXT NOT NULL,
  start_time           REAL,
  end_time             REAL,
  transcript_text      TEXT,
  subtitle_text        TEXT,
  ocr_text             TEXT,
  keyframe_path        TEXT,
  analysis_model       TEXT,
  confidence           REAL,
  evidence_status      TEXT NOT NULL DEFAULT 'unreviewed',
  source_reference     TEXT,
  processing_run_id    TEXT REFERENCES media_processing_runs(processing_run_id),
  content_hash         TEXT,
  created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_segments_media ON media_segments(media_id);
CREATE INDEX IF NOT EXISTS idx_media_segments_modality ON media_segments(modality);

CREATE TABLE IF NOT EXISTS media_links (
  link_id              TEXT PRIMARY KEY,
  media_id             TEXT NOT NULL REFERENCES media_assets(media_id),
  from_segment_id      TEXT REFERENCES media_segments(segment_id),
  to_segment_id        TEXT REFERENCES media_segments(segment_id),
  link_type            TEXT NOT NULL,
  reason               TEXT,
  score                REAL,
  review_status        TEXT NOT NULL DEFAULT 'auto',
  created_by           TEXT NOT NULL,
  created_at           TEXT NOT NULL,
  revoked_at           TEXT
);

CREATE INDEX IF NOT EXISTS idx_media_links_media ON media_links(media_id);

-- Phase 4: research projects, alerts, reports
CREATE TABLE IF NOT EXISTS research_projects (
  project_id           TEXT PRIMARY KEY,
  name                 TEXT NOT NULL,
  research_question    TEXT,
  target_market        TEXT,
  geo_scope            TEXT,
  time_start           TEXT,
  time_end             TEXT,
  price_min            REAL,
  price_max            REAL,
  source_filters_json  TEXT,
  quality_requirements TEXT,
  notes                TEXT,
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_keyword_versions (
  version_id           TEXT PRIMARY KEY,
  project_id           TEXT NOT NULL REFERENCES research_projects(project_id),
  version_number       INTEGER NOT NULL,
  keywords_json        TEXT NOT NULL,
  synonyms_json        TEXT,
  exclude_keywords_json TEXT,
  change_note          TEXT,
  created_at           TEXT NOT NULL,
  UNIQUE(project_id, version_number)
);

CREATE TABLE IF NOT EXISTS project_runs (
  run_id               TEXT PRIMARY KEY,
  project_id           TEXT NOT NULL REFERENCES research_projects(project_id),
  keyword_version_id   TEXT REFERENCES project_keyword_versions(version_id),
  window_days          INTEGER,
  started_at           TEXT NOT NULL,
  finished_at          TEXT,
  status               TEXT NOT NULL,
  metrics_json         TEXT,
  alert_count          INTEGER,
  report_path          TEXT,
  error_summary        TEXT
);

CREATE TABLE IF NOT EXISTS trend_alerts (
  alert_id             TEXT PRIMARY KEY,
  project_id           TEXT REFERENCES research_projects(project_id),
  run_id               TEXT REFERENCES project_runs(run_id),
  alert_type           TEXT NOT NULL,
  severity             TEXT NOT NULL,
  title                TEXT NOT NULL,
  trigger_reason       TEXT NOT NULL,
  metric_values_json   TEXT,
  compare_window_days  INTEGER,
  sample_size          INTEGER,
  supporting_evidence_json TEXT,
  opposing_evidence_json TEXT,
  quality_notes        TEXT,
  review_suggestion    TEXT,
  review_status        TEXT NOT NULL DEFAULT 'unreviewed',
  created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trend_alerts_project ON trend_alerts(project_id);

CREATE TABLE IF NOT EXISTS report_exports (
  export_id            TEXT PRIMARY KEY,
  project_id           TEXT REFERENCES research_projects(project_id),
  run_id               TEXT REFERENCES project_runs(run_id),
  format               TEXT NOT NULL,
  file_path            TEXT NOT NULL,
  citation_ok          INTEGER NOT NULL DEFAULT 0,
  citation_errors_json TEXT,
  created_at           TEXT NOT NULL
);

-- Public product: anonymous search / report archive (no login required)
CREATE TABLE IF NOT EXISTS search_sessions (
  session_id           TEXT PRIMARY KEY,
  anonymous_id         TEXT,
  mode                 TEXT NOT NULL,
  keywords_json        TEXT NOT NULL,
  research_brief       TEXT,
  collector_ids_json   TEXT,
  document_count       INTEGER,
  unique_document_count INTEGER,
  report_run_id        TEXT,
  report_summary       TEXT,
  metrics_json         TEXT,
  llm_mode             TEXT,
  created_at           TEXT NOT NULL,
  client_meta_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_search_sessions_created ON search_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_search_sessions_anon ON search_sessions(anonymous_id);

-- Local prefs (plaintext) + encrypted secrets (API keys). Encryption key lives in data/.fernet_key
CREATE TABLE IF NOT EXISTS app_prefs (
  pref_key   TEXT PRIMARY KEY,
  pref_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_secrets (
  secret_key   TEXT PRIMARY KEY,
  ciphertext   BLOB NOT NULL,
  updated_at   TEXT NOT NULL
);

-- Async public analysis jobs (continue while user switches pages)
CREATE TABLE IF NOT EXISTS analysis_jobs (
  job_id         TEXT PRIMARY KEY,
  anonymous_id   TEXT,
  status         TEXT NOT NULL,
  message        TEXT,
  progress       REAL NOT NULL DEFAULT 0,
  mode           TEXT NOT NULL,
  params_json    TEXT NOT NULL,
  result_json    TEXT,
  error_message  TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  finished_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_anon_created
  ON analysis_jobs(anonymous_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
