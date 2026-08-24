"""
YOLO Mode Runner — automated weekly content discovery, curation, and blurb generation.

Usage:
  python batch_yolo.py                  # prior week (default)
  python batch_yolo.py --week current   # this week
  python batch_yolo.py --week 2026-03-30  # specific Monday
  python batch_yolo.py --dry-run        # print what would run
"""
import argparse
import os
import socket
import sys
import re
import subprocess
import time
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# Supabase config
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://ksqrakczmecdbzxwsvea.supabase.co')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzcXJha2N6bWVjZGJ6eHdzdmVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjYxMTMsImV4cCI6MjA4MzYwMjExM30.sotuDt98HLIaDvkINuT-2mC8DPgpDTB6luu_xKCxe64'
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# YOLO config defaults — overridden by newsletter_settings table when available
YOLO_DEFAULTS = {
    'yolo_max_youtube': 8,
    'yolo_max_podcast': 8,
    'yolo_max_article': 8,
    'yolo_max_reddit': 9,
    'yolo_reddit_min_comments': 20,
    'yolo_reddit_min_upvotes': 20,
}

YOLO_CONFIG = dict(YOLO_DEFAULTS)


# ── Supabase API helpers ──

def get_headers():
    key = SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def supabase_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    try:
        r = requests.get(url, headers=get_headers())
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print(f"  GET error: {e}")
        return []

def supabase_patch(table, params, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    try:
        r = requests.patch(url, headers=get_headers(), json=data)
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"  PATCH error: {e}")
        return False

def supabase_delete(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    try:
        r = requests.delete(url, headers=get_headers())
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"  DELETE error: {e}")
        return False

def supabase_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = requests.post(url, headers=get_headers(), json=data)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"  POST error: {e}")
        return False


# ── Config loader ──

def load_yolo_config():
    """Load YOLO settings from Supabase newsletter_settings, fall back to defaults."""
    global YOLO_CONFIG
    try:
        rows = supabase_get('newsletter_settings') or []
        db_settings = {row['key']: row['value'] for row in rows}
        for key in YOLO_DEFAULTS:
            if key in db_settings:
                YOLO_CONFIG[key] = int(db_settings[key])
        print(f"  Loaded YOLO config from database")
    except Exception as e:
        print(f"  Could not load settings from DB ({e}), using defaults")
        YOLO_CONFIG.update(YOLO_DEFAULTS)


def resolve_week(week_arg: str):
    """Return (week_start, week_end) datetimes for the given --week argument."""
    today = datetime.now()
    this_monday = today - timedelta(days=today.weekday())
    this_monday = this_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    if week_arg == 'prior':
        week_start = this_monday - timedelta(days=7)
    elif week_arg == 'current':
        week_start = this_monday
    else:
        week_start = datetime.strptime(week_arg, '%Y-%m-%d')
        if week_start.weekday() != 0:
            raise ValueError(f"{week_arg} is not a Monday (it's a {week_start.strftime('%A')})")

    week_end = week_start + timedelta(days=6)
    return week_start, week_end


# ── Core YOLO functions ──

def clear_content_for_week(week_start, week_end):
    """Clear all content for the week."""
    end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')
    ws = week_start.strftime('%Y-%m-%d')
    total = 0
    for platform in ['youtube', 'podcast', 'article', 'reddit', 'instagram']:
        items = supabase_get('content_items',
            f'platform=eq.{platform}&published_date=gte.{ws}&published_date=lt.{end_date}&select=id') or []
        for item in items:
            supabase_delete('content_items', f'id=eq.{item["id"]}')
        total += len(items)
    return total


