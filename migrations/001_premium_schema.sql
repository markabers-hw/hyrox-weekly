-- Migration 001: Premium Features Schema
-- Run this to add premium functionality to existing database
-- Date: 2026-01-09

-- =============================================================================
-- UPGRADE EXISTING ATHLETES TABLE
-- =============================================================================

-- Add missing columns to existing athletes table
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS slug VARCHAR(100);
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS country_code CHAR(3);
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS gender VARCHAR(10);
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS tier VARCHAR(50) DEFAULT 'elite_15';
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS youtube_channel_id VARCHAR(255);
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS website_url TEXT;

-- Create index on slug if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_athletes_gender ON athletes(gender);
CREATE INDEX IF NOT EXISTS idx_athletes_tier ON athletes(tier);
CREATE INDEX IF NOT EXISTS idx_athletes_slug ON athletes(slug);

-- Update slug from name for existing athletes (lowercase, hyphenated)
UPDATE athletes SET slug = LOWER(REPLACE(REPLACE(name, ' ', '-'), '''', ''))
WHERE slug IS NULL;

-- Make slug unique after populating
-- ALTER TABLE athletes ADD CONSTRAINT athletes_slug_unique UNIQUE (slug);
-- Note: Running this separately after verifying no duplicates

-- =============================================================================
-- PREMIUM FEATURES SCHEMA
-- =============================================================================

-- Table: subscribers (syncs with Stripe)
CREATE TABLE IF NOT EXISTS subscribers (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    stripe_customer_id VARCHAR(255) UNIQUE,
    stripe_subscription_id VARCHAR(255),
    subscription_status VARCHAR(50) DEFAULT 'none', -- none, active, cancelled, past_due, incomplete
    subscription_tier VARCHAR(50), -- monthly, yearly
    price_cents INTEGER, -- actual price paid (for early bird tracking)
    is_early_bird BOOLEAN DEFAULT false,
    early_bird_number INTEGER,
    magic_link_token VARCHAR(255),
    magic_link_expires_at TIMESTAMP,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancelled_at TIMESTAMP,
    beehiiv_synced BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email);
CREATE INDEX IF NOT EXISTS idx_subscribers_stripe_customer ON subscribers(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscribers_status ON subscribers(subscription_status);
CREATE INDEX IF NOT EXISTS idx_subscribers_early_bird ON subscribers(is_early_bird);

-- Table: athlete_editions (configuration for each athlete's premium page)
CREATE TABLE IF NOT EXISTS athlete_editions (
    id SERIAL PRIMARY KEY,
    athlete_id INTEGER REFERENCES athletes(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'draft', -- draft, published
    overview_text TEXT,
    featured_video_url TEXT,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_athlete_editions_status ON athlete_editions(status);
CREATE INDEX IF NOT EXISTS idx_athlete_editions_athlete ON athlete_editions(athlete_id);

-- Table: performance_topics (for Performance Editions)
CREATE TABLE IF NOT EXISTS performance_topics (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL, -- stations, running, other
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    icon_emoji VARCHAR(10),
    overview_data JSONB, -- flexible data like target times, distances, etc.
    status VARCHAR(50) DEFAULT 'draft', -- draft, published
    display_order INTEGER DEFAULT 0,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_performance_topics_category ON performance_topics(category);
CREATE INDEX IF NOT EXISTS idx_performance_topics_slug ON performance_topics(slug);
CREATE INDEX IF NOT EXISTS idx_performance_topics_status ON performance_topics(status);

-- Table: athlete_content (linking athletes to curated content)
CREATE TABLE IF NOT EXISTS athlete_content (
    id SERIAL PRIMARY KEY,
    athlete_edition_id INTEGER REFERENCES athlete_editions(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    content_type VARCHAR(50), -- video_latest, video_popular, podcast, article
    display_order INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(athlete_edition_id, content_id)
);

CREATE INDEX IF NOT EXISTS idx_athlete_content_edition ON athlete_content(athlete_edition_id);
CREATE INDEX IF NOT EXISTS idx_athlete_content_type ON athlete_content(content_type);

-- Table: performance_content (linking performance topics to curated content)
CREATE TABLE IF NOT EXISTS performance_content (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER REFERENCES performance_topics(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    display_order INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, content_id)
);

CREATE INDEX IF NOT EXISTS idx_performance_content_topic ON performance_content(topic_id);

-- Table: premium_settings (global settings for premium features)
CREATE TABLE IF NOT EXISTS premium_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings (only if table was just created/empty)
INSERT INTO premium_settings (key, value) VALUES
('early_bird_limit', '100'),
('monthly_price_cents', '500'),
('yearly_price_cents', '3900'),
('early_bird_monthly_price_cents', '400'),
('early_bird_yearly_price_cents', '3000')
ON CONFLICT (key) DO NOTHING;

-- Function: Get early bird count
CREATE OR REPLACE FUNCTION get_early_bird_count()
RETURNS INTEGER AS $$
BEGIN
    RETURN (SELECT COUNT(*) FROM subscribers WHERE is_early_bird = true AND subscription_status = 'active');
END;
$$ LANGUAGE plpgsql;

-- Function: Check if early bird pricing is available
CREATE OR REPLACE FUNCTION is_early_bird_available()
RETURNS BOOLEAN AS $$
DECLARE
    limit_val INTEGER;
    current_count INTEGER;
BEGIN
    SELECT value::INTEGER INTO limit_val FROM premium_settings WHERE key = 'early_bird_limit';
    SELECT COUNT(*) INTO current_count FROM subscribers WHERE is_early_bird = true AND subscription_status = 'active';
    RETURN current_count < limit_val;
END;
$$ LANGUAGE plpgsql;

-- View: Subscriber stats for admin dashboard
DROP VIEW IF EXISTS subscriber_stats;
CREATE VIEW subscriber_stats AS
SELECT
    COUNT(*) FILTER (WHERE subscription_status = 'active') as total_active,
    COUNT(*) FILTER (WHERE subscription_status = 'active' AND subscription_tier = 'monthly') as monthly_count,
    COUNT(*) FILTER (WHERE subscription_status = 'active' AND subscription_tier = 'yearly') as yearly_count,
    COUNT(*) FILTER (WHERE is_early_bird = true AND subscription_status = 'active') as early_bird_count,
    (SELECT value::INTEGER FROM premium_settings WHERE key = 'early_bird_limit') -
        COUNT(*) FILTER (WHERE is_early_bird = true AND subscription_status = 'active') as early_bird_remaining
FROM subscribers;

-- View: Athlete edition summary
DROP VIEW IF EXISTS athlete_edition_summary;
CREATE VIEW athlete_edition_summary AS
SELECT
    ae.id,
    ae.status,
    a.name as athlete_name,
    a.slug as athlete_slug,
    a.profile_image_url as photo_url,
    a.country,
    a.gender,
    a.tier,
    COUNT(ac.id) as content_count,
    ae.published_at,
    ae.updated_at
FROM athlete_editions ae
JOIN athletes a ON ae.athlete_id = a.id
LEFT JOIN athlete_content ac ON ae.id = ac.athlete_edition_id
GROUP BY ae.id, a.id
ORDER BY a.tier, a.name;

-- View: Performance topic summary
DROP VIEW IF EXISTS performance_topic_summary;
CREATE VIEW performance_topic_summary AS
SELECT
    pt.id,
    pt.category,
    pt.slug,
    pt.name,
    pt.icon_emoji,
    pt.status,
    pt.display_order,
    COUNT(pc.id) as content_count,
    pt.published_at,
    pt.updated_at
FROM performance_topics pt
LEFT JOIN performance_content pc ON pt.id = pc.topic_id
GROUP BY pt.id
ORDER BY pt.category, pt.display_order;

-- Seed performance topics with the 8 Hyrox stations + extras
INSERT INTO performance_topics (category, slug, name, icon_emoji, display_order) VALUES
-- 8 Stations
('stations', 'ski-erg', 'Ski Erg', '⛷️', 1),
('stations', 'sled-push', 'Sled Push', '🛷', 2),
('stations', 'sled-pull', 'Sled Pull', '🪢', 3),
('stations', 'burpee-broad-jump', 'Burpee Broad Jump', '🤸', 4),
('stations', 'rowing', 'Rowing', '🚣', 5),
('stations', 'farmers-carry', 'Farmers Carry', '🏋️', 6),
('stations', 'sandbag-lunges', 'Sandbag Lunges', '👟', 7),
('stations', 'wall-balls', 'Wall Balls', '🏐', 8),
-- Running
('running', 'pacing', 'Pacing Strategy', '⏱️', 1),
('running', 'transitions', 'Transitions', '🔄', 2),
('running', 'endurance', 'Running Endurance', '🏃', 3),
-- Other
('other', 'programming', 'Training Programming', '📋', 1),
('other', 'recovery', 'Recovery', '🧘', 2),
('other', 'nutrition', 'Nutrition', '🥗', 3),
('other', 'race-day', 'Race Day Strategy', '🏁', 4)
ON CONFLICT (slug) DO NOTHING;
