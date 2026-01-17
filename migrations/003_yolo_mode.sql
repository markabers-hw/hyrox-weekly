-- Migration: YOLO Mode
-- Adds selection_method column to track auto vs manual selection

ALTER TABLE content_items ADD COLUMN IF NOT EXISTS selection_method VARCHAR(20) DEFAULT 'manual';
COMMENT ON COLUMN content_items.selection_method IS 'Selection method: manual or yolo (auto-selected)';

-- Index for filtering by selection method
CREATE INDEX IF NOT EXISTS idx_content_selection_method ON content_items(selection_method);
