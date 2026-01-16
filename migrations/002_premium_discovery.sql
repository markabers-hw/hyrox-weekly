-- Migration: Premium Content Discovery
-- Adds search_terms columns and status tracking for discovery/curation workflow

-- Add search_terms to athletes table
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS search_terms TEXT[];
COMMENT ON COLUMN athletes.search_terms IS 'Array of search terms for content discovery (e.g., name variations, handles)';

-- Add search_terms to performance_topics table
ALTER TABLE performance_topics ADD COLUMN IF NOT EXISTS search_terms TEXT[];
COMMENT ON COLUMN performance_topics.search_terms IS 'Array of search terms for content discovery';

-- Add status to athlete_content for curation workflow
ALTER TABLE athlete_content ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'selected';
COMMENT ON COLUMN athlete_content.status IS 'Curation status: discovered, selected, rejected';

-- Add status to performance_content for curation workflow
ALTER TABLE performance_content ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'selected';
COMMENT ON COLUMN performance_content.status IS 'Curation status: discovered, selected, rejected';

-- Create premium_content_discovery table to track discovery runs
CREATE TABLE IF NOT EXISTS premium_content_discovery (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,  -- 'athlete' or 'topic'
    entity_id INTEGER NOT NULL,
    platform VARCHAR(50) NOT NULL,     -- 'youtube', 'podcast', 'article', 'reddit'
    items_found INTEGER DEFAULT 0,
    items_saved INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'completed',
    error_message TEXT,
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for querying discovery history
CREATE INDEX IF NOT EXISTS idx_premium_discovery_entity
ON premium_content_discovery(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_premium_discovery_run_at
ON premium_content_discovery(run_at DESC);

-- Index for filtering by status in linking tables
CREATE INDEX IF NOT EXISTS idx_athlete_content_status
ON athlete_content(status);

CREATE INDEX IF NOT EXISTS idx_performance_content_status
ON performance_content(status);
