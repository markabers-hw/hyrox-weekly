"""
Hyrox Weekly - Unified Dashboard

Complete workflow management:
1. Content Discovery (YouTube, Podcasts, Articles, Reddit)
2. Content Curation (Review & Select)
3. Newsletter Generation
4. Publishing & Archives
"""

import streamlit as st
from dotenv import load_dotenv
import os
import subprocess
import sys
import requests
from datetime import datetime, timedelta, timezone
from jinja2 import Template
import pytz
from urllib.parse import quote

load_dotenv()

# Anthropic API for AI blurb generation
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Supabase config (primary database)
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://ksqrakczmecdbzxwsvea.supabase.co')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzcXJha2N6bWVjZGJ6eHdzdmVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjYxMTMsImV4cCI6MjA4MzYwMjExM30.sotuDt98HLIaDvkINuT-2mC8DPgpDTB6luu_xKCxe64'

def get_supabase_headers(use_service_key=True):
    """Get headers for Supabase API requests"""
    key = SUPABASE_SERVICE_KEY if use_service_key and SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def supabase_get(table, params=None, single=False):
    """GET request to Supabase REST API"""
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
    """POST request to Supabase REST API"""
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
    """PATCH request to Supabase REST API"""
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

def supabase_delete(table, params):
    """DELETE request to Supabase REST API"""
    headers = get_supabase_headers()
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    try:
        response = requests.delete(url, headers=headers)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"Supabase DELETE error: {e}")
        return False

def supabase_upsert(table, data, on_conflict=None):
    """UPSERT request to Supabase REST API"""
    headers = get_supabase_headers()
    if on_conflict:
        headers['Prefer'] = f'resolution=merge-duplicates,return=representation'
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            result = response.json()
            return result[0] if isinstance(result, list) and result else result
        print(f"Supabase UPSERT error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Supabase UPSERT error: {e}")
        return None

# Timezone options for settings
TIMEZONE_OPTIONS = {
    'US/Pacific': 'US Pacific (PT)',
    'US/Mountain': 'US Mountain (MT)',
    'US/Central': 'US Central (CT)',
    'US/Eastern': 'US Eastern (ET)',
    'UTC': 'UTC',
    'Europe/London': 'UK (GMT/BST)',
    'Europe/Paris': 'Central Europe (CET)',
    'Australia/Sydney': 'Australia Sydney (AEST)',
    'Australia/Perth': 'Australia Perth (AWST)',
    'Asia/Tokyo': 'Japan (JST)',
    'Asia/Singapore': 'Singapore (SGT)',
}


def get_utc_now():
    """Get current time in UTC"""
    return datetime.now(timezone.utc)


def utc_to_local(utc_dt, tz_name='US/Pacific'):
    """Convert UTC datetime to local timezone"""
    if utc_dt is None:
        return None
    
    # If datetime is naive, assume it's UTC
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    
    local_tz = pytz.timezone(tz_name)
    return utc_dt.astimezone(local_tz)


def local_to_utc(local_dt, tz_name='US/Pacific'):
    """Convert local timezone datetime to UTC"""
    if local_dt is None:
        return None
    
    local_tz = pytz.timezone(tz_name)
    
    # If datetime is naive, localize it
    if local_dt.tzinfo is None:
        local_dt = local_tz.localize(local_dt)
    
    return local_dt.astimezone(timezone.utc)


def format_datetime_local(dt, tz_name='US/Pacific', fmt='%b %d, %Y %I:%M %p'):
    """Format a datetime for display in local timezone"""
    if dt is None:
        return ''

    # Handle string dates from Supabase REST API
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt[:16] if len(dt) >= 16 else dt

    local_dt = utc_to_local(dt, tz_name)
    return local_dt.strftime(fmt)


def format_date_local(dt, tz_name='US/Pacific', fmt='%b %d, %Y'):
    """Format a date for display in local timezone"""
    if dt is None:
        return ''

    # Handle string dates from Supabase REST API
    if isinstance(dt, str):
        try:
            # Try parsing ISO format datetime
            if 'T' in dt:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            else:
                # Just a date string
                from datetime import date
                parts = dt.split('-')
                if len(parts) == 3:
                    return datetime(int(parts[0]), int(parts[1]), int(parts[2])).strftime(fmt)
                return dt
        except:
            return dt[:10] if len(dt) >= 10 else dt

    if hasattr(dt, 'tzinfo'):
        local_dt = utc_to_local(dt, tz_name)
        return local_dt.strftime(fmt)
    else:
        # It's a date object, not datetime
        return dt.strftime(fmt)

CATEGORIES = [
    ('other', '📺 Other'),
    ('race_recap', '🏆 Race Recap'),
    ('training', '💪 Training'),
    ('nutrition', '🥗 Nutrition'),
    ('athlete_profile', '🌟 Athlete Profile'),
    ('gear', '⚙️ Gear'),
]

PLATFORM_CONFIG = {
    'youtube': {'emoji': '🎬', 'name': 'YouTube', 'color': '#FF0000'},
    'podcast': {'emoji': '🎙️', 'name': 'Podcasts', 'color': '#8e44ad'},
    'article': {'emoji': '📰', 'name': 'Articles', 'color': '#2980b9'},
    'reddit': {'emoji': '🔗', 'name': 'Reddit', 'color': '#FF4500'},
    'instagram': {'emoji': '📸', 'name': 'Instagram', 'color': '#E1306C'},
}

# Pagination settings
ITEMS_PER_PAGE = 15

# ============================================================================
# DATABASE FUNCTIONS (using Supabase REST API)
# ============================================================================

# No init functions needed - tables already exist in Supabase

@st.cache_data(ttl=120)
def get_priority_sources(platform=None):
    """Get all priority sources, optionally filtered by platform"""
    params = "is_active=eq.true&order=platform,source_name"
    if platform:
        params = f"is_active=eq.true&platform=eq.{platform}&order=source_name"
    return supabase_get('priority_sources', params) or []


def add_priority_source(platform, source_type, source_name, source_id=None, source_url=None, notes=None):
    """Add a new priority source"""
    data = {
        'platform': platform,
        'source_type': source_type,
        'source_name': source_name,
        'source_id': source_id,
        'source_url': source_url,
        'notes': notes,
        'is_active': True
    }
    result = supabase_upsert('priority_sources', data, 'platform,source_name')
    if result:
        get_priority_sources.clear()
    return result.get('id') if result else None


def remove_priority_source(source_id):
    """Remove (deactivate) a priority source"""
    result = supabase_patch('priority_sources', f'id=eq.{source_id}', {'is_active': False})
    return result is not None


def delete_priority_source(source_id):
    """Permanently delete a priority source"""
    result = supabase_delete('priority_sources', f'id=eq.{source_id}')
    if result:
        get_priority_sources.clear()
    return result


def get_athletes(category_filter='all', active_only=True):
    """Get athletes from database"""
    params = "order=name"
    filters = []
    if active_only:
        filters.append("is_active=eq.true")
    if category_filter != 'all':
        filters.append(f"category=eq.{category_filter}")
    if filters:
        params = "&".join(filters) + "&" + params
    return supabase_get('athletes', params) or []


def get_athlete_by_id(athlete_id):
    """Get a single athlete by ID"""
    return supabase_get('athletes', f'id=eq.{athlete_id}', single=True)


def add_athlete(name, instagram_handle, instagram_url=None, bio=None, category='elite', country=None, achievements=None, profile_image_url=None, website=None):
    """Add a new athlete to database"""
    if not instagram_url and instagram_handle:
        handle = instagram_handle.replace('@', '')
        instagram_url = f"https://instagram.com/{handle}"

    data = {
        'name': name,
        'instagram_handle': instagram_handle,
        'instagram_url': instagram_url,
        'bio': bio,
        'category': category,
        'country': country,
        'achievements': achievements,
        'profile_image_url': profile_image_url,
        'website': website
    }
    result = supabase_post('athletes', data)
    return result.get('id') if result else None


def update_athlete(athlete_id, **kwargs):
    """Update an athlete's information"""
    allowed_fields = ['name', 'instagram_handle', 'instagram_url', 'bio', 'category', 'country', 'achievements', 'profile_image_url', 'is_active', 'website']
    data = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not data:
        return False
    data['updated_at'] = datetime.now(timezone.utc).isoformat()
    return supabase_patch('athletes', f'id=eq.{athlete_id}', data) is not None


def delete_athlete(athlete_id):
    """Delete an athlete from database"""
    return supabase_delete('athletes', f'id=eq.{athlete_id}')


