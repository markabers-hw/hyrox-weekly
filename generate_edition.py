"""
Generate Hyrox Weekly edition HTML from curated content in Supabase.

Produces both website HTML (for /archive/) and Beehiiv email HTML.
Reuses templates from hyrox_dashboard.py via regex extraction.

Usage:
    python generate_edition.py --week-start 2026-03-30 --week-end 2026-04-05 --edition 16
"""
import os
import re
import sys
import argparse
import requests
from datetime import datetime, timedelta, timezone
from jinja2 import Template
from dotenv import load_dotenv

load_dotenv()

# Supabase config
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://ksqrakczmecdbzxwsvea.supabase.co')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzcXJha2N6bWVjZGJ6eHdzdmVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjYxMTMsImV4cCI6MjA4MzYwMjExM30.sotuDt98HLIaDvkINuT-2mC8DPgpDTB6luu_xKCxe64'

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), 'hyrox_dashboard.py')
SITE_DIR = os.path.join(os.path.dirname(__file__), 'hyroxweekly-site')


def get_supabase_headers():
    key = SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }


def supabase_get(table, params=None, single=False):
    headers = get_supabase_headers()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data[0] if single and data else data
        return [] if not single else None
    except Exception as e:
        print(f"Supabase GET error: {e}")
        return [] if not single else None


def supabase_post(table, data):
    headers = get_supabase_headers()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            result = response.json()
            return result[0] if isinstance(result, list) and result else result
        print(f"Supabase POST error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Supabase POST error: {e}")
        return None


def supabase_patch(table, params, data):
    headers = get_supabase_headers()
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    try:
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code in [200, 204]:
            if response.text:
                result = response.json()
                return result[0] if isinstance(result, list) and result else result
            return True
        print(f"Supabase PATCH error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Supabase PATCH error: {e}")
        return None


# ── Helper functions (replicated from dashboard) ──

def format_duration(sec):
    if not sec:
        return ""
    sec = int(sec)
    if sec < 60:
        return f"{sec} sec"
    if sec < 3600:
        return f"{sec // 60} min"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def parse_podcast_links(note):
    spotify, apple = "", ""
    if note and "Spotify:" in note:
        for part in note.split("|"):
            if "Spotify:" in part:
                spotify = part.replace("Spotify:", "").strip()
            elif "Apple:" in part:
                apple = part.replace("Apple:", "").strip()
    return spotify, apple


def parse_reddit_info(note):
    author, external = "", ""
    if note:
        for part in note.split("|"):
            if "Author:" in part:
                author = part.replace("Author:", "").strip()
            elif "Link:" in part:
                external = part.replace("Link:", "").strip()
    return author, external


def organize_content_for_newsletter(content):
    """Organize content into categories for template rendering."""
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

        # Description priority: AI > custom > original
        if item.get('use_ai_description') and item.get('ai_description'):
            item['description'] = item['ai_description']
        elif item.get('custom_description'):
            item['description'] = item['custom_description']

        if platform == 'youtube':
            cat = cats.get(item.get('category') or 'other', cats['other'])
            if cat not in videos:
                videos[cat] = []
            item['duration_display'] = format_duration(item.get('duration_seconds'))
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

    # Sort each video category by display_order
    for cat in videos:
        videos[cat] = sorted(videos[cat], key=lambda x: x.get('display_order') or 999)

    # Sort video categories by their lowest display_order item
    videos = dict(sorted(videos.items(),
                         key=lambda kv: min((x.get('display_order') or 999) for x in kv[1])))

    # Sort podcasts, articles, reddit by display_order
    podcasts = sorted(podcasts, key=lambda x: x.get('display_order') or 999)
    articles = sorted(articles, key=lambda x: x.get('display_order') or 999)
    reddit_posts = sorted(reddit_posts, key=lambda x: x.get('display_order') or 999)

    return videos, podcasts, articles, reddit_posts


# ── Template extraction ──

def extract_template(name):
    """Extract a template string from hyrox_dashboard.py by variable name."""
    with open(DASHBOARD_PATH, 'r') as f:
        source = f.read()

    # Match: TEMPLATE_NAME = """...""" or '''...'''
    pattern = rf'{name}\s*=\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')'
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        print(f"ERROR: Could not extract {name} from {DASHBOARD_PATH}")
        sys.exit(1)
    return match.group(1) if match.group(1) is not None else match.group(2)


# ── Week range formatting ──

def format_week_range(start_date, end_date):
    """Format week range like 'March 30 - April 5, 2026'."""
    if start_date.month == end_date.month:
        return f"{start_date.strftime('%B')} {start_date.day}-{end_date.day}, {end_date.year}"
    elif start_date.year == end_date.year:
        return f"{start_date.strftime('%B')} {start_date.day} - {end_date.strftime('%B')} {end_date.day}, {end_date.year}"
    else:
        return f"{start_date.strftime('%B')} {start_date.day}, {start_date.year} - {end_date.strftime('%B')} {end_date.day}, {end_date.year}"


# ── HTML generation ──

