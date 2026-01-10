-- Hyrox Weekly Database Schema

-- Table: creators (content creators/sources)
CREATE TABLE creators (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL, -- youtube, podcast, blog, instagram
    platform_id VARCHAR(255), -- channel ID, podcast feed URL, etc.
    follower_count INTEGER,
    credibility_score DECIMAL(3,2) DEFAULT 0.5, -- 0-1 scale, tune over time
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_id)
);

-- Table: content_items (discovered content)
CREATE TABLE content_items (
    id SERIAL PRIMARY KEY,
    creator_id INTEGER REFERENCES creators(id),
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    platform VARCHAR(50) NOT NULL, -- youtube, podcast, blog, instagram
    content_type VARCHAR(50), -- video, podcast_episode, article, reel
    
    -- Metadata
    published_date TIMESTAMP,
    discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds INTEGER, -- for videos/podcasts
    thumbnail_url TEXT,
    
    -- Engagement metrics
    view_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    engagement_score DECIMAL(10,2), -- calculated score for ranking
    
    -- Curation
    category VARCHAR(50), -- training, race_recap, nutrition, gear, athlete_profile, news
    status VARCHAR(20) DEFAULT 'discovered', -- discovered, reviewed, selected, published, rejected
    editorial_note TEXT, -- your commentary/context for newsletter
    
    -- Publishing
    selected_for_edition_id INTEGER, -- which edition this was selected for
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for common queries
CREATE INDEX idx_content_published_date ON content_items(published_date DESC);
CREATE INDEX idx_content_status ON content_items(status);
CREATE INDEX idx_content_engagement ON content_items(engagement_score DESC);
CREATE INDEX idx_content_platform ON content_items(platform);

-- Table: weekly_editions (published newsletters)
CREATE TABLE weekly_editions (
    id SERIAL PRIMARY KEY,
    edition_number INTEGER NOT NULL UNIQUE,
    publish_date DATE NOT NULL,
    week_start_date DATE NOT NULL, -- the Monday of the week being covered
    week_end_date DATE NOT NULL, -- the Sunday
    
    -- Content
    headline TEXT, -- main theme/title
    intro_text TEXT, -- editorial intro paragraph
    
    -- Publishing
    status VARCHAR(20) DEFAULT 'draft', -- draft, scheduled, published
    beehiiv_post_id VARCHAR(255), -- ID from Beehiiv after publishing
    beehiiv_url TEXT,
    
    -- Analytics (updated from Beehiiv API)
    subscriber_count INTEGER,
    open_count INTEGER,
    click_count INTEGER,
    open_rate DECIMAL(5,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: edition_content (many-to-many: which content in which edition)
CREATE TABLE edition_content (
    id SERIAL PRIMARY KEY,
    edition_id INTEGER REFERENCES weekly_editions(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL, -- order in newsletter
    section VARCHAR(50), -- youtube, podcasts, articles, instagram
    is_featured BOOLEAN DEFAULT false, -- hero/top placement
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edition_id, content_id)
);

CREATE INDEX idx_edition_content_edition ON edition_content(edition_id);
CREATE INDEX idx_edition_content_order ON edition_content(edition_id, display_order);

-- Table: instagram_posts (social media cross-posting)
CREATE TABLE instagram_posts (
    id SERIAL PRIMARY KEY,
    edition_id INTEGER REFERENCES weekly_editions(id),
    content_id INTEGER REFERENCES content_items(id), -- if post is about specific content
    
    post_type VARCHAR(20), -- feed, carousel, story, reel
    caption TEXT,
    image_urls TEXT[], -- array of image URLs
    
    status VARCHAR(20) DEFAULT 'draft', -- draft, scheduled, posted
    scheduled_for TIMESTAMP,
    posted_at TIMESTAMP,
    
    instagram_post_id VARCHAR(255), -- ID from Instagram after posting
    instagram_url TEXT,
    
    -- Analytics
    like_count INTEGER,
    comment_count INTEGER,
    reach INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: discovery_runs (track scraping jobs)
CREATE TABLE discovery_runs (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    items_discovered INTEGER DEFAULT 0,
    status VARCHAR(20), -- success, failed, partial
    error_message TEXT,
    execution_time_seconds INTEGER
);

-- Table: ad_placements (for future ad management)
CREATE TABLE ad_placements (
    id SERIAL PRIMARY KEY,
    edition_id INTEGER REFERENCES weekly_editions(id),
    
    advertiser_name VARCHAR(255),
    ad_type VARCHAR(50), -- banner, sponsored_content, native
    position VARCHAR(50), -- header, mid_content, footer
    
    ad_content TEXT, -- HTML or markdown
    ad_image_url TEXT,
    click_url TEXT,
    
    -- Business
    rate_usd DECIMAL(10,2),
    status VARCHAR(20), -- active, paused, completed
    
    -- Analytics
    impression_count INTEGER DEFAULT 0,
    click_count INTEGER DEFAULT 0,
    click_through_rate DECIMAL(5,2),
    
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- View: Content ready for curation (this week's discoveries)
CREATE VIEW content_for_curation AS
SELECT 
    ci.id,
    ci.title,
    ci.url,
    ci.platform,
    ci.content_type,
    ci.published_date,
    ci.engagement_score,
    ci.view_count,
    ci.like_count,
    ci.status,
    ci.category,
    c.name as creator_name,
    c.follower_count
FROM content_items ci
LEFT JOIN creators c ON ci.creator_id = c.id
WHERE ci.status = 'discovered'
    AND ci.published_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY ci.engagement_score DESC;

-- View: Edition summary with content count
CREATE VIEW edition_summary AS
SELECT 
    we.id,
    we.edition_number,
    we.publish_date,
    we.headline,
    we.status,
    COUNT(ec.id) as content_count,
    we.open_rate,
    we.subscriber_count
FROM weekly_editions we
LEFT JOIN edition_content ec ON we.id = ec.edition_id
GROUP BY we.id
ORDER BY we.edition_number DESC;

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
    -- Weighted formula: emphasize views, bonus for engagement rate, decay over time
    RETURN (
        (views * 1.0) + 
        (likes * 5.0) + 
        (comments * 10.0)
    ) * creator_credibility * (1.0 / (1.0 + days_old * 0.1));
END;
$$ LANGUAGE plpgsql;

-- Trigger: Auto-update engagement score when metrics change
CREATE OR REPLACE FUNCTION update_engagement_score()
RETURNS TRIGGER AS $$
BEGIN
    NEW.engagement_score := calculate_engagement_score(
        NEW.view_count,
        NEW.like_count,
        NEW.comment_count,
        COALESCE((SELECT credibility_score FROM creators WHERE id = NEW.creator_id), 0.5),
        EXTRACT(DAY FROM CURRENT_DATE - NEW.published_date::DATE)
    );
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER content_engagement_trigger
BEFORE INSERT OR UPDATE OF view_count, like_count, comment_count
ON content_items
FOR EACH ROW
EXECUTE FUNCTION update_engagement_score();

-- Seed some categories for reference
CREATE TABLE content_categories (
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
('other', 'General Hyrox content', 8);

-- =============================================================================
-- PREMIUM FEATURES SCHEMA
-- =============================================================================

-- Table: athletes (for Athlete Editions)
CREATE TABLE athletes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    country VARCHAR(100),
    country_code CHAR(3),
    gender VARCHAR(10), -- 'male', 'female'
    tier VARCHAR(50) DEFAULT 'elite_15', -- elite_15, notable, rising_star
    bio TEXT,
    photo_url TEXT,
    instagram_handle VARCHAR(100),
    youtube_channel_id VARCHAR(255),
    website_url TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_athletes_gender ON athletes(gender);
CREATE INDEX idx_athletes_tier ON athletes(tier);
CREATE INDEX idx_athletes_slug ON athletes(slug);

-- Table: subscribers (syncs with Stripe)
CREATE TABLE subscribers (
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

CREATE INDEX idx_subscribers_email ON subscribers(email);
CREATE INDEX idx_subscribers_stripe_customer ON subscribers(stripe_customer_id);
CREATE INDEX idx_subscribers_status ON subscribers(subscription_status);
CREATE INDEX idx_subscribers_early_bird ON subscribers(is_early_bird);

-- Table: athlete_editions (configuration for each athlete's premium page)
CREATE TABLE athlete_editions (
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

CREATE INDEX idx_athlete_editions_status ON athlete_editions(status);
CREATE INDEX idx_athlete_editions_athlete ON athlete_editions(athlete_id);

-- Table: performance_topics (for Performance Editions)
CREATE TABLE performance_topics (
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

CREATE INDEX idx_performance_topics_category ON performance_topics(category);
CREATE INDEX idx_performance_topics_slug ON performance_topics(slug);
CREATE INDEX idx_performance_topics_status ON performance_topics(status);

-- Table: athlete_content (linking athletes to curated content)
CREATE TABLE athlete_content (
    id SERIAL PRIMARY KEY,
    athlete_edition_id INTEGER REFERENCES athlete_editions(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    content_type VARCHAR(50), -- video_latest, video_popular, podcast, article
    display_order INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(athlete_edition_id, content_id)
);

CREATE INDEX idx_athlete_content_edition ON athlete_content(athlete_edition_id);
CREATE INDEX idx_athlete_content_type ON athlete_content(content_type);

-- Table: performance_content (linking performance topics to curated content)
CREATE TABLE performance_content (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER REFERENCES performance_topics(id) ON DELETE CASCADE,
    content_id INTEGER REFERENCES content_items(id) ON DELETE CASCADE,
    display_order INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, content_id)
);

CREATE INDEX idx_performance_content_topic ON performance_content(topic_id);

-- Table: premium_settings (global settings for premium features)
CREATE TABLE premium_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT INTO premium_settings (key, value) VALUES
('early_bird_limit', '100'),
('monthly_price_cents', '500'),
('yearly_price_cents', '3900'),
('early_bird_monthly_price_cents', '400'),
('early_bird_yearly_price_cents', '3000');

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
CREATE VIEW athlete_edition_summary AS
SELECT
    ae.id,
    ae.status,
    a.name as athlete_name,
    a.slug as athlete_slug,
    a.photo_url,
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
('other', 'race-day', 'Race Day Strategy', '🏁', 4);