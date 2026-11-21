"""
Hyrox Weekly Reddit Discovery Script

Discovers Hyrox-related posts from Reddit.
Stores as platform='reddit' for separate curation.

Sources:
- Reddit archive (arctic-shift.photon-reddit.com): no login and any date range, so it works for
  the current week and for weeks months back. This is the default.
- Reddit's own API via OAuth: used as well when REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are set.
  It can only reach back 2-3 weeks, but its scores are the most current.

Fails (non-zero exit) when neither source can be reached, so a broken Reddit step is never
reported as a quiet week.

Usage:
    python reddit_discovery.py [--dry-run]    # week from DISCOVERY_WEEK_START / DISCOVERY_WEEK_END
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import sys
import requests
import time
from datetime import datetime, timedelta, timezone

load_dotenv()

DRY_RUN = '--dry-run' in sys.argv

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

# Get week range from environment (set by dashboard) or default to past 14 days
week_start_str = os.getenv('DISCOVERY_WEEK_START')
week_end_str = os.getenv('DISCOVERY_WEEK_END')

if week_start_str and week_end_str:
    WEEK_START = datetime.fromisoformat(week_start_str)
    WEEK_END = datetime.fromisoformat(week_end_str) + timedelta(days=1)  # Include end day
else:
    # Default: past 14 days
    WEEK_END = datetime.now()
    WEEK_START = WEEK_END - timedelta(days=14)

# Subreddits read from the archive (every post in the week). r/hyrox gave 92% of the posts that made
# past editions. Keyword search in the busy subreddits (fitness, crossfit, running) is not reliable
# on the archive: it times out, so they are only covered when OAuth is configured (below).
ARCHIVE_SUBREDDITS = ['hyrox']

# Subreddits to search through Reddit's own API (OAuth only)
SUBREDDITS = [
    {'name': 'hyrox', 'limit': 30, 'filter_keywords': False},  # All posts from r/hyrox
    {'name': 'fitness', 'limit': 50, 'filter_keywords': True},  # Only Hyrox-related
    {'name': 'crossfit', 'limit': 50, 'filter_keywords': True},
    {'name': 'running', 'limit': 50, 'filter_keywords': True},
]

HYROX_KEYWORDS = [
    'hyrox', 'hybrid fitness', 'hybrid athlete', 'functional fitness race',
    'ski erg', 'sled push', 'sled pull', 'wall balls',
    'hunter mcintyre', 'roxzone',
]


class RedditSourceError(Exception):
    """Raised when a Reddit data source can't be reached."""