def mark_athlete_featured(athlete_id):
    """Mark an athlete as featured (increment count and set date)"""
    # Get current featured_count first
    athlete = get_athlete_by_id(athlete_id)
    if not athlete:
        return False
    new_count = (athlete.get('featured_count') or 0) + 1
    data = {
        'featured_count': new_count,
        'last_featured_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    return supabase_patch('athletes', f'id=eq.{athlete_id}', data) is not None


def get_athletes_for_spotlight(count=4):
    """Get athletes for newsletter spotlight, prioritizing those not recently featured"""
    # Get all active athletes and sort client-side (Supabase REST doesn't support NULLS FIRST easily)
    athletes = supabase_get('athletes', 'is_active=eq.true') or []
    # Sort by last_featured_date (None first), then by featured_count
    import random
    athletes.sort(key=lambda a: (
        a.get('last_featured_date') or '0000-00-00',
        a.get('featured_count') or 0,
        random.random()
    ))
    return athletes[:count]


def seed_initial_athletes():
    """Seed the athletes table with top Hyrox athletes and influencers"""
    
    # Check if we already have athletes
    existing = get_athletes(active_only=False)
    if existing:
        return len(existing)
    
    # Top Hyrox athletes - Elite 15 and notable athletes/influencers
    initial_athletes = [
        # Elite 15 Men
        {"name": "Hunter McIntyre", "instagram_handle": "hunterthehunter", "category": "elite", "country": "USA", "achievements": "Multiple Hyrox World Champion, CrossFit athlete", "bio": "Professional Hyrox athlete and world champion. Pushing the limits of hybrid fitness."},
        {"name": "Tobias Tondering", "instagram_handle": "tobiastondering", "category": "elite", "country": "Germany", "achievements": "Hyrox Elite 15, Multiple podium finishes", "bio": "German Hyrox elite athlete competing at the highest level."},
        {"name": "Ryan Kent", "instagram_handle": "ryankentpt", "category": "elite", "country": "UK", "achievements": "Hyrox Elite 15 athlete", "bio": "British elite Hyrox competitor and personal trainer."},
        {"name": "Kris Ruglys", "instagram_handle": "krisruglys", "category": "elite", "country": "Lithuania", "achievements": "Hyrox Elite 15, European Champion", "bio": "Lithuanian Hyrox champion dominating the European circuit."},
        {"name": "Alex Roncevic", "instagram_handle": "alex.roncevic", "category": "elite", "country": "Croatia", "achievements": "Hyrox Elite 15 athlete", "bio": "Croatian elite athlete known for consistent podium finishes."},
        
        # Elite 15 Women
        {"name": "Lauren Weeks", "instagram_handle": "laurenweeksfitness", "category": "elite", "country": "USA", "achievements": "Hyrox World Champion, Elite 15", "bio": "American Hyrox world champion and fitness professional."},
        {"name": "Leah Gilbert", "instagram_handle": "leahgilbertfit", "category": "elite", "country": "UK", "achievements": "Hyrox Elite 15, British Champion", "bio": "British Hyrox elite athlete and coach."},
        {"name": "Meg Jacoby", "instagram_handle": "megjacoby", "category": "elite", "country": "USA", "achievements": "Hyrox Elite 15 athlete", "bio": "American elite Hyrox competitor."},
        {"name": "Phoebe Campbell", "instagram_handle": "phoebe_campbell_", "category": "elite", "country": "Australia", "achievements": "Hyrox Elite 15, Australian Champion", "bio": "Australian Hyrox champion and elite athlete."},
        {"name": "Tia-Clair Toomey", "instagram_handle": "tiaclair1", "category": "elite", "country": "Australia", "achievements": "CrossFit Champion, Hyrox competitor", "bio": "CrossFit legend competing in Hyrox events."},
        
        # More Elite Athletes
        {"name": "Michael Miraglia", "instagram_handle": "mikemiraglia", "category": "elite", "country": "USA", "achievements": "Hyrox Elite athlete", "bio": "Elite Hyrox competitor from the USA."},
        {"name": "Jo McRae", "instagram_handle": "jomcrae_", "category": "elite", "country": "UK", "achievements": "Hyrox Elite 15", "bio": "British elite Hyrox athlete."},
        {"name": "David Ronneblad", "instagram_handle": "david_ronneblad", "category": "elite", "country": "Sweden", "achievements": "Hyrox Elite athlete", "bio": "Swedish Hyrox elite competitor."},
        {"name": "Ellie Turner", "instagram_handle": "ellieturner_fit", "category": "elite", "country": "UK", "achievements": "Hyrox Elite 15", "bio": "British elite athlete and fitness coach."},
        {"name": "Mark Van Burik", "instagram_handle": "markvanburik", "category": "elite", "country": "Netherlands", "achievements": "Hyrox Elite athlete", "bio": "Dutch elite Hyrox competitor."},
        
        # Influencers & Content Creators
        {"name": "Fergus Crawley", "instagram_handle": "ferguscrawley", "category": "influencer", "country": "UK", "achievements": "Hyrox content creator, YouTuber", "bio": "Hyrox athlete and popular fitness content creator."},
        {"name": "Will Sheridan", "instagram_handle": "willsheridanpt", "category": "influencer", "country": "UK", "achievements": "Hyrox athlete and coach", "bio": "Personal trainer specializing in Hyrox preparation."},
        {"name": "Zack George", "instagram_handle": "zaborgeorge", "category": "influencer", "country": "UK", "achievements": "UK's Fittest Man, Hyrox competitor", "bio": "Former UK's Fittest Man competing in Hyrox."},
        {"name": "Hyrox Training Club", "instagram_handle": "hyroxtrainingclub", "category": "influencer", "country": "Global", "achievements": "Official Hyrox training content", "bio": "Official Hyrox training tips and community."},
        {"name": "Andrew Hume", "instagram_handle": "andrewhume_", "category": "influencer", "country": "UK", "achievements": "Hyrox athlete and coach", "bio": "Hyrox coach and competitive athlete."},
        
        # More Athletes
        {"name": "Katrin Davidsdottir", "instagram_handle": "katrintanja", "category": "elite", "country": "Iceland", "achievements": "2x CrossFit Games Champion, Hyrox competitor", "bio": "Two-time CrossFit Games champion exploring Hyrox."},
        {"name": "James Sherwin", "instagram_handle": "jamessherwin_", "category": "elite", "country": "UK", "achievements": "Hyrox Elite athlete", "bio": "British elite Hyrox competitor."},
        {"name": "Emma McQuaid", "instagram_handle": "emmamcquaid_", "category": "elite", "country": "Ireland", "achievements": "Hyrox Elite athlete", "bio": "Irish elite Hyrox competitor."},
        {"name": "Moritz Klatten", "instagram_handle": "moritzklatten", "category": "influencer", "country": "Germany", "achievements": "Hyrox Co-Founder", "bio": "Co-founder of Hyrox and fitness visionary."},
        {"name": "Christian Toetzke", "instagram_handle": "christiantoetzke", "category": "influencer", "country": "Germany", "achievements": "Hyrox Co-Founder", "bio": "Co-founder of Hyrox, shaping the future of fitness racing."},
        
        # Additional Notable Athletes
        {"name": "Marcus Sheridan", "instagram_handle": "marcus_sheridan_", "category": "elite", "country": "UK", "achievements": "Hyrox competitive athlete", "bio": "Competitive Hyrox athlete from the UK."},
        {"name": "Nicole Owen", "instagram_handle": "nicolelowen", "category": "elite", "country": "USA", "achievements": "Hyrox Elite athlete", "bio": "American elite Hyrox competitor."},
        {"name": "Jake Dearden", "instagram_handle": "jakedearden", "category": "influencer", "country": "UK", "achievements": "Hyrox coach and content creator", "bio": "Hyrox specialist coach and content creator."},
        {"name": "Sarah Sheridan", "instagram_handle": "sarahsheridanfit", "category": "elite", "country": "UK", "achievements": "Hyrox competitive athlete", "bio": "British Hyrox competitor and fitness professional."},
        {"name": "Tom Evans", "instagram_handle": "tomevansultra", "category": "elite", "country": "UK", "achievements": "Ultra runner, Hyrox competitor", "bio": "Elite ultra runner competing in Hyrox events."},
    ]
    
    count = 0
    for athlete in initial_athletes:
        result = add_athlete(
            name=athlete["name"],
            instagram_handle=athlete["instagram_handle"],
            category=athlete.get("category", "elite"),
            country=athlete.get("country"),
            achievements=athlete.get("achievements"),
            bio=athlete.get("bio")
        )
        if result:
            count += 1
    
    return count


def record_discovery_run(platform, week_start, week_end, items_found=0, items_saved=0, status='completed'):
    """Record or update a discovery run"""
    data = {
        'platform': platform,
        'run_date': datetime.now(timezone.utc).isoformat(),
        'items_discovered': items_found,
        'items_new': items_saved,
        'status': status,
        'date_range_start': str(week_start),
        'date_range_end': str(week_end)
    }
    return supabase_post('discovery_runs', data) is not None


def get_discovery_runs(week_start, week_end):
    """Get discovery runs for a specific week"""
    runs = supabase_get('discovery_runs',
        f'date_range_start=eq.{week_start}&date_range_end=eq.{week_end}&order=platform') or []
    result = {}
    for run in runs:
        run['items_found'] = run.get('items_discovered', 0)
        run['items_saved'] = run.get('items_new', 0)
        run['run_at'] = run.get('run_date')
        result[run['platform']] = run
    return result


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_newsletter_settings():
    """Load all newsletter settings from database"""
    defaults = {
        'newsletter_name': 'HYROX WEEKLY',
        'tagline': 'Everything Hyrox, Every Week',
        'intro_template': "Welcome! This week we've curated {content_summary} of the best Hyrox content.",
        'cta_heading': 'Never Miss an Edition',
        'cta_subtext': 'The best Hyrox content, delivered weekly direct to your inbox.',
        'cta_button_text': 'Subscribe',
        'cta_button_url': 'https://hyroxweekly.com',
        'sponsor_enabled': 'true',
        'sponsor_label': 'Presented by',
        'sponsor_cta': 'Your brand here →',
        'sponsor_email': 'sponsor@hyroxweekly.com',
        'footer_instagram': 'https://instagram.com/hyroxweekly',
        'footer_website': 'https://hyroxweekly.com',
        'footer_contact_email': 'team@hyroxweekly.com',
        'youtube_min_duration': '60',
        'youtube_region': '',
        'podcast_country': '',
        'display_timezone': 'US/Pacific',
        'section_title_race_recap': 'Race Recaps',
        'section_title_training': 'Training & Workouts',
        'section_title_nutrition': 'Nutrition & Recovery',
        'section_title_athlete_profile': 'Athlete Spotlights',
        'section_title_gear': 'Gear & Equipment',
        'section_title_other': 'More Videos',
        'section_title_podcasts': 'Worth a Listen',
        'section_title_articles': 'Worth Reading',
        'section_title_reddit': 'Community Discussions',
        'section_title_athletes': '🏃 Athletes to Follow',
    }

    rows = supabase_get('newsletter_settings') or []
    for row in rows:
        defaults[row['key']] = row['value']
    return defaults


def save_newsletter_setting(key, value):
    """Save a single newsletter setting to database"""
    data = {'key': key, 'value': value, 'updated_at': datetime.now(timezone.utc).isoformat()}
    return supabase_upsert('newsletter_settings', data, 'key') is not None


def save_all_newsletter_settings(config):
    """Save all newsletter settings to database"""
    for key, value in config.items():
        save_newsletter_setting(key, value)
    return True


@st.cache_data(ttl=60)
def get_stats():
    """Get content counts by platform and status"""
    content = supabase_get('content_items', 'select=platform,status') or []
    # Count by platform and status
    counts = {}
    for item in content:
        key = (item.get('platform', 'unknown'), item.get('status', 'unknown'))
        counts[key] = counts.get(key, 0) + 1
    return [{'platform': k[0], 'status': k[1], 'count': v} for k, v in counts.items()]


@st.cache_data(ttl=60)
def get_content_counts_by_week(week_start=None, week_end=None):
    """Get content counts grouped by platform and status for a specific week"""
    params = 'select=platform,status'
    if week_start and week_end:
        params += f'&discovered_date=gte.{week_start}&discovered_date=lte.{week_end}'
    content = supabase_get('content_items', params) or []

    # Build nested dict: {platform: {status: count, 'total': count}}
    counts = {}
    for item in content:
        platform = item.get('platform', 'unknown')
        status = item.get('status', 'unknown')
        if platform not in counts:
            counts[platform] = {'discovered': 0, 'selected': 0, 'rejected': 0, 'published': 0, 'total': 0}
        counts[platform][status] = counts[platform].get(status, 0) + 1
        counts[platform]['total'] += 1

    return counts


@st.cache_data(ttl=300)
def get_content_cached(platform_filter='all', status_filter='discovered', week_start=None, week_end=None):
    """Cached version of get_content for read-only operations"""
    return _get_content_impl(platform_filter, status_filter, week_start, week_end)


def get_content(platform_filter='all', status_filter='discovered', week_start=None, week_end=None):
    """Get content - use this when you need fresh data after updates"""
    return _get_content_impl(platform_filter, status_filter, week_start, week_end)


def _get_content_impl(platform_filter='all', status_filter='discovered', week_start=None, week_end=None):
    """Internal implementation of get_content"""
    # Build filters
    filters = []
    if platform_filter != 'all':
        filters.append(f'platform=eq.{platform_filter}')
    if status_filter != 'all':
        filters.append(f'status=eq.{status_filter}')
    if week_start and week_end:
        filters.append(f'published_date=gte.{week_start}')
        end_date = week_end + timedelta(days=1)
        filters.append(f'published_date=lt.{end_date}')

    params = '&'.join(filters) if filters else ''
    params += ('&' if params else '') + 'order=display_order.asc.nullslast,view_count.desc.nullslast,engagement_score.desc.nullslast,published_date.desc'

    content = supabase_get('content_items', params) or []

    # Fetch creators for content that has creator_id
    creator_ids = list(set(c.get('creator_id') for c in content if c.get('creator_id')))
    creators_map = {}
    if creator_ids:
        creators = supabase_get('creators', f'id=in.({",".join(map(str, creator_ids))})') or []
        creators_map = {c['id']: c for c in creators}

    # Add creator info to content
    for item in content:
        creator = creators_map.get(item.get('creator_id'), {})
        item['creator_name'] = creator.get('name')
        item['creator_followers'] = creator.get('follower_count')
        item['creator_platform_id'] = creator.get('platform_id')

    return content


def clear_content_caches():
    """Clear all content-related caches after data updates"""
    get_content_cached.clear()
    get_stats.clear()
    get_content_counts_by_week.clear()


def clear_content_for_week(platforms, week_start, week_end):
    """Delete content items for specified platforms within a date range."""
    results = {}
    if 'all' in platforms:
        platforms = ['youtube', 'podcast', 'article', 'reddit', 'instagram']

    for platform in platforms:
        # Get items to count them first
        end_date = week_end + timedelta(days=1)
        items = supabase_get('content_items',
            f'platform=eq.{platform}&published_date=gte.{week_start}&published_date=lt.{end_date}&select=id') or []
        # Delete them
        for item in items:
            supabase_delete('content_items', f'id=eq.{item["id"]}')
        results[platform] = len(items)

    clear_content_caches()
    return results


def update_content_status(content_id, status):
    """Update content status"""
    data = {'status': status, 'updated_at': datetime.now(timezone.utc).isoformat()}
    result = supabase_patch('content_items', f'id=eq.{content_id}', data)
    clear_content_caches()
    return result


def update_content_category(content_id, category):
    """Update content category"""
    data = {'category': category, 'updated_at': datetime.now(timezone.utc).isoformat()}
    result = supabase_patch('content_items', f'id=eq.{content_id}', data)
    clear_content_caches()
    return result


def update_content_custom_description(content_id, custom_description):
    """Update the custom/override description for a content item"""
    data = {'custom_description': custom_description, 'updated_at': datetime.now(timezone.utc).isoformat()}
    result = supabase_patch('content_items', f'id=eq.{content_id}', data)
    clear_content_caches()
    return result


def update_content_display_order(content_id, display_order):
    """Update the display order for a content item"""
    data = {'display_order': display_order, 'updated_at': datetime.now(timezone.utc).isoformat()}
    result = supabase_patch('content_items', f'id=eq.{content_id}', data)
    clear_content_caches()
    return result


def update_content_editorial_note(content_id, editorial_note):
    """Update the editorial_note field (used for podcast Spotify/Apple links)"""
    data = {'editorial_note': editorial_note, 'updated_at': datetime.now(timezone.utc).isoformat()}
    return supabase_patch('content_items', f'id=eq.{content_id}', data)


def update_podcast_links(content_id, spotify_url, apple_url):
    """Update Spotify and Apple podcast links for an episode"""
    editorial_note = f"Spotify: {spotify_url} | Apple: {apple_url}"
    update_content_editorial_note(content_id, editorial_note)


def ensure_content_columns():
    """No-op - columns already exist in Supabase schema"""
    pass


# ============================================================================
# AI BLURB GENERATION
# ============================================================================

def generate_ai_blurb(title, description, platform, creator_name=None):
    """Generate an AI blurb for content using Claude API"""
    if not ANTHROPIC_API_KEY:
        return None, "Anthropic API key not configured. Add ANTHROPIC_API_KEY to your .env file."
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        # Build context based on platform
        platform_context = {
            'youtube': 'YouTube video',
            'podcast': 'podcast episode',
            'article': 'article',
            'reddit': 'Reddit discussion'
        }.get(platform, 'content')
        
        creator_info = f" by {creator_name}" if creator_name else ""
        
        prompt = f"""Write a brief blurb for this {platform_context}{creator_info} for a Hyrox fitness newsletter.

Title: {title}

Original Description: {description[:1000] if description else 'No description available'}

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
            model="claude-3-5-haiku-20241022",
            max_tokens=100,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        blurb = message.content[0].text.strip()
        
        # Ensure we don't exceed 250 chars (hard limit for newsletter display)
        if len(blurb) > 250:
            # Truncate at last complete sentence or word
            truncated = blurb[:247]
            last_period = truncated.rfind('.')
            last_space = truncated.rfind(' ')
            if last_period > 180:
                blurb = truncated[:last_period + 1]
            elif last_space > 200:
                blurb = truncated[:last_space] + '...'
            else:
                blurb = truncated + '...'
        
        return blurb, None
        
    except ImportError:
        return None, "Anthropic library not installed. Run: pip install anthropic"
    except Exception as e:
        return None, f"Error generating blurb: {str(e)}"


def update_content_ai_description(content_id, ai_description):
    """Update the AI-generated description for a content item"""
    data = {'ai_description': ai_description, 'updated_at': datetime.now(timezone.utc).isoformat()}
    return supabase_patch('content_items', f'id=eq.{content_id}', data)


def update_content_use_ai_description(content_id, use_ai):
    """Update whether to use AI description for a content item"""
    data = {'use_ai_description': use_ai, 'updated_at': datetime.now(timezone.utc).isoformat()}
    result = supabase_patch('content_items', f'id=eq.{content_id}', data)
    clear_content_caches()
    return result


def generate_blurbs_for_selected(week_start=None, week_end=None):
    """Generate AI blurbs for all selected content that doesn't have one yet"""
    content = get_content(status_filter='selected', week_start=week_start, week_end=week_end)
    
    results = []
    for item in content:
        if not item.get('ai_description'):
            blurb, error = generate_ai_blurb(
                title=item['title'],
                description=item.get('description', ''),
                platform=item['platform'],
                creator_name=item.get('creator_name')
            )
            if blurb:
                update_content_ai_description(item['id'], blurb)
                results.append({'id': item['id'], 'title': item['title'], 'success': True, 'blurb': blurb})
            else:
                results.append({'id': item['id'], 'title': item['title'], 'success': False, 'error': error})
    
    return results


def regenerate_blurbs(week_start=None, week_end=None, platform_filter='all'):
    """Regenerate AI blurbs for all selected content, overwriting existing blurbs
    
    Args:
        week_start: Start date for filtering
        week_end: End date for filtering  
        platform_filter: 'all' or specific platform like 'youtube', 'podcast', etc.
    """
    if platform_filter == 'all':
        content = get_content(status_filter='selected', week_start=week_start, week_end=week_end)
    else:
        content = get_content(platform_filter=platform_filter, status_filter='selected', week_start=week_start, week_end=week_end)
    
    results = []
    for item in content:
        blurb, error = generate_ai_blurb(
            title=item['title'],
            description=item.get('description', ''),
            platform=item['platform'],
            creator_name=item.get('creator_name')
        )
        if blurb:
            update_content_ai_description(item['id'], blurb)
            # Also set use_ai_description to True
            update_content_use_ai_description(item['id'], True)
            results.append({'id': item['id'], 'title': item['title'], 'platform': item['platform'], 'success': True, 'blurb': blurb})
        else:
            results.append({'id': item['id'], 'title': item['title'], 'platform': item['platform'], 'success': False, 'error': error})
    
    return results


def get_editions():
    """Get recent editions"""
    return supabase_get('weekly_editions', 'order=edition_number.desc&limit=10') or []


def get_next_edition_number():
    """Get the next edition number"""
    editions = supabase_get('weekly_editions', 'order=edition_number.desc&limit=1')
    if editions and len(editions) > 0:
        return (editions[0].get('edition_number') or 0) + 1
    return 1


def create_edition_record(edition_number, content_ids):
    """Create a new edition record and mark content as published"""
    week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
    week_end = week_start + timedelta(days=6)

    data = {
        'edition_number': edition_number,
        'publish_date': datetime.now(timezone.utc).isoformat(),
        'week_start_date': str(week_start),
        'week_end_date': str(week_end),
        'status': 'published'
    }
    result = supabase_post('weekly_editions', data)
    edition_id = result.get('id') if result else None

    # Mark content as published
    for content_id in content_ids:
        supabase_patch('content_items', f'id=eq.{content_id}', {'status': 'published'})

    return edition_id


# ============================================================================
# DISCOVERY FUNCTIONS
# ============================================================================

def parse_discovery_output(output):
    """Parse discovery script output to extract items found/saved counts"""
    import re
    
    items_found = 0
    items_saved = 0
    
    # Try different patterns for "found" count (after filtering)
    # Pattern 1: "X videos to process" (YouTube after filtering)
    to_process_match = re.search(r'(\d+)\s+(?:videos|posts|episodes|articles|items)\s+to\s+process', output, re.IGNORECASE)
    if to_process_match:
        items_found = int(to_process_match.group(1))
    else:
        # Pattern 2: "Saving X episodes/posts/articles" (Podcast, Reddit, Articles)
        saving_match = re.search(r'[Ss]aving\s+(\d+)\s+(?:episodes|posts|articles|videos|items)', output)
        if saving_match:
            items_found = int(saving_match.group(1))
        else:
            # Pattern 3: "Processing X videos" 
            processing_match = re.search(r'Processing\s+(\d+)', output)
            if processing_match:
                items_found = int(processing_match.group(1))
    
    # Look for saved count patterns
    # Pattern 1: "Saved: X" or "saved: X"
    saved_match = re.search(r'Saved:\s*(\d+)', output, re.IGNORECASE)
    if saved_match:
        items_saved = int(saved_match.group(1))
    else:
        # Pattern 2: "New episodes saved: X" or "New videos saved: X"
        new_saved_match = re.search(r'New\s+\w+\s+saved:\s*(\d+)', output, re.IGNORECASE)
        if new_saved_match:
            items_saved = int(new_saved_match.group(1))
    
    return items_found, items_saved


def run_discovery_script(script_name, week_start=None, week_end=None):
    """Run a discovery script and capture output."""
    script_path = os.path.join(os.getcwd(), script_name)
    
    if not os.path.exists(script_path):
        return False, f"Script not found: {script_path}", 0, 0
    
    try:
        # Set up environment with week dates and settings
        env = os.environ.copy()
        if week_start:
            env['DISCOVERY_WEEK_START'] = week_start
        if week_end:
            env['DISCOVERY_WEEK_END'] = week_end
        
        # Pass YouTube and Podcast settings
        if 'newsletter_config' in st.session_state:
            config = st.session_state['newsletter_config']
            env['YOUTUBE_MIN_DURATION'] = config.get('youtube_min_duration', '60')
            env['YOUTUBE_REGION'] = config.get('youtube_region', '')
            env['PODCAST_COUNTRY'] = config.get('podcast_country', '')
        
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd(),
            env=env
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        
        # Parse output for counts
        items_found, items_saved = parse_discovery_output(output)
        
        return success, output, items_found, items_saved
    except subprocess.TimeoutExpired:
        return False, "Script timed out after 120 seconds", 0, 0
    except Exception as e:
        return False, str(e), 0, 0


# ============================================================================
# NEWSLETTER GENERATION
# ============================================================================

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
<h1>{{ newsletter_name }}</h1>
<div class="tagline">{{ tagline }}</div>
<div class="edition-date">{{ week_range }}</div>
</div>

<div class="intro"><p>{{ intro_text }}</p></div>

{% if sponsor_enabled %}
<div class="sponsor-banner">
<span class="sponsor-label">{{ sponsor_label }}</span> &middot; <a href="mailto:{{ sponsor_email }}">{{ sponsor_cta }}</a>
</div>
{% endif %}

{% for category, items in videos.items() %}{% if items %}
<div class="section">
<h2 class="section-title">{{ category }}</h2>
<div class="content-grid">
{% for item in items %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><a href="{{ item.url }}"><img src="{{ item.thumbnail_url }}" alt=""></a></div>{% endif %}
<div class="content-platform">YouTube</div>
<h3 class="content-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="content-creator">{{ item.creator_name }}{% if item.duration_display %} &bull; {{ item.duration_display }}{% endif %}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" class="content-link">Watch &rarr;</a>
</div>
{% endfor %}
</div>
</div>
{% endif %}{% endfor %}

{% if podcasts %}
<div class="section section-podcast">
<h2 class="section-title">{{ section_title_podcasts }}</h2>
<div class="content-grid">
{% for item in podcasts %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><img src="{{ item.thumbnail_url }}" alt=""></div>{% endif %}
<div class="content-platform">Podcast</div>
<h3 class="content-title">{{ item.title }}</h3>
<div class="content-creator">{{ item.creator_name }}{% if item.duration_display %} &bull; {{ item.duration_display }}{% endif %}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
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
<h2 class="section-title">{{ section_title_articles }}</h2>
<div class="content-grid">
{% for item in articles %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><a href="{{ item.url }}"><img src="{{ item.thumbnail_url }}" alt=""></a></div>{% endif %}
<div class="content-platform">Article</div>
<h3 class="content-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="content-creator">{{ item.creator_name }}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" class="content-link">Read &rarr;</a>
</div>
{% endfor %}
</div>
</div>
{% endif %}

{% if reddit_posts %}
<div class="section">
<h2 class="section-title">{{ section_title_reddit }}</h2>
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

{% if spotlight_athletes %}
<div class="section">
<h2 class="section-title">{{ section_title_athletes }}</h2>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;">
{% for athlete in spotlight_athletes %}
<div style="text-align:center;padding:16px;background:#f8f9fa;border-radius:8px;">
<a href="{{ athlete.instagram_url }}" style="display:block;margin-bottom:10px;text-decoration:none;">
{% if athlete.profile_image_url %}
<img src="{{ athlete.profile_image_url }}" alt="{{ athlete.name }}" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:2px solid #E1306C;">
{% else %}
<div style="width:70px;height:70px;border-radius:50%;background:#E1306C;border:2px solid #E1306C;margin:0 auto;display:flex;align-items:center;justify-content:center;">
<span style="color:#fff;font-weight:700;font-size:24px;font-family:Arial,sans-serif;">{{ athlete.initials }}</span>
</div>
{% endif %}
</a>
<div style="font-weight:700;font-size:14px;margin-bottom:4px;">{{ athlete.name }}</div>
<a href="{{ athlete.instagram_url }}" style="color:#E1306C;font-size:13px;text-decoration:none;">@{{ athlete.instagram_handle }}</a>
{% if athlete.country_code %}
<div style="margin-top:6px;">
<img src="https://flagcdn.com/24x18/{{ athlete.country_code }}.png" alt="{{ athlete.country }}" style="height:14px;vertical-align:middle;border-radius:2px;box-shadow:0 1px 2px rgba(0,0,0,0.1);">
<span style="font-size:12px;color:#666;margin-left:4px;vertical-align:middle;">{{ athlete.country }}</span>
</div>
{% elif athlete.country %}
<div style="font-size:12px;color:#666;margin-top:6px;">{{ athlete.country }}</div>
{% endif %}
{% if athlete.bio %}<div style="font-size:11px;color:#888;margin-top:8px;line-height:1.4;">{{ athlete.bio[:80] }}{% if athlete.bio|length > 80 %}...{% endif %}</div>{% endif %}
</div>
{% endfor %}
</div>
</div>
{% endif %}

<div class="cta-section">
<h3>{{ cta_heading }}</h3>
<p>{{ cta_subtext }}</p>
<a href="{{ cta_button_url }}" class="cta-button">{{ cta_button_text }}</a>
</div>

<div class="footer">
<p><a href="{{ footer_instagram }}">Instagram</a> &middot; <a href="{{ footer_website }}">Website</a> &middot; <a href="mailto:{{ footer_contact_email }}">Contact Us</a> &middot; <a href="#">Unsubscribe</a></p>
<p style="margin-top:16px">&copy; {{ current_year }} {{ newsletter_name }}</p>
</div>

</div></body></html>"""


# Beehiiv-compatible template with ALL inline styles (no <style> tags)
BEEHIIV_TEMPLATE = """
<div style="max-width:640px;margin:0 auto;background:#ffffff;font-family:'Barlow',Helvetica,Arial,sans-serif;line-height:1.6;color:#1a1a1a;">

<!-- Header -->
<div style="background:#1a1a1a;padding:48px 32px;text-align:center;">
<h1 style="color:#ffffff;font-size:36px;font-weight:800;letter-spacing:6px;margin:0 0 8px 0;">{{ newsletter_name }}</h1>
<div style="color:rgba(255,255,255,0.5);font-size:13px;font-weight:500;letter-spacing:2px;text-transform:uppercase;">{{ tagline }}</div>
<div style="color:#CC5500;font-size:12px;margin-top:16px;font-weight:600;letter-spacing:1px;">{{ week_range }}</div>
</div>

<!-- Intro -->
<div style="padding:32px;border-bottom:1px solid #eeeeee;">
<p style="font-size:16px;color:#444444;line-height:1.7;font-weight:400;margin:0;">{{ intro_text }}</p>
</div>

{% if sponsor_enabled %}
<!-- Sponsor -->
<div style="padding:16px 32px;background:#fafafa;border-bottom:1px solid #eeeeee;text-align:center;">
<span style="font-size:10px;text-transform:uppercase;letter-spacing:2px;color:#999999;font-weight:600;">{{ sponsor_label }}</span> · <a href="mailto:{{ sponsor_email }}" style="color:#CC5500;text-decoration:none;font-weight:600;">{{ sponsor_cta }}</a>
</div>
{% endif %}

{% for category, items in videos.items() %}{% if items %}
<!-- Video Section: {{ category }} -->
<div style="padding:32px;border-bottom:1px solid #eeeeee;">
<h2 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#1a1a1a;margin:0 0 24px 0;padding-bottom:12px;border-bottom:2px solid #1a1a1a;">{{ category }}</h2>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
{% for item in items %}
<td width="50%" style="vertical-align:top;padding:{% if loop.index is odd %}0 12px 24px 0{% else %}0 0 24px 12px{% endif %};">
{% if item.thumbnail_url %}
<a href="{{ item.url }}" style="display:block;margin-bottom:12px;">
<img src="{{ item.thumbnail_url }}" alt="" style="width:100%;height:140px;object-fit:cover;border-radius:4px;">
</a>
{% endif %}
<div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#CC5500;margin-bottom:6px;">YouTube</div>
<h3 style="font-size:15px;font-weight:700;color:#1a1a1a;margin:0 0 6px 0;line-height:1.3;"><a href="{{ item.url }}" style="color:#1a1a1a;text-decoration:none;">{{ item.title }}</a></h3>
<div style="font-size:11px;color:#999999;font-weight:500;margin-bottom:8px;">{{ item.creator_name }}{% if item.duration_display %} • {{ item.duration_display }}{% endif %}</div>
{% if item.description %}<p style="font-size:13px;color:#555555;line-height:1.5;margin:0 0 8px 0;font-weight:400;">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" style="display:inline-block;font-size:11px;font-weight:700;color:#CC5500;text-decoration:none;text-transform:uppercase;letter-spacing:1px;">Watch →</a>
</td>
{% if loop.index is even or loop.last %}</tr>{% if not loop.last %}<tr>{% endif %}{% endif %}
{% endfor %}
</table>
</div>
{% endif %}{% endfor %}

{% if podcasts %}
<!-- Podcasts -->
<div style="padding:32px;border-bottom:1px solid #eeeeee;background:#fafafa;">
<h2 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#1a1a1a;margin:0 0 24px 0;padding-bottom:12px;border-bottom:2px solid #1a1a1a;">{{ section_title_podcasts }}</h2>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
{% for item in podcasts %}
<td width="50%" style="vertical-align:top;padding:{% if loop.index is odd %}0 12px 24px 0{% else %}0 0 24px 12px{% endif %};">
{% if item.thumbnail_url %}
<img src="{{ item.thumbnail_url }}" alt="" style="width:100%;height:140px;object-fit:cover;border-radius:4px;margin-bottom:12px;">
{% endif %}
<div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#CC5500;margin-bottom:6px;">Podcast</div>
<h3 style="font-size:15px;font-weight:700;color:#1a1a1a;margin:0 0 6px 0;line-height:1.3;">{{ item.title }}</h3>
<div style="font-size:11px;color:#999999;font-weight:500;margin-bottom:10px;">{{ item.creator_name }}{% if item.duration_display %} • {{ item.duration_display }}{% endif %}</div>
{% if item.description %}<p style="font-size:13px;color:#555555;line-height:1.5;margin:0 0 10px 0;font-weight:400;">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<div>
{% if item.spotify_url %}<a href="{{ item.spotify_url }}" style="display:inline-block;font-size:10px;font-weight:700;color:#1a1a1a;text-decoration:none;padding:6px 12px;border:2px solid #1a1a1a;text-transform:uppercase;letter-spacing:1px;margin-right:8px;">Spotify</a>{% endif %}
{% if item.apple_url %}<a href="{{ item.apple_url }}" style="display:inline-block;font-size:10px;font-weight:700;color:#1a1a1a;text-decoration:none;padding:6px 12px;border:2px solid #1a1a1a;text-transform:uppercase;letter-spacing:1px;">Apple</a>{% endif %}
</div>
</td>
{% if loop.index is even or loop.last %}</tr>{% if not loop.last %}<tr>{% endif %}{% endif %}
{% endfor %}
</table>
</div>
{% endif %}

{% if articles %}
<!-- Articles -->
<div style="padding:32px;border-bottom:1px solid #eeeeee;">
<h2 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#1a1a1a;margin:0 0 24px 0;padding-bottom:12px;border-bottom:2px solid #1a1a1a;">{{ section_title_articles }}</h2>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
{% for item in articles %}
<td width="50%" style="vertical-align:top;padding:{% if loop.index is odd %}0 12px 24px 0{% else %}0 0 24px 12px{% endif %};">
{% if item.thumbnail_url %}
<a href="{{ item.url }}" style="display:block;margin-bottom:12px;">
<img src="{{ item.thumbnail_url }}" alt="" style="width:100%;height:140px;object-fit:cover;border-radius:4px;">
</a>
{% endif %}
<div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#CC5500;margin-bottom:6px;">Article</div>
<h3 style="font-size:15px;font-weight:700;color:#1a1a1a;margin:0 0 6px 0;line-height:1.3;"><a href="{{ item.url }}" style="color:#1a1a1a;text-decoration:none;">{{ item.title }}</a></h3>
<div style="font-size:11px;color:#999999;font-weight:500;margin-bottom:8px;">{{ item.creator_name }}</div>
{% if item.description %}<p style="font-size:13px;color:#555555;line-height:1.5;margin:0 0 8px 0;font-weight:400;">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" style="display:inline-block;font-size:11px;font-weight:700;color:#CC5500;text-decoration:none;text-transform:uppercase;letter-spacing:1px;">Read →</a>
</td>
{% if loop.index is even or loop.last %}</tr>{% if not loop.last %}<tr>{% endif %}{% endif %}
{% endfor %}
</table>
</div>
{% endif %}

{% if reddit_posts %}
<!-- Reddit -->
<div style="padding:32px;border-bottom:1px solid #eeeeee;">
<h2 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#1a1a1a;margin:0 0 24px 0;padding-bottom:12px;border-bottom:2px solid #1a1a1a;">{{ section_title_reddit }}</h2>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
{% for item in reddit_posts %}
<td width="33%" style="vertical-align:top;padding:0 6px 12px 6px;">
<div style="padding:12px;background:#fafafa;border-left:2px solid #1a1a1a;">
<div style="font-size:9px;color:#999999;margin-bottom:4px;font-weight:500;text-transform:uppercase;">{{ item.creator_name }}</div>
<h3 style="font-size:12px;font-weight:600;color:#1a1a1a;margin:0 0 4px 0;line-height:1.25;"><a href="{{ item.url }}" style="color:#1a1a1a;text-decoration:none;">{{ item.title[:50] }}{% if item.title|length > 50 %}...{% endif %}</a></h3>
<div style="font-size:10px;color:#666666;font-weight:500;">{{ "{:,}".format(item.score or 0) }} upvotes</div>
</div>
</td>
{% if loop.index % 3 == 0 and not loop.last %}</tr><tr>{% endif %}
{% endfor %}
</tr>
</table>
</div>
{% endif %}

{% if spotlight_athletes %}
<!-- Athletes -->
<div style="padding:32px;border-bottom:1px solid #eeeeee;">
<h2 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#1a1a1a;margin:0 0 24px 0;padding-bottom:12px;border-bottom:2px solid #1a1a1a;">{{ section_title_athletes }}</h2>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
{% for athlete in spotlight_athletes %}
<td width="25%" style="vertical-align:top;text-align:center;padding:8px;">
<div style="padding:16px;background:#f8f9fa;border-radius:8px;">
<a href="{{ athlete.instagram_url }}" style="display:block;margin-bottom:10px;text-decoration:none;">
{% if athlete.profile_image_url %}
<img src="{{ athlete.profile_image_url }}" alt="{{ athlete.name }}" width="70" height="70" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:2px solid #E1306C;">
{% else %}
<div style="width:70px;height:70px;border-radius:50%;background:#E1306C;border:2px solid #E1306C;margin:0 auto;display:table;">
<span style="display:table-cell;vertical-align:middle;text-align:center;color:#ffffff;font-weight:700;font-size:24px;font-family:Arial,sans-serif;">{{ athlete.initials }}</span>
</div>
{% endif %}
</a>
<div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#1a1a1a;">{{ athlete.name }}</div>
<a href="{{ athlete.instagram_url }}" style="color:#E1306C;font-size:13px;text-decoration:none;">@{{ athlete.instagram_handle }}</a>
{% if athlete.country_code %}
<div style="margin-top:6px;">
<img src="https://flagcdn.com/24x18/{{ athlete.country_code }}.png" alt="{{ athlete.country }}" width="24" height="18" style="vertical-align:middle;border-radius:2px;">
<span style="font-size:12px;color:#666666;margin-left:4px;vertical-align:middle;">{{ athlete.country }}</span>
</div>
{% elif athlete.country %}
<div style="font-size:12px;color:#666666;margin-top:6px;">{{ athlete.country }}</div>
{% endif %}
</div>
</td>
{% if loop.index % 4 == 0 and not loop.last %}</tr><tr>{% endif %}
{% endfor %}
</tr>
</table>
</div>
{% endif %}

<!-- CTA -->
<div style="padding:32px;text-align:center;background:#1a1a1a;">
<h3 style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:1px;margin:0 0 6px 0;">{{ cta_heading }}</h3>
<p style="color:rgba(255,255,255,0.5);font-size:13px;margin:0 0 16px 0;font-weight:400;">{{ cta_subtext }}</p>
<a href="{{ cta_button_url }}" style="display:inline-block;padding:12px 32px;background:#CC5500;color:#ffffff;text-decoration:none;font-weight:700;font-size:12px;letter-spacing:2px;text-transform:uppercase;">{{ cta_button_text }}</a>
</div>

<!-- Footer - Beehiiv will add its own footer, but keeping minimal one -->
<div style="padding:24px;text-align:center;background:#1a1a1a;border-top:1px solid #333333;">
<p style="color:rgba(255,255,255,0.4);font-size:12px;margin:0;">
<a href="{{ footer_instagram }}" style="color:rgba(255,255,255,0.6);text-decoration:none;">Instagram</a> · 
<a href="{{ footer_website }}" style="color:rgba(255,255,255,0.6);text-decoration:none;">Website</a> · 
<a href="mailto:{{ footer_contact_email }}" style="color:rgba(255,255,255,0.6);text-decoration:none;">Contact</a>
</p>
</div>

</div>
"""


# Website-ready HTML template with SEO and social meta tags
WEBSITE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ newsletter_name }} - {{ week_range }}</title>
<meta name="description" content="{{ intro_text[:160] }}">

<!-- Open Graph / Facebook -->
<meta property="og:type" content="article">
<meta property="og:title" content="{{ newsletter_name }} - {{ week_range }}">
<meta property="og:description" content="{{ intro_text[:160] }}">
<meta property="og:url" content="{{ canonical_url }}">

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{{ newsletter_name }} - {{ week_range }}">
<meta name="twitter:description" content="{{ intro_text[:160] }}">

<!-- Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Barlow', sans-serif; line-height: 1.6; color: #1a1a1a; background: #f5f5f5; }
.page-wrapper { max-width: 800px; margin: 0 auto; padding: 20px; }
.nav { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; margin-bottom: 20px; }
.nav-brand { font-weight: 800; font-size: 18px; color: #1a1a1a; text-decoration: none; letter-spacing: 2px; }
.nav-links a { color: #666; text-decoration: none; margin-left: 20px; font-size: 14px; }
.nav-links a:hover { color: #CC5500; }
.newsletter-container { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.header { background: #1a1a1a; padding: 48px 32px; text-align: center; }
.header h1 { color: #fff; font-size: 36px; font-weight: 800; letter-spacing: 6px; margin-bottom: 8px; }
.header .tagline { color: rgba(255,255,255,0.5); font-size: 13px; font-weight: 500; letter-spacing: 2px; text-transform: uppercase; }
.header .edition-date { color: #CC5500; font-size: 12px; margin-top: 16px; font-weight: 600; letter-spacing: 1px; }
.intro { padding: 32px; border-bottom: 1px solid #eee; }
.intro p { font-size: 16px; color: #444; line-height: 1.7; }
.section { padding: 32px; border-bottom: 1px solid #eee; }
.section-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 3px; color: #1a1a1a; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 2px solid #1a1a1a; }
.section-podcast { background: #fafafa; }
.content-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; }
.content-item { margin-bottom: 0; }
.content-thumbnail { width: 100%; height: 140px; border-radius: 4px; overflow: hidden; margin-bottom: 12px; background: #f0f0f0; }
.content-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
.content-platform { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #CC5500; margin-bottom: 6px; }
.content-title { font-size: 15px; font-weight: 700; color: #1a1a1a; margin-bottom: 6px; line-height: 1.3; }
.content-title a { color: #1a1a1a; text-decoration: none; }
.content-title a:hover { color: #CC5500; }
.content-creator { font-size: 11px; color: #999; font-weight: 500; margin-bottom: 8px; }
.content-preview { font-size: 13px; color: #555; line-height: 1.5; margin-bottom: 8px; }
.content-link { display: inline-block; font-size: 11px; font-weight: 700; color: #CC5500; text-decoration: none; text-transform: uppercase; letter-spacing: 1px; }
.content-link:hover { text-decoration: underline; }
.podcast-links { display: flex; gap: 8px; margin-top: 10px; }
.podcast-link { font-size: 10px; font-weight: 700; color: #1a1a1a; text-decoration: none; padding: 6px 12px; border: 2px solid #1a1a1a; text-transform: uppercase; letter-spacing: 1px; }
.podcast-link:hover { background: #1a1a1a; color: #fff; }
.reddit-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.reddit-item { padding: 12px; background: #fafafa; border-left: 2px solid #1a1a1a; }
.reddit-meta { font-size: 9px; color: #999; margin-bottom: 4px; font-weight: 500; text-transform: uppercase; }
.reddit-title { font-size: 12px; font-weight: 600; color: #1a1a1a; margin-bottom: 4px; line-height: 1.25; }
.reddit-title a { color: #1a1a1a; text-decoration: none; }
.reddit-title a:hover { color: #CC5500; }
.reddit-stats { font-size: 10px; color: #666; }
.cta-section { padding: 32px; text-align: center; background: #1a1a1a; }
.cta-section h3 { color: #fff; font-size: 20px; font-weight: 700; letter-spacing: 1px; margin-bottom: 6px; }
.cta-section p { color: rgba(255,255,255,0.5); font-size: 13px; margin-bottom: 16px; }
.cta-button { display: inline-block; padding: 12px 32px; background: #CC5500; color: #fff; text-decoration: none; font-weight: 700; font-size: 12px; letter-spacing: 2px; text-transform: uppercase; }
.cta-button:hover { background: #b34a00; }
.footer { padding: 32px; text-align: center; background: #1a1a1a; }
.footer p { color: rgba(255,255,255,0.4); font-size: 12px; margin-bottom: 8px; }
.footer a { color: rgba(255,255,255,0.6); text-decoration: none; }
.footer a:hover { color: #CC5500; }
.subscribe-box { background: #fff; border-radius: 8px; padding: 32px; margin-top: 30px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }
.subscribe-box h3 { font-size: 20px; margin-bottom: 10px; }
.subscribe-box p { color: #666; margin-bottom: 20px; }
.archive-nav { display: flex; justify-content: space-between; margin-top: 30px; padding: 20px 0; border-top: 1px solid #eee; }
.archive-nav a { color: #CC5500; text-decoration: none; font-weight: 600; }
.archive-nav a:hover { text-decoration: underline; }
@media (max-width: 600px) {
  .content-grid { grid-template-columns: 1fr; }
  .reddit-grid { grid-template-columns: 1fr; }
  .header h1 { font-size: 28px; letter-spacing: 4px; }
  .nav { flex-direction: column; gap: 10px; }
  .subscribe-box { padding: 20px 10px; margin-left: -10px; margin-right: -10px; border-radius: 0; }
}
</style>
</head>
<body>

<div class="page-wrapper">

<!-- Navigation -->
<nav class="nav">
<a href="/" class="nav-brand">{{ newsletter_name }}</a>
<div class="nav-links">
<a href="/archive">Archive</a>
<a href="/#subscribe">Subscribe</a>
</div>
</nav>

<!-- Newsletter Content -->
<article class="newsletter-container">

<div class="header">
<h1>{{ newsletter_name }}</h1>
<div class="tagline">{{ tagline }}</div>
<div class="edition-date">{{ week_range }}</div>
</div>

<div class="intro"><p>{{ intro_text }}</p></div>

{% for category, items in videos.items() %}{% if items %}
<div class="section">
<h2 class="section-title">{{ category }}</h2>
<div class="content-grid">
{% for item in items %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><a href="{{ item.url }}"><img src="{{ item.thumbnail_url }}" alt="" loading="lazy"></a></div>{% endif %}
<div class="content-platform">YouTube</div>
<h3 class="content-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="content-creator">{{ item.creator_name }}{% if item.duration_display %} • {{ item.duration_display }}{% endif %}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" class="content-link">Watch →</a>
</div>
{% endfor %}
</div>
</div>
{% endif %}{% endfor %}

{% if podcasts %}
<div class="section section-podcast">
<h2 class="section-title">{{ section_title_podcasts }}</h2>
<div class="content-grid">
{% for item in podcasts %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><img src="{{ item.thumbnail_url }}" alt="" loading="lazy"></div>{% endif %}
<div class="content-platform">Podcast</div>
<h3 class="content-title">{{ item.title }}</h3>
<div class="content-creator">{{ item.creator_name }}{% if item.duration_display %} • {{ item.duration_display }}{% endif %}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
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
<h2 class="section-title">{{ section_title_articles }}</h2>
<div class="content-grid">
{% for item in articles %}
<div class="content-item">
{% if item.thumbnail_url %}<div class="content-thumbnail"><a href="{{ item.url }}"><img src="{{ item.thumbnail_url }}" alt="" loading="lazy"></a></div>{% endif %}
<div class="content-platform">Article</div>
<h3 class="content-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="content-creator">{{ item.creator_name }}</div>
{% if item.description %}<p class="content-preview">{{ item.description[:250] }}{% if item.description|length > 250 %}...{% endif %}</p>{% endif %}
<a href="{{ item.url }}" class="content-link">Read →</a>
</div>
{% endfor %}
</div>
</div>
{% endif %}

{% if reddit_posts %}
<div class="section">
<h2 class="section-title">{{ section_title_reddit }}</h2>
<div class="reddit-grid">
{% for item in reddit_posts %}
<div class="reddit-item">
<div class="reddit-meta">{{ item.creator_name }}</div>
<h3 class="reddit-title"><a href="{{ item.url }}">{{ item.title }}</a></h3>
<div class="reddit-stats">{{ "{:,}".format(item.score or 0) }} upvotes • {{ "{:,}".format(item.comments or 0) }} comments</div>
</div>
{% endfor %}
</div>
</div>
{% endif %}

{% if spotlight_athletes %}
<div class="section">
<h2 class="section-title">{{ section_title_athletes }}</h2>
<div class="content-grid" style="grid-template-columns: repeat(4, 1fr);">
{% for athlete in spotlight_athletes %}
<div style="text-align:center;padding:16px;background:#f8f9fa;border-radius:8px;">
<a href="{{ athlete.instagram_url }}" style="display:block;margin-bottom:10px;text-decoration:none;">
{% if athlete.profile_image_url %}
<img src="{{ athlete.profile_image_url }}" alt="{{ athlete.name }}" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:2px solid #E1306C;">
{% else %}
<div style="width:70px;height:70px;border-radius:50%;background:#E1306C;border:2px solid #E1306C;margin:0 auto;display:flex;align-items:center;justify-content:center;">
<span style="color:#fff;font-weight:700;font-size:24px;">{{ athlete.initials }}</span>
</div>
{% endif %}
</a>
<div style="font-weight:700;font-size:14px;margin-bottom:4px;">{{ athlete.name }}</div>
<a href="{{ athlete.instagram_url }}" style="color:#E1306C;font-size:13px;text-decoration:none;">@{{ athlete.instagram_handle }}</a>
{% if athlete.country_code %}
<div style="margin-top:6px;">
<img src="https://flagcdn.com/24x18/{{ athlete.country_code }}.png" alt="{{ athlete.country }}" style="height:14px;vertical-align:middle;">
<span style="font-size:12px;color:#666;margin-left:4px;">{{ athlete.country }}</span>
</div>
{% endif %}
</div>
{% endfor %}
</div>
</div>
{% endif %}

<div class="footer">
<p><a href="{{ footer_instagram }}">Instagram</a> · <a href="{{ footer_website }}">Website</a> · <a href="mailto:{{ footer_contact_email }}">Contact</a></p>
<p style="margin-top:16px">© {{ current_year }} {{ newsletter_name }}</p>
</div>

</article>

<!-- Subscribe Box -->
<div class="subscribe-box" id="subscribe">
<h3>Never Miss an Edition</h3>
<p>Get the best Hyrox content delivered to your inbox every week.</p>
{% if beehiiv_embed_code %}
{{ beehiiv_embed_code | safe }}
{% else %}
<a href="https://hyroxweekly.com" class="cta-button" style="margin-top: 10px;">Subscribe Free</a>
{% endif %}
</div>

<!-- Archive Navigation -->
<div class="archive-nav">
<a href="/archive">← Back to Archive</a>
<a href="/archive">View All Editions →</a>
</div>

</div>

</body>
</html>"""


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


def organize_content_for_newsletter(content, config=None):
    """Organize content into categories, using config for section titles."""
    # Get section titles from config or use defaults
    if config:
        cats = {
            'race_recap': config.get('section_title_race_recap', 'Race Recaps'), 
            'training': config.get('section_title_training', 'Training & Workouts'),
            'nutrition': config.get('section_title_nutrition', 'Nutrition & Recovery'), 
            'athlete_profile': config.get('section_title_athlete_profile', 'Athlete Spotlights'),
            'gear': config.get('section_title_gear', 'Gear & Equipment'), 
            'other': config.get('section_title_other', 'More Videos')
        }
    else:
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
        
        # Determine which description to use:
        # 1. If use_ai_description is True and ai_description exists, use AI description
        # 2. Else if custom_description exists, use custom description
        # 3. Otherwise fall back to original description
        if item.get('use_ai_description') and item.get('ai_description'):
            item['description'] = item['ai_description']
        elif item.get('custom_description'):
            item['description'] = item['custom_description']
        
        if platform == 'youtube':
            cat = cats.get(item.get('category') or 'other', cats['other'])
            if cat not in videos: videos[cat] = []
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
    
    # Sort podcasts, articles, reddit by display_order
    podcasts = sorted(podcasts, key=lambda x: x.get('display_order') or 999)
    articles = sorted(articles, key=lambda x: x.get('display_order') or 999)
    reddit_posts = sorted(reddit_posts, key=lambda x: x.get('display_order') or 999)
    
    return videos, podcasts, articles, reddit_posts


@st.cache_data(ttl=3600)  # Cache for 1 hour (weeks don't change often)
def generate_week_options(num_weeks=5):
    """Generate a list of week options for selectors"""
    today = datetime.now()
    weeks = []
    
    for i in range(num_weeks):
        # Calculate Monday of that week
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday + (i * 7))
        week_end = week_start + timedelta(days=6)
        
        # Format label
        if week_start.month == week_end.month:
            label = f"{week_start.strftime('%B')} {week_start.day}-{week_end.day}, {week_end.year}"
        elif week_start.year == week_end.year:
            label = f"{week_start.strftime('%B')} {week_start.day} - {week_end.strftime('%B')} {week_end.day}, {week_end.year}"
        else:
            label = f"{week_start.strftime('%B')} {week_start.day}, {week_start.year} - {week_end.strftime('%B')} {week_end.day}, {week_end.year}"
        
        if i == 0:
            label = f"📍 Current Week: {label}"
        
        weeks.append({
            'label': label,
            'start': week_start.date(),
            'end': week_end.date()
        })
    
    # Add "All Time" option
    weeks.append({
        'label': '📚 All Time (no date filter)',
        'start': None,
        'end': None
    })
    
    return weeks


def generate_newsletter_html(content, edition_number, config=None, selected_athletes=None):
    videos, podcasts, articles, reddit_posts = organize_content_for_newsletter(content, config)
    video_count = sum(len(v) for v in videos.values())
    
    # Build content summary for intro
    parts = []
    if video_count: parts.append(f"{video_count} videos")
    if podcasts: parts.append(f"{len(podcasts)} podcasts")
    if articles: parts.append(f"{len(articles)} articles")
    if reddit_posts: parts.append(f"{len(reddit_posts)} community discussions")
    content_summary = ', '.join(parts)
    
    # Use config or defaults
    if config:
        intro = config.get('intro_template', "Welcome! This week we've curated {content_summary} of the best Hyrox content.").format(content_summary=content_summary)
    else:
        intro = f"Welcome! This week we've curated {content_summary} of the best Hyrox content."
    
    # Get week range from config if provided, otherwise calculate
    if config and config.get('week_start') and config.get('week_end'):
        start_of_week = config['week_start']
        end_of_week = config['week_end']
        # Convert date to datetime if needed for strftime
        if hasattr(start_of_week, 'strftime'):
            pass  # Already has strftime
        else:
            start_of_week = datetime.combine(start_of_week, datetime.min.time())
            end_of_week = datetime.combine(end_of_week, datetime.min.time())
    else:
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
    
    # Use provided athletes or empty list (no auto-selection)
    # Add country codes for flag display
    spotlight_athletes = add_country_codes_to_athletes(selected_athletes) if selected_athletes else []
    
    template = Template(NEWSLETTER_TEMPLATE)
    html = template.render(
        week_range=week_range,
        intro_text=intro,
        videos=videos,
        podcasts=podcasts,
        articles=articles,
        reddit_posts=reddit_posts,
        spotlight_athletes=spotlight_athletes,
        current_year=datetime.now().year,
        # Config values
        newsletter_name=config.get('newsletter_name', 'HYROX WEEKLY') if config else 'HYROX WEEKLY',
        tagline=config.get('tagline', 'Everything Hyrox, Every Week') if config else 'Everything Hyrox, Every Week',
        cta_heading=config.get('cta_heading', 'Never Miss an Edition') if config else 'Never Miss an Edition',
        cta_subtext=config.get('cta_subtext', 'The best Hyrox content, delivered weekly direct to your inbox.') if config else 'The best Hyrox content, delivered weekly direct to your inbox.',
        cta_button_text=config.get('cta_button_text', 'Subscribe') if config else 'Subscribe',
        cta_button_url=config.get('cta_button_url', 'https://hyroxweekly.com') if config else 'https://hyroxweekly.com',
        sponsor_enabled=config.get('sponsor_enabled', 'true') == 'true' if config else True,
        sponsor_label=config.get('sponsor_label', 'Presented by') if config else 'Presented by',
        sponsor_cta=config.get('sponsor_cta', 'Your brand here →') if config else 'Your brand here →',
        sponsor_email=config.get('sponsor_email', 'sponsor@hyroxweekly.com') if config else 'sponsor@hyroxweekly.com',
        footer_instagram=config.get('footer_instagram', 'https://instagram.com/hyroxweekly') if config else 'https://instagram.com/hyroxweekly',
        footer_website=config.get('footer_website', 'https://hyroxweekly.com') if config else 'https://hyroxweekly.com',
        footer_contact_email=config.get('footer_contact_email', 'team@hyroxweekly.com') if config else 'team@hyroxweekly.com',
        # Section titles
        section_title_podcasts=config.get('section_title_podcasts', 'Worth a Listen') if config else 'Worth a Listen',
        section_title_articles=config.get('section_title_articles', 'Worth Reading') if config else 'Worth Reading',
        section_title_reddit=config.get('section_title_reddit', 'Community Discussions') if config else 'Community Discussions',
        section_title_athletes=config.get('section_title_athletes', '🏃 Athletes to Follow') if config else '🏃 Athletes to Follow',
    )
    return html


def generate_beehiiv_html(content, edition_number, config=None, selected_athletes=None):
    """Generate Beehiiv-compatible HTML with all inline styles (no <style> tags)"""
    videos, podcasts, articles, reddit_posts = organize_content_for_newsletter(content, config)
    video_count = sum(len(v) for v in videos.values())
    
    # Build content summary for intro
    parts = []
    if video_count: parts.append(f"{video_count} videos")
    if podcasts: parts.append(f"{len(podcasts)} podcasts")
    if articles: parts.append(f"{len(articles)} articles")
    if reddit_posts: parts.append(f"{len(reddit_posts)} community discussions")
    content_summary = ', '.join(parts)
    
    # Use config or defaults
    if config:
        intro = config.get('intro_template', "Welcome! This week we've curated {content_summary} of the best Hyrox content.").format(content_summary=content_summary)
    else:
        intro = f"Welcome! This week we've curated {content_summary} of the best Hyrox content."
    
    # Get week range from config if provided, otherwise calculate
    if config and config.get('week_start') and config.get('week_end'):
        start_of_week = config['week_start']
        end_of_week = config['week_end']
        if hasattr(start_of_week, 'strftime'):
            pass
        else:
            start_of_week = datetime.combine(start_of_week, datetime.min.time())
            end_of_week = datetime.combine(end_of_week, datetime.min.time())
    else:
        today = datetime.now()
        days_since_sunday = (today.weekday() + 1) % 7
        if days_since_sunday == 0:
            days_since_sunday = 7
        end_of_week = today - timedelta(days=days_since_sunday)
        start_of_week = end_of_week - timedelta(days=6)
    
    # Format week range
    if start_of_week.month == end_of_week.month:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day}-{end_of_week.day}, {end_of_week.year}"
    elif start_of_week.year == end_of_week.year:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day} - {end_of_week.strftime('%B')} {end_of_week.day}, {end_of_week.year}"
    else:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day}, {start_of_week.year} - {end_of_week.strftime('%B')} {end_of_week.day}, {end_of_week.year}"
    
    # Add country codes for flag display
    spotlight_athletes = add_country_codes_to_athletes(selected_athletes) if selected_athletes else []
    
    template = Template(BEEHIIV_TEMPLATE)
    html = template.render(
        week_range=week_range,
        intro_text=intro,
        videos=videos,
        podcasts=podcasts,
        articles=articles,
        reddit_posts=reddit_posts,
        spotlight_athletes=spotlight_athletes,
        current_year=datetime.now().year,
        newsletter_name=config.get('newsletter_name', 'HYROX WEEKLY') if config else 'HYROX WEEKLY',
        tagline=config.get('tagline', 'Everything Hyrox, Every Week') if config else 'Everything Hyrox, Every Week',
        cta_heading=config.get('cta_heading', 'Never Miss an Edition') if config else 'Never Miss an Edition',
        cta_subtext=config.get('cta_subtext', 'The best Hyrox content, delivered weekly direct to your inbox.') if config else 'The best Hyrox content, delivered weekly direct to your inbox.',
        cta_button_text=config.get('cta_button_text', 'Subscribe') if config else 'Subscribe',
        cta_button_url=config.get('cta_button_url', 'https://hyroxweekly.com') if config else 'https://hyroxweekly.com',
        sponsor_enabled=config.get('sponsor_enabled', 'true') == 'true' if config else True,
        sponsor_label=config.get('sponsor_label', 'Presented by') if config else 'Presented by',
        sponsor_cta=config.get('sponsor_cta', 'Your brand here →') if config else 'Your brand here →',
        sponsor_email=config.get('sponsor_email', 'sponsor@hyroxweekly.com') if config else 'sponsor@hyroxweekly.com',
        footer_instagram=config.get('footer_instagram', 'https://instagram.com/hyroxweekly') if config else 'https://instagram.com/hyroxweekly',
        footer_website=config.get('footer_website', 'https://hyroxweekly.com') if config else 'https://hyroxweekly.com',
        footer_contact_email=config.get('footer_contact_email', 'team@hyroxweekly.com') if config else 'team@hyroxweekly.com',
        # Section titles
        section_title_podcasts=config.get('section_title_podcasts', 'Worth a Listen') if config else 'Worth a Listen',
        section_title_articles=config.get('section_title_articles', 'Worth Reading') if config else 'Worth Reading',
        section_title_reddit=config.get('section_title_reddit', 'Community Discussions') if config else 'Community Discussions',
        section_title_athletes=config.get('section_title_athletes', '🏃 Athletes to Follow') if config else '🏃 Athletes to Follow',
    )
    return html