def generate_html(content, edition_number, week_start, week_end):
    """Generate both website and beehiiv HTML. Returns (website_html, beehiiv_html, counts)."""
    videos, podcasts, articles, reddit_posts = organize_content_for_newsletter(content)
    video_count = sum(len(v) for v in videos.values())

    # Build content summary
    parts = []
    if video_count:
        parts.append(f"{video_count} videos")
    if podcasts:
        parts.append(f"{len(podcasts)} podcasts")
    if articles:
        parts.append(f"{len(articles)} articles")
    if reddit_posts:
        parts.append(f"{len(reddit_posts)} community discussions")
    content_summary = ', '.join(parts)

    intro = f"Welcome! This week we've curated {content_summary} of the best Hyrox content."
    week_range = format_week_range(week_start, week_end)
    canonical_url = f"https://hyroxweekly.com/archive/edition-{edition_number}"

    # Common template vars
    common_vars = dict(
        week_range=week_range,
        intro_text=intro,
        videos=videos,
        podcasts=podcasts,
        articles=articles,
        reddit_posts=reddit_posts,
        spotlight_athletes=[],
        current_year=datetime.now().year,
        newsletter_name='HYROX WEEKLY',
        tagline='Everything Hyrox, Every Week',
        footer_instagram='https://instagram.com/hyroxweekly',
        footer_website='https://hyroxweekly.com',
        footer_contact_email='team@hyroxweekly.com',
        section_title_podcasts='Worth a Listen',
        section_title_articles='Worth Reading',
        section_title_reddit='Community Discussions',
        section_title_athletes='\U0001f3c3 Athletes to Follow',
    )

    # Website HTML
    website_template_str = extract_template('WEBSITE_TEMPLATE')
    website_template = Template(website_template_str)
    website_html = website_template.render(
        **common_vars,
        canonical_url=canonical_url,
    )

    # Beehiiv HTML
    beehiiv_template_str = extract_template('BEEHIIV_TEMPLATE')
    beehiiv_template = Template(beehiiv_template_str)
    beehiiv_html = beehiiv_template.render(
        **common_vars,
        cta_heading='Never Miss an Edition',
        cta_subtext='The best Hyrox content, delivered weekly direct to your inbox.',
        cta_button_text='Subscribe',
        cta_button_url='https://hyroxweekly.com',
        sponsor_enabled=True,
        sponsor_label='Presented by',
        sponsor_cta='Your brand here \u2192',
        sponsor_email='sponsor@hyroxweekly.com',
    )

    counts = {
        'videos': video_count,
        'podcasts': len(podcasts),
        'articles': len(articles),
        'reddit': len(reddit_posts),
    }

    return website_html, beehiiv_html, counts


# ── Edition record creation ──

def get_next_edition_number():
    editions = supabase_get('weekly_editions', 'order=edition_number.desc&limit=1')
    if editions and len(editions) > 0:
        return (editions[0].get('edition_number') or 0) + 1
    return 1


def create_edition_record(edition_number, week_start_str, week_end_str):
    """Create edition record in DB and mark content as published.

    Args:
        edition_number: Edition number
        week_start_str: Week start date as YYYY-MM-DD string
        week_end_str: Week end date as YYYY-MM-DD string

    Returns:
        Edition ID or None
    """
    # Get selected content IDs for this week
    params = (
        f"status=eq.selected"
        f"&published_date=gte.{week_start_str}"
        f"&published_date=lte.{week_end_str}"
        f"&select=id"
    )
    content = supabase_get('content_items', params)
    content_ids = [item['id'] for item in content] if content else []

    data = {
        'edition_number': edition_number,
        'publish_date': datetime.now(timezone.utc).isoformat(),
        'week_start_date': week_start_str,
        'week_end_date': week_end_str,
        'status': 'published'
    }
    result = supabase_post('weekly_editions', data)
    edition_id = result.get('id') if result else None

    # Mark content as published
    for content_id in content_ids:
        supabase_patch('content_items', f'id=eq.{content_id}', {'status': 'published'})

    print(f"Created edition record (ID: {edition_id}), marked {len(content_ids)} items as published")
    return edition_id


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description='Generate Hyrox Weekly edition HTML')
    parser.add_argument('--week-start', required=True, help='Week start date (YYYY-MM-DD, Monday)')
    parser.add_argument('--week-end', required=True, help='Week end date (YYYY-MM-DD, Sunday)')
    parser.add_argument('--edition', required=True, type=int, help='Edition number')
    args = parser.parse_args()

    week_start = datetime.strptime(args.week_start, '%Y-%m-%d')
    week_end = datetime.strptime(args.week_end, '%Y-%m-%d')
    edition = args.edition

    print(f"Generating Edition #{edition}: {format_week_range(week_start, week_end)}")

    # Fetch selected content for the week
    params = (
        f"status=eq.selected"
        f"&published_date=gte.{args.week_start}"
        f"&published_date=lte.{args.week_end}"
        f"&order=display_order.asc"
    )
    content = supabase_get('content_items', params)

    if not content:
        print("ERROR: No selected content found for this week range.")
        print("Make sure you've reviewed and selected content in the dashboard first.")
        sys.exit(1)

    print(f"Found {len(content)} selected content items")

    # Generate HTML
    website_html, beehiiv_html, counts = generate_html(content, edition, week_start, week_end)

    # Save website HTML
    website_filename = f"edition-{edition}-{args.week_start}.html"
    website_path = os.path.join(SITE_DIR, 'archive', website_filename)
    with open(website_path, 'w') as f:
        f.write(website_html)
    print(f"Saved website HTML: {website_path}")

    # Save beehiiv HTML
    beehiiv_filename = f"newsletter_beehiiv_edition_{edition}.html"
    beehiiv_path = os.path.join(os.path.dirname(__file__), beehiiv_filename)
    with open(beehiiv_path, 'w') as f:
        f.write(beehiiv_html)
    print(f"Saved Beehiiv HTML: {beehiiv_path}")

    # Print summary
    print(f"\nContent summary:")
    print(f"  Videos:      {counts['videos']}")
    print(f"  Podcasts:    {counts['podcasts']}")
    print(f"  Articles:    {counts['articles']}")
    print(f"  Discussions: {counts['reddit']}")
    print(f"  Total:       {sum(counts.values())}")

    # Print counts in machine-readable format for the slash command
    print(f"\nCOUNTS:{counts['videos']},{counts['podcasts']},{counts['articles']},{counts['reddit']}")


if __name__ == '__main__':
    main()