def parse_discovery_output(output):
    items_found = 0
    items_saved = 0
    m = re.search(r'(\d+)\s+(?:videos|posts|episodes|articles|items)\s+to\s+process', output, re.IGNORECASE)
    if m:
        items_found = int(m.group(1))
    else:
        m = re.search(r'[Ss]aving\s+(\d+)\s+(?:episodes|posts|articles|videos|items)', output)
        if m:
            items_found = int(m.group(1))
        else:
            m = re.search(r'Processing\s+(\d+)', output)
            if m:
                items_found = int(m.group(1))
    # Match the script-specific summary lines only. The loose r'Saved:\s*(\d+)'
    # pattern used to match per-item lines like "✓ Saved: 87: Your heart..."
    # which would spoof the count when an episode title started with a number.
    m = re.search(r'New\s+\w+\s+saved:\s*(\d+)', output, re.IGNORECASE)  # YouTube, Podcast
    if not m:
        m = re.search(r'complete!\s+Saved:\s*(\d+)', output, re.IGNORECASE)  # Article, Reddit
    if m:
        items_saved = int(m.group(1))
    return items_found, items_saved


def run_discovery_script(script_name, week_start_str, week_end_str):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    if not os.path.exists(script_path):
        return False, f"Script not found: {script_path}", 0, 0
    try:
        env = os.environ.copy()
        env['DISCOVERY_WEEK_START'] = week_start_str
        env['DISCOVERY_WEEK_END'] = week_end_str
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        found, saved = parse_discovery_output(output)
        return success, output, found, saved
    except subprocess.TimeoutExpired:
        return False, "Timed out after 300s", 0, 0
    except Exception as e:
        return False, str(e), 0, 0


def auto_curate_yolo(week_start, week_end):
    """Select top content per platform by engagement score."""
    priority_sources = supabase_get('priority_sources', 'is_active=eq.true') or []
    priority_names = {p['source_name'].lower() for p in priority_sources}

    limits = {
        'youtube': YOLO_CONFIG['yolo_max_youtube'],
        'podcast': YOLO_CONFIG['yolo_max_podcast'],
        'article': YOLO_CONFIG['yolo_max_article'],
        'reddit': YOLO_CONFIG['yolo_max_reddit'],
    }
    reddit_min_comments = YOLO_CONFIG['yolo_reddit_min_comments']
    reddit_min_upvotes = YOLO_CONFIG['yolo_reddit_min_upvotes']

    ws = week_start.strftime('%Y-%m-%d')
    end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')
    summary = {}

    for platform in ['youtube', 'podcast', 'article', 'reddit']:
        content = supabase_get('content_items',
            f'platform=eq.{platform}&status=eq.discovered'
            f'&published_date=gte.{ws}&published_date=lt.{end_date}'
            f'&select=id,title,platform,url,view_count,comment_count,published_date,creators(name)'
            f'&order=view_count.desc.nullslast') or []

        if platform == 'reddit':
            content = [c for c in content
                      if (c.get('comment_count', 0) or 0) >= reddit_min_comments
                      or (c.get('view_count', 0) or 0) >= reddit_min_upvotes]

        def sort_key(item):
            creator = (item.get('creators', {}).get('name') or '').lower() if item.get('creators') else ''
            is_priority = creator in priority_names
            return (0 if is_priority else 1, -(item.get('view_count') or 0))

        content.sort(key=sort_key)
        selected = content[:limits[platform]]

        for i, item in enumerate(selected):
            supabase_patch('content_items', f'id=eq.{item["id"]}', {
                'status': 'selected',
                'display_order': (i + 1) * 10,
                'selection_method': 'yolo',
                'updated_at': datetime.now(timezone.utc).isoformat()
            })

        summary[platform] = len(selected)

    summary['total'] = sum(summary.values())
    return summary