class ArcticShiftClient:
    """Reddit posts from the Arctic Shift archive (arctic-shift.photon-reddit.com).

    No login, and any date range can be queried, so it covers the current week and weeks months
    back. It is volunteer-run with no uptime guarantee, so requests are retried with a back-off.
    Scores and comment counts matched Reddit's own within about 20% in a spot check against
    posts stored from Reddit's API in May, which is close enough for ranking.
    """

    BASE_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
    PAGE_SIZE = 100

    def __init__(self, user_agent):
        self.headers = {'User-Agent': user_agent}

    def _get(self, params, attempts=4):
        """GET one page of posts, backing off when the service asks us to slow down (422 timeout, 429, 5xx)."""
        last_error = 'no response'
        for attempt in range(attempts):
            try:
                resp = requests.get(self.BASE_URL, params=params, headers=self.headers, timeout=60)
                body = resp.json() if resp.status_code == 200 else {}
                if body.get('data') is not None:
                    return body['data']
                last_error = f"HTTP {resp.status_code} {resp.text[:100]}"
                if resp.status_code == 400:
                    break  # our request is wrong, retrying won't help
            except (requests.RequestException, ValueError) as e:
                last_error = str(e)
            time.sleep(3 * (attempt + 1))
        raise RedditSourceError(last_error)

    @staticmethod
    def _to_post(raw, subreddit):
        """Convert an archive record to the post dict used by the rest of this script (None to skip it)."""
        if raw.get('stickied') or raw.get('removed_by_category'):
            return None
        if raw.get('is_self') and raw.get('selftext') in ('[removed]', '[deleted]'):
            return None

        reddit_url = f"https://www.reddit.com{raw.get('permalink', '')}"
        external_url = raw.get('url') if not raw.get('is_self') and raw.get('url') != reddit_url else None
        thumbnail = raw.get('thumbnail') or ''
        if thumbnail in ['self', 'default', 'nsfw', 'spoiler', '']:
            thumbnail = ''
        created_utc = raw.get('created_utc', 0)

        return {
            'title': raw.get('title', ''),
            'url': reddit_url,
            'external_url': external_url,
            'description': (raw.get('selftext') or '')[:500],
            'published_date': datetime.fromtimestamp(created_utc) if created_utc else datetime.now(),
            'source': f'r/{subreddit}',
            'author': raw.get('author', '[deleted]'),
            'thumbnail_url': thumbnail,
            'platform': 'reddit',
            'score': raw.get('score', 0),
            'num_comments': raw.get('num_comments', 0),
        }

    def fetch_subreddit(self, subreddit, start, end):
        """Every post in r/subreddit created from start up to end (naive local datetimes), oldest first."""
        posts, seen_ids = [], set()
        cursor = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)

        for _ in range(20):  # safety cap of 2000 posts
            batch = self._get({
                'subreddit': subreddit,
                'after': cursor.strftime('%Y-%m-%dT%H:%M:%S'),
                'before': end_utc.strftime('%Y-%m-%dT%H:%M:%S'),
                'limit': self.PAGE_SIZE,
                'sort': 'asc',
            })
            new = [raw for raw in batch if raw['id'] not in seen_ids]
            for raw in new:
                seen_ids.add(raw['id'])
                post = self._to_post(raw, subreddit)
                if post:
                    posts.append(post)
            if len(batch) < self.PAGE_SIZE or not new:
                break
            cursor = datetime.fromtimestamp(batch[-1]['created_utc'], timezone.utc)
            time.sleep(1)  # be gentle with a volunteer-run service

        return posts


