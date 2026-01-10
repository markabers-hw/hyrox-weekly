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