def generate_website_html(content, edition_number, config=None, selected_athletes=None):
    """Generate website-ready HTML with SEO meta tags for self-hosting"""
    videos, podcasts, articles, reddit_posts = organize_content_for_newsletter(content, config)
    video_count = sum(len(v) for v in videos.values())
    
    # Build content summary for intro
    parts = []
    if video_count: parts.append(f"{video_count} videos")
    if podcasts: parts.append(f"{len(podcasts)} podcasts")
    if articles: parts.append(f"{len(articles)} articles")
    if reddit_posts: parts.append(f"{len(reddit_posts)} community discussions")
    content_summary = ', '.join(parts)
    
    # Use config or defaults
    if config:
        intro = config.get('intro_template', "Welcome! This week we've curated {content_summary} of the best Hyrox content.").format(content_summary=content_summary)
    else:
        intro = f"Welcome! This week we've curated {content_summary} of the best Hyrox content."
    
    # Get week range from config if provided, otherwise calculate
    if config and config.get('week_start') and config.get('week_end'):
        start_of_week = config['week_start']
        end_of_week = config['week_end']
        if hasattr(start_of_week, 'strftime'):
            pass
        else:
            start_of_week = datetime.combine(start_of_week, datetime.min.time())
            end_of_week = datetime.combine(end_of_week, datetime.min.time())
    else:
        today = datetime.now()
        days_since_sunday = (today.weekday() + 1) % 7
        if days_since_sunday == 0:
            days_since_sunday = 7
        end_of_week = today - timedelta(days=days_since_sunday)
        start_of_week = end_of_week - timedelta(days=6)
    
    # Format week range
    if start_of_week.month == end_of_week.month:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day}-{end_of_week.day}, {end_of_week.year}"
    elif start_of_week.year == end_of_week.year:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day} - {end_of_week.strftime('%B')} {end_of_week.day}, {end_of_week.year}"
    else:
        week_range = f"{start_of_week.strftime('%B')} {start_of_week.day}, {start_of_week.year} - {end_of_week.strftime('%B')} {end_of_week.day}, {end_of_week.year}"
    
    # Add country codes for flag display
    spotlight_athletes = add_country_codes_to_athletes(selected_athletes) if selected_athletes else []
    
    # Generate canonical URL
    website_url = config.get('footer_website', 'https://hyroxweekly.com') if config else 'https://hyroxweekly.com'
    canonical_url = f"{website_url}/archive/edition-{edition_number}"
    
    template = Template(WEBSITE_TEMPLATE)
    html = template.render(
        week_range=week_range,
        intro_text=intro,
        videos=videos,
        podcasts=podcasts,
        articles=articles,
        reddit_posts=reddit_posts,
        spotlight_athletes=spotlight_athletes,
        current_year=datetime.now().year,
        canonical_url=canonical_url,
        newsletter_name=config.get('newsletter_name', 'HYROX WEEKLY') if config else 'HYROX WEEKLY',
        tagline=config.get('tagline', 'Everything Hyrox, Every Week') if config else 'Everything Hyrox, Every Week',
        footer_instagram=config.get('footer_instagram', 'https://instagram.com/hyroxweekly') if config else 'https://instagram.com/hyroxweekly',
        footer_website=config.get('footer_website', 'https://hyroxweekly.com') if config else 'https://hyroxweekly.com',
        footer_contact_email=config.get('footer_contact_email', 'team@hyroxweekly.com') if config else 'team@hyroxweekly.com',
        # Section titles
        section_title_podcasts=config.get('section_title_podcasts', 'Worth a Listen') if config else 'Worth a Listen',
        section_title_articles=config.get('section_title_articles', 'Worth Reading') if config else 'Worth Reading',
        section_title_reddit=config.get('section_title_reddit', 'Community Discussions') if config else 'Community Discussions',
        section_title_athletes=config.get('section_title_athletes', '🏃 Athletes to Follow') if config else '🏃 Athletes to Follow',
        # Beehiiv embed
        beehiiv_embed_code=config.get('beehiiv_embed_code', '<p style="color:#999;font-size:12px;">Subscribe form coming soon</p>') if config else '',
    )
    return html


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Country name to ISO 3166-1 alpha-2 code mapping for flag images
COUNTRY_CODE_MAP = {
    'usa': 'us', 'united states': 'us', 'america': 'us', 'us': 'us',
    'uk': 'gb', 'united kingdom': 'gb', 'great britain': 'gb', 'england': 'gb', 'britain': 'gb', 'gb': 'gb',
    'germany': 'de', 'deutschland': 'de', 'de': 'de',
    'australia': 'au', 'aus': 'au', 'au': 'au',
    'canada': 'ca', 'ca': 'ca',
    'france': 'fr', 'fr': 'fr',
    'netherlands': 'nl', 'holland': 'nl', 'nl': 'nl',
    'sweden': 'se', 'se': 'se',
    'norway': 'no', 'no': 'no',
    'denmark': 'dk', 'dk': 'dk',
    'finland': 'fi', 'fi': 'fi',
    'iceland': 'is', 'is': 'is',
    'ireland': 'ie', 'ie': 'ie',
    'spain': 'es', 'es': 'es',
    'italy': 'it', 'it': 'it',
    'portugal': 'pt', 'pt': 'pt',
    'austria': 'at', 'at': 'at',
    'switzerland': 'ch', 'ch': 'ch',
    'belgium': 'be', 'be': 'be',
    'poland': 'pl', 'pl': 'pl',
    'czech republic': 'cz', 'czechia': 'cz', 'cz': 'cz',
    'hungary': 'hu', 'hu': 'hu',
    'croatia': 'hr', 'hr': 'hr',
    'lithuania': 'lt', 'lt': 'lt',
    'latvia': 'lv', 'lv': 'lv',
    'estonia': 'ee', 'ee': 'ee',
    'new zealand': 'nz', 'nz': 'nz',
    'japan': 'jp', 'jp': 'jp',
    'south korea': 'kr', 'korea': 'kr', 'kr': 'kr',
    'china': 'cn', 'cn': 'cn',
    'singapore': 'sg', 'sg': 'sg',
    'brazil': 'br', 'br': 'br',
    'mexico': 'mx', 'mx': 'mx',
    'south africa': 'za', 'za': 'za',
    'uae': 'ae', 'united arab emirates': 'ae', 'dubai': 'ae', 'ae': 'ae',
    'global': None,  # No flag for global
}