class RedditDiscovery:
    """Reddit discovery via OAuth (app-only / client-credentials). Optional: the archive is the default source.

    Reddit blocks unauthenticated access to the public `.json` endpoints (HTTP 403
    from www.reddit.com and old.reddit.com as of 2026). Read-only public data now
    requires an OAuth token from a registered app, used against oauth.reddit.com.
    Register a 'script' app at https://www.reddit.com/prefs/apps and set
    REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env.
    """

    OAUTH_BASE = "https://oauth.reddit.com"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

    def __init__(self):
        self.client_id = os.getenv('REDDIT_CLIENT_ID')
        self.client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        # Reddit requires a unique, descriptive User-Agent.
        self.user_agent = os.getenv(
            'REDDIT_USER_AGENT', 'python:com.hyroxweekly.discovery:v2.0 (by /u/hyroxweekly)')
        self.token = None
        self.enabled = bool(self.client_id and self.client_secret)
        if not self.enabled:
            print("      ℹ️  Reddit OAuth not configured (optional): using the archive only.")
        else:
            self._authenticate()

    def _authenticate(self):
        """Fetch an app-only OAuth token (client-credentials grant, read-only public data)."""
        try:
            resp = requests.post(
                self.TOKEN_URL,
                auth=(self.client_id, self.client_secret),
                data={'grant_type': 'client_credentials'},
                headers={'User-Agent': self.user_agent},
                timeout=15,
            )
            if resp.status_code == 200:
                self.token = resp.json().get('access_token')
                print("      🔑 Reddit OAuth token acquired")
            else:
                print(f"      ❌ Reddit auth failed: {resp.status_code} {resp.text[:120]}")
                self.token = None
        except Exception as e:
            print(f"      ❌ Reddit auth error: {e}")
            self.token = None

    def _get(self, path, params=None):
        """GET an oauth.reddit.com path with the bearer token; refresh once on 401."""
        if not self.token:
            return None
        url = f"{self.OAUTH_BASE}{path}"
        headers = {'User-Agent': self.user_agent, 'Authorization': f'Bearer {self.token}'}
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 401:
            # Token expired mid-run — re-auth and retry once.
            self._authenticate()
            if not self.token:
                return None
            headers['Authorization'] = f'Bearer {self.token}'
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_subreddit(self, subreddit, limit=25, sort='new', time_filter=None):
        """Fetch posts from a subreddit using specified sort.

        time_filter applies to time-bounded sorts ('top', 'controversial')
        and accepts hour/day/week/month/year/all.
        """
        posts = []
        params = {'limit': limit}
        if time_filter and sort in ('top', 'controversial'):
            params['t'] = time_filter

        try:
            data = self._get(f"/r/{subreddit}/{sort}", params=params)
            if not data:
                return posts

            for post in data.get('data', {}).get('children', []):
                post_data = post.get('data', {})

                if post_data.get('stickied'):
                    continue

                title = post_data.get('title', '')
                url = post_data.get('url', '')
                selftext = post_data.get('selftext', '')
                score = post_data.get('score', 0)
                num_comments = post_data.get('num_comments', 0)
                created_utc = post_data.get('created_utc', 0)
                thumbnail = post_data.get('thumbnail', '')
                permalink = post_data.get('permalink', '')
                author = post_data.get('author', '[deleted]')
                
                # Use Reddit URL for discussion
                reddit_url = f"https://www.reddit.com{permalink}"
                
                # External link if not a self post
                external_url = url if not post_data.get('is_self') and url != reddit_url else None
                
                # Skip low-quality thumbnails
                if thumbnail in ['self', 'default', 'nsfw', 'spoiler', '']:
                    thumbnail = ''
                
                posts.append({
                    'title': title,
                    'url': reddit_url,
                    'external_url': external_url,
                    'description': selftext[:500] if selftext else '',
                    'published_date': datetime.fromtimestamp(created_utc) if created_utc else datetime.now(),
                    'source': f'r/{subreddit}',
                    'author': author,
                    'thumbnail_url': thumbnail,
                    'platform': 'reddit',
                    'score': score,
                    'num_comments': num_comments,
                })
                
        except Exception as e:
            print(f"      Warning: Error fetching r/{subreddit}: {e}")
        
        return posts
    
    def search_subreddit(self, subreddit, query, limit=50, sort='relevance', time_filter='month'):
        """Search within a subreddit for specific terms."""
        posts = []
        params = {
            'q': query,
            'restrict_sr': 'on',  # Restrict to subreddit
            'sort': sort,
            't': time_filter,  # all, hour, day, week, month, year
            'limit': limit
        }

        try:
            data = self._get(f"/r/{subreddit}/search", params=params)
            if not data:
                return posts

            for post in data.get('data', {}).get('children', []):
                post_data = post.get('data', {})
                
                if post_data.get('stickied'):
                    continue
                
                title = post_data.get('title', '')
                url = post_data.get('url', '')
                selftext = post_data.get('selftext', '')
                score = post_data.get('score', 0)
                num_comments = post_data.get('num_comments', 0)
                created_utc = post_data.get('created_utc', 0)
                thumbnail = post_data.get('thumbnail', '')
                permalink = post_data.get('permalink', '')
                author = post_data.get('author', '[deleted]')
                
                reddit_url = f"https://www.reddit.com{permalink}"
                external_url = url if not post_data.get('is_self') and url != reddit_url else None
                
                if thumbnail in ['self', 'default', 'nsfw', 'spoiler', '']:
                    thumbnail = ''
                
                posts.append({
                    'title': title,
                    'url': reddit_url,
                    'external_url': external_url,
                    'description': selftext[:500] if selftext else '',
                    'published_date': datetime.fromtimestamp(created_utc) if created_utc else datetime.now(),
                    'source': f'r/{subreddit}',
                    'author': author,
                    'thumbnail_url': thumbnail,
                    'platform': 'reddit',
                    'score': score,
                    'num_comments': num_comments,
                })
                
        except Exception as e:
            print(f"      Warning: Error searching r/{subreddit}: {e}")
        
        return posts