def generate_blurbs(week_start, week_end):
    """Generate AI blurbs for all YOLO-selected content."""
    if not ANTHROPIC_API_KEY:
        print("  WARNING: No ANTHROPIC_API_KEY - skipping blurb generation")
        return {'generated': 0, 'failed': 0, 'total': 0}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    ws = week_start.strftime('%Y-%m-%d')
    end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')

    content = supabase_get('content_items',
        f'status=eq.selected&selection_method=eq.yolo'
        f'&published_date=gte.{ws}&published_date=lt.{end_date}'
        f'&select=id,title,description,platform,ai_description,creator_id') or []

    # Fetch creator names
    creator_ids = list(set(c.get('creator_id') for c in content if c.get('creator_id')))
    creators_map = {}
    if creator_ids:
        creators = supabase_get('creators', f'id=in.({",".join(map(str, creator_ids))})') or []
        creators_map = {c['id']: c.get('name') for c in creators}

    needs_blurb = [c for c in content if not c.get('ai_description')]
    generated = 0
    failed = 0

    for item in needs_blurb:
        try:
            platform_context = {
                'youtube': 'YouTube video', 'podcast': 'podcast episode',
                'article': 'article', 'reddit': 'Reddit discussion'
            }.get(item.get('platform'), 'content')

            creator_name = creators_map.get(item.get('creator_id'))
            creator_info = f" by {creator_name}" if creator_name else ""

            prompt = f"""Write a brief blurb for this {platform_context}{creator_info} for a Hyrox fitness newsletter.

Title: {item.get('title', '')}

Original Description: {(item.get('description') or 'No description available')[:1000]}

Requirements:
- STRICT LIMIT: Keep under 230 characters (about 1-2 short sentences)
- Write in a crisp, professional sports journalism style (think Sports Illustrated)
- Be informative and direct - no hype or exaggeration
- Avoid words like: epic, amazing, incredible, ultimate, game-changer, crushing it, insane
- Assume readers already know what Hyrox is - no need to explain the sport
- Focus on the specific value: what will readers learn or gain?
- Do not use quotation marks around the blurb
- Do not start with "This video..." or "In this episode..."

Just return the blurb text, nothing else."""

            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            blurb = message.content[0].text.strip()

            if len(blurb) > 250:
                truncated = blurb[:247]
                last_period = truncated.rfind('.')
                last_space = truncated.rfind(' ')
                if last_period > 180:
                    blurb = truncated[:last_period + 1]
                elif last_space > 200:
                    blurb = truncated[:last_space] + '...'
                else:
                    blurb = truncated + '...'

            supabase_patch('content_items', f'id=eq.{item["id"]}', {
                'ai_description': blurb,
                'use_ai_description': True,
                'updated_at': datetime.now(timezone.utc).isoformat()
            })
            generated += 1
        except Exception as e:
            print(f"    Blurb failed for '{item.get('title', '?')[:50]}': {e}")
            failed += 1

    return {'generated': generated, 'failed': failed, 'total': len(needs_blurb)}


def record_discovery_run(platform, week_start, week_end, items_found, items_saved, status):
    supabase_post('discovery_runs', {
        'platform': platform,
        'run_date': datetime.now(timezone.utc).isoformat(),
        'items_discovered': items_found,
        'items_new': items_saved,
        'status': status,
        'date_range_start': str(week_start.strftime('%Y-%m-%d')),
        'date_range_end': str(week_end.strftime('%Y-%m-%d'))
    })


# ── Network readiness ──