def get_country_code(country_name):
    """Convert country name to ISO 3166-1 alpha-2 code for flag images."""
    if not country_name:
        return None
    return COUNTRY_CODE_MAP.get(country_name.lower().strip())


def get_initials(name):
    """Get initials from a name (e.g., 'Hunter McIntyre' -> 'HM')"""
    if not name:
        return '?'
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1:
        return parts[0][0].upper()
    return '?'


def add_country_codes_to_athletes(athletes):
    """Add country_code and initials fields to athlete dictionaries."""
    enhanced = []
    for athlete in athletes:
        # Create a copy to avoid modifying original
        athlete_copy = dict(athlete)
        athlete_copy['country_code'] = get_country_code(athlete.get('country'))
        athlete_copy['initials'] = get_initials(athlete.get('name'))
        enhanced.append(athlete_copy)
    return enhanced


def format_number(num):
    if not num: return "0"
    num = int(num)
    if num >= 1000000: return f"{num/1000000:.1f}M"
    if num >= 1000: return f"{num/1000:.1f}K"
    return str(num)


def format_duration(seconds):
    """Format duration in seconds to human readable string (e.g., '5:30' or '1:23:45')"""
    if not seconds:
        return ""

    seconds = int(seconds)
    if seconds < 60:
        return f"0:{seconds:02d}"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


# ============================================================================
# CONTENT ITEM FRAGMENT - Renders independently to avoid full page reruns
# ============================================================================

@st.fragment
def render_content_item(item, display_tz):
    """Render a single content item as a fragment - reruns independently on interaction"""
    with st.container(border=True):
        col1, col2, col3 = st.columns([1, 3, 1])

        platform = item['platform']
        platform_cfg = PLATFORM_CONFIG.get(platform, {'emoji': '📺', 'name': platform})
        status = item['status']

        with col1:
            if item['thumbnail_url']:
                st.image(item['thumbnail_url'], width=150)
            else:
                st.markdown(f"### {platform_cfg['emoji']}")

        with col2:
            st.markdown(f"**{platform_cfg['emoji']} [{item['title'][:60]}{'...' if len(item['title']) > 60 else ''}]({item['url']})**")

            # Format published date using timezone
            pub_date = item.get('published_date')
            pub_date_str = format_date_local(pub_date, display_tz) if pub_date else ''

            creator_info = item['creator_name'] or 'Unknown'
            if pub_date_str:
                creator_info += f" • 📅 {pub_date_str}"
            st.caption(creator_info)

            if platform == 'youtube':
                duration_str = format_duration(item.get('duration_seconds'))
                duration_display = f" • ⏱️ {duration_str}" if duration_str else ""
                st.caption(f"👁️ {format_number(item['view_count'])} views • 👍 {format_number(item['like_count'])}{duration_display}")
            elif platform == 'podcast':
                duration_str = format_duration(item.get('duration_seconds'))
                duration_display = f"⏱️ {duration_str}" if duration_str else ""
                popularity = item.get('view_count', 0)
                popularity_display = f"📊 {popularity} episodes" if popularity else ""
                parts = [p for p in [duration_display, popularity_display] if p]
                st.caption(" • ".join(parts) if parts else "🎙️ Podcast episode")

                # Parse and display Spotify/Apple links
                spotify_url, apple_url = parse_podcast_links(item.get('editorial_note', ''))
                link_parts = []
                if spotify_url:
                    is_search = '/search/' in spotify_url
                    if is_search:
                        link_parts.append(f"[🎵 Spotify (search)]({spotify_url})")
                    else:
                        link_parts.append(f"[🎵 Spotify]({spotify_url})")
                if apple_url:
                    link_parts.append(f"[🍎 Apple]({apple_url})")
                if link_parts:
                    st.markdown(" • ".join(link_parts))

                # Edit podcast links expander
                with st.expander("🔗 Edit Podcast Links", expanded=False):
                    st.caption("Update Spotify and Apple Podcast URLs for this episode")

                    new_spotify = st.text_input(
                        "Spotify URL",
                        value=spotify_url or '',
                        key=f"spotify_{item['id']}",
                        placeholder="https://open.spotify.com/episode/..."
                    )

                    new_apple = st.text_input(
                        "Apple Podcasts URL",
                        value=apple_url or '',
                        key=f"apple_{item['id']}",
                        placeholder="https://podcasts.apple.com/..."
                    )

                    if st.button("💾 Save Links", key=f"save_links_{item['id']}"):
                        update_podcast_links(item['id'], new_spotify, new_apple)
                        st.success("✅ Podcast links updated!")
                        st.rerun()

            elif platform == 'reddit':
                st.caption(f"⬆️ {format_number(item['view_count'])} upvotes • 💬 {format_number(item['comment_count'])}")

        with col3:
            # Status badge with custom styling
            status_colors = {
                'discovered': ('📥', 'status-discovered'),
                'selected': ('✅', 'status-selected'),
                'rejected': ('❌', 'status-rejected'),
                'published': ('📤', 'status-discovered')
            }
            icon, badge_class = status_colors.get(status, ('📋', 'status-discovered'))
            st.markdown(f'<span class="status-badge {badge_class}">{icon} {status.title()}</span>', unsafe_allow_html=True)

            bcol1, bcol2 = st.columns(2)
            with bcol1:
                if item['status'] != 'selected':
                    if st.button("✅", key=f"sel_{item['id']}", help="Select"):
                        update_content_status(item['id'], 'selected')
                        clear_content_caches()
                        st.rerun()
            with bcol2:
                if item['status'] != 'rejected':
                    if st.button("❌", key=f"rej_{item['id']}", help="Reject"):
                        update_content_status(item['id'], 'rejected')
                        clear_content_caches()
                        st.rerun()

            current_cat = item['category'] or 'other'
            cat_opts = [c[0] for c in CATEGORIES]
            new_cat = st.selectbox(
                "Category",
                options=cat_opts,
                index=cat_opts.index(current_cat) if current_cat in cat_opts else 0,
                format_func=lambda x: dict(CATEGORIES)[x],
                key=f"cat_{item['id']}",
                label_visibility="collapsed"
            )
            if new_cat != current_cat:
                update_content_category(item['id'], new_cat)
                clear_content_caches()

            # Display order
            current_order = item.get('display_order') or 999
            new_order = st.number_input(
                "Order",
                min_value=1,
                max_value=99,
                value=current_order if current_order < 999 else 1,
                key=f"order_{item['id']}",
                help="Lower numbers appear first (1 = first)"
            )
            if new_order != current_order:
                update_content_display_order(item['id'], new_order)
                clear_content_caches()

        # Expandable section for description editing with AI blurb
        with st.expander("✏️ Edit Description / AI Blurb", expanded=False):
            original_desc = item.get('description') or ''
            custom_desc = item.get('custom_description') or ''
            ai_desc = item.get('ai_description') or ''
            use_ai = item.get('use_ai_description') or False

            st.markdown("**📄 Original Description:**")
            if original_desc:
                st.caption(original_desc[:300] + ('...' if len(original_desc) > 300 else ''))
            else:
                st.caption("_No original description available_")

            st.markdown("---")

            st.markdown("**✨ AI-Generated Blurb:**")

            if ai_desc:
                st.info(ai_desc)
            else:
                st.caption("_No AI blurb generated yet_")

            col_gen1, col_gen2 = st.columns([1, 2])
            with col_gen1:
                if st.button("✨ Generate AI Blurb", key=f"gen_ai_{item['id']}"):
                    with st.spinner("Generating..."):
                        blurb, error = generate_ai_blurb(
                            title=item['title'],
                            description=original_desc,
                            platform=item['platform'],
                            creator_name=item.get('creator_name')
                        )
                        if blurb:
                            update_content_ai_description(item['id'], blurb)
                            st.success("AI blurb generated!")
                            st.rerun()
                        else:
                            st.error(error)

            st.markdown("---")

            st.markdown("**✏️ Custom Description (editable):**")
            edited_desc = st.text_area(
                "Edit description",
                value=custom_desc if custom_desc else (ai_desc if ai_desc else ''),
                key=f"desc_{item['id']}",
                height=80,
                label_visibility="collapsed",
                placeholder="Enter a custom description or edit the AI blurb..."
            )

            if st.button("💾 Save Custom Description", key=f"save_desc_{item['id']}"):
                update_content_custom_description(item['id'], edited_desc if edited_desc.strip() else None)
                st.success("Custom description saved!")
                st.rerun()

            st.markdown("---")

            st.markdown("**🎯 Use in Newsletter:**")

            if use_ai and ai_desc:
                current_selection = "ai"
            elif custom_desc:
                current_selection = "custom"
            else:
                current_selection = "original"

            desc_options = ["original", "custom", "ai"]
            desc_labels = {
                "original": "📄 Original Description",
                "custom": "✏️ Custom Description",
                "ai": "✨ AI Blurb"
            }

            selected_desc = st.radio(
                "Select which description to use",
                options=desc_options,
                index=desc_options.index(current_selection),
                format_func=lambda x: desc_labels[x],
                key=f"desc_choice_{item['id']}",
                horizontal=True,
                label_visibility="collapsed"
            )

            if selected_desc != current_selection:
                if selected_desc == "ai":
                    update_content_use_ai_description(item['id'], True)
                    update_content_custom_description(item['id'], None)
                elif selected_desc == "custom":
                    update_content_use_ai_description(item['id'], False)
                else:  # original
                    update_content_use_ai_description(item['id'], False)
                    update_content_custom_description(item['id'], None)
                st.rerun()

            st.markdown("**Preview (what will appear in newsletter):**")
            if selected_desc == "ai" and ai_desc:
                st.success(ai_desc)
            elif selected_desc == "custom" and custom_desc:
                st.success(custom_desc)
            elif selected_desc == "custom" and edited_desc:
                st.warning(f"(Unsaved) {edited_desc}")
            else:
                st.success(original_desc[:200] + ('...' if len(original_desc) > 200 else '') if original_desc else "_No description_")

        # Priority source button
        creator_name = item.get('creator_name') or 'Unknown'
        if creator_name and creator_name != 'Unknown':
            existing_priorities = get_priority_sources(platform)
            is_priority = any(p['source_name'].lower() == creator_name.lower() for p in existing_priorities)

            if is_priority:
                st.caption("⭐ Priority Source")
            else:
                if st.button(f"⭐ Add '{creator_name}' as Priority", key=f"priority_{item['id']}", help="Always check this source during discovery"):
                    source_type = 'channel' if platform == 'youtube' else 'show' if platform == 'podcast' else 'source'
                    source_id = item.get('creator_platform_id') if platform == 'youtube' else None
                    add_priority_source(
                        platform=platform,
                        source_type=source_type,
                        source_name=creator_name,
                        source_id=source_id,
                        source_url=item.get('url', ''),
                        notes=f"Added from curation on {datetime.now().strftime('%Y-%m-%d')}"
                    )
                    st.success(f"✅ Added '{creator_name}' as priority source!")
                    st.rerun()


# ============================================================================
# ATHLETE CARD FRAGMENT - For Athletes page list
# ============================================================================

@st.fragment
def render_athlete_card(athlete):
    """Render a single athlete card as a fragment - reruns independently on interaction"""
    with st.expander(f"{'🏆' if athlete['category'] == 'elite' else '📱'} {athlete['name']} (@{athlete['instagram_handle'] or 'N/A'})" + (" 🚫" if not athlete['is_active'] else "")):
        # Top row with thumbnail and basic info
        top_col1, top_col2 = st.columns([1, 4])

        with top_col1:
            if athlete.get('profile_image_url'):
                st.image(athlete['profile_image_url'], width=100)
            else:
                st.markdown("### 👤")
                st.caption("No photo")

        with top_col2:
            st.markdown(f"**{athlete['name']}**")
            if athlete['instagram_handle']:
                st.markdown(f"[@{athlete['instagram_handle']}]({athlete['instagram_url']})")
            st.caption(f"🌍 {athlete['country'] or 'Unknown'} • {'🏆 Elite' if athlete['category'] == 'elite' else '📱 Influencer'}")
            st.caption(f"Featured {athlete['featured_count'] or 0} times | Last: {athlete['last_featured_date'] or 'Never'}")

        st.markdown("---")

        # Edit form with all fields
        with st.form(key=f"edit_athlete_{athlete['id']}"):
            # Row 1: Name and Instagram
            row1_col1, row1_col2, row1_col3 = st.columns(3)
            with row1_col1:
                new_name = st.text_input("Name", value=athlete['name'] or '', key=f"name_{athlete['id']}")
            with row1_col2:
                new_handle = st.text_input("Instagram Handle", value=athlete['instagram_handle'] or '', key=f"handle_{athlete['id']}")
            with row1_col3:
                new_instagram_url = st.text_input("Instagram URL", value=athlete['instagram_url'] or '', key=f"igurl_{athlete['id']}")

            # Row 2: Country, Category, Website
            row2_col1, row2_col2, row2_col3 = st.columns(3)
            with row2_col1:
                new_country = st.text_input("Country", value=athlete['country'] or '', key=f"country_{athlete['id']}")
            with row2_col2:
                new_category = st.selectbox(
                    "Category",
                    options=['elite', 'influencer'],
                    index=0 if athlete['category'] == 'elite' else 1,
                    key=f"cat_{athlete['id']}"
                )
            with row2_col3:
                new_website = st.text_input("Website", value=athlete.get('website') or '', key=f"web_{athlete['id']}")

            # Row 3: Profile Image URL
            new_profile_image = st.text_input("Profile Image URL", value=athlete.get('profile_image_url') or '', key=f"img_{athlete['id']}")

            # Row 4: Bio and Achievements
            new_bio = st.text_area("Bio", value=athlete['bio'] or '', height=80, key=f"bio_{athlete['id']}")
            new_achievements = st.text_input("Achievements", value=athlete['achievements'] or '', key=f"ach_{athlete['id']}")

            # Row 5: Active checkbox and buttons
            row5_col1, row5_col2, row5_col3 = st.columns([2, 1, 1])
            with row5_col1:
                is_active = st.checkbox("Active", value=athlete['is_active'], key=f"active_{athlete['id']}")
            with row5_col2:
                if st.form_submit_button("💾 Save", use_container_width=True):
                    # Auto-generate Instagram URL if handle changed but URL not
                    final_instagram_url = new_instagram_url
                    if new_handle and (not new_instagram_url or new_instagram_url == athlete.get('instagram_url')):
                        handle_clean = new_handle.replace('@', '')
                        final_instagram_url = f"https://instagram.com/{handle_clean}"

                    update_athlete(
                        athlete['id'],
                        name=new_name,
                        instagram_handle=new_handle,
                        instagram_url=final_instagram_url,
                        country=new_country,
                        category=new_category,
                        website=new_website,
                        profile_image_url=new_profile_image,
                        bio=new_bio,
                        achievements=new_achievements,
                        is_active=is_active
                    )
                    st.success("Updated!")
                    st.rerun()
            with row5_col3:
                if st.form_submit_button("🗑️ Delete", type="secondary", use_container_width=True):
                    delete_athlete(athlete['id'])
                    st.success("Deleted!")
                    st.rerun()


# ============================================================================
# SPOTLIGHT ATHLETE FRAGMENT - For spotlight preview
# ============================================================================

@st.fragment
def render_spotlight_athlete(athlete):
    """Render a single spotlight athlete preview as a fragment"""
    with st.container(border=True):
        if athlete.get('profile_image_url'):
            st.image(athlete['profile_image_url'], width=80)
        else:
            st.markdown("👤")

        st.markdown(f"**{athlete['name']}**")
        if athlete['instagram_handle']:
            st.markdown(f"[@{athlete['instagram_handle']}]({athlete['instagram_url']})")
        st.caption(f"🌍 {athlete['country'] or 'Unknown'}")
        if athlete.get('website'):
            st.caption(f"[🌐 Website]({athlete['website']})")
        st.caption(athlete['bio'][:80] + '...' if athlete['bio'] and len(athlete['bio']) > 80 else athlete['bio'] or '')

        if st.button("⭐ Mark Featured", key=f"feature_{athlete['id']}", use_container_width=True):
            mark_athlete_featured(athlete['id'])
            st.success(f"Marked {athlete['name']} as featured!")
            st.rerun()


# ============================================================================
# PRIORITY SOURCE FRAGMENT - For settings page
# ============================================================================

@st.fragment
def render_priority_source(source, platform):
    """Render a single priority source as a fragment"""
    col1, col2 = st.columns([4, 1])
    with col1:
        if platform == 'youtube' and source.get('source_id'):
            st.write(f"• {source['source_name']} (Channel ID: `{source['source_id']}`)")
        else:
            url_display = f" ({source['source_url'][:50]}...)" if source.get('source_url') and len(source['source_url']) > 50 else (f" ({source['source_url']})" if source.get('source_url') else "")
            st.write(f"• {source['source_name']}{url_display}")
    with col2:
        if st.button("🗑️", key=f"del_priority_{source['id']}", help="Remove"):
            delete_priority_source(source['id'])
            st.rerun()


# ============================================================================
# STREAMLIT APP
# ============================================================================