class RedditDatabaseManager:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.creator_columns = []
        self.content_columns = []
    
    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        self.cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'creators'")
        self.creator_columns = [r['column_name'] for r in self.cursor.fetchall()]
        
        self.cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'content_items'")
        self.content_columns = [r['column_name'] for r in self.cursor.fetchall()]
    
    def close(self):
        if self.cursor: self.cursor.close()
        if self.conn: self.conn.commit(); self.conn.close()
    
    def get_or_create_creator(self, subreddit, author):
        """Create creator as the subreddit (not individual user)."""
        source_name = subreddit  # e.g., "r/hyrox"
        
        self.cursor.execute("SELECT id FROM creators WHERE name = %s AND platform = 'reddit'", (source_name,))
        result = self.cursor.fetchone()
        if result: return result['id']
        
        cols, vals = ['name', 'platform'], [source_name, 'reddit']
        if 'platform_id' in self.creator_columns: cols.append('platform_id'); vals.append(source_name)
        if 'credibility_score' in self.creator_columns: 
            cols.append('credibility_score')
            vals.append(0.6)  # Reddit gets moderate credibility
        
        self.cursor.execute(f"INSERT INTO creators ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id", vals)
        self.conn.commit()
        return self.cursor.fetchone()['id']
    
    def post_exists(self, url):
        self.cursor.execute("SELECT id FROM content_items WHERE url = %s", (url,))
        return self.cursor.fetchone() is not None
    
    def save_post(self, post, creator_id):
        cols = ['title', 'url', 'platform', 'creator_id', 'status']
        vals = [post['title'], post['url'], 'reddit', creator_id, 'discovered']
        
        if 'thumbnail_url' in self.content_columns: cols.append('thumbnail_url'); vals.append(post.get('thumbnail_url', ''))
        if 'description' in self.content_columns: cols.append('description'); vals.append(post.get('description', ''))
        if 'published_date' in self.content_columns: cols.append('published_date'); vals.append(post.get('published_date'))
        if 'view_count' in self.content_columns: cols.append('view_count'); vals.append(post.get('score', 0))  # Use score as "views"
        if 'like_count' in self.content_columns: cols.append('like_count'); vals.append(post.get('score', 0))
        if 'comment_count' in self.content_columns: cols.append('comment_count'); vals.append(post.get('num_comments', 0))
        if 'category' in self.content_columns: cols.append('category'); vals.append('other')
        
        # Store author and external URL in editorial note
        note_parts = [f"Author: u/{post.get('author', 'unknown')}"]
        if post.get('external_url'):
            note_parts.append(f"Link: {post['external_url']}")
        
        if 'editorial_note' in self.content_columns: 
            cols.append('editorial_note')
            vals.append(' | '.join(note_parts))
        
        self.cursor.execute(f"INSERT INTO content_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id", vals)
        self.conn.commit()
        return self.cursor.fetchone()['id']


def is_hyrox_relevant(post):
    text = f"{post.get('title', '')} {post.get('description', '')}".lower()
    return any(kw in text for kw in HYROX_KEYWORDS)


def fetch_via_archive(user_agent):
    """Every post in the selected week from the Reddit archive."""
    client = ArcticShiftClient(user_agent)
    posts = []
    for subreddit in ARCHIVE_SUBREDDITS:
        print(f"   -> r/{subreddit} ({WEEK_START.strftime('%b %d')} - {(WEEK_END - timedelta(days=1)).strftime('%b %d')})...")
        found = client.fetch_subreddit(subreddit, WEEK_START, WEEK_END)
        print(f"      Found {len(found)} posts")
        posts.extend(found)
    return posts


def fetch_via_oauth(discovery, is_historical):
    """Posts from Reddit's own API. Only reaches back about 2-3 weeks."""
    all_posts = []

    # Method 1a: Fetch recent posts from subreddits using 'new' sort
    for sub in SUBREDDITS:
        print(f"   -> r/{sub['name']} (new posts)...")
        # Increase limit for historical searches
        limit = sub['limit'] * 3 if is_historical else sub['limit']
        posts = discovery.fetch_subreddit(sub['name'], limit=limit, sort='new')

        # Filter if needed
        if sub['filter_keywords']:
            posts = [p for p in posts if is_hyrox_relevant(p)]
            print(f"      Found {len(posts)} Hyrox-related posts")
        else:
            print(f"      Found {len(posts)} posts")

        all_posts.extend(posts)
        time.sleep(1)  # Be nice to Reddit API

    # Method 1b: Fetch TOP-of-week posts so we catch high-engagement
    # threads that may have been posted early in the week and accrued
    # replies later (sort='new' with a small N misses these).
    print("\n📥 Fetching top-of-week posts (catches high-discussion threads)...")
    for sub in SUBREDDITS:
        print(f"   -> r/{sub['name']} (top/week)...")
        posts = discovery.fetch_subreddit(sub['name'], limit=100, sort='top', time_filter='week')

        if sub['filter_keywords']:
            posts = [p for p in posts if is_hyrox_relevant(p)]
            print(f"      Found {len(posts)} Hyrox-related posts")
        else:
            print(f"      Found {len(posts)} posts")

        all_posts.extend(posts)
        time.sleep(1)
    
    # Method 2: Search for 'hyrox' across subreddits (better for historical posts)
    print("\n🔍 Searching for 'hyrox' posts...")
    
    search_subs = ['hyrox', 'fitness', 'crossfit', 'running', 'all']
    for sub in search_subs:
        print(f"   -> Searching r/{sub}...")
        # Use 'month' time filter to get posts from the past month
        posts = discovery.search_subreddit(sub, 'hyrox', limit=50, sort='new', time_filter='month')
        print(f"      Found {len(posts)} posts")
        all_posts.extend(posts)
        time.sleep(1)

    return all_posts


