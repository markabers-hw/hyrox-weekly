# Hyrox Weekly - Project Context

## What This Is
Hyrox Weekly is a free newsletter that curates the best Hyrox fitness content from across the internet each week. The goal is to become the definitive source for everything Hyrox-related, serving the hybrid fitness community.

**Website:** HyroxWeekly.com (Netlify)  
**Distribution:** Beehiiv  
**Publishing Schedule:** Monday 3:00 PM Sydney time (hits US Sunday planning, EU Monday morning)

## Tech Stack
- **Language:** Python 3.x
- **Database:** PostgreSQL on AWS RDS
- **Content Discovery:** YouTube Data API v3
- **Curation Interface:** Streamlit dashboard
- **Newsletter Generation:** Jinja2 templates
- **Hosting:** AWS (backend), Netlify (frontend)
- **Distribution:** Beehiiv

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Content        │────▶│  PostgreSQL      │────▶│  Streamlit      │
│  Discovery      │     │  (scored content)│     │  Dashboard      │
│  (YouTube API)  │     └──────────────────┘     │  (curation)     │
└─────────────────┘                              └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Jinja2         │
                                                 │  Generator      │
                                                 └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Beehiiv        │
                                                 │  (distribution) │
                                                 └─────────────────┘
```

## Directory Structure

```
/Users/mark/hyrox-weekly/
│
├── # ─── CONTENT DISCOVERY ───
├── youtube_discovery.py        # YouTube content fetching
├── podcast_discovery.py        # Podcast content fetching
├── article_discovery.py        # Article/blog content fetching
├── reddit_discovery.py         # Reddit content fetching
├── instagram_discovery.py      # Instagram content fetching
├── instagram_manager.py        # Instagram account management
│
├── # ─── DATABASE ───
├── schema.sql                  # Database schema definition
├── create_database.py          # DB initialization
├── db_setup.py                 # DB configuration
├── fix_trigger.py              # DB trigger fixes
├── view_content.py             # Content viewing utility
│
├── # ─── CURATION & DASHBOARD ───
├── hyrox_dashboard.py          # Main Streamlit dashboard (222KB)
├── curation_dashboard.py       # Curation interface
│
├── # ─── NEWSLETTER GENERATION ───
├── newsletter_generator.py     # Original generator
├── newsletter_generator_v2.py  # Updated generator
├── newsletter_edition_1.html   # Sample output
├── newsletter_preview.html     # Preview template
│
├── # ─── WEBSITE (Netlify) ───
├── hyroxweekly-site/
│   ├── index.html              # Homepage
│   ├── 404.html                # Error page
│   ├── netlify.toml            # Netlify config
│   ├── README.md
│   ├── assets/                 # Static assets (images, CSS)
│   ├── archive/                # Past editions
│   │   ├── index.html
│   │   ├── edition-1-2025-12-15.html
│   │   ├── edition-2-2025-12-22.html
│   │   └── edition-3-2025-12-29.html
│   ├── premium/                # Premium tier landing
│   │   └── index.html
│   └── privacy/                # Privacy policy
│
├── venv/                       # Python virtual environment
└── hyroxweekly-site.zip        # Site backup
```

## Key Components

### Content Discovery Scripts
Multiple discovery scripts for different platforms:
- `youtube_discovery.py` - YouTube content (primary source)
- `podcast_discovery.py` - Podcast episodes
- `article_discovery.py` - Blog/article content
- `reddit_discovery.py` - Reddit posts from r/hyrox
- `instagram_discovery.py` - Instagram content

Each script fetches content and stores it in PostgreSQL with engagement metrics.

### Database Layer
- `schema.sql` - Full database schema
- `create_database.py` / `db_setup.py` - Database initialization
- `view_content.py` - Utility for viewing stored content

### Curation Dashboard
- `hyrox_dashboard.py` - Main Streamlit dashboard (222KB, primary interface)
- `curation_dashboard.py` - Additional curation interface
- Allows accept/reject, categorization, editorial notes

### Newsletter Generator
- `newsletter_generator_v2.py` - Current generator (use this one)
- `newsletter_generator.py` - Original version (legacy)
- Outputs HTML ready for Beehiiv

### Website (hyroxweekly-site/)
- Static site hosted on Netlify
- `/archive/` contains past editions
- `/premium/` has premium tier landing page (in development)

## Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `creators` | Content creators/sources (YouTube channels, podcasts, blogs) |
| `content_items` | Discovered content with engagement metrics and curation status |
| `weekly_editions` | Published newsletter editions with Beehiiv integration |
| `edition_content` | Many-to-many linking content to editions (with display order, section, featured flag) |
| `content_categories` | Reference table for content categories |

### Supporting Tables

| Table | Purpose |
|-------|---------|
| `discovery_runs` | Tracks scraping job history (platform, items found, errors) |
| `instagram_posts` | Social media cross-posting management |
| `ad_placements` | Future ad/sponsorship management |

### Key Views

- `content_for_curation` - Content from last 7 days with status='discovered', sorted by engagement score
- `edition_summary` - Edition overview with content counts and analytics

### Content Status Flow
```
discovered → reviewed → selected → published
                    ↘ rejected