def main():
    st.set_page_config(
        page_title="Hyrox Weekly - Dashboard",
        page_icon="🏋️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS - Modern styling
    st.markdown("""
    <style>
    /* Headers */
    .main-header {font-size: 2.5rem; font-weight: 800; color: #ff6b35; margin-bottom: 0;}
    .sub-header {color: #888; margin-bottom: 2rem;}

    /* Cards and containers */
    .metric-card {background: #1a1d24; padding: 1rem; border-radius: 12px; text-align: center; border: 1px solid #2d3139;}
    .step-header {background: linear-gradient(135deg, #ff6b35, #f7931e); color: white; padding: 1rem; border-radius: 12px; margin-bottom: 1rem;}

    /* Buttons - modern rounded style */
    .stButton > button {
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s ease;
        border: 1px solid transparent;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255, 107, 53, 0.3);
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #ff6b35, #f7931e);
    }

    /* Expanders - cleaner look */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 0.95rem;
        border-radius: 8px;
    }

    /* Selectboxes and inputs */
    .stSelectbox > div > div {
        border-radius: 8px;
    }
    .stTextInput > div > div > input {
        border-radius: 8px;
    }
    .stTextArea > div > div > textarea {
        border-radius: 8px;
    }

    /* Tabs - modern style */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 16px;
    }

    /* Metrics - enhanced */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0e1117 0%, #1a1d24 100%);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.9rem;
    }

    /* Container borders - card effect */
    [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
        border-color: #2d3139;
        background: #1a1d24;
        padding: 1rem;
    }

    /* Image styling */
    [data-testid="stImage"] img {
        border-radius: 8px;
    }

    /* Success/warning/error messages */
    .stSuccess, .stWarning, .stError, .stInfo {
        border-radius: 8px;
    }

    /* Dividers - subtle */
    hr {
        border-color: #2d3139;
        opacity: 0.5;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-discovered { background: #1e3a5f; color: #60a5fa; }
    .status-selected { background: #1a4d3e; color: #34d399; }
    .status-rejected { background: #4d1f2a; color: #f87171; }
    </style>
    """, unsafe_allow_html=True)
    
    # ========================================================================
    # ONE-TIME DATABASE INITIALIZATION (only runs once per session)
    # ========================================================================
    if 'db_initialized' not in st.session_state:
        ensure_content_columns()  # Ensure new columns exist
        st.session_state['db_initialized'] = True
    
    # ========================================================================
    # NEWSLETTER CONFIG (loaded from database)
    # ========================================================================
    if 'newsletter_config' not in st.session_state:
        st.session_state['newsletter_config'] = get_newsletter_settings()
    
    # Initialize shared week selection (persists across pages)
    if 'selected_week_idx' not in st.session_state:
        st.session_state['selected_week_idx'] = 0  # Default to current week
    
    # Sidebar Navigation
    with st.sidebar:
        st.markdown("## 🏋️ Hyrox Weekly")
        st.markdown("---")
        
        page = st.radio(
            "Navigation",
            ["🏠 Dashboard", "🔍 Discovery", "✅ Curation", "📰 Generate", "🏃 Athletes", "💎 Premium", "📊 Analytics", "⚙️ Settings"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        
        # Quick Stats
        stats = get_stats()
        discovered = sum(s['count'] for s in stats if s['status'] == 'discovered')
        selected = sum(s['count'] for s in stats if s['status'] == 'selected')
        
        st.metric("📥 To Review", discovered)
        st.metric("✅ Selected", selected)
        
        st.markdown("---")
        st.markdown("**Launch Date:** Jan 3, 2025")
        days_until = (datetime(2025, 1, 3) - datetime.now()).days
        st.markdown(f"**Days Until Launch:** {max(0, days_until)}")
    
    # ========================================================================
    # DASHBOARD PAGE
    # ========================================================================
    if page == "🏠 Dashboard":
        st.markdown('<p class="main-header">Hyrox Weekly Dashboard</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Your complete newsletter workflow</p>', unsafe_allow_html=True)
        
        # Workflow Overview
        st.markdown("### 📋 Weekly Workflow")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("""
            <div class="metric-card">
                <h3>Step 1</h3>
                <p>🔍 Discovery</p>
                <small>Find new content</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="metric-card">
                <h3>Step 2</h3>
                <p>✅ Curation</p>
                <small>Select best content</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="metric-card">
                <h3>Step 3</h3>
                <p>📰 Generate</p>
                <small>Create newsletter</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown("""
            <div class="metric-card">
                <h3>Step 4</h3>
                <p>📤 Publish</p>
                <small>Send via Beehiiv</small>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Content Summary
        st.markdown("### 📊 Content Summary")
        
        stats = get_stats()
        
        col1, col2, col3, col4, col5 = st.columns(5)
        columns = [col1, col2, col3, col4, col5]
        
        for i, (platform, config) in enumerate(PLATFORM_CONFIG.items()):
            if i < len(columns):
                total = sum(s['count'] for s in stats if s['platform'] == platform)
                discovered = sum(s['count'] for s in stats if s['platform'] == platform and s['status'] == 'discovered')
                
                with columns[i]:
                    st.metric(
                        f"{config['emoji']} {config['name']}",
                        total,
                        f"{discovered} to review"
                    )
        
        st.markdown("---")
        
        # Recent Editions
        st.markdown("### 📚 Recent Editions")
        editions = get_editions()
        
        if editions:
            display_tz = st.session_state['newsletter_config'].get('display_timezone', 'US/Pacific')
            for ed in editions[:5]:
                pub_date = ed.get('publish_date', '')
                pub_date_str = format_date_local(pub_date, display_tz) if pub_date else ''
                st.write(f"**Edition #{ed['edition_number']}** - {pub_date_str}")
        else:
            st.info("No editions published yet.")
    
    # ========================================================================
    # DISCOVERY PAGE
    # ========================================================================
    elif page == "🔍 Discovery":
        st.markdown("## 🔍 Content Discovery")
        st.markdown("Run discovery scripts to find new Hyrox content")
        
        st.markdown("---")
        
        # Week Selector
        st.markdown("### 📅 Select Week")
        
        # Generate list of weeks (current week + past 4 weeks)
        today = datetime.now()
        weeks = []
        for i in range(5):
            # Calculate Monday of that week
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday + (i * 7))
            week_end = week_start + timedelta(days=6)
            
            # Format label
            if week_start.month == week_end.month:
                label = f"{week_start.strftime('%B')} {week_start.day}-{week_end.day}, {week_end.year}"
            elif week_start.year == week_end.year:
                label = f"{week_start.strftime('%B')} {week_start.day} - {week_end.strftime('%B')} {week_end.day}, {week_end.year}"
            else:
                label = f"{week_start.strftime('%B')} {week_start.day}, {week_start.year} - {week_end.strftime('%B')} {week_end.day}, {week_end.year}"
            
            if i == 0:
                label = f"📍 Current Week: {label}"
            
            weeks.append({
                'label': label,
                'start': week_start.date(),
                'end': week_end.date()
            })
        
        selected_week = st.selectbox(
            "Week to discover content for",
            options=range(len(weeks)),
            format_func=lambda i: weeks[i]['label'],
            index=st.session_state['selected_week_idx'],
            key="discovery_week"
        )
        
        # Update shared state when selection changes
        if selected_week != st.session_state['selected_week_idx']:
            st.session_state['selected_week_idx'] = selected_week
        
        # Store selected week in session state for scripts to use
        st.session_state['discovery_week_start'] = weeks[selected_week]['start'].isoformat()
        st.session_state['discovery_week_end'] = weeks[selected_week]['end'].isoformat()
        
        week_start = st.session_state['discovery_week_start']
        week_end = st.session_state['discovery_week_end']
        week_start_date = weeks[selected_week]['start']
        week_end_date = weeks[selected_week]['end']
        
        st.info(f"🔍 Discovery will search for content from **{week_start_date}** to **{week_end_date}**")
        
        # Get last run times for this week
        discovery_runs = get_discovery_runs(week_start_date, week_end_date)
        
        st.markdown("---")
        
        # Discovery Status Table
        st.markdown("### 📊 Discovery Status for Selected Week")
        
        # Get display timezone from config
        display_tz = st.session_state['newsletter_config'].get('display_timezone', 'US/Pacific')
        
        status_cols = st.columns(5)
        platforms_list = ['youtube', 'podcast', 'article', 'reddit', 'instagram']
        
        for i, platform in enumerate(platforms_list):
            platform_config = PLATFORM_CONFIG.get(platform, {'emoji': '📺', 'name': platform})
            run_info = discovery_runs.get(platform)
            
            with status_cols[i]:
                st.markdown(f"**{platform_config['emoji']} {platform_config['name']}**")
                if run_info:
                    run_time = run_info['run_at']
                    time_str = format_datetime_local(run_time, display_tz, '%b %d, %I:%M %p')
                    if not time_str and run_time:
                        time_str = str(run_time)[:16]
                    st.caption(f"✅ {time_str}")
                    st.caption(f"Found: {run_info['items_found']} | Saved: {run_info['items_saved']}")
                else:
                    st.caption("⏳ Not run yet")
        
        st.markdown("---")
        
        # Discovery Scripts
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🎬 YouTube")
            if st.button("Run YouTube Discovery", key="yt_btn", use_container_width=True):
                with st.spinner("Searching YouTube..."):
                    success, output, items_found, items_saved = run_discovery_script("youtube_discovery.py", week_start, week_end)
                    record_discovery_run('youtube', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                    if success:
                        st.success("YouTube discovery complete!")
                    else:
                        st.error("YouTube discovery failed")
                    with st.expander("View Output", expanded=True):
                        st.code(output)
            
            st.markdown("### 🎙️ Podcasts")
            if st.button("Run Podcast Discovery", key="pod_btn", use_container_width=True):
                with st.spinner("Searching podcasts..."):
                    success, output, items_found, items_saved = run_discovery_script("podcast_discovery.py", week_start, week_end)
                    record_discovery_run('podcast', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                    if success:
                        st.success("Podcast discovery complete!")
                    else:
                        st.error("Podcast discovery failed")
                    with st.expander("View Output", expanded=True):
                        st.code(output)
        
        with col2:
            st.markdown("### 📰 Articles")
            if st.button("Run Article Discovery", key="art_btn", use_container_width=True):
                with st.spinner("Searching RSS feeds..."):
                    success, output, items_found, items_saved = run_discovery_script("article_discovery.py", week_start, week_end)
                    record_discovery_run('article', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                    if success:
                        st.success("Article discovery complete!")
                    else:
                        st.error("Article discovery failed")
                    with st.expander("View Output", expanded=True):
                        st.code(output)
            
            st.markdown("### 🔗 Reddit")
            if st.button("Run Reddit Discovery", key="red_btn", use_container_width=True):
                with st.spinner("Searching Reddit..."):
                    success, output, items_found, items_saved = run_discovery_script("reddit_discovery.py", week_start, week_end)
                    record_discovery_run('reddit', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                    if success:
                        st.success("Reddit discovery complete!")
                    else:
                        st.error("Reddit discovery failed")
                    with st.expander("View Output", expanded=True):
                        st.code(output)
            
            st.markdown("### 📸 Instagram")
            if st.button("Run Instagram Discovery", key="ig_btn", use_container_width=True):
                with st.spinner("Searching Instagram hashtags..."):
                    success, output, items_found, items_saved = run_discovery_script("instagram_discovery.py", week_start, week_end)
                    record_discovery_run('instagram', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                    if success:
                        st.success("Instagram discovery complete!")
                    else:
                        st.error("Instagram discovery failed")
                    with st.expander("View Output", expanded=True):
                        st.code(output)
        
        st.markdown("---")
        
        # Clear & Re-discover Section
        st.markdown("### 🔄 Clear & Re-discover")
        st.caption("Delete existing content for selected platforms and re-run discovery. Useful when you need fresh data (e.g., updated Spotify links).")
        
        with st.expander("⚠️ Clear & Re-discover Options"):
            st.warning("**Warning:** This will permanently delete discovered content for the selected week. Selected/published items will also be deleted.")
            
            # Platform selection
            clear_platforms = st.multiselect(
                "Select platforms to clear",
                options=['youtube', 'podcast', 'article', 'reddit', 'instagram'],
                default=[],
                format_func=lambda x: {
                    'youtube': '🎬 YouTube',
                    'podcast': '🎙️ Podcasts', 
                    'article': '📰 Articles',
                    'reddit': '🔗 Reddit',
                    'instagram': '📸 Instagram'
                }.get(x, x),
                key="clear_platforms"
            )
            
            col_clear1, col_clear2 = st.columns(2)
            
            with col_clear1:
                if st.button("🗑️ Clear Selected Platforms", disabled=len(clear_platforms) == 0, use_container_width=True):
                    results = clear_content_for_week(clear_platforms, week_start_date, week_end_date)
                    total_deleted = sum(results.values())
                    if total_deleted > 0:
                        details = ", ".join([f"{p}: {c}" for p, c in results.items() if c > 0])
                        st.success(f"✅ Deleted {total_deleted} items ({details})")
                    else:
                        st.info("No items to delete for selected platforms/week")
            
            with col_clear2:
                if st.button("🗑️ Clear ALL Platforms", type="secondary", use_container_width=True):
                    results = clear_content_for_week(['all'], week_start_date, week_end_date)
                    total_deleted = sum(results.values())
                    if total_deleted > 0:
                        details = ", ".join([f"{p}: {c}" for p, c in results.items() if c > 0])
                        st.success(f"✅ Deleted {total_deleted} items ({details})")
                    else:
                        st.info("No items to delete for selected week")
            
            st.markdown("---")
            
            # Clear & Re-discover in one step
            st.markdown("**One-Click Clear & Re-discover:**")
            
            col_rediscover1, col_rediscover2 = st.columns(2)
            
            with col_rediscover1:
                if st.button("🔄 Clear & Re-discover Podcasts", use_container_width=True):
                    with st.spinner("Clearing podcasts and re-discovering..."):
                        # Clear
                        clear_results = clear_content_for_week(['podcast'], week_start_date, week_end_date)
                        st.info(f"Cleared {clear_results.get('podcast', 0)} podcast episodes")
                        
                        # Re-discover
                        success, output, items_found, items_saved = run_discovery_script("podcast_discovery.py", week_start, week_end)
                        record_discovery_run('podcast', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                        
                        if success:
                            st.success(f"✅ Re-discovered {items_saved} podcast episodes!")
                        else:
                            st.error("Podcast discovery failed")
                        
                        with st.expander("View Output", expanded=True):
                            st.code(output)
            
            with col_rediscover2:
                if st.button("🔄 Clear & Re-discover YouTube", use_container_width=True):
                    with st.spinner("Clearing YouTube and re-discovering..."):
                        # Clear
                        clear_results = clear_content_for_week(['youtube'], week_start_date, week_end_date)
                        st.info(f"Cleared {clear_results.get('youtube', 0)} YouTube videos")
                        
                        # Re-discover
                        success, output, items_found, items_saved = run_discovery_script("youtube_discovery.py", week_start, week_end)
                        record_discovery_run('youtube', week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                        
                        if success:
                            st.success(f"✅ Re-discovered {items_saved} YouTube videos!")
                        else:
                            st.error("YouTube discovery failed")
                        
                        with st.expander("View Output", expanded=True):
                            st.code(output)
            
            if st.button("🔄 Clear & Re-discover ALL Platforms", type="primary", use_container_width=True):
                with st.spinner("Clearing all content and re-discovering..."):
                    # Clear all
                    clear_results = clear_content_for_week(['all'], week_start_date, week_end_date)
                    total_cleared = sum(clear_results.values())
                    st.info(f"Cleared {total_cleared} total items")
                    
                    # Re-discover all
                    progress = st.progress(0)
                    status_text = st.empty()
                    
                    scripts = [
                        ("youtube_discovery.py", "YouTube", "youtube"),
                        ("podcast_discovery.py", "Podcasts", "podcast"),
                        ("article_discovery.py", "Articles", "article"),
                        ("reddit_discovery.py", "Reddit", "reddit"),
                    ]
                    
                    all_output = []
                    total_saved = 0
                    for i, (script, name, platform) in enumerate(scripts):
                        status_text.text(f"Re-discovering {name}...")
                        success, output, items_found, items_saved = run_discovery_script(script, week_start, week_end)
                        record_discovery_run(platform, week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                        all_output.append(f"=== {name} ===\n{output}\n")
                        total_saved += items_saved
                        progress.progress((i + 1) / len(scripts))
                    
                    status_text.text("Re-discovery complete!")
                    st.success(f"✅ Re-discovered {total_saved} total items!")
                    
                    with st.expander("View Full Output", expanded=True):
                        st.code("\n".join(all_output))
        
        st.markdown("---")
        
        # Run All
        st.markdown("### 🚀 Run All Discovery")
        if st.button("Run All Discovery Scripts", type="primary", use_container_width=True):
            progress = st.progress(0)
            status = st.empty()
            
            scripts = [
                ("youtube_discovery.py", "YouTube", "youtube"),
                ("podcast_discovery.py", "Podcasts", "podcast"),
                ("article_discovery.py", "Articles", "article"),
                ("reddit_discovery.py", "Reddit", "reddit"),
                ("instagram_discovery.py", "Instagram", "instagram"),
            ]
            
            results = []
            for i, (script, name, platform) in enumerate(scripts):
                status.text(f"Running {name} discovery...")
                success, output, items_found, items_saved = run_discovery_script(script, week_start, week_end)
                record_discovery_run(platform, week_start_date, week_end_date, items_found, items_saved, 'completed' if success else 'failed')
                results.append((name, success, output))
                progress.progress((i + 1) / len(scripts))
            
            status.text("Discovery complete!")
            
            for name, success, output in results:
                if success:
                    st.success(f"✅ {name} discovery complete")
                else:
                    st.error(f"❌ {name} discovery failed")
                    with st.expander(f"View {name} Output"):
                        st.code(output)
            
            st.rerun()
    
    # ========================================================================
    # CURATION PAGE
    # ========================================================================
    elif page == "✅ Curation":
        st.markdown("## ✅ Content Curation")
        st.markdown("Review and select content for the newsletter")
        
        # Week Selector
        weeks = generate_week_options()
        
        # Ensure index is within bounds (in case weeks list is different)
        current_idx = min(st.session_state['selected_week_idx'], len(weeks) - 1)
        
        selected_week_idx = st.selectbox(
            "📅 Filter by Week",
            options=range(len(weeks)),
            format_func=lambda i: weeks[i]['label'],
            index=current_idx,
            key="curation_week"
        )
        
        # Update shared state when selection changes
        if selected_week_idx != st.session_state['selected_week_idx']:
            st.session_state['selected_week_idx'] = selected_week_idx
        
        selected_week = weeks[selected_week_idx]
        week_start_date = selected_week['start']
        week_end_date = selected_week['end']
        
        if week_start_date and week_end_date:
            st.caption(f"Showing content published from **{week_start_date}** to **{week_end_date}**")
        
        st.markdown("---")
        
        # Content Summary by Platform and Status
        st.markdown("### 📊 Content Summary")
        
        counts = get_content_counts_by_week(week_start_date, week_end_date)
        
        if counts:
            # Create summary table
            summary_cols = st.columns(6)
            
            # Header row
            with summary_cols[0]:
                st.markdown("**Platform**")
            with summary_cols[1]:
                st.markdown("**📥 To Review**")
            with summary_cols[2]:
                st.markdown("**✅ Selected**")
            with summary_cols[3]:
                st.markdown("**❌ Rejected**")
            with summary_cols[4]:
                st.markdown("**📤 Published**")
            with summary_cols[5]:
                st.markdown("**Total**")
            
            # Platform rows
            platforms_order = ['youtube', 'podcast', 'article', 'reddit', 'instagram']
            totals = {'discovered': 0, 'selected': 0, 'rejected': 0, 'published': 0, 'total': 0}
            
            for platform in platforms_order:
                if platform in counts:
                    platform_cfg = PLATFORM_CONFIG.get(platform, {'emoji': '📺', 'name': platform})
                    data = counts[platform]
                    
                    row_cols = st.columns(6)
                    with row_cols[0]:
                        st.write(f"{platform_cfg['emoji']} {platform_cfg['name']}")
                    with row_cols[1]:
                        st.write(data.get('discovered', 0))
                    with row_cols[2]:
                        st.write(f"**{data.get('selected', 0)}**" if data.get('selected', 0) > 0 else "0")
                    with row_cols[3]:
                        st.write(data.get('rejected', 0))
                    with row_cols[4]:
                        st.write(data.get('published', 0))
                    with row_cols[5]:
                        st.write(data.get('total', 0))
                    
                    # Add to totals
                    for key in totals:
                        totals[key] += data.get(key, 0)
            
            # Totals row
            st.markdown("---")
            total_cols = st.columns(6)
            with total_cols[0]:
                st.markdown("**TOTAL**")
            with total_cols[1]:
                st.markdown(f"**{totals['discovered']}**")
            with total_cols[2]:
                st.markdown(f"**✅ {totals['selected']}**")
            with total_cols[3]:
                st.markdown(f"**{totals['rejected']}**")
            with total_cols[4]:
                st.markdown(f"**{totals['published']}**")
            with total_cols[5]:
                st.markdown(f"**{totals['total']}**")
        else:
            st.info("No content for this week yet. Run discovery to find content.")
        
        st.markdown("---")
        
        # Batch AI Blurb Generation
        st.markdown("### ✨ AI Blurb Generation")
        
        # Get selected content for counts - use cached version
        selected_content = get_content_cached(status_filter='selected', week_start=week_start_date, week_end=week_end_date)
        needs_blurb = [c for c in selected_content if not c.get('ai_description')]
        has_blurb = [c for c in selected_content if c.get('ai_description')]
        
        col_ai1, col_ai2 = st.columns([1, 2])
        
        with col_ai1:
            st.caption(f"📊 **{len(selected_content)}** selected items")
            st.caption(f"   • {len(needs_blurb)} need blurbs")
            st.caption(f"   • {len(has_blurb)} have blurbs")
            
            if not ANTHROPIC_API_KEY:
                st.warning("⚠️ API key missing")
        
        with col_ai2:
            # Generate missing blurbs
            if st.button("✨ Generate Missing Blurbs", disabled=len(needs_blurb) == 0, use_container_width=True):
                with st.spinner(f"Generating blurbs for {len(needs_blurb)} items..."):
                    results = generate_blurbs_for_selected(week_start_date, week_end_date)
                    success_count = sum(1 for r in results if r['success'])
                    fail_count = len(results) - success_count
                    
                    if success_count > 0:
                        st.success(f"✅ Generated {success_count} AI blurbs!")
                    if fail_count > 0:
                        st.warning(f"⚠️ {fail_count} items failed to generate")
                    st.rerun()
        
        # Regenerate options in expander
        with st.expander("🔄 Regenerate Existing Blurbs", expanded=False):
            st.caption("Use this to regenerate blurbs after updating the AI prompt style")
            
            regen_col1, regen_col2 = st.columns([1, 1])
            
            with regen_col1:
                regen_platform = st.selectbox(
                    "Platform to regenerate",
                    options=['all', 'youtube', 'podcast', 'article', 'reddit'],
                    format_func=lambda x: {
                        'all': '🔄 All Platforms',
                        'youtube': '🎬 YouTube only',
                        'podcast': '🎙️ Podcasts only',
                        'article': '📰 Articles only',
                        'reddit': '🔗 Reddit only'
                    }.get(x, x),
                    key="regen_platform"
                )
            
            with regen_col2:
                # Count items that will be regenerated
                if regen_platform == 'all':
                    regen_count = len(has_blurb)
                else:
                    regen_count = len([c for c in has_blurb if c['platform'] == regen_platform])
                
                st.caption(f"")  # Spacing
                st.caption(f"**{regen_count}** items will be regenerated")
            
            if st.button(f"🔄 Regenerate {regen_platform.title() if regen_platform != 'all' else 'All'} Blurbs", 
                        disabled=regen_count == 0, 
                        type="secondary",
                        use_container_width=True):
                with st.spinner(f"Regenerating {regen_count} blurbs..."):
                    results = regenerate_blurbs(week_start_date, week_end_date, regen_platform)
                    success_count = sum(1 for r in results if r['success'])
                    fail_count = len(results) - success_count
                    
                    if success_count > 0:
                        st.success(f"✅ Regenerated {success_count} AI blurbs!")
                    if fail_count > 0:
                        st.warning(f"⚠️ {fail_count} items failed")
                        for r in results:
                            if not r['success']:
                                st.caption(f"- {r['title'][:40]}...: {r['error']}")
                    st.rerun()
        
        st.markdown("---")
        
        # Filters
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            platform_options = ['all'] + list(PLATFORM_CONFIG.keys())
            platform_filter = st.selectbox(
                "Platform",
                options=platform_options,
                format_func=lambda x: "📺 All Platforms" if x == 'all' else f"{PLATFORM_CONFIG[x]['emoji']} {PLATFORM_CONFIG[x]['name']}"
            )
        
        with col2:
            status_filter = st.selectbox(
                "Status",
                options=['discovered', 'selected', 'rejected', 'all'],
                format_func=lambda x: {'discovered': '📥 To Review', 'selected': '✅ Selected', 'rejected': '❌ Rejected', 'all': '📋 All'}[x]
            )
        
        with col3:
            if st.button("🔄 Refresh"):
                clear_content_caches()
                st.rerun()
        
        st.markdown("---")

        # Content List - use cached version for faster loading
        content = get_content_cached(platform_filter, status_filter, week_start_date, week_end_date)

        if not content:
            st.info("No content found. Run discovery scripts or adjust filters.")
        else:
            # Initialize pagination state
            pagination_key = f"curation_page_{platform_filter}_{status_filter}"
            if pagination_key not in st.session_state:
                st.session_state[pagination_key] = 0

            total_items = len(content)
            total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            current_page = st.session_state[pagination_key]

            # Ensure current page is valid
            if current_page >= total_pages:
                current_page = total_pages - 1
                st.session_state[pagination_key] = current_page

            # Calculate slice indices
            start_idx = current_page * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

            # Pagination controls - top
            pag_col1, pag_col2, pag_col3, pag_col4, pag_col5 = st.columns([1, 1, 2, 1, 1])

            with pag_col1:
                if st.button("⏮️ First", disabled=current_page == 0, key="pag_first_top"):
                    st.session_state[pagination_key] = 0
                    st.rerun()

            with pag_col2:
                if st.button("◀️ Prev", disabled=current_page == 0, key="pag_prev_top"):
                    st.session_state[pagination_key] = current_page - 1
                    st.rerun()

            with pag_col3:
                st.markdown(f"<div style='text-align: center; padding-top: 5px;'><b>Page {current_page + 1} of {total_pages}</b> ({start_idx + 1}-{end_idx} of {total_items})</div>", unsafe_allow_html=True)

            with pag_col4:
                if st.button("Next ▶️", disabled=current_page >= total_pages - 1, key="pag_next_top"):
                    st.session_state[pagination_key] = current_page + 1
                    st.rerun()

            with pag_col5:
                if st.button("Last ⏭️", disabled=current_page >= total_pages - 1, key="pag_last_top"):
                    st.session_state[pagination_key] = total_pages - 1
                    st.rerun()

            st.markdown("---")

            # Get display timezone once for all items
            display_tz = st.session_state['newsletter_config'].get('display_timezone', 'US/Pacific')

            # Render only the current page of content items as independent fragments
            for item in content[start_idx:end_idx]:
                render_content_item(item, display_tz)

            # Pagination controls - bottom (for long lists)
            if total_pages > 1:
                st.markdown("---")
                pag_col1b, pag_col2b, pag_col3b, pag_col4b, pag_col5b = st.columns([1, 1, 2, 1, 1])

                with pag_col1b:
                    if st.button("⏮️ First", disabled=current_page == 0, key="pag_first_bottom"):
                        st.session_state[pagination_key] = 0
                        st.rerun()

                with pag_col2b:
                    if st.button("◀️ Prev", disabled=current_page == 0, key="pag_prev_bottom"):
                        st.session_state[pagination_key] = current_page - 1
                        st.rerun()

                with pag_col3b:
                    st.markdown(f"<div style='text-align: center; padding-top: 5px;'><b>Page {current_page + 1} of {total_pages}</b></div>", unsafe_allow_html=True)

                with pag_col4b:
                    if st.button("Next ▶️", disabled=current_page >= total_pages - 1, key="pag_next_bottom"):
                        st.session_state[pagination_key] = current_page + 1
                        st.rerun()

                with pag_col5b:
                    if st.button("Last ⏭️", disabled=current_page >= total_pages - 1, key="pag_last_bottom"):
                        st.session_state[pagination_key] = total_pages - 1
                        st.rerun()

        # Manual Content Entry Section
        st.markdown("---")
        with st.expander("➕ Add Content Manually", expanded=False):
            st.markdown("**Add content from any source manually**")
            
            # Platform selection first - this determines which fields to show
            manual_platform = st.selectbox(
                "Platform",
                options=['article', 'youtube', 'podcast', 'instagram', 'reddit'],
                format_func=lambda x: f"{PLATFORM_CONFIG.get(x, {'emoji': '📺'})['emoji']} {x.title()}",
                key="manual_platform"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                manual_url = st.text_input(
                    "URL",
                    placeholder={
                        'article': "https://www.example.com/article-title",
                        'youtube': "https://www.youtube.com/watch?v=...",
                        'podcast': "https://open.spotify.com/episode/... or Apple Podcasts link",
                        'instagram': "https://www.instagram.com/p/ABC123/",
                        'reddit': "https://www.reddit.com/r/hyrox/comments/..."
                    }.get(manual_platform, "https://...")
                )
                
                manual_title = st.text_input(
                    "Title",
                    placeholder="Title of the content"
                )
                
                manual_creator = st.text_input(
                    {
                        'article': "Publication / Author",
                        'youtube': "Channel Name",
                        'podcast': "Podcast Name",
                        'instagram': "Username",
                        'reddit': "Subreddit"
                    }.get(manual_platform, "Creator"),
                    placeholder={
                        'article': "e.g., Red Bull, The Rx Review",
                        'youtube': "e.g., UKHXR, Hybrid Calisthenics",
                        'podcast': "e.g., Hyrox World Podcast",
                        'instagram': "e.g., @hyroxworld",
                        'reddit': "e.g., r/hyrox"
                    }.get(manual_platform, "Creator name")
                )
            
            with col2:
                # Publish date - default to today within selected week
                manual_date = st.date_input(
                    "Publish Date",
                    value=datetime.now().date(),
                    help="When was this content published?"
                )
                
                manual_thumbnail = st.text_input(
                    "Thumbnail URL (optional)",
                    placeholder="https://..."
                )
                
                # Platform-specific fields
                if manual_platform == 'youtube':
                    mcol1, mcol2 = st.columns(2)
                    with mcol1:
                        manual_views = st.number_input("Views", min_value=0, value=0)
                    with mcol2:
                        manual_duration = st.number_input("Duration (minutes)", min_value=0, value=0)
                    manual_likes = manual_views // 20  # Estimate
                    manual_comments = 0
                    
                elif manual_platform == 'podcast':
                    mcol1, mcol2 = st.columns(2)
                    with mcol1:
                        manual_duration = st.number_input("Duration (minutes)", min_value=0, value=0)
                    with mcol2:
                        manual_listens = st.number_input("Listens (optional)", min_value=0, value=0)
                    manual_views = manual_listens
                    manual_likes = 0
                    manual_comments = 0
                    
                    # Spotify/Apple links
                    st.caption("Add alternative listening links:")
                    manual_spotify = st.text_input("Spotify URL (optional)", placeholder="https://open.spotify.com/episode/...")
                    manual_apple = st.text_input("Apple Podcasts URL (optional)", placeholder="https://podcasts.apple.com/...")
                    
                elif manual_platform == 'instagram':
                    mcol1, mcol2 = st.columns(2)
                    with mcol1:
                        manual_likes = st.number_input("Likes", min_value=0, value=0)
                    with mcol2:
                        manual_comments = st.number_input("Comments", min_value=0, value=0)
                    manual_views = manual_likes
                    manual_duration = 0
                    
                elif manual_platform == 'reddit':
                    mcol1, mcol2 = st.columns(2)
                    with mcol1:
                        manual_upvotes = st.number_input("Upvotes", min_value=0, value=0)
                    with mcol2:
                        manual_comments = st.number_input("Comments", min_value=0, value=0)
                    manual_views = manual_upvotes
                    manual_likes = manual_upvotes
                    manual_duration = 0
                    
                else:  # article
                    manual_views = 0
                    manual_likes = 0
                    manual_comments = 0
                    manual_duration = 0
            
            manual_description = st.text_area(
                "Description (optional)",
                placeholder="Brief description or summary of the content...",
                height=80
            )
            
            # Category for YouTube
            manual_category = None
            if manual_platform == 'youtube':
                manual_category = st.selectbox(
                    "Category",
                    options=['race_recap', 'training', 'nutrition', 'athlete_profile', 'gear', 'other'],
                    format_func=lambda x: {
                        'race_recap': '🏁 Race Recap',
                        'training': '💪 Training & Workouts',
                        'nutrition': '🥗 Nutrition & Recovery',
                        'athlete_profile': '👤 Athlete Profile',
                        'gear': '🎒 Gear & Equipment',
                        'other': '📺 Other'
                    }.get(x, x)
                )
            
            # Status selector - default to 'selected' for manual adds
            manual_status = st.radio(
                "Initial Status",
                options=['selected', 'discovered'],
                format_func=lambda x: '✅ Selected (ready for newsletter)' if x == 'selected' else '📥 To Review (needs curation)',
                horizontal=True,
                help="Selected = ready to include in newsletter. To Review = will appear in curation queue."
            )
            
            if st.button("➕ Add Content", type="primary"):
                if not manual_url or not manual_title:
                    st.error("URL and Title are required")
                else:
                    try:
                        # Get or create creator
                        creator_name = manual_creator or "Unknown"
                        existing_creator = supabase_get('creators',
                            f'name=eq.{quote(creator_name)}&platform=eq.{manual_platform}', single=True)

                        if existing_creator:
                            creator_id = existing_creator['id']
                        else:
                            new_creator = supabase_post('creators', {
                                'name': creator_name,
                                'platform': manual_platform,
                                'platform_id': creator_name
                            })
                            creator_id = new_creator['id'] if new_creator else None

                        # Check if URL already exists
                        existing_content = supabase_get('content_items',
                            f'url=eq.{quote(manual_url)}', single=True)
                        if existing_content:
                            st.warning("This URL already exists in the database")
                        else:
                            # Build editorial note for podcasts (Spotify/Apple links)
                            editorial_note = None
                            if manual_platform == 'podcast':
                                links = []
                                if manual_spotify:
                                    links.append(f"Spotify: {manual_spotify}")
                                if manual_apple:
                                    links.append(f"Apple: {manual_apple}")
                                if links:
                                    editorial_note = " | ".join(links)

                            # Calculate duration in seconds
                            duration_seconds = manual_duration * 60 if manual_duration else None

                            # Insert content
                            content_data = {
                                'title': manual_title,
                                'url': manual_url,
                                'platform': manual_platform,
                                'creator_id': creator_id,
                                'status': manual_status,
                                'thumbnail_url': manual_thumbnail or None,
                                'description': manual_description or None,
                                'like_count': manual_likes,
                                'comment_count': manual_comments,
                                'view_count': manual_views,
                                'published_date': manual_date.isoformat() if manual_date else None,
                                'category': manual_category,
                                'duration_seconds': duration_seconds,
                                'editorial_note': editorial_note
                            }
                            result = supabase_post('content_items', content_data)

                            if result:
                                clear_content_caches()
                                st.success(f"✅ Added: {manual_title[:50]}...")
                                st.rerun()
                            else:
                                st.error("Failed to add content")

                    except Exception as e:
                        st.error(f"Error adding content: {e}")
    
    # ========================================================================
    # GENERATE PAGE
    # ========================================================================
    elif page == "📰 Generate":
        st.markdown("## 📰 Generate Newsletter")
        st.markdown("Create and publish this week's edition")
        
        # Week Selector
        weeks = generate_week_options()
        # Remove "All Time" option for Generate page - must select a specific week
        weeks_for_generate = [w for w in weeks if w['start'] is not None]
        
        # Ensure index is within bounds for generate weeks (no "All Time" option)
        current_idx = min(st.session_state['selected_week_idx'], len(weeks_for_generate) - 1)
        
        selected_week_idx = st.selectbox(
            "📅 Select Week for Newsletter",
            options=range(len(weeks_for_generate)),
            format_func=lambda i: weeks_for_generate[i]['label'],
            index=current_idx,
            key="generate_week"
        )
        
        # Update shared state when selection changes
        if selected_week_idx != st.session_state['selected_week_idx']:
            st.session_state['selected_week_idx'] = selected_week_idx
        
        selected_week = weeks_for_generate[selected_week_idx]
        week_start_date = selected_week['start']
        week_end_date = selected_week['end']
        
        st.caption(f"Generating newsletter for content published from **{week_start_date}** to **{week_end_date}**")
        
        st.markdown("---")
        
        # Get selected content for the chosen week - use cached version
        selected_content = get_content_cached(status_filter='selected', week_start=week_start_date, week_end=week_end_date)
        
        # Summary
        st.markdown("### 📋 Selected Content Summary")
        
        videos = [c for c in selected_content if c['platform'] == 'youtube']
        podcasts = [c for c in selected_content if c['platform'] == 'podcast']
        articles = [c for c in selected_content if c['platform'] == 'article']
        reddit = [c for c in selected_content if c['platform'] == 'reddit']
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🎬 Videos", len(videos))
        col2.metric("🎙️ Podcasts", len(podcasts))
        col3.metric("📰 Articles", len(articles))
        col4.metric("🔗 Reddit", len(reddit))
        
        st.markdown("---")
        
        # Athlete Spotlight Selection
        st.markdown("### 🏃 Athlete Spotlight")
        st.markdown("Select athletes to feature in this edition")
        
        all_athletes = get_athletes(active_only=True)
        
        if not all_athletes:
            st.info("No athletes available. Go to the Athletes page to add some.")
            selected_athlete_ids = []
        else:
            # Initialize session state for selected athletes if not exists
            if 'selected_athletes' not in st.session_state:
                st.session_state['selected_athletes'] = []
            
            # Create athlete selection grid
            athlete_cols = st.columns(4)
            
            # Sort athletes: previously selected first, then by name
            selected_ids_set = set(st.session_state['selected_athletes'])
            sorted_athletes = sorted(all_athletes, key=lambda a: (a['id'] not in selected_ids_set, a['name']))
            
            for i, athlete in enumerate(sorted_athletes):
                with athlete_cols[i % 4]:
                    is_selected = athlete['id'] in st.session_state['selected_athletes']
                    
                    # Show thumbnail
                    if athlete.get('profile_image_url'):
                        st.image(athlete['profile_image_url'], width=60)
                    else:
                        st.markdown("👤")
                    
                    # Checkbox for selection
                    if st.checkbox(
                        f"{athlete['name']}", 
                        value=is_selected,
                        key=f"ath_select_{athlete['id']}",
                        help=f"@{athlete['instagram_handle']} • {athlete['country'] or 'Unknown'}"
                    ):
                        if athlete['id'] not in st.session_state['selected_athletes']:
                            st.session_state['selected_athletes'].append(athlete['id'])
                    else:
                        if athlete['id'] in st.session_state['selected_athletes']:
                            st.session_state['selected_athletes'].remove(athlete['id'])
            
            selected_athlete_ids = st.session_state['selected_athletes']
            
            # Show selection count
            st.caption(f"**{len(selected_athlete_ids)} athletes selected** for spotlight")
            
            # Quick actions
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Clear All Athletes"):
                    st.session_state['selected_athletes'] = []
                    st.rerun()
            with col_b:
                if st.button("Select Suggested (4)"):
                    suggested = get_athletes_for_spotlight(4)
                    st.session_state['selected_athletes'] = [a['id'] for a in suggested]
                    st.rerun()
        
        st.markdown("---")
        
        if not selected_content:
            st.warning(f"No content selected for this week! Go to Curation, select the same week ({week_start_date} to {week_end_date}), and mark content as selected.")
        else:
            edition_number = get_next_edition_number()
            st.markdown(f"### 📰 Edition #{edition_number}")
            
            # Store week info for newsletter generation
            st.session_state['generate_week_start'] = week_start_date
            st.session_state['generate_week_end'] = week_end_date
            
            # Generate Preview
            if st.button("🔄 Generate Preview", type="primary", use_container_width=True):
                with st.spinner("Generating newsletter..."):
                    # Pass week dates to newsletter generator
                    config = st.session_state['newsletter_config'].copy()
                    config['week_start'] = week_start_date
                    config['week_end'] = week_end_date
                    
                    # Get selected athletes
                    selected_athletes_list = [a for a in all_athletes if a['id'] in selected_athlete_ids] if all_athletes else []
                    
                    # Generate both versions
                    html_standalone = generate_newsletter_html(selected_content, edition_number, config, selected_athletes=selected_athletes_list)
                    html_beehiiv = generate_beehiiv_html(selected_content, edition_number, config, selected_athletes=selected_athletes_list)
                    html_website = generate_website_html(selected_content, edition_number, config, selected_athletes=selected_athletes_list)
                    
                    st.session_state['newsletter_html'] = html_standalone
                    st.session_state['newsletter_beehiiv'] = html_beehiiv
                    st.session_state['newsletter_website'] = html_website
                    st.session_state['edition_number'] = edition_number
                    st.session_state['featured_athlete_ids'] = selected_athlete_ids.copy()
                    st.success("Newsletter generated!")
            
            # Show Preview
            if 'newsletter_html' in st.session_state:
                st.markdown("### 👁️ Preview")
                
                # Preview in iframe
                with st.expander("View Newsletter Preview", expanded=True):
                    st.components.v1.html(st.session_state['newsletter_html'], height=800, scrolling=True)
                
                st.markdown("---")
                
                # Export Tabs
                export_tab1, export_tab2, export_tab3 = st.tabs(["🐝 Beehiiv Export", "🌐 Website Export", "📄 Standalone HTML"])
                
                with export_tab1:
                    st.markdown("### Export for Beehiiv (Email)")
                    
                    st.info("""
                    **Workflow:**
                    1. Copy the HTML below
                    2. In Beehiiv, create new post using your "Hyrox Weekly - Clean" template
                    3. Type `/` → select **"HTML Snippet"**
                    4. Paste the HTML
                    5. **Web tab:** Enable "Hide post from feed"
                    6. Preview, schedule, and send!
                    """)
                    
                    st.text_area(
                        "Beehiiv HTML (Select All + Copy):",
                        st.session_state.get('newsletter_beehiiv', ''),
                        height=150,
                        key="beehiiv_html_copy",
                    )
                    
                    st.download_button(
                        "📥 Download Beehiiv HTML",
                        st.session_state.get('newsletter_beehiiv', ''),
                        file_name=f"beehiiv_edition_{st.session_state['edition_number']}.html",
                        mime="text/html",
                        use_container_width=True
                    )
                
                with export_tab2:
                    st.markdown("### Export for Your Website")
                    
                    st.info("""
                    **This HTML is ready for your own website hosting:**
                    - Full HTML page with SEO meta tags
                    - Open Graph tags for social sharing
                    - Responsive design
                    - Subscribe form placeholder (add your Beehiiv embed code)
                    
                    **Upload to:** Netlify, Vercel, GitHub Pages, or your own server
                    """)
                    
                    # Generate filename based on week
                    week_start = st.session_state.get('generate_week_start', datetime.now().date())
                    filename_slug = f"edition-{st.session_state['edition_number']}-{week_start.strftime('%Y-%m-%d')}"
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            "📥 Download Website HTML",
                            st.session_state.get('newsletter_website', ''),
                            file_name=f"{filename_slug}.html",
                            mime="text/html",
                            use_container_width=True
                        )
                    
                    with col2:
                        st.text_input("Suggested filename:", filename_slug + ".html", disabled=True)
                    
                    with st.expander("Preview Website HTML"):
                        st.components.v1.html(st.session_state.get('newsletter_website', ''), height=600, scrolling=True)
                
                with export_tab3:
                    st.markdown("### Standalone HTML")
                    st.caption("Full HTML file for local preview or other email platforms")
                    
                    st.download_button(
                        "📥 Download Standalone HTML",
                        st.session_state['newsletter_html'],
                        file_name=f"newsletter_edition_{st.session_state['edition_number']}.html",
                        mime="text/html",
                        use_container_width=True
                    )
                
                st.markdown("---")
                
                # Publish
                st.markdown("### 📤 Mark as Published")
                
                if st.button("✅ Mark as Published", type="primary"):
                    content_ids = [item['id'] for item in selected_content]
                    edition_id = create_edition_record(st.session_state['edition_number'], content_ids)
                    
                    # Mark athletes as featured
                    if 'featured_athlete_ids' in st.session_state:
                        for athlete_id in st.session_state['featured_athlete_ids']:
                            mark_athlete_featured(athlete_id)
                    
                    st.success(f"Edition #{st.session_state['edition_number']} published! (ID: {edition_id})")
                    del st.session_state['newsletter_html']
                    if 'newsletter_beehiiv' in st.session_state:
                        del st.session_state['newsletter_beehiiv']
                    del st.session_state['edition_number']
                    if 'featured_athlete_ids' in st.session_state:
                        del st.session_state['featured_athlete_ids']
                    st.session_state['selected_athletes'] = []
                    st.rerun()
    
    # ========================================================================
    # ATHLETES PAGE
    # ========================================================================
    elif page == "🏃 Athletes":
        st.markdown("## 🏃 Athlete Spotlight Management")
        st.markdown("Manage athletes for the newsletter spotlight section")

        # Seed button
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            athletes = get_athletes(active_only=False)
            st.write(f"**Total Athletes:** {len(athletes)}")
        with col2:
            if not athletes:
                if st.button("🌱 Seed Initial Athletes", type="primary"):
                    count = seed_initial_athletes()
                    st.success(f"Added {count} athletes!")
                    st.rerun()
        with col3:
            if st.button("🔄 Refresh"):
                st.rerun()
        
        st.markdown("---")
        
        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["📋 All Athletes", "➕ Add Athlete", "⭐ Spotlight Preview"])
        
        # Tab 1: All Athletes
        with tab1:
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                category_filter = st.selectbox(
                    "Category",
                    options=['all', 'elite', 'influencer'],
                    format_func=lambda x: {'all': '👥 All Categories', 'elite': '🏆 Elite Athletes', 'influencer': '📱 Influencers'}[x]
                )
            with col2:
                show_inactive = st.checkbox("Show inactive athletes")
            
            # Get and display athletes
            athletes = get_athletes(category_filter=category_filter, active_only=not show_inactive)
            
            if not athletes:
                st.info("No athletes found. Click 'Seed Initial Athletes' to add the top 30 Hyrox athletes.")
            else:
                # Render each athlete as an independent fragment
                for athlete in athletes:
                    render_athlete_card(athlete)

        # Tab 2: Add Athlete
        with tab2:
            st.markdown("### Add New Athlete")
            
            st.info("""
            **📸 Profile Image Tips:**
            - Instagram CDN URLs (instagram.*.fbcdn.net) won't work in newsletters - they expire and block embedding
            - Use permanent image URLs from: athlete websites, Wikipedia, sports databases, or upload to Imgur/Cloudinary
            - If no image URL is provided, a stylized avatar with initials will be generated automatically
            """)
            
            with st.form("add_athlete_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    name = st.text_input("Name *", placeholder="Hunter McIntyre")
                    instagram_handle = st.text_input("Instagram Handle *", placeholder="hunterthehunter")
                    country = st.text_input("Country", placeholder="USA")
                    category = st.selectbox("Category", options=['elite', 'influencer'])
                    website = st.text_input("Website", placeholder="https://...")
                
                with col2:
                    bio = st.text_area("Bio", placeholder="Professional Hyrox athlete...", height=100)
                    achievements = st.text_input("Achievements", placeholder="World Champion, Elite 15")
                    profile_image_url = st.text_input("Profile Image URL", placeholder="https://example.com/photo.jpg", help="Use permanent URLs only - not Instagram CDN links")
                
                submitted = st.form_submit_button("➕ Add Athlete", type="primary", use_container_width=True)
                
                if submitted:
                    if name and instagram_handle:
                        athlete_id = add_athlete(
                            name=name,
                            instagram_handle=instagram_handle,
                            category=category,
                            country=country,
                            bio=bio,
                            achievements=achievements,
                            profile_image_url=profile_image_url,
                            website=website
                        )
                        if athlete_id:
                            st.success(f"Added {name}!")
                            st.rerun()
                        else:
                            st.error("Error adding athlete")
                    else:
                        st.error("Name and Instagram handle are required")
        
        # Tab 3: Spotlight Preview
        with tab3:
            st.markdown("### Athlete Spotlight Preview")
            st.markdown("This shows how athletes will appear in the newsletter")
            
            num_athletes = st.slider("Number of athletes to feature", 2, 6, 4)
            
            if st.button("🔄 Refresh Spotlight Selection"):
                st.rerun()
            
            spotlight_athletes = get_athletes_for_spotlight(num_athletes)
            
            if not spotlight_athletes:
                st.info("No athletes available for spotlight. Add some athletes first!")
            else:
                st.markdown("---")

                # Preview grid - render each athlete as a fragment within its column
                cols = st.columns(min(len(spotlight_athletes), 4))
                for i, athlete in enumerate(spotlight_athletes):
                    with cols[i % 4]:
                        render_spotlight_athlete(athlete)

                st.markdown("---")
                st.markdown("**Note:** Athletes who haven't been featured recently are prioritized. Click 'Mark Featured' when you include them in a newsletter.")

    # ========================================================================
    # PREMIUM PAGE
    # ========================================================================
    elif page == "💎 Premium":
        st.markdown("## 💎 Premium Management")
        st.markdown("Manage subscribers, athlete editions, and performance topics")

        # Check Supabase connection
        if not SUPABASE_SERVICE_KEY:
            st.warning("⚠️ SUPABASE_SERVICE_KEY not configured in .env file. Premium features require Supabase connection.")
            st.code("""
# Add to your .env file:
SUPABASE_URL=https://ksqrakczmecdbzxwsvea.supabase.co
SUPABASE_SERVICE_KEY=your_service_key_here
            """)
        else:
            # Premium tabs
            premium_tab1, premium_tab2, premium_tab3, premium_tab4 = st.tabs(["📊 Subscribers", "🏃 Athlete Editions", "📈 Performance Topics", "📦 Content Library"])

            # =================== SUBSCRIBERS TAB ===================
            with premium_tab1:
                st.markdown("### 📊 Subscriber Overview")

                # Fetch subscribers
                subscribers = supabase_get('subscribers', 'order=created_at.desc')

                if subscribers:
                    # Stats
                    total = len(subscribers)
                    active = len([s for s in subscribers if s.get('subscription_status') == 'active'])
                    monthly = len([s for s in subscribers if s.get('subscription_status') == 'active' and s.get('subscription_tier') == 'monthly'])
                    yearly = len([s for s in subscribers if s.get('subscription_status') == 'active' and s.get('subscription_tier') == 'yearly'])
                    early_bird = len([s for s in subscribers if s.get('is_early_bird') and s.get('subscription_status') == 'active'])

                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Total Subscribers", total)
                    with col2:
                        st.metric("Active", active, delta=f"{active}/{total}")
                    with col3:
                        st.metric("Monthly", monthly)
                    with col4:
                        st.metric("Yearly", yearly)
                    with col5:
                        st.metric("Early Bird Spots Left", max(0, 100 - early_bird), delta=f"{early_bird}/100 used")

                    st.markdown("---")
                    st.markdown("### 📋 Subscriber List")

                    # Filter
                    status_filter = st.selectbox("Filter by Status", ["All", "Active", "Cancelled", "Past Due"])

                    filtered = subscribers
                    if status_filter == "Active":
                        filtered = [s for s in subscribers if s.get('subscription_status') == 'active']
                    elif status_filter == "Cancelled":
                        filtered = [s for s in subscribers if s.get('subscription_status') == 'cancelled']
                    elif status_filter == "Past Due":
                        filtered = [s for s in subscribers if s.get('subscription_status') == 'past_due']

                    # Display table
                    if filtered:
                        for sub in filtered:
                            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                            with col1:
                                email = sub.get('email', 'N/A')
                                eb_badge = "🌟" if sub.get('is_early_bird') else ""
                                st.write(f"{eb_badge} **{email}**")
                            with col2:
                                tier = sub.get('subscription_tier', 'N/A').title()
                                st.write(f"📦 {tier}")
                            with col3:
                                status = sub.get('subscription_status', 'N/A')
                                status_color = "🟢" if status == 'active' else "🔴" if status == 'cancelled' else "🟡"
                                st.write(f"{status_color} {status.title()}")
                            with col4:
                                created = sub.get('created_at', '')[:10] if sub.get('created_at') else 'N/A'
                                st.write(f"📅 {created}")
                            st.markdown("---")
                    else:
                        st.info("No subscribers match the filter")
                else:
                    st.info("No subscribers yet. Once you get your first premium subscriber, they'll appear here!")

                    # Show test mode notice
                    st.markdown("---")
                    st.markdown("### 🧪 Test Your Setup")
                    st.markdown("""
                    To test the full flow:
                    1. Go to your [Stripe Dashboard](https://dashboard.stripe.com/test/products)
                    2. Make sure you're in **Test Mode**
                    3. Visit your site's `/premium` page
                    4. Use Stripe test card: `4242 4242 4242 4242`
                    5. Complete checkout and check back here!
                    """)

            # =================== ATHLETE EDITIONS TAB ===================
            with premium_tab2:
                st.markdown("### 🏃 Athlete Editions")
                st.markdown("Manage premium athlete profile content")

                # Fetch athletes from Supabase
                athletes = supabase_get('athletes', 'order=name')

                if athletes:
                    st.markdown(f"**{len(athletes)} athletes** in database")

                    # Athlete selector for detailed view
                    athlete_names = ["Select an athlete..."] + [f"{a['name']} ({a.get('country', 'N/A')})" for a in athletes]
                    selected_idx = st.selectbox("Select Athlete to Manage", range(len(athlete_names)),
                                               format_func=lambda i: athlete_names[i], key="athlete_selector")

                    if selected_idx > 0:
                        athlete = athletes[selected_idx - 1]
                        athlete_id = athlete['id']

                        st.markdown("---")
                        col1, col2 = st.columns([1, 2])

                        with col1:
                            # Athlete info card
                            with st.container(border=True):
                                if athlete.get('profile_image_url'):
                                    st.image(athlete['profile_image_url'], width=150)
                                st.markdown(f"### {athlete['name']}")
                                st.caption(f"{athlete.get('country', '')} | {athlete.get('gender', '').title()}")
                                if athlete.get('instagram_handle'):
                                    st.markdown(f"[@{athlete['instagram_handle']}](https://instagram.com/{athlete['instagram_handle']})")

                        with col2:
                            # Edit athlete info
                            with st.expander("✏️ Edit Athlete Info", expanded=False):
                                new_bio = st.text_area("Bio", value=athlete.get('bio', ''), key=f"edit_bio_{athlete_id}", height=100)
                                new_instagram = st.text_input("Instagram", value=athlete.get('instagram_handle', ''), key=f"edit_ig_{athlete_id}")
                                new_image = st.text_input("Image URL", value=athlete.get('profile_image_url', ''), key=f"edit_img_{athlete_id}")
                                new_website = st.text_input("Website", value=athlete.get('website_url', '') or '', key=f"edit_web_{athlete_id}")

                                if st.button("💾 Save Changes", key=f"save_athlete_{athlete_id}"):
                                    success = supabase_patch('athletes', f'id=eq.{athlete_id}', {
                                        'bio': new_bio,
                                        'instagram_handle': new_instagram,
                                        'profile_image_url': new_image,
                                        'website_url': new_website
                                    })
                                    if success:
                                        st.success("Saved!")
                                        st.rerun()

                        # Content Linking Section
                        st.markdown("---")
                        st.markdown("### 🔗 Linked Content")

                        # Fetch linked content for this athlete
                        linked_content = supabase_get('athlete_content',
                            f'athlete_id=eq.{athlete_id}&select=id,display_order,content_type,content_id,content_items(id,title,platform,url,thumbnail_url)&order=display_order') or []

                        if linked_content:
                            st.markdown(f"**{len(linked_content)} items** linked to this athlete")

                            for idx, link in enumerate(linked_content):
                                content = link.get('content_items', {})
                                if content:
                                    col1, col2, col3, col4 = st.columns([4, 2, 1, 1])
                                    with col1:
                                        platform_emoji = {'youtube': '▶️', 'podcast': '🎙️', 'article': '📄', 'reddit': '💬'}.get(content.get('platform', ''), '🔗')
                                        st.write(f"{platform_emoji} **{content.get('title', 'Untitled')[:50]}**")
                                    with col2:
                                        st.caption(content.get('platform', '').title())
                                    with col3:
                                        new_order = st.number_input("Order", value=link.get('display_order', idx), key=f"order_{link['id']}", min_value=0, label_visibility="collapsed")
                                    with col4:
                                        if st.button("🗑️", key=f"unlink_{link['id']}", help="Remove link"):
                                            supabase_delete('athlete_content', f'id=eq.{link["id"]}')
                                            st.rerun()

                            # Update order button
                            if st.button("💾 Update Order", key="update_order_athletes"):
                                for link in linked_content:
                                    new_order = st.session_state.get(f"order_{link['id']}", link.get('display_order', 0))
                                    supabase_patch('athlete_content', f'id=eq.{link["id"]}', {'display_order': new_order})
                                st.success("Order updated!")
                                st.rerun()
                        else:
                            st.info("No content linked yet. Add content from the Content Library tab.")

                        # Add content link
                        st.markdown("#### ➕ Link New Content")
                        all_content = supabase_get('content_items', 'select=id,title,platform&order=title&limit=100') or []

                        if all_content:
                            content_options = {c['id']: f"{c.get('platform', '').title()}: {c.get('title', 'Untitled')[:60]}" for c in all_content}
                            selected_content_id = st.selectbox("Select content to link",
                                options=[None] + list(content_options.keys()),
                                format_func=lambda x: "Choose content..." if x is None else content_options.get(x, "Unknown"),
                                key=f"link_content_{athlete_id}")

                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                link_type = st.selectbox("Content Type", ["video", "podcast", "article", "other"], key=f"link_type_{athlete_id}")
                            with col2:
                                link_order = st.number_input("Display Order", min_value=0, value=len(linked_content), key=f"link_order_{athlete_id}")
                            with col3:
                                if st.button("🔗 Link", key=f"do_link_{athlete_id}", disabled=selected_content_id is None):
                                    # Check if already linked
                                    existing = supabase_get('athlete_content', f'athlete_id=eq.{athlete_id}&content_id=eq.{selected_content_id}')
                                    if existing:
                                        st.warning("This content is already linked to this athlete")
                                    else:
                                        result = supabase_post('athlete_content', {
                                            'athlete_id': athlete_id,
                                            'content_id': selected_content_id,
                                            'content_type': link_type,
                                            'display_order': link_order
                                        })
                                        if result:
                                            st.success("Content linked!")
                                            st.rerun()
                        else:
                            st.info("No content available. Add content in the Content Library tab first.")

                    else:
                        # Show athlete grid when none selected
                        st.markdown("---")
                        for i in range(0, len(athletes), 4):
                            cols = st.columns(4)
                            for j, col in enumerate(cols):
                                if i + j < len(athletes):
                                    athlete = athletes[i + j]
                                    with col:
                                        with st.container(border=True):
                                            # Count linked content
                                            linked_count = len(supabase_get('athlete_content', f'athlete_id=eq.{athlete["id"]}&select=id') or [])
                                            st.markdown(f"**{athlete.get('name', 'Unknown')}**")
                                            st.caption(f"{athlete.get('country', '')} | {linked_count} items")

                    st.markdown("---")
                    st.markdown("### ➕ Add New Athlete")

                    with st.form("add_athlete_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_name = st.text_input("Name *")
                            new_country = st.text_input("Country")
                            new_gender = st.selectbox("Gender", ["male", "female"])
                        with col2:
                            new_slug = st.text_input("Slug (URL-friendly)", help="e.g., 'hunter-mcintyre'")
                            new_ig = st.text_input("Instagram Handle")
                            new_img_url = st.text_input("Profile Image URL")

                        new_bio_text = st.text_area("Bio", height=100)

                        submitted = st.form_submit_button("Add Athlete")
                        if submitted and new_name:
                            slug = new_slug or new_name.lower().replace(' ', '-')
                            result = supabase_post('athletes', {
                                'name': new_name,
                                'slug': slug,
                                'country': new_country,
                                'gender': new_gender,
                                'instagram_handle': new_ig,
                                'profile_image_url': new_img_url,
                                'bio': new_bio_text
                            })
                            if result:
                                st.success(f"Added {new_name}!")
                                st.rerun()
                            else:
                                st.error("Failed to add athlete. Check if slug is unique.")
                else:
                    st.info("No athletes in database. Add some athletes to create Athlete Editions.")

            # =================== PERFORMANCE TOPICS TAB ===================
            with premium_tab3:
                st.markdown("### 📈 Performance Topics")
                st.markdown("Manage performance guide content for each Hyrox station and topic")

                # Fetch performance topics
                topics = supabase_get('performance_topics', 'order=display_order,category')

                if topics:
                    st.markdown(f"**{len(topics)} topics** in database")

                    # Topic selector for detailed view
                    topic_names = ["Select a topic..."] + [f"{t.get('icon_emoji', '📌')} {t['name']}" for t in topics]
                    selected_topic_idx = st.selectbox("Select Topic to Manage", range(len(topic_names)),
                                                     format_func=lambda i: topic_names[i], key="topic_selector")

                    if selected_topic_idx > 0:
                        topic = topics[selected_topic_idx - 1]
                        topic_id = topic['id']

                        st.markdown("---")
                        col1, col2 = st.columns([1, 2])

                        with col1:
                            # Topic info card
                            with st.container(border=True):
                                st.markdown(f"## {topic.get('icon_emoji', '📌')} {topic['name']}")
                                st.caption(f"Category: {topic.get('category', 'other').title()}")
                                st.caption(f"Slug: `{topic.get('slug', '')}`")
                                status = topic.get('status', 'draft')
                                status_color = "🟢" if status == 'published' else "🟡"
                                st.write(f"Status: {status_color} {status.title()}")

                        with col2:
                            # Edit topic info
                            with st.expander("✏️ Edit Topic Info", expanded=False):
                                edit_name = st.text_input("Name", value=topic.get('name', ''), key=f"edit_name_{topic_id}")
                                edit_desc = st.text_area("Description", value=topic.get('description', ''), key=f"edit_desc_{topic_id}", height=80)
                                edit_emoji = st.text_input("Icon Emoji", value=topic.get('icon_emoji', ''), key=f"edit_emoji_{topic_id}")
                                edit_status = st.selectbox("Status", ["draft", "published"],
                                    index=0 if topic.get('status') == 'draft' else 1, key=f"edit_status_{topic_id}")
                                edit_order = st.number_input("Display Order", value=topic.get('display_order', 0), key=f"edit_order_{topic_id}")

                                if st.button("💾 Save Changes", key=f"save_topic_{topic_id}"):
                                    success = supabase_patch('performance_topics', f'id=eq.{topic_id}', {
                                        'name': edit_name,
                                        'description': edit_desc,
                                        'icon_emoji': edit_emoji,
                                        'status': edit_status,
                                        'display_order': edit_order
                                    })
                                    if success:
                                        st.success("Saved!")
                                        st.rerun()

                        # Content Linking Section
                        st.markdown("---")
                        st.markdown("### 🔗 Linked Content")

                        # Fetch linked content for this topic
                        linked_content = supabase_get('performance_content',
                            f'topic_id=eq.{topic_id}&select=id,display_order,content_id,content_items(id,title,platform,url,thumbnail_url)&order=display_order') or []

                        if linked_content:
                            st.markdown(f"**{len(linked_content)} items** linked to this topic")

                            for idx, link in enumerate(linked_content):
                                content = link.get('content_items', {})
                                if content:
                                    col1, col2, col3, col4 = st.columns([4, 2, 1, 1])
                                    with col1:
                                        platform_emoji = {'youtube': '▶️', 'podcast': '🎙️', 'article': '📄', 'reddit': '💬'}.get(content.get('platform', ''), '🔗')
                                        st.write(f"{platform_emoji} **{content.get('title', 'Untitled')[:50]}**")
                                    with col2:
                                        st.caption(content.get('platform', '').title())
                                    with col3:
                                        new_order = st.number_input("Order", value=link.get('display_order', idx), key=f"torder_{link['id']}", min_value=0, label_visibility="collapsed")
                                    with col4:
                                        if st.button("🗑️", key=f"tunlink_{link['id']}", help="Remove link"):
                                            supabase_delete('performance_content', f'id=eq.{link["id"]}')
                                            st.rerun()

                            # Update order button
                            if st.button("💾 Update Order", key="update_order_topics"):
                                for link in linked_content:
                                    new_order = st.session_state.get(f"torder_{link['id']}", link.get('display_order', 0))
                                    supabase_patch('performance_content', f'id=eq.{link["id"]}', {'display_order': new_order})
                                st.success("Order updated!")
                                st.rerun()
                        else:
                            st.info("No content linked yet. Add content from the Content Library tab.")

                        # Add content link
                        st.markdown("#### ➕ Link New Content")
                        all_content = supabase_get('content_items', 'select=id,title,platform&order=title&limit=100') or []

                        if all_content:
                            content_options = {c['id']: f"{c.get('platform', '').title()}: {c.get('title', 'Untitled')[:60]}" for c in all_content}
                            selected_content_id = st.selectbox("Select content to link",
                                options=[None] + list(content_options.keys()),
                                format_func=lambda x: "Choose content..." if x is None else content_options.get(x, "Unknown"),
                                key=f"tlink_content_{topic_id}")

                            col1, col2 = st.columns([3, 1])
                            with col1:
                                tlink_order = st.number_input("Display Order", min_value=0, value=len(linked_content), key=f"tlink_order_{topic_id}")
                            with col2:
                                if st.button("🔗 Link", key=f"tdo_link_{topic_id}", disabled=selected_content_id is None):
                                    # Check if already linked
                                    existing = supabase_get('performance_content', f'topic_id=eq.{topic_id}&content_id=eq.{selected_content_id}')
                                    if existing:
                                        st.warning("This content is already linked to this topic")
                                    else:
                                        result = supabase_post('performance_content', {
                                            'topic_id': topic_id,
                                            'content_id': selected_content_id,
                                            'display_order': tlink_order
                                        })
                                        if result:
                                            st.success("Content linked!")
                                            st.rerun()
                        else:
                            st.info("No content available. Add content in the Content Library tab first.")

                    else:
                        # Show topics grouped by category when none selected
                        st.markdown("---")
                        categories = {}
                        for topic in topics:
                            cat = topic.get('category', 'other')
                            if cat not in categories:
                                categories[cat] = []
                            categories[cat].append(topic)

                        for cat, cat_topics in categories.items():
                            with st.expander(f"📁 {cat.title()} ({len(cat_topics)} topics)", expanded=True):
                                for topic in cat_topics:
                                    linked_count = len(supabase_get('performance_content', f'topic_id=eq.{topic["id"]}&select=id') or [])
                                    col1, col2, col3 = st.columns([3, 2, 1])
                                    with col1:
                                        emoji = topic.get('icon_emoji', '📌')
                                        st.write(f"{emoji} **{topic.get('name', 'Unknown')}**")
                                    with col2:
                                        status = topic.get('status', 'draft')
                                        status_color = "🟢" if status == 'published' else "🟡"
                                        st.caption(f"{status_color} {status.title()}")
                                    with col3:
                                        st.caption(f"{linked_count} items")

                    st.markdown("---")

                st.markdown("### ➕ Add New Topic")

                with st.form("add_topic_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        topic_name = st.text_input("Topic Name *", placeholder="e.g., Ski Erg")
                        topic_slug = st.text_input("Slug *", placeholder="e.g., ski-erg")
                        topic_category = st.selectbox("Category", ["stations", "running", "other"])
                    with col2:
                        topic_emoji = st.text_input("Icon Emoji", placeholder="🎿")
                        topic_order = st.number_input("Display Order", min_value=0, value=0)
                        topic_status = st.selectbox("Status", ["draft", "published"])

                    topic_description = st.text_area("Description", height=80)

                    if st.form_submit_button("Add Topic"):
                        if topic_name and topic_slug:
                            result = supabase_post('performance_topics', {
                                'name': topic_name,
                                'slug': topic_slug,
                                'category': topic_category,
                                'icon_emoji': topic_emoji,
                                'display_order': topic_order,
                                'status': topic_status,
                                'description': topic_description
                            })
                            if result:
                                st.success(f"Added topic: {topic_name}")
                                st.rerun()
                            else:
                                st.error("Failed to add topic. Check if slug is unique.")
                        else:
                            st.warning("Name and slug are required")

            # =================== CONTENT LIBRARY TAB ===================
            with premium_tab4:
                st.markdown("### 📦 Content Library")
                st.markdown("Manage all content items that can be linked to athletes and performance topics")

                # Fetch all content
                all_content = supabase_get('content_items', 'order=created_at.desc&limit=200') or []

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Items", len(all_content))
                with col2:
                    youtube_count = len([c for c in all_content if c.get('platform') == 'youtube'])
                    st.metric("Videos", youtube_count)
                with col3:
                    podcast_count = len([c for c in all_content if c.get('platform') == 'podcast'])
                    st.metric("Podcasts", podcast_count)

                st.markdown("---")

                # Filter controls
                col1, col2 = st.columns(2)
                with col1:
                    platform_filter = st.selectbox("Filter by Platform",
                        ["All", "youtube", "podcast", "article", "reddit"],
                        format_func=lambda x: "All Platforms" if x == "All" else x.title())
                with col2:
                    search_term = st.text_input("Search by title", placeholder="Search...")

                # Apply filters
                filtered_content = all_content
                if platform_filter != "All":
                    filtered_content = [c for c in filtered_content if c.get('platform') == platform_filter]
                if search_term:
                    filtered_content = [c for c in filtered_content if search_term.lower() in c.get('title', '').lower()]

                st.markdown(f"**Showing {len(filtered_content)} items**")

                # Content list
                if filtered_content:
                    for content in filtered_content[:50]:  # Limit display
                        with st.container(border=True):
                            col1, col2, col3 = st.columns([4, 1, 1])
                            with col1:
                                platform_emoji = {'youtube': '▶️', 'podcast': '🎙️', 'article': '📄', 'reddit': '💬'}.get(content.get('platform', ''), '🔗')
                                title = content.get('title', 'Untitled')[:80]
                                st.markdown(f"{platform_emoji} **{title}**")
                                st.caption(f"URL: {content.get('url', 'N/A')[:60]}...")
                            with col2:
                                st.caption(content.get('platform', '').title())
                                if content.get('view_count'):
                                    st.caption(f"👁 {content['view_count']:,}")
                            with col3:
                                if st.button("🗑️", key=f"del_content_{content['id']}", help="Delete"):
                                    supabase_delete('content_items', f'id=eq.{content["id"]}')
                                    st.rerun()

                st.markdown("---")
                st.markdown("### ➕ Add New Content")

                with st.expander("Add Content Manually", expanded=False):
                    with st.form("add_content_form"):
                        content_title = st.text_input("Title *")
                        content_url = st.text_input("URL *")
                        col1, col2 = st.columns(2)
                        with col1:
                            content_platform = st.selectbox("Platform", ["youtube", "podcast", "article", "reddit"])
                            content_thumbnail = st.text_input("Thumbnail URL")
                        with col2:
                            content_views = st.number_input("View Count", min_value=0, value=0)
                            content_duration = st.number_input("Duration (minutes)", min_value=0, value=0)

                        content_description = st.text_area("Description", height=80)

                        if st.form_submit_button("Add Content"):
                            if content_title and content_url:
                                # Check if URL exists
                                existing = supabase_get('content_items', f'url=eq.{quote(content_url)}')
                                if existing:
                                    st.warning("This URL already exists in the database")
                                else:
                                    result = supabase_post('content_items', {
                                        'title': content_title,
                                        'url': content_url,
                                        'platform': content_platform,
                                        'thumbnail_url': content_thumbnail or None,
                                        'view_count': content_views,
                                        'duration_seconds': content_duration * 60 if content_duration else None,
                                        'description': content_description,
                                        'status': 'discovered'
                                    })
                                    if result:
                                        st.success(f"Added: {content_title}")
                                        st.rerun()
                            else:
                                st.warning("Title and URL are required")

                # YouTube Discovery
                with st.expander("🎬 YouTube Discovery", expanded=False):
                    st.markdown("Search YouTube for Hyrox-related content")

                    yt_search = st.text_input("Search Query", value="hyrox training", key="yt_search")
                    col1, col2 = st.columns(2)
                    with col1:
                        yt_max_results = st.slider("Max Results", 5, 50, 10)
                    with col2:
                        yt_order = st.selectbox("Order By", ["relevance", "date", "viewCount"])

                    if st.button("🔍 Search YouTube", key="yt_search_btn"):
                        youtube_api_key = os.getenv('YOUTUBE_API_KEY')
                        if not youtube_api_key:
                            st.error("YOUTUBE_API_KEY not configured in .env file")
                        else:
                            try:
                                search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={quote(yt_search)}&type=video&maxResults={yt_max_results}&order={yt_order}&key={youtube_api_key}"
                                response = requests.get(search_url)
                                if response.status_code == 200:
                                    data = response.json()
                                    videos = data.get('items', [])
                                    st.success(f"Found {len(videos)} videos")

                                    for video in videos:
                                        video_id = video['id']['videoId']
                                        snippet = video['snippet']
                                        title = snippet['title']
                                        thumbnail = snippet['thumbnails']['medium']['url']
                                        channel = snippet['channelTitle']

                                        col1, col2 = st.columns([3, 1])
                                        with col1:
                                            st.image(thumbnail, width=120)
                                            st.markdown(f"**{title}**")
                                            st.caption(f"Channel: {channel}")
                                        with col2:
                                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                                            # Check if already in database
                                            existing = supabase_get('content_items', f'url=eq.{quote(video_url)}')
                                            if existing:
                                                st.write("✅ Already added")
                                            else:
                                                if st.button("➕ Add", key=f"add_yt_{video_id}"):
                                                    result = supabase_post('content_items', {
                                                        'title': title,
                                                        'url': video_url,
                                                        'platform': 'youtube',
                                                        'thumbnail_url': thumbnail,
                                                        'description': snippet.get('description', ''),
                                                        'status': 'discovered'
                                                    })
                                                    if result:
                                                        st.success("Added!")
                                                        st.rerun()
                                        st.markdown("---")
                                else:
                                    st.error(f"YouTube API error: {response.status_code}")
                            except Exception as e:
                                st.error(f"Error searching YouTube: {e}")

                # Podcast Discovery (using Podcast Index API)
                with st.expander("🎙️ Podcast Discovery", expanded=False):
                    st.markdown("Search for Hyrox-related podcasts")

                    podcast_search = st.text_input("Search Query", value="hyrox fitness", key="podcast_search")

                    if st.button("🔍 Search Podcasts", key="podcast_search_btn"):
                        podcast_api_key = os.getenv('PODCAST_INDEX_KEY')
                        podcast_api_secret = os.getenv('PODCAST_INDEX_SECRET')

                        if not podcast_api_key or not podcast_api_secret:
                            st.warning("Podcast Index API keys not configured. Add PODCAST_INDEX_KEY and PODCAST_INDEX_SECRET to .env")
                            st.info("Get free API keys at: https://api.podcastindex.org/")
                        else:
                            try:
                                import hashlib
                                import time as time_module

                                # Create auth headers for Podcast Index
                                epoch_time = int(time_module.time())
                                data_to_hash = podcast_api_key + podcast_api_secret + str(epoch_time)
                                sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()

                                headers = {
                                    "X-Auth-Date": str(epoch_time),
                                    "X-Auth-Key": podcast_api_key,
                                    "Authorization": sha_1,
                                    "User-Agent": "HyroxWeekly/1.0"
                                }

                                search_url = f"https://api.podcastindex.org/api/1.0/search/byterm?q={quote(podcast_search)}"
                                response = requests.get(search_url, headers=headers)

                                if response.status_code == 200:
                                    data = response.json()
                                    podcasts = data.get('feeds', [])[:10]
                                    st.success(f"Found {len(podcasts)} podcasts")

                                    for podcast in podcasts:
                                        title = podcast.get('title', 'Unknown')
                                        url = podcast.get('url', '')
                                        image = podcast.get('image', '')
                                        author = podcast.get('author', 'Unknown')

                                        col1, col2 = st.columns([3, 1])
                                        with col1:
                                            if image:
                                                st.image(image, width=80)
                                            st.markdown(f"**{title}**")
                                            st.caption(f"By: {author}")
                                        with col2:
                                            existing = supabase_get('content_items', f'url=eq.{quote(url)}') if url else None
                                            if existing:
                                                st.write("✅ Already added")
                                            elif url:
                                                if st.button("➕ Add", key=f"add_pod_{podcast.get('id', title[:10])}"):
                                                    result = supabase_post('content_items', {
                                                        'title': title,
                                                        'url': url,
                                                        'platform': 'podcast',
                                                        'thumbnail_url': image,
                                                        'description': podcast.get('description', ''),
                                                        'status': 'discovered'
                                                    })
                                                    if result:
                                                        st.success("Added!")
                                                        st.rerun()
                                        st.markdown("---")
                                else:
                                    st.error(f"Podcast API error: {response.status_code}")
                            except Exception as e:
                                st.error(f"Error searching podcasts: {e}")

    # ========================================================================
    # ANALYTICS PAGE
    # ========================================================================
    elif page == "📊 Analytics":
        st.markdown("## 📊 Analytics")
        st.markdown("Track your newsletter performance")
        
        # Get display timezone
        display_tz = st.session_state['newsletter_config'].get('display_timezone', 'US/Pacific')
        
        # Editions
        st.markdown("### 📚 Published Editions")
        editions = get_editions()
        
        if editions:
            for ed in editions:
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(f"**Edition #{ed['edition_number']}**")
                with col2:
                    pub_date = ed.get('publish_date', '')
                    pub_date_str = format_date_local(pub_date, display_tz) if pub_date else ''
                    st.write(pub_date_str)
                with col3:
                    st.write(ed.get('status', 'unknown'))
        else:
            st.info("No editions published yet.")
        
        st.markdown("---")
        
        # Content Stats
        st.markdown("### 📈 Content Statistics")
        stats = get_stats()
        
        if stats:
            # By Platform
            st.markdown("#### By Platform")
            for platform, config in PLATFORM_CONFIG.items():
                total = sum(s['count'] for s in stats if s['platform'] == platform)
                st.write(f"{config['emoji']} **{config['name']}**: {total} items")
            
            # By Status
            st.markdown("#### By Status")
            statuses = {}
            for s in stats:
                status = s['status']
                statuses[status] = statuses.get(status, 0) + s['count']
            
            for status, count in statuses.items():
                st.write(f"**{status.title()}**: {count}")
    
    # ========================================================================
    # SETTINGS PAGE
    # ========================================================================
    elif page == "⚙️ Settings":
        st.markdown("## ⚙️ Newsletter Settings")
        st.markdown("Configure the text and links that appear in every edition")
        
        config = st.session_state['newsletter_config']
        
        # Header Section
        st.markdown("### 📰 Header")
        
        col1, col2 = st.columns(2)
        with col1:
            config['newsletter_name'] = st.text_input(
                "Newsletter Name",
                value=config['newsletter_name'],
                help="The main title displayed in the header"
            )
        with col2:
            config['tagline'] = st.text_input(
                "Tagline",
                value=config['tagline'],
                help="The subtitle under the newsletter name"
            )
        
        st.markdown("---")
        
        # Intro Section
        st.markdown("### 📝 Introduction")
        config['intro_template'] = st.text_area(
            "Intro Template",
            value=config['intro_template'],
            help="Use {content_summary} to insert the content count (e.g., '4 videos, 2 podcasts')",
            height=80
        )
        st.caption("Example: \"Welcome! This week we've curated {content_summary} of the best Hyrox content.\"")
        
        st.markdown("---")
        
        # Sponsor Section
        st.markdown("### 💼 Sponsor Banner")
        
        config['sponsor_enabled'] = st.toggle(
            "Enable Sponsor Banner",
            value=config.get('sponsor_enabled', 'true') == 'true',
            help="Turn off to hide the sponsor section from the newsletter"
        )
        # Store as string for database compatibility
        config['sponsor_enabled'] = 'true' if config['sponsor_enabled'] else 'false'
        
        if config['sponsor_enabled'] == 'true':
            col1, col2, col3 = st.columns(3)
            with col1:
                config['sponsor_label'] = st.text_input(
                    "Sponsor Label",
                    value=config['sponsor_label'],
                    help="Text before the sponsor CTA"
                )
            with col2:
                config['sponsor_cta'] = st.text_input(
                    "Sponsor CTA Text",
                    value=config['sponsor_cta'],
                    help="Call-to-action text for sponsors"
                )
            with col3:
                config['sponsor_email'] = st.text_input(
                    "Sponsor Email",
                    value=config['sponsor_email'],
                    help="Email address for sponsor inquiries"
                )
        else:
            st.info("Sponsor banner is hidden from the newsletter")
        
        st.markdown("---")
        
        # CTA Section
        st.markdown("### 🎯 Call-to-Action (Footer)")
        
        col1, col2 = st.columns(2)
        with col1:
            config['cta_heading'] = st.text_input(
                "CTA Heading",
                value=config['cta_heading'],
                help="Main heading in the subscribe section"
            )
            config['cta_button_text'] = st.text_input(
                "Button Text",
                value=config['cta_button_text'],
                help="Text on the subscribe button"
            )
        with col2:
            config['cta_subtext'] = st.text_input(
                "CTA Subtext",
                value=config['cta_subtext'],
                help="Supporting text under the heading"
            )
            config['cta_button_url'] = st.text_input(
                "Button URL",
                value=config['cta_button_url'],
                help="Link for the subscribe button"
            )
        
        st.markdown("---")
        
        # Beehiiv Subscribe Embed
        st.markdown("### 📬 Website Subscribe Form (Beehiiv Embed)")
        st.caption("This embed code appears on the website archive pages. Get it from Beehiiv → Grow → Subscribe Forms → Embed.")
        
        config['beehiiv_embed_code'] = st.text_area(
            "Beehiiv Embed Code",
            value=config.get('beehiiv_embed_code', ''),
            height=150,
            help="Paste your Beehiiv subscribe form embed code here (the full HTML/iframe code)",
            placeholder='<iframe src="https://embeds.beehiiv.com/..." ...></iframe>'
        )
        
        if not config.get('beehiiv_embed_code'):
            st.info("💡 To get your embed code: Beehiiv Dashboard → Grow → Subscribe Forms → Select a form → Embed → Copy the code")
        
        st.markdown("---")
        
        # Discovery Settings
        st.markdown("### 🔍 Discovery Settings")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            duration_options = {
                '5': '5 seconds',
                '15': '15 seconds',
                '30': '30 seconds',
                '60': '1 minute',
                '90': '1.5 minutes',
                '120': '2 minutes'
            }
            
            current_duration = config.get('youtube_min_duration', '60')
            
            config['youtube_min_duration'] = st.selectbox(
                "YouTube Minimum Video Duration",
                options=list(duration_options.keys()),
                index=list(duration_options.keys()).index(current_duration) if current_duration in duration_options else 3,
                format_func=lambda x: duration_options[x],
                help="Videos shorter than this will be filtered out during YouTube discovery"
            )
        
        with col2:
            region_options = {
                '': '🌍 Global (no region bias)',
                'US': '🇺🇸 United States',
                'GB': '🇬🇧 United Kingdom',
                'DE': '🇩🇪 Germany',
                'AU': '🇦🇺 Australia',
                'CA': '🇨🇦 Canada',
                'FR': '🇫🇷 France',
                'NL': '🇳🇱 Netherlands',
            }
            
            current_region = config.get('youtube_region', '')
            region_keys = list(region_options.keys())
            
            config['youtube_region'] = st.selectbox(
                "YouTube Region",
                options=region_keys,
                index=region_keys.index(current_region) if current_region in region_keys else 0,
                format_func=lambda x: region_options[x],
                help="Filter YouTube results by region. 'Global' returns unbiased worldwide results."
            )
        
        with col3:
            current_tz = config.get('display_timezone', 'US/Pacific')
            tz_keys = list(TIMEZONE_OPTIONS.keys())
            
            config['display_timezone'] = st.selectbox(
                "Display Timezone",
                options=tz_keys,
                index=tz_keys.index(current_tz) if current_tz in tz_keys else 0,
                format_func=lambda x: TIMEZONE_OPTIONS[x],
                help="Timestamps will be displayed in this timezone"
            )
        
        # Second row of discovery settings
        col1, col2, col3 = st.columns(3)
        
        with col1:
            podcast_country_options = {
                '': '🌍 Global (no country filter)',
                'US': '🇺🇸 United States',
                'GB': '🇬🇧 United Kingdom',
                'DE': '🇩🇪 Germany',
                'AU': '🇦🇺 Australia',
                'CA': '🇨🇦 Canada',
                'FR': '🇫🇷 France',
                'NL': '🇳🇱 Netherlands',
            }
            
            current_podcast_country = config.get('podcast_country', '')
            podcast_keys = list(podcast_country_options.keys())
            
            config['podcast_country'] = st.selectbox(
                "Podcast Country",
                options=podcast_keys,
                index=podcast_keys.index(current_podcast_country) if current_podcast_country in podcast_keys else 0,
                format_func=lambda x: podcast_country_options[x],
                help="Filter podcast results by country (iTunes/Spotify). 'Global' returns unbiased results."
            )
        
        st.markdown("---")
        
        # Section Titles
        st.markdown("### 📑 Section Titles")
        st.caption("Customize the headings for each content section in the newsletter")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            config['section_title_race_recap'] = st.text_input(
                "Race Recaps",
                value=config.get('section_title_race_recap', 'Race Recaps'),
                help="Title for race recap videos"
            )
            config['section_title_training'] = st.text_input(
                "Training Videos",
                value=config.get('section_title_training', 'Training & Workouts'),
                help="Title for training videos"
            )
            config['section_title_nutrition'] = st.text_input(
                "Nutrition Videos",
                value=config.get('section_title_nutrition', 'Nutrition & Recovery'),
                help="Title for nutrition videos"
            )
        with col2:
            config['section_title_athlete_profile'] = st.text_input(
                "Athlete Profile Videos",
                value=config.get('section_title_athlete_profile', 'Athlete Spotlights'),
                help="Title for athlete profile videos"
            )
            config['section_title_gear'] = st.text_input(
                "Gear Videos",
                value=config.get('section_title_gear', 'Gear & Equipment'),
                help="Title for gear review videos"
            )
            config['section_title_other'] = st.text_input(
                "Other Videos",
                value=config.get('section_title_other', 'More Videos'),
                help="Title for uncategorized videos"
            )
        with col3:
            config['section_title_podcasts'] = st.text_input(
                "Podcasts Section",
                value=config.get('section_title_podcasts', 'Worth a Listen'),
                help="Title for the podcasts section"
            )
            config['section_title_articles'] = st.text_input(
                "Articles Section",
                value=config.get('section_title_articles', 'Worth Reading'),
                help="Title for the articles section"
            )
            config['section_title_reddit'] = st.text_input(
                "Reddit Section",
                value=config.get('section_title_reddit', 'Community Discussions'),
                help="Title for the Reddit section"
            )
            config['section_title_athletes'] = st.text_input(
                "Athletes Section",
                value=config.get('section_title_athletes', '🏃 Athletes to Follow'),
                help="Title for the athletes section"
            )
        
        st.markdown("---")
        
        # Priority Sources
        st.markdown("### ⭐ Priority Sources")
        st.caption("Sources that will always be checked during discovery. Add sources from the Curate page or manually below.")
        
        priority_sources = get_priority_sources()
        
        if priority_sources:
            # Group by platform
            platforms = {}
            for source in priority_sources:
                plat = source['platform']
                if plat not in platforms:
                    platforms[plat] = []
                platforms[plat].append(source)

            for plat, sources in platforms.items():
                platform_emoji = {'youtube': '📺', 'podcast': '🎙️', 'article': '📝', 'reddit': '💬'}.get(plat, '📄')
                st.markdown(f"**{platform_emoji} {plat.title()}**")

                # Render each source as an independent fragment
                for source in sources:
                    render_priority_source(source, plat)
        else:
            st.info("No priority sources yet. Add them from the Curate page by clicking '⭐ Add as Priority' on any content item.")
        
        # Manual add priority source
        with st.expander("➕ Add Priority Source Manually"):
            ps_col1, ps_col2 = st.columns(2)
            with ps_col1:
                new_ps_platform = st.selectbox(
                    "Platform",
                    options=['youtube', 'podcast', 'article', 'reddit'],
                    format_func=lambda x: {'youtube': '📺 YouTube', 'podcast': '🎙️ Podcast', 'article': '📝 Article', 'reddit': '💬 Reddit'}.get(x, x)
                )
                new_ps_name = st.text_input(
                    "Source Name",
                    placeholder="e.g., UKHXR, Hybrid Calisthenics, etc."
                )
            with ps_col2:
                new_ps_type = st.selectbox(
                    "Source Type",
                    options=['channel', 'show', 'website', 'subreddit'],
                    format_func=lambda x: x.title()
                )
                
                # Show different URL guidance based on platform
                if new_ps_platform == 'article':
                    st.caption("⚠️ **For articles, enter the RSS feed URL** (usually ends in `/feed` or `/rss`)")
                    url_placeholder = "e.g., https://example.com/feed or https://newsletter.substack.com/feed"
                elif new_ps_platform == 'youtube':
                    st.caption("💡 For YouTube, enter the Channel ID for best results")
                    url_placeholder = "https://youtube.com/@channelname (optional)"
                elif new_ps_platform == 'podcast':
                    st.caption("⚠️ **For podcasts, enter the RSS feed URL** to ensure all episodes are discovered")
                    url_placeholder = "e.g., https://feeds.libsyn.com/123456/rss"
                else:
                    url_placeholder = "https://..."
                
                new_ps_url = st.text_input(
                    "URL",
                    placeholder=url_placeholder,
                    help="For podcasts & articles: Must be an RSS feed URL for reliable discovery"
                )
            
            # YouTube Channel ID field
            new_ps_channel_id = None
            if new_ps_platform == 'youtube':
                new_ps_channel_id = st.text_input(
                    "YouTube Channel ID",
                    placeholder="e.g., UCxxxxxxxxxxxxxxxxxxxxxxxx",
                    help="The channel ID ensures all videos from this channel are found. Find it in the channel URL or page source."
                )
                st.info("""
                **How to find a YouTube Channel ID:**
                1. Go to the channel page
                2. Right-click → View Page Source
                3. Search for `"channelId":"` - the 24-character ID follows
                4. Or use [commentpicker.com/youtube-channel-id.php](https://commentpicker.com/youtube-channel-id.php)
                """)
            
            # Show RSS URL examples for articles
            if new_ps_platform == 'article':
                st.info("""
                **Common RSS feed URL patterns:**
                - Substack: `https://newsletter.substack.com/feed` or `https://customdomain.com/feed`
                - WordPress: `https://site.com/feed/`
                - Medium: `https://medium.com/feed/@username`
                - Beehiiv: `https://newsletter.beehiiv.com/rss`
                """)
            
            # Show RSS URL examples for podcasts
            if new_ps_platform == 'podcast':
                st.info("""
                **How to find a podcast RSS feed:**
                1. Go to [castos.com/tools/find-podcast-rss-feed](https://castos.com/tools/find-podcast-rss-feed/)
                2. Search for the podcast name
                3. Copy the RSS feed URL
                
                **Or from Apple Podcasts:**
                1. Find the podcast on Apple Podcasts
                2. Look for the RSS feed icon or check the podcast's website
                """)
            
            if st.button("➕ Add Priority Source"):
                if new_ps_name:
                    final_url = new_ps_url.strip() if new_ps_url else None
                    final_source_id = new_ps_channel_id.strip() if new_ps_platform == 'youtube' and new_ps_channel_id else None
                    
                    # Auto-detect and fix common URL patterns for articles
                    if new_ps_platform == 'article' and final_url:
                        original_url = final_url
                        
                        # Check if it's a Substack URL without /feed
                        if 'substack.com' in final_url or any(domain in final_url for domain in ['hybridletter.com']):
                            if not final_url.endswith('/feed') and '/feed' not in final_url:
                                final_url = final_url.rstrip('/') + '/feed'
                                st.info(f"🔧 Auto-converted Substack URL to RSS feed: {final_url}")
                        
                        # Check for common patterns that suggest it's not an RSS feed
                        elif not any(pattern in final_url.lower() for pattern in ['/feed', '/rss', '.xml', 'atom']):
                            # Try appending /feed for generic sites
                            if final_url.count('/') <= 3:  # Likely a homepage URL
                                final_url = final_url.rstrip('/') + '/feed'
                                st.warning(f"⚠️ URL didn't look like an RSS feed. Trying: {final_url}")
                    
                    add_priority_source(
                        platform=new_ps_platform,
                        source_type=new_ps_type,
                        source_name=new_ps_name,
                        source_id=final_source_id,
                        source_url=final_url,
                        notes=f"Manually added on {datetime.now().strftime('%Y-%m-%d')}"
                    )
                    st.success(f"✅ Added '{new_ps_name}' as priority source!")
                    st.rerun()
                else:
                    st.error("Please enter a source name")
        
        
        st.markdown("---")
        
        # Footer Links
        st.markdown("### 🔗 Footer Links")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            config['footer_instagram'] = st.text_input(
                "Instagram URL",
                value=config['footer_instagram']
            )
        with col2:
            config['footer_website'] = st.text_input(
                "Website URL",
                value=config['footer_website']
            )
        with col3:
            config['footer_contact_email'] = st.text_input(
                "Contact Email",
                value=config.get('footer_contact_email', 'team@hyroxweekly.com'),
                help="Email for 'Contact Us' link in footer"
            )
        
        st.markdown("---")
        
        # Save to database
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            if st.button("💾 Save Settings", type="primary", use_container_width=True):
                st.session_state['newsletter_config'] = config
                if save_all_newsletter_settings(config):
                    st.success("✅ Settings saved to database!")
                else:
                    st.error("❌ Error saving settings")
        
        with col2:
            if st.button("🔄 Reload from DB", use_container_width=True):
                st.session_state['newsletter_config'] = get_newsletter_settings()
                st.success("Settings reloaded!")
                st.rerun()
        
        with col3:
            if st.button("↩️ Reset Defaults", use_container_width=True):
                defaults = {
                    'newsletter_name': 'HYROX WEEKLY',
                    'tagline': 'Everything Hyrox, Every Week',
                    'intro_template': "Welcome! This week we've curated {content_summary} of the best Hyrox content.",
                    'cta_heading': 'Never Miss an Edition',
                    'cta_subtext': 'The best Hyrox content, delivered weekly direct to your inbox.',
                    'cta_button_text': 'Subscribe',
                    'cta_button_url': 'https://hyroxweekly.com',
                    'sponsor_enabled': 'true',
                    'sponsor_label': 'Presented by',
                    'sponsor_cta': 'Your brand here →',
                    'sponsor_email': 'sponsor@hyroxweekly.com',
                    'footer_instagram': 'https://instagram.com/hyroxweekly',
                    'footer_website': 'https://hyroxweekly.com',
                    'footer_contact_email': 'team@hyroxweekly.com',
                    'youtube_min_duration': '60',
                    'youtube_region': '',
                    'podcast_country': '',
                    'display_timezone': 'US/Pacific',
                    # Section titles
                    'section_title_race_recap': 'Race Recaps',
                    'section_title_training': 'Training & Workouts',
                    'section_title_nutrition': 'Nutrition & Recovery',
                    'section_title_athlete_profile': 'Athlete Spotlights',
                    'section_title_gear': 'Gear & Equipment',
                    'section_title_other': 'More Videos',
                    'section_title_podcasts': 'Worth a Listen',
                    'section_title_articles': 'Worth Reading',
                    'section_title_reddit': 'Community Discussions',
                    'section_title_athletes': '🏃 Athletes to Follow',
                }
                st.session_state['newsletter_config'] = defaults
                save_all_newsletter_settings(defaults)
                st.success("Settings reset to defaults!")
                st.rerun()
        
        # Preview current config
        with st.expander("📋 View Current Configuration"):
            st.json(config)


if __name__ == "__main__":
    main()