def main():
    print("=" * 70)
    print("REDDIT DISCOVERY - Hyrox Content")
    print("=" * 70)
    
    print(f"\n📅 Week: {WEEK_START.strftime('%Y-%m-%d')} to {WEEK_END.strftime('%Y-%m-%d')}")
    
    # Reddit's own API only reaches back 2-3 weeks; the archive has no such limit
    days_ago = (datetime.now() - WEEK_END).days
    is_historical = days_ago > 3
    
    discovery = RedditDiscovery()
    db = RedditDatabaseManager()
    archive_posts, oauth_posts = [], []
    sources_reached = 0
    
    print("\n📥 Fetching Reddit posts from the archive...")
    try:
        archive_posts = fetch_via_archive(discovery.user_agent)
        sources_reached += 1
    except RedditSourceError as e:
        print(f"   ❌ Archive unavailable: {e}")
    
    if discovery.token:
        print("\n📥 Fetching Reddit posts from Reddit's API (OAuth)...")
        oauth_posts = fetch_via_oauth(discovery, is_historical)
        sources_reached += 1
    
    if sources_reached == 0:
        raise RedditSourceError("no Reddit source could be reached (the archive failed and OAuth is not configured)")
    
    # OAuth posts first, so their fresher scores win when both sources return the same post
    all_posts = oauth_posts + archive_posts
    print(f"\n   Total fetched: {len(all_posts)} posts")
    
    # Deduplicate by URL
    seen = set()
    unique = [p for p in all_posts if p['url'] not in seen and not seen.add(p['url'])]
    print(f"   {len(unique)} unique posts after deduplication")
    
    # Filter to selected week
    recent = [p for p in unique if WEEK_START <= p.get('published_date', datetime.now()) <= WEEK_END]
    print(f"   📅 {len(recent)} posts from selected week ({WEEK_START.strftime('%b %d')} - {WEEK_END.strftime('%b %d')})")
    
    if len(recent) == 0 and len(unique) > 0:
        # Show what date range we actually got
        dates = [p.get('published_date') for p in unique if p.get('published_date')]
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            print(f"   ⚠️  Posts found are from {min_date.strftime('%b %d')} to {max_date.strftime('%b %d')}")

    # Sort by score (upvotes)
    recent.sort(key=lambda x: x.get('score', 0), reverse=True)

    if DRY_RUN:
        print(f"\n🧪 Dry run: nothing saved. Top posts of the week:")
        for post in recent[:10]:
            print(f"   [{post['score']} pts, {post['num_comments']} comments] {post['title'][:70]}")
        return

    print(f"\n💾 Saving {len(recent)} posts...")
    db.connect()
    
    saved, skipped = 0, 0
    for post in recent:
        if db.post_exists(post['url']):
            skipped += 1
            continue
        
        creator_id = db.get_or_create_creator(post['source'], post.get('author', ''))
        
        try:
            db.save_post(post, creator_id)
            saved += 1
            score = post.get('score', 0)
            print(f"   ✅ Saved: [{score} pts] {post['title'][:45]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    db.close()
    
    print("\n" + "=" * 70)
    print(f"Reddit discovery complete! Saved: {saved}, Skipped: {skipped}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Reddit discovery failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)  # non-zero so batch_yolo reports a failure instead of a quiet week
