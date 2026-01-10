"""
Hyrox Weekly Reddit Discovery Script

Discovers Hyrox-related posts from Reddit.
Stores as platform='reddit' for separate curation.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import requests
import time
from datetime import datetime, timedelta

load_dotenv()

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

# Subreddits to search
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


class RedditDiscovery:
    def __init__(self):
        self.headers = {'User-Agent': 'HyroxWeekly/1.0 (Content Aggregator)'}
    
    def fetch_subreddit(self, subreddit, limit=25, sort='new'):
        """Fetch posts from a subreddit using specified sort."""
        posts = []
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
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
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            'q': query,
            'restrict_sr': 'on',  # Restrict to subreddit
            'sort': sort,
            't': time_filter,  # all, hour, day, week, month, year
            'limit': limit
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
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


def main():
    print("=" * 70)
    print("REDDIT DISCOVERY - Hyrox Content")
    print("=" * 70)
    
    print(f"\n📅 Week: {WEEK_START.strftime('%Y-%m-%d')} to {WEEK_END.strftime('%Y-%m-%d')}")
    
    # Check if we're looking for historical posts (more than a few days ago)
    days_ago = (datetime.now() - WEEK_END).days
    is_historical = days_ago > 3
    
    if is_historical:
        print(f"   ⏳ Looking for posts from {days_ago} days ago - using search method")
    
    discovery = RedditDiscovery()
    db = RedditDatabaseManager()
    all_posts = []
    
    print("\n📥 Fetching Reddit posts...")
    
    # Method 1: Fetch recent posts from subreddits using 'new' sort
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
            print(f"   ⚠️  Reddit's API may not return posts older than ~2-3 weeks")
    
    # Sort by score (upvotes)
    recent.sort(key=lambda x: x.get('score', 0), reverse=True)
    
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
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
