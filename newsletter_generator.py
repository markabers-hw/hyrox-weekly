"""
Hyrox Weekly Newsletter Generator

Supports: YouTube, Podcasts, Articles, Reddit
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from jinja2 import Template

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

NEWSLETTER_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hyrox Weekly - {{ edition_date }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Barlow',sans-serif;line-height:1.6;color:#1a1a1a;background:#f5f5f5}
.container{max-width:640px;margin:0 auto;background:#fff}
.header{background:#1a1a1a;padding:48px 32px;text-align:center}
.header h1{color:#fff;font-size:36px;font-weight:800;letter-spacing:6px;margin-bottom:8px}
.header .tagline{color:rgba(255,255,255,0.5);font-size:13px;font-weight:500;letter-spacing:2px;text-transform:uppercase}
.header .edition-date{color:#CC5500;font-size:12px;margin-top:16px;font-weight:600;letter-spacing:1px}
.intro{padding:32px;border-bottom:1px solid #eee}
.intro p{font-size:16px;color:#444;line-height:1.7;font-weight:400}
.sponsor-banner{padding:16px 32px;background:#fafafa;border-bottom:1px solid #eee;text-align:center}
.sponsor-banner .sponsor-label{font-size:10px;text-transform:uppercase;letter-spacing:2px;color:#999;font-weight:600}
.sponsor-banner a{color:#CC5500;text-decoration:none;font-weight:600}
.section{padding:32px;border-bottom:1px solid #eee}
.section-title{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#1a1a1a;margin-bottom:24px;padding-bottom:12px;border-bottom:2px solid #1a1a1a}
.section-podcast{background:#fafafa}
.content-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}
.content-item{margin-bottom:0}
.content-thumbnail{width:100%;height:140px;border-radius:4px;overflow:hidden;margin-bottom:12px;background:#f0f0f0}
.content-thumbnail img{width:100%;height:100%;object-fit:cover}
.content-platform{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#CC5500;margin-bottom:6px}
.content-title{font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:6px;line-height:1.3}
.content-title a{color:#1a1a1a;text-decoration:none}
.content-title a:hover{color:#CC5500}
.content-creator{font-size:11px;color:#999;font-weight:500;margin-bottom:8px}
.content-preview{font-size:13px;color:#555;line-height:1.5;margin-bottom:8px;font-weight:400}
.content-stats{font-size:11px;color:#999;font-weight:500;margin-bottom:6px}
.content-link{display:inline-block;font-size:11px;font-weight:700;color:#CC5500;text-decoration:none;text-transform:uppercase;letter-spacing:1px}
.content-link:hover{text-decoration:underline}
.podcast-links{display:flex;gap:8px;margin-top:10px}
.podcast-link{font-size:10px;font-weight:700;color:#1a1a1a;text-decoration:none;padding:6px 12px;border:2px solid #1a1a1a;text-transform:uppercase;letter-spacing:1px}
.podcast-link:hover{background:#1a1a1a;color:#fff}
.reddit-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.reddit-item{padding:12px;background:#fafafa;border-left:2px solid #1a1a1a}
.reddit-meta{font-size:9px;color:#999;margin-bottom:4px;font-weight:500;text-transform:uppercase}
.reddit-title{font-size:12px;font-weight:600;color:#1a1a1a;margin-bottom:4px;line-height:1.25}
.reddit-title a{color:#1a1a1a;text-decoration:none}
.reddit-title a:hover{color:#CC5500}
.reddit-stats{font-size:10px;color:#666;font-weight:500}
.cta-section{padding:32px;text-align:center;background:#1a1a1a}
.cta-section h3{color:#fff;font-size:20px;font-weight:700;letter-spacing:1px;margin-bottom:6px}
.cta-section p{color:rgba(255,255,255,0.5);font-size:13px;margin-bottom:16px;font-weight:400}
.cta-button{display:inline-block;padding:12px 32px;background:#CC5500;color:#fff;text-decoration:none;font-weight:700;font-size:12px;letter-spacing:2px;text-transform:uppercase}
.cta-button:hover{background:#b34a00}
.footer{padding:32px;text-align:center;background:#1a1a1a;border-top:1px solid #333}
.footer p{color:rgba(255,255,255,0.4);font-size:12px;margin-bottom:8px;font-weight:400}
.footer a{color:rgba(255,255,255,0.6);text-decoration:none}
.footer a:hover{color:#CC5500}
@media(max-width:480px){.header{padding:32px 20px}.header h1{font-size:28px;letter-spacing:4px}.section{padding:24px 20px}.content-grid{grid-template-columns:1fr}.reddit-grid{grid-template-columns:1fr}.content-thumbnail{height:180px}}
</style></head>
<body><div class="container">

<div class="header">
<h1>HYROX WEEKLY</h1>
<div class="tagline">Everything Hyrox, Every Week</div>
<div class="edition-date">{{ week_range }}</div>
</div>

<div class="intro"><p>{{ intro_text }}</p></div>

<div class="sponsor-banner">
<span class="sponsor-label">Presented by</span> &middot; <a href="mailto:sponsor@hyroxweekly.com">Your brand here &rarr;</a>
</div>

{% for category, items in videos.items() %}{% if items %}
<div class="section">
<h2 class="section-title">{{ category }}</h2>
<div class="content-grid">
{% for item in items %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><a href="{{ item.url }}"><img src="{{ item.thumbnail_url }}" alt=""></a></div>{% endif %}
<div class="content-platform">YouTube</div>
<h3 class="content-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="content-creator">{{ item.creator_name }}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:100] }}{% if item.description|length > 100 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" class="content-link">Watch &rarr;</a>
</div>
{% endfor %}
</div>
</div>
{% endif %}{% endfor %}

{% if podcasts %}
<div class="section section-podcast">
<h2 class="section-title">Worth a Listen</h2>
<div class="content-grid">
{% for item in podcasts %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><img src="{{ item.thumbnail_url }}" alt=""></div>{% endif %}
<div class="content-platform">Podcast</div>
<h3 class="content-title">{{ item.title }}</h3>
<div class="content-creator">{{ item.creator_name }}{% if item.duration_display %} &bull; {{ item.duration_display }}{% endif %}</div>
<div class="podcast-links">
{% if item.spotify_url %}<a href="{{ item.spotify_url }}" class="podcast-link">Spotify</a>{% endif %}
{% if item.apple_url %}<a href="{{ item.apple_url }}" class="podcast-link">Apple</a>{% endif %}
</div>
</div>
{% endfor %}
</div>
</div>
{% endif %}

{% if articles %}
<div class="section">
<h2 class="section-title">Worth Reading</h2>
<div class="content-grid">
{% for item in articles %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><a href="{{ item.url }}"><img src="{{ item.thumbnail_url }}" alt=""></a></div>{% endif %}
<div class="content-platform">Article</div>
<h3 class="content-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="content-creator">{{ item.creator_name }}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:100] }}{% if item.description|length > 100 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" class="content-link">Read &rarr;</a>
</div>
{% endfor %}
</div>
</div>
{% endif %}

{% if reddit_posts %}
<div class="section">
<h2 class="section-title">Community Discussions</h2>
<div class="reddit-grid">
{% for item in reddit_posts %}
<div class="reddit-item">
<div class="reddit-meta">{{ item.creator_name }}</div>
<h3 class="reddit-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="reddit-stats">{{ "{:,}".format(item.score or 0) }} upvotes &bull; {{ "{:,}".format(item.comments or 0) }} comments</div>
</div>
{% endfor %}
</div>
</div>
{% endif %}

<div class="cta-section">
<h3>Never Miss an Edition</h3>
<p>The best Hyrox content, delivered weekly direct to your inbox.</p>
<a href="https://hyroxweekly.com" class="cta-button">Subscribe</a>
</div>

<div class="footer">
<p><a href="https://instagram.com/hyroxweekly">Instagram</a> &middot; <a href="https://hyroxweekly.com">Website</a> &middot; <a href="#">Unsubscribe</a></p>
<p style="margin-top:16px">&copy; {{ current_year }} Hyrox Weekly</p>
</div>

</div></body></html>"""