def wait_for_network(timeout_secs: int = 300, interval_secs: int = 10) -> bool:
    """Block until Supabase DNS resolves and the API responds, or timeout.

    The launchd schedule fires Monday 06:00, but if the Mac was sleeping
    it wakes some time later (e.g. on lid-open). When that happens, WiFi
    and DNS aren't immediately ready — calls fail with `gaierror` for
    a minute or two. Without this guard, every discovery step misfires
    and the YOLO produces empty/broken results (as happened May 4 2026,
    where the Mac woke at 06:42 and the job ran with all DNS lookups
    failing).
    """
    host = SUPABASE_URL.replace('https://', '').replace('http://', '').rstrip('/')
    start = time.time()
    attempt = 0
    last_err = None
    while time.time() - start < timeout_secs:
        attempt += 1
        try:
            socket.gethostbyname(host)
            r = requests.get(f"{SUPABASE_URL}/rest/v1/", headers=get_headers(), timeout=5)
            if r.status_code < 500:
                if attempt > 1:
                    print(f"  Network ready after {attempt} attempt(s).")
                return True
            last_err = f"HTTP {r.status_code}"
        except socket.gaierror as e:
            last_err = f"DNS: {e}"
        except requests.RequestException as e:
            last_err = f"HTTP error: {e}"
        if attempt == 1:
            print(f"  Network not ready ({last_err}). Waiting up to {timeout_secs}s...")
        time.sleep(interval_secs)
    print(f"  Network never became ready after {timeout_secs}s. Last error: {last_err}. Aborting.")
    return False


# ── Main batch runner ──

def run_yolo_for_week(week_start, week_end, label=None):
    ws = week_start.strftime('%Y-%m-%d')
    we = week_end.strftime('%Y-%m-%d')
    header = label or f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

    print(f"\n{'='*60}")
    print(f"  YOLO: {header}")
    print(f"{'='*60}")

    # Step 1: Clear
    print(f"  [1/4] Clearing existing content...")
    cleared = clear_content_for_week(week_start, week_end)
    print(f"         Cleared {cleared} items")

    # Step 2: Discovery
    scripts = [
        ('youtube_discovery.py', 'YouTube', 'youtube'),
        ('podcast_discovery.py', 'Podcasts', 'podcast'),
        ('article_discovery.py', 'Articles', 'article'),
        ('reddit_discovery.py', 'Reddit', 'reddit'),
    ]
    print(f"  [2/4] Running discovery...")
    discovery_results = {}
    for script, name, platform in scripts:
        success, output, found, saved = run_discovery_script(script, ws, we)
        record_discovery_run(platform, week_start, week_end, found, saved, 'completed' if success else 'failed')
        status_icon = "OK" if success else "FAIL"
        print(f"         {name:10s} [{status_icon}] found={found}, saved={saved}")
        discovery_results[platform] = {'success': success, 'found': found, 'saved': saved}

    # Step 3: Auto-curate
    print(f"  [3/4] Auto-selecting content...")
    curation = auto_curate_yolo(week_start, week_end)
    print(f"         Selected: {curation.get('youtube',0)} videos, {curation.get('podcast',0)} podcasts, "
          f"{curation.get('article',0)} articles, {curation.get('reddit',0)} reddit = {curation.get('total',0)} total")

    # Step 4: Generate blurbs
    print(f"  [4/4] Generating AI blurbs...")
    blurbs = generate_blurbs(week_start, week_end)
    fail_msg = f" ({blurbs['failed']} failed)" if blurbs['failed'] else ""
    print(f"         Generated {blurbs['generated']}/{blurbs['total']} blurbs{fail_msg}")

    print(f"  DONE: {header}")
    return curation


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='YOLO Mode — automated weekly content discovery')
    parser.add_argument('--week', default='prior',
                        help='"prior" (default), "current", or a Monday date YYYY-MM-DD')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would run without executing')
    args = parser.parse_args()

    try:
        week_start, week_end = resolve_week(args.week)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    label = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

    if args.dry_run:
        print(f"Would run YOLO for {label}")
        sys.exit(0)

    print("=" * 60)
    print("  HYROX WEEKLY - YOLO MODE")
    print(f"  Week: {label}")
    print("=" * 60)

    # Wait for network — protects against running on cold-wake when WiFi/DNS isn't ready yet.
    if not wait_for_network():
        sys.exit(1)

    load_yolo_config()

    result = run_yolo_for_week(week_start, week_end, label)
    total = result.get('total', 0) if result else 0

    print(f"\n{'='*60}")
    print(f"  COMPLETE — {total} items selected for {label}")
    print(f"{'='*60}")
    sys.exit(0)
