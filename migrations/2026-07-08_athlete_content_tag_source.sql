-- Phase 1 athlete-tagging: track provenance of athlete_content rows.
-- 'discovery'  = created by premium_discovery.py per-athlete search (existing rows)
-- 'manual'     = tagged by hand in the dashboard
-- 'suggested'  = proposed by suggest_athlete_tags.py, pending confirmation
ALTER TABLE athlete_content
  ADD COLUMN IF NOT EXISTS tag_source VARCHAR(20);

-- Backfill: everything that exists today came from the discovery flow.
UPDATE athlete_content SET tag_source = 'discovery' WHERE tag_source IS NULL;

-- Default for future rows written by tools that don't set it explicitly.
ALTER TABLE athlete_content ALTER COLUMN tag_source SET DEFAULT 'manual';

-- Helpful index for the review-queue and per-athlete tag lookups.
CREATE INDEX IF NOT EXISTS idx_athlete_content_status_source
  ON athlete_content(status, tag_source);
