-- Migration: Add content discovery tables to Supabase
-- Run this in Supabase SQL Editor

-- Table: creators (content creators/sources)
CREATE TABLE IF NOT EXISTS creators (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    platform_id VARCHAR(255),
    follower_count INTEGER,
    credibility_score DECIMAL(3,2) DEFAULT 0.5,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_id)
);

-- Table: content_items (discovered content)
CREATE TABLE IF NOT EXISTS content_items (
    id SERIAL PRIMARY KEY,
    creator_id INTEGER REFERENCES creators(id),
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    platform VARCHAR(50) NOT NULL,
    content_type VARCHAR(50),
    published_date TIMESTAMP,
    discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds INTEGER,
    thumbnail_url TEXT,
    view_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    engagement_score DECIMAL(10,2),
    category VARCHAR(50),
    status VARCHAR(20) DEFAULT 'discovered',
    editorial_note TEXT,
    custom_description TEXT,
    ai_description TEXT,
    use_ai_description BOOLEAN DEFAULT false,
    display_order INTEGER DEFAULT 0,
    selected_for_edition_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_content_published_date ON content_items(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_content_status ON content_items(status);
CREATE INDEX IF NOT EXISTS idx_content_engagement ON content_items(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_content_platform ON content_items(platform);

-- Table: weekly_editions (published newsletters)
CREATE TABLE IF NOT EXISTS weekly_editions (
    id SERIAL PRIMARY KEY,
    edition_number INTEGER NOT NULL UNIQUE,
    publish_date DATE NOT NULL,
    week_start_date DATE NOT NULL,
    week_end_date DATE NOT NULL,
    headline TEXT,
    intro_text TEXT,
    status VARCHAR(20) DEFAULT 'draft',
    beehiiv_post_id VARCHAR(255),
    beehiiv_url TEXT,
    subscriber_count INTEGER,
    open_count INTEGER,
    click_count INTEGER,
    open_rate DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: edition_content (many-to-many: which content in which edition)
CREATE TABLE IF NOT EXISTS edition_content (
    id SERIAL PRIMARY KEY,
    edition_id INTEGER REFERENCES weekly_editions(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL,
    section VARCHAR(50),
    is_featured BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edition_id, content_id)
);

CREATE INDEX IF NOT EXISTS idx_edition_content_edition ON edition_content(edition_id);
CREATE INDEX IF NOT EXISTS idx_edition_content_order ON edition_content(edition_id, display_order);

-- Table: discovery_runs (track scraping jobs)
CREATE TABLE IF NOT EXISTS discovery_runs (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    items_discovered INTEGER DEFAULT 0,
    items_new INTEGER DEFAULT 0,
    status VARCHAR(20),
    error_message TEXT,
    execution_time_seconds INTEGER,
    search_query TEXT,
    date_range_start DATE,
    date_range_end DATE
);

-- Table: content_categories
CREATE TABLE IF NOT EXISTS content_categories (
    name VARCHAR(50) PRIMARY KEY,
    description TEXT,
    display_order INTEGER
);

INSERT INTO content_categories (name, description, display_order) VALUES
('training', 'Training tips, workout guides, programming', 1),
('race_recap', 'Race results, athlete performances, event coverage', 2),
('technique', 'Form guides, movement tutorials', 3),
('nutrition', 'Diet, supplements, fueling strategies', 4),
('gear', 'Equipment reviews, gear recommendations', 5),
('athlete_profile', 'Athlete interviews, stories, journeys', 6),
('news', 'Hyrox news, announcements, community updates', 7),
('other', 'General Hyrox content', 8)
ON CONFLICT (name) DO NOTHING;

-- Table: athlete_editions (configuration for each athlete's premium page)
CREATE TABLE IF NOT EXISTS athlete_editions (
    id SERIAL PRIMARY KEY,
    athlete_id INTEGER REFERENCES athletes(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'draft',
    overview_text TEXT,
    featured_video_url TEXT,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_athlete_editions_status ON athlete_editions(status);
CREATE INDEX IF NOT EXISTS idx_athlete_editions_athlete ON athlete_editions(athlete_id);

-- Table: athlete_content (linking athletes to curated content)
CREATE TABLE IF NOT EXISTS athlete_content (
    id SERIAL PRIMARY KEY,
    athlete_id INTEGER REFERENCES athletes(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    content_type VARCHAR(50),
    display_order INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(athlete_id, content_id)
);

CREATE INDEX IF NOT EXISTS idx_athlete_content_athlete ON athlete_content(athlete_id);
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

-- Table: newsletter_settings (for dashboard config)
CREATE TABLE IF NOT EXISTS newsletter_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: priority_sources (for content discovery)
CREATE TABLE IF NOT EXISTS priority_sources (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(255),
    source_name VARCHAR(255) NOT NULL,
    source_url VARCHAR(500),
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, source_name)
);

-- Function: Calculate engagement score
CREATE OR REPLACE FUNCTION calculate_engagement_score(
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    creator_credibility DECIMAL,
    days_old INTEGER
)
RETURNS DECIMAL AS $$
BEGIN
    RETURN (
        (COALESCE(views, 0) * 1.0) +
        (COALESCE(likes, 0) * 5.0) +
        (COALESCE(comments, 0) * 10.0)
    ) * COALESCE(creator_credibility, 0.5) * (1.0 / (1.0 + COALESCE(days_old, 0) * 0.1));
END;
$$ LANGUAGE plpgsql;

-- Add icon_emoji column to performance_topics if missing
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='performance_topics' AND column_name='icon_emoji') THEN
        ALTER TABLE performance_topics ADD COLUMN icon_emoji VARCHAR(10);
    END IF;
END $$;

-- Update performance topics with emojis if they're missing
UPDATE performance_topics SET icon_emoji = '⛷️' WHERE slug = 'ski-erg' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🛷' WHERE slug = 'sled-push' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🪢' WHERE slug = 'sled-pull' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🤸' WHERE slug = 'burpee-broad-jump' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🚣' WHERE slug = 'rowing' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🏋️' WHERE slug = 'farmers-carry' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '👟' WHERE slug = 'sandbag-lunges' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🏐' WHERE slug = 'wall-balls' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '⏱️' WHERE slug = 'pacing' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🔄' WHERE slug = 'transitions' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🏃' WHERE slug = 'endurance' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '📋' WHERE slug = 'programming' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🧘' WHERE slug = 'recovery' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🥗' WHERE slug = 'nutrition' AND icon_emoji IS NULL;
UPDATE performance_topics SET icon_emoji = '🏁' WHERE slug = 'race-day' AND icon_emoji IS NULL;