def get_selected_content():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT ci.id, ci.title, ci.url, ci.platform, ci.thumbnail_url, ci.description,
               ci.view_count, ci.like_count, ci.comment_count, ci.duration_seconds,
               ci.category, ci.editorial_note, ci.engagement_score,
               c.name as creator_name
        FROM content_items ci
        LEFT JOIN creators c ON ci.creator_id = c.id
        WHERE ci.status = 'selected'
        ORDER BY ci.platform, ci.engagement_score DESC
    """)
    content = cursor.fetchall()
    cursor.close()
    conn.close()
    return content


def parse_podcast_links(note):
    spotify, apple = "", ""
    if note and "Spotify:" in note:
        for part in note.split("|"):
            if "Spotify:" in part: spotify = part.replace("Spotify:", "").strip()
            elif "Apple:" in part: apple = part.replace("Apple:", "").strip()
    return spotify, apple


def parse_reddit_info(note):
    author, external = "", ""
    if note:
        for part in note.split("|"):
            if "Author:" in part: author = part.replace("Author:", "").strip()
            elif "Link:" in part: external = part.replace("Link:", "").strip()
    return author, external


def format_duration(sec):
    if not sec: return ""
    sec = int(sec)
    if sec < 60: return f"{sec} sec"
    if sec < 3600: return f"{sec // 60} min"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def organize_content(content):
    cats = {
        'race_recap': 'Race Recaps', 
        'training': 'Training & Workouts',
        'nutrition': 'Nutrition & Recovery', 
        'athlete_profile': 'Athlete Spotlights',
        'gear': 'Gear & Equipment', 
        'other': 'More Videos'
    }
    
    videos, podcasts, articles, reddit_posts = {}, [], [], []
    
    for item in content:
        platform = item['platform']
        
        if platform == 'youtube':
            cat = cats.get(item.get('category') or 'other', cats['other'])
            if cat not in videos: videos[cat] = []
            videos[cat].append(item)
        
        elif platform == 'podcast':
            spotify, apple = parse_podcast_links(item.get('editorial_note'))
            item['spotify_url'] = spotify
            item['apple_url'] = apple
            item['duration_display'] = format_duration(item.get('duration_seconds'))
            podcasts.append(item)
        
        elif platform == 'article':
            articles.append(item)
        
        elif platform == 'reddit':
            author, external = parse_reddit_info(item.get('editorial_note'))
            item['author'] = author
            item['external_url'] = external
            item['score'] = item.get('view_count', 0)
            item['comments'] = item.get('comment_count', 0)
            reddit_posts.append(item)
    
    return videos, podcasts, articles, reddit_posts


def get_next_edition_number():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(edition_number), 0) + 1 FROM weekly_editions")
    num = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return num


def create_edition_record(edition_number, content_ids):
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
    week_end = week_start + timedelta(days=6)
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'weekly_editions'")
    cols = [r[0] for r in cursor.fetchall()]
    
    ins_cols, ins_vals = ['edition_number', 'publish_date'], [edition_number, datetime.now()]
    if 'week_start_date' in cols: ins_cols.append('week_start_date'); ins_vals.append(week_start)
    if 'week_end_date' in cols: ins_cols.append('week_end_date'); ins_vals.append(week_end)
    if 'status' in cols: ins_cols.append('status'); ins_vals.append('published')
    
    cursor.execute(f"INSERT INTO weekly_editions ({','.join(ins_cols)}) VALUES ({','.join(['%s']*len(ins_vals))}) RETURNING id", ins_vals)
    edition_id = cursor.fetchone()[0]
    
    cursor.execute("UPDATE content_items SET status = 'published' WHERE id = ANY(%s)", (content_ids,))
    conn.commit()
    cursor.close()
    conn.close()
    return edition_id


def main():
    print("=" * 70)
    print("HYROX WEEKLY - Newsletter Generator")
    print("=" * 70)
    
    print("\n Fetching selected content...")
    content = get_selected_content()
    
    if not content:
        print("\n No content selected! Run: streamlit run curation_dashboard.py")
        return
    
    print(f"   Found {len(content)} selected items")
    
    videos, podcasts, articles, reddit_posts = organize_content(content)
    video_count = sum(len(v) for v in videos.values())
    
    print(f"\n Content Summary:")
    print(f"   🎬 Videos: {video_count}")
    print(f"   🎙️ Podcasts: {len(podcasts)}")
    print(f"   📰 Articles: {len(articles)}")
    print(f"   🔗 Reddit: {len(reddit_posts)}")
    
    edition_number = get_next_edition_number()
    print(f"\n Generating Edition #{edition_number}...")
    
    # Calculate week range (Monday to Sunday of the previous week)
    today = datetime.now()
    # Find the most recent Sunday (end of last week)
    days_since_sunday = (today.weekday() + 1) % 7
    if days_since_sunday == 0:
        days_since_sunday = 7  # If today is Sunday, go back to last Sunday
    end_of_week = today - timedelta(days=days_since_sunday)
    start_of_week = end_of_week - timedelta(days=6)
    
    # Format: "December 22-28, 2025" or "December 29 - January 4, 2026" if spans months/years
    if start_of_week.month == end_of_week.month:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day}-{end_of_week.day}, {end_of_week.year}"
    elif start_of_week.year == end_of_week.year:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day} - {end_of_week.strftime('%B')} {end_of_week.day}, {end_of_week.year}"
    else:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day}, {start_of_week.year} - {end_of_week.strftime('%B')} {end_of_week.day}, {end_of_week.year}"
    
    # Build intro
    parts = []
    if video_count: parts.append(f"{video_count} videos")
    if podcasts: parts.append(f"{len(podcasts)} podcasts")
    if articles: parts.append(f"{len(articles)} articles")
    if reddit_posts: parts.append(f"{len(reddit_posts)} community discussions")
    intro = f"Welcome! This week we've curated {', '.join(parts)} of the best Hyrox content."
    
    template = Template(NEWSLETTER_TEMPLATE)
    html = template.render(
        week_range=week_range,
        intro_text=intro,
        videos=videos,
        podcasts=podcasts,
        articles=articles,
        reddit_posts=reddit_posts,
        current_year=datetime.now().year
    )
    
    # Save files
    preview_file = "newsletter_preview.html"
    archive_file = f"newsletter_edition_{edition_number}.html"
    
    with open(preview_file, 'w') as f: f.write(html)
    with open(archive_file, 'w') as f: f.write(html)
    
    print(f"   Preview: {preview_file}")
    print(f"   Archive: {archive_file}")
    
    os.system(f"open {preview_file}")
    
    print("\n" + "=" * 70)
    print("REVIEW YOUR NEWSLETTER")
    print("=" * 70)
    
    resp = input("\nSave to database and mark as published? (yes/no): ").strip().lower()
    if resp == 'yes':
        content_ids = [item['id'] for item in content]
        edition_id = create_edition_record(edition_number, content_ids)
        print(f"   Edition #{edition_number} saved (ID: {edition_id})")
        print(f"   {len(content_ids)} items marked as published")
    
    print("\n Newsletter generation complete!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