```

### Content Categories
`training`, `race_recap`, `technique`, `nutrition`, `gear`, `athlete_profile`, `news`, `other`

### Engagement Score
Auto-calculated via trigger using formula:
```
(views × 1.0 + likes × 5.0 + comments × 10.0) × creator_credibility × time_decay
```
Time decay: `1 / (1 + days_old × 0.1)`

### Key Fields on content_items
- `status` - discovered/reviewed/selected/published/rejected
- `category` - content category for newsletter sections
- `editorial_note` - your commentary for the newsletter
- `engagement_score` - auto-calculated ranking score
- `selected_for_edition_id` - links to weekly_editions

## Current State
- ✅ Free tier fully operational
- ✅ Engine takes <1 hour per weekly edition
- ✅ 3 editions published (Dec 15, Dec 22, Dec 29)
- ✅ Premium landing page exists (`/premium/index.html`)
- 🚧 Premium tier functionality (in development)
- 🚧 Instagram/Reddit marketing (early stage)

## Premium Tier (In Development)

**Key Value Proposition:** Early access to curated content

| Tier | Publish Day | Price |
|------|-------------|-------|
| Free | Monday 3PM Sydney | $0 |
| Premium | Tuesday (early access) | TBD |

**Implementation needs:**
- Beehiiv premium tier setup
- Database flag for premium content
- Separate generation workflow for premium vs free
- Landing page copy

## Coding Conventions

- Use type hints for all functions
- Docstrings for public functions
- Tests in `/tests` mirroring `/src` structure
- Environment variables for secrets (never commit)
- Use `python-dotenv` for local development

## Environment Variables
<!-- ENV VARIABLES BELOW -->

DB_HOST=hyrox-weekly-db.c21ug8y2clu9.us-east-1.rds.amazonaws.com
DB_NAME=hyrox_weekly
DB_USER=hyroxadmin
DB_PASSWORD=
DB_PORT=5432
```
YOUTUBE_API_KEY=
```
BEEHIIV_API_KEY=
BEEHIIV_PUBLICATION_ID=
```
GOOGLE_API_KEY=
GOOGLE_CSE_ID=
```
RAPIDAPI_KEY=
```
ANTHROPIC_API_KEY=
```

## Common Tasks

### Run content discovery
```bash
python youtube_discovery.py
python podcast_discovery.py
python article_discovery.py
python reddit_discovery.py
```

### Launch curation dashboard
```bash
streamlit run hyrox_dashboard.py
```

### Generate newsletter
```bash
python newsletter_generator_v2.py
```

## Future Roadmap

1. **Premium tier** - Early access for paid subscribers
2. **Expand content sources** - Podcasts, blogs, Reddit
3. **SaaS potential** - Make engine configurable for other niches (ultra running, etc.)

## Notes for Claude

- This is a solo project - keep solutions simple and maintainable
- Prefer readable code over clever code
- The human (Mark) is technical but values speed over perfection
- When suggesting changes, explain the tradeoffs
- Ask before making large refactors
