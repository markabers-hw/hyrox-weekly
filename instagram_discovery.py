"""
Hyrox Weekly Instagram Discovery Script

Discovers Hyrox-related posts from Instagram using RapidAPI.
Stores as platform='instagram' for separate curation.
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

RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
RAPIDAPI_HOST = 'instagram-scraper.p.rapidapi.com'

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

# Hashtags to search for Hyrox content
HASHTAGS = [
    'hyrox',
    'hyroxtraining',
    'hyroxworkout',
    'hyroxathlete',
    'hyroxrace',
    'hyroxworld',
]

# Minimum engagement thresholds
MIN_LIKES = 50
MIN_COMMENTS = 5


class InstagramDiscovery:
    def __init__(self):
        if not RAPIDAPI_KEY:
            raise ValueError("RAPIDAPI_KEY not found in environment variables")
        
        self.headers = {
            'x-rapidapi-host': RAPIDAPI_HOST,
            'x-rapidapi-key': RAPIDAPI_KEY,
        }
        self.base_url = f'https://{RAPIDAPI_HOST}/api/v1'
    
    def fetch_hashtag_posts(self, hashtag, max_posts=50, retries=3):
        """Fetch posts for a given hashtag."""
        posts = []
        url = f"{self.base_url}/hashtag_medias"
        params = {'query': hashtag}
        
        for attempt in range(retries):
            try:
                print(f"      Fetching #{hashtag}... (attempt {attempt + 1})")
                response = requests.get(url, headers=self.headers, params=params, timeout=60)
                response.raise_for_status()
                data = response.json()
                
                # Debug: print response structure
                if attempt == 0:
                    print(f"      Response type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"      Keys: {list(data.keys())[:5]}")
                
                # Handle different response structures
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get('data', data.get('items', data.get('medias', [])))
                    if isinstance(items, dict):
                        items = items.get('items', [])
                
                for item in items[:max_posts]:
                    post = self._parse_post(item, hashtag)
                    if post:
                        posts.append(post)
                
                print(f"      Found {len(posts)} posts for #{hashtag}")
                return posts  # Success, exit retry loop
                
            except requests.exceptions.Timeout:
                print(f"      Timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    print(f"      Waiting 10 seconds before retry...")
                    time.sleep(10)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print(f"      Rate limited! Waiting 60 seconds...")
                    time.sleep(60)
                else:
                    print(f"      HTTP Error for #{hashtag}: {e.response.status_code} - {e}")
                    break
            except Exception as e:
                print(f"      Error fetching #{hashtag}: {e}")
                break
        
        return posts
    
    def _parse_post(self, item, hashtag):
        """Parse a post from the API response."""
        try:
            # Handle different API response formats
            post_id = item.get('id') or item.get('pk') or item.get('code')
            
            # Get media URL
            code = item.get('code') or item.get('shortcode')
            if not code:
                return None
            
            url = f"https://www.instagram.com/p/{code}/"
            
            # Get caption/description
            caption = ''
            caption_obj = item.get('caption')
            if isinstance(caption_obj, dict):
                caption = caption_obj.get('text', '')
            elif isinstance(caption_obj, str):
                caption = caption_obj
            
            # Get thumbnail
            thumbnail = ''
            if item.get('thumbnail_url'):
                thumbnail = item['thumbnail_url']
            elif item.get('image_versions2'):
                candidates = item['image_versions2'].get('candidates', [])
                if candidates:
                    thumbnail = candidates[0].get('url', '')
            elif item.get('display_url'):
                thumbnail = item['display_url']
            elif item.get('thumbnail_src'):
                thumbnail = item['thumbnail_src']
            
            # Get user info
            user = item.get('user', {}) or item.get('owner', {})
            username = user.get('username', 'unknown')
            user_id = user.get('pk') or user.get('id')
            full_name = user.get('full_name', username)
            follower_count = user.get('follower_count', 0)
            
            # Get engagement metrics
            like_count = item.get('like_count', 0) or item.get('likes', {}).get('count', 0)
            comment_count = item.get('comment_count', 0) or item.get('comments', {}).get('count', 0)
            view_count = item.get('view_count', 0) or item.get('video_view_count', 0)
            
            # Get timestamp
            taken_at = item.get('taken_at') or item.get('taken_at_timestamp')
            if taken_at:
                if isinstance(taken_at, (int, float)):
                    published_date = datetime.fromtimestamp(taken_at)
                else:
                    published_date = datetime.now()
            else:
                published_date = datetime.now()
            
            # Determine media type
            media_type = item.get('media_type', 1)
            is_video = media_type == 2 or item.get('is_video', False)
            
            return {
                'post_id': str(post_id),
                'code': code,
                'url': url,
                'caption': caption[:1000] if caption else '',
                'thumbnail_url': thumbnail,
                'username': username,
                'user_id': str(user_id) if user_id else '',
                'full_name': full_name,
                'follower_count': follower_count,
                'like_count': like_count,
                'comment_count': comment_count,
                'view_count': view_count if is_video else like_count,
                'published_date': published_date,
                'is_video': is_video,
                'hashtag': hashtag,
            }
            
        except Exception as e:
            print(f"      Error parsing post: {e}")
            return None


class InstagramDatabaseManager:
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
    
    def get_or_create_creator(self, post):
        """Get or create creator from Instagram username."""
        username = post['username']
        
        self.cursor.execute("SELECT id FROM creators WHERE platform_id = %s AND platform = 'instagram'", (username,))
        result = self.cursor.fetchone()
        if result: return result['id']
        
        cols = ['name', 'platform']
        vals = [post.get('full_name') or username, 'instagram']
        
        if 'platform_id' in self.creator_columns: 
            cols.append('platform_id')
            vals.append(username)
        if 'follower_count' in self.creator_columns: 
            cols.append('follower_count')
            vals.append(post.get('follower_count', 0))
        if 'profile_url' in self.creator_columns: 
            cols.append('profile_url')
            vals.append(f"https://www.instagram.com/{username}/")
        if 'credibility_score' in self.creator_columns: 
            cols.append('credibility_score')
            # Higher follower count = higher credibility
            followers = post.get('follower_count', 0)
            if followers > 100000:
                score = 0.9
            elif followers > 10000:
                score = 0.7
            else:
                score = 0.5
            vals.append(score)
        
        self.cursor.execute(
            f"INSERT INTO creators ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id", 
            vals
        )
        self.conn.commit()
        return self.cursor.fetchone()['id']
    
    def post_exists(self, url):
        self.cursor.execute("SELECT id FROM content_items WHERE url = %s", (url,))
        return self.cursor.fetchone() is not None
    
    def save_post(self, post, creator_id):
        cols = ['title', 'url', 'platform', 'creator_id', 'status']
        # Use first line of caption as title, or generate one
        caption = post.get('caption', '')
        title = caption.split('\n')[0][:100] if caption else f"Instagram post by @{post['username']}"
        vals = [title, post['url'], 'instagram', creator_id, 'discovered']
        
        if 'thumbnail_url' in self.content_columns: 
            cols.append('thumbnail_url')
            vals.append(post.get('thumbnail_url', ''))
        if 'description' in self.content_columns: 
            cols.append('description')
            vals.append(post.get('caption', '')[:500])
        if 'published_date' in self.content_columns: 
            cols.append('published_date')
            vals.append(post.get('published_date'))
        if 'view_count' in self.content_columns: 
            cols.append('view_count')
            vals.append(post.get('view_count', 0))
        if 'like_count' in self.content_columns: 
            cols.append('like_count')
            vals.append(post.get('like_count', 0))
        if 'comment_count' in self.content_columns: 
            cols.append('comment_count')
            vals.append(post.get('comment_count', 0))
        if 'category' in self.content_columns: 
            cols.append('category')
            vals.append('other')
        if 'platform_id' in self.content_columns:
            cols.append('platform_id')
            vals.append(post.get('post_id', ''))
        
        # Store hashtag source in editorial note
        if 'editorial_note' in self.content_columns: 
            cols.append('editorial_note')
            note = f"Hashtag: #{post.get('hashtag', 'hyrox')}"
            if post.get('is_video'):
                note += " | Type: Video/Reel"
            vals.append(note)
        
        self.cursor.execute(
            f"INSERT INTO content_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id", 
            vals
        )
        self.conn.commit()
        return self.cursor.fetchone()['id']


def test_api_connection():
    """Test the API connection with a simple request."""
    print("\n🔌 Testing API connection...")
    
    headers = {
        'x-rapidapi-host': RAPIDAPI_HOST,
        'x-rapidapi-key': RAPIDAPI_KEY,
    }
    
    # Try a simple user search first (usually faster)
    test_url = f"https://{RAPIDAPI_HOST}/api/v1/users"
    params = {'query': 'hyrox'}
    
    try:
        response = requests.get(test_url, headers=headers, params=params, timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Response type: {type(data)}")
            if isinstance(data, dict):
                print(f"   Keys: {list(data.keys())}")
            print("   ✅ API connection successful!")
            return True
        else:
            print(f"   ❌ API returned: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print("   ❌ Connection timed out")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    print("=" * 70)
    print("INSTAGRAM DISCOVERY - Hyrox Content")
    print("=" * 70)
    
    print(f"\n📅 Week: {WEEK_START.strftime('%Y-%m-%d')} to {WEEK_END.strftime('%Y-%m-%d')}")
    
    if not RAPIDAPI_KEY:
        print("\n❌ Error: RAPIDAPI_KEY not found in .env file")
        print("   Add: RAPIDAPI_KEY=your_key_here")
        return
    
    print(f"\n   API Key: {RAPIDAPI_KEY[:10]}...{RAPIDAPI_KEY[-4:]}")
    
    # Test API connection first
    if not test_api_connection():
        print("\n⚠️  API test failed. Check your API key and subscription.")
        print("   Make sure you've subscribed to the Instagram Scraper API on RapidAPI.")
        return
    
    discovery = InstagramDiscovery()
    db = InstagramDatabaseManager()
    all_posts = []
    
    print("\n📸 Fetching Instagram posts by hashtag...")
    
    for hashtag in HASHTAGS:
        posts = discovery.fetch_hashtag_posts(hashtag, max_posts=30)
        all_posts.extend(posts)
        time.sleep(3)  # Rate limiting between hashtags
    
    print(f"\n   Total: {len(all_posts)} posts fetched")
    
    # Deduplicate by URL
    seen = set()
    unique = [p for p in all_posts if p['url'] not in seen and not seen.add(p['url'])]
    print(f"   {len(unique)} unique posts")
    
    # Filter by engagement
    engaged = [p for p in unique if p.get('like_count', 0) >= MIN_LIKES or p.get('comment_count', 0) >= MIN_COMMENTS]
    print(f"   {len(engaged)} posts meet engagement threshold (>{MIN_LIKES} likes or >{MIN_COMMENTS} comments)")
    
    # Filter to selected week
    recent = [p for p in engaged if WEEK_START <= p.get('published_date', datetime.now()) <= WEEK_END]
    print(f"   {len(recent)} from selected week")
    
    # Sort by engagement (likes + comments)
    recent.sort(key=lambda x: x.get('like_count', 0) + x.get('comment_count', 0) * 2, reverse=True)
    
    print(f"\n💾 Saving {len(recent)} posts...")
    db.connect()
    
    saved, skipped = 0, 0
    for post in recent:
        if db.post_exists(post['url']):
            skipped += 1
            continue
        
        creator_id = db.get_or_create_creator(post)
        
        try:
            db.save_post(post, creator_id)
            saved += 1
            likes = post.get('like_count', 0)
            username = post.get('username', 'unknown')
            print(f"   ✅ Saved: [{likes:,} ❤️] @{username}: {post.get('caption', '')[:40]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    db.close()
    
    print("\n" + "=" * 70)
    print(f"Instagram discovery complete! Saved: {saved}, Skipped: {skipped}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
