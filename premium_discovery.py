"""
Hyrox Weekly - Premium Content Discovery
Discovers content for Athletes and Performance Topics
"""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import requests
import re
import feedparser
from urllib.parse import quote
from bs4 import BeautifulSoup

# Try to import Google News URL decoder
try:
    from googlenewsdecoder import new_decoderv1
    HAS_GNEWS_DECODER = True
except ImportError:
    HAS_GNEWS_DECODER = False

load_dotenv()

# Configuration
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

# Entity info passed from dashboard
ENTITY_TYPE = os.getenv('PREMIUM_ENTITY_TYPE')  # 'athlete' or 'topic'
ENTITY_ID = os.getenv('PREMIUM_ENTITY_ID')
PLATFORM = os.getenv('PREMIUM_PLATFORM')  # 'youtube', 'podcast', 'article', 'reddit', 'all'

# YouTube settings
YOUTUBE_MIN_DURATION = int(os.getenv('YOUTUBE_MIN_DURATION', '60'))  # seconds


class DatabaseManager:
    """Handle database connections and operations"""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        return self.conn.cursor(cursor_factory=RealDictCursor)

    def close(self):
        if self.conn:
            self.conn.close()

    def commit(self):
        if self.conn:
            self.conn.commit()

    def rollback(self):
        if self.conn:
            self.conn.rollback()


def decode_google_news_url(url):
    """Decode a Google News URL to get the actual article URL."""
    if not HAS_GNEWS_DECODER:
        return url
    if 'news.google.com' not in url:
        return url
    try:
        result = new_decoderv1(url)
        if result.get('status') and result.get('decoded_url'):
            return result['decoded_url']
    except Exception:
        pass
    return url


def extract_thumbnail(url):
    """Extract thumbnail from article page using og:image meta tag."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; HyroxWeekly/1.0)'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Try og:image first (most common)
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            img_url = og['content']
            # Skip Google placeholder images
            if 'lh3.googleusercontent.com' not in img_url:
                return img_url

        # Try twitter:image
        twitter = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter and twitter.get('content'):
            img_url = twitter['content']
            if 'lh3.googleusercontent.com' not in img_url:
                return img_url

        return None
    except Exception:
        return None


class AthleteDiscovery:
    """Discover content related to a specific athlete"""

    def __init__(self, athlete_id):
        self.athlete_id = athlete_id
        self.db = DatabaseManager()
        self.athlete = None
        self.search_terms = []
        self.youtube = None

    def load_athlete(self):
        """Load athlete from database"""
        cursor = self.db.connect()
        cursor.execute("""
            SELECT id, name, slug, instagram_handle, youtube_channel_id, search_terms
            FROM athletes WHERE id = %s
        """, (self.athlete_id,))
        self.athlete = cursor.fetchone()

        if not self.athlete:
            raise ValueError(f"Athlete {self.athlete_id} not found")

        # Build search terms
        self.search_terms = []

        # Use custom search terms if set
        if self.athlete.get('search_terms'):
            self.search_terms = list(self.athlete['search_terms'])
        else:
            # Default to name
            self.search_terms.append(self.athlete['name'])

            # Add Instagram handle without @
            if self.athlete.get('instagram_handle'):
                handle = self.athlete['instagram_handle'].lstrip('@')
                if handle not in self.search_terms:
                    self.search_terms.append(handle)

        print(f"🏃 Athlete: {self.athlete['name']}")
        print(f"🔍 Search terms: {self.search_terms}")

        return self.athlete

    def discover_youtube(self, max_results=20):
        """Search YouTube for videos related to the athlete"""
        if not self.youtube:
            self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

        print(f"\n▶️ Discovering YouTube videos...")

        all_videos = []
        video_ids_seen = set()

        # Search with each search term
        for term in self.search_terms[:3]:  # Limit to 3 terms to save API quota
            try:
                search_params = {
                    'q': f'{term} hyrox',
                    'type': 'video',
                    'part': 'id,snippet',
                    'maxResults': max_results,
                    'order': 'relevance',
                    'relevanceLanguage': 'en',
                }

                response = self.youtube.search().list(**search_params).execute()

                for item in response.get('items', []):
                    video_id = item['id']['videoId']
                    if video_id not in video_ids_seen:
                        video_ids_seen.add(video_id)
                        all_videos.append(item)

                print(f"   '{term} hyrox': {len(response.get('items', []))} videos")

            except HttpError as e:
                print(f"   ❌ Error searching '{term}': {e}")

        # Also fetch from athlete's YouTube channel if set
        if self.athlete.get('youtube_channel_id'):
            channel_id = self.athlete['youtube_channel_id']
            print(f"   📺 Fetching from athlete's channel: {channel_id}")

            try:
                response = self.youtube.search().list(
                    channelId=channel_id,
                    type='video',
                    part='id,snippet',
                    maxResults=20,
                    order='date'
                ).execute()

                for item in response.get('items', []):
                    video_id = item['id']['videoId']
                    if video_id not in video_ids_seen:
                        video_ids_seen.add(video_id)
                        all_videos.append(item)

                print(f"   Channel videos: {len(response.get('items', []))} videos")

            except HttpError as e:
                print(f"   ❌ Error fetching channel: {e}")

        # Get video statistics
        if all_videos:
            video_ids = [v['id']['videoId'] for v in all_videos]
            stats = self._get_video_stats(video_ids)

            # Merge stats into videos
            for video in all_videos:
                video_id = video['id']['videoId']
                video['stats'] = stats.get(video_id, {})

            # Filter out videos shorter than minimum duration
            if YOUTUBE_MIN_DURATION > 0:
                before_count = len(all_videos)
                all_videos = [
                    v for v in all_videos
                    if self._parse_duration(v.get('stats', {}).get('duration', 'PT0S')) >= YOUTUBE_MIN_DURATION
                ]
                filtered_count = before_count - len(all_videos)
                if filtered_count > 0:
                    print(f"   🔇 Filtered out {filtered_count} videos shorter than {YOUTUBE_MIN_DURATION}s")

        print(f"   ✅ Total unique videos: {len(all_videos)}")
        return all_videos

    def _get_video_stats(self, video_ids):
        """Get statistics for videos"""
        stats = {}
        try:
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                response = self.youtube.videos().list(
                    part='statistics,contentDetails',
                    id=','.join(batch)
                ).execute()

                for item in response.get('items', []):
                    vid = item['id']
                    stats[vid] = {
                        'view_count': int(item['statistics'].get('viewCount', 0)),
                        'like_count': int(item['statistics'].get('likeCount', 0)),
                        'comment_count': int(item['statistics'].get('commentCount', 0)),
                        'duration': item['contentDetails'].get('duration', 'PT0S'),
                    }
        except HttpError as e:
            print(f"   ⚠️ Error getting stats: {e}")
        return stats

    def _parse_duration(self, duration_str):
        """Convert ISO 8601 duration to seconds"""
        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds
        return 0

    def discover_podcasts(self, max_results=20):
        """Search iTunes for podcast episodes mentioning the athlete"""
        print(f"\n🎙️ Discovering podcasts...")

        all_episodes = []
        seen_urls = set()

        for term in self.search_terms[:2]:  # Limit terms
            try:
                # iTunes Search API
                search_url = f"https://itunes.apple.com/search?term={quote(term + ' hyrox')}&entity=podcastEpisode&limit={max_results}"
                resp = requests.get(search_url, timeout=15)

                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get('results', [])

                    for ep in results:
                        url = ep.get('episodeUrl') or ep.get('trackViewUrl')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_episodes.append({
                                'title': ep.get('trackName', ''),
                                'url': url,
                                'thumbnail_url': ep.get('artworkUrl160', '').replace('160x160', '600x600'),
                                'description': ep.get('description', ''),
                                'published_date': ep.get('releaseDate'),
                                'duration_seconds': ep.get('trackTimeMillis', 0) // 1000,
                                'creator_name': ep.get('collectionName', ''),
                            })

                    print(f"   '{term} hyrox': {len(results)} episodes")

            except Exception as e:
                print(f"   ❌ Error searching '{term}': {e}")

        print(f"   ✅ Total unique episodes: {len(all_episodes)}")
        return all_episodes

    def discover_articles(self, max_results=20):
        """Search Google News for articles about the athlete"""
        print(f"\n📰 Discovering articles...")

        all_articles = []
        seen_urls = set()

        for term in self.search_terms[:2]:
            try:
                # Google News RSS
                rss_url = f"https://news.google.com/rss/search?q={quote(term + ' hyrox')}&hl=en-US&gl=US&ceid=US:en"
                feed = feedparser.parse(rss_url)

                for entry in feed.entries[:max_results]:
                    url = entry.get('link', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)

                        # Extract source from <source> element
                        source = entry.get('source', {})
                        source_name = source.get('title', 'Unknown') if isinstance(source, dict) else 'Unknown'

                        # Decode Google News URL to get actual article URL
                        actual_url = decode_google_news_url(url)

                        # Extract thumbnail from actual article
                        thumbnail = None
                        if actual_url != url:
                            thumbnail = extract_thumbnail(actual_url)
                            print(f"      📷 Extracted thumbnail for: {entry.get('title', '')[:40]}...")

                        all_articles.append({
                            'title': entry.get('title', ''),
                            'url': actual_url,
                            'description': entry.get('summary', ''),
                            'published_date': entry.get('published'),
                            'creator_name': source_name,
                            'thumbnail_url': thumbnail,
                        })

                print(f"   '{term} hyrox': {len(feed.entries)} articles")

            except Exception as e:
                print(f"   ❌ Error searching '{term}': {e}")

        print(f"   ✅ Total unique articles: {len(all_articles)}")
        return all_articles

    def save_content(self, items, platform):
        """Save discovered content to database and link to athlete"""
        cursor = self.db.connect()
        saved_count = 0

        for item in items:
            try:
                # Check if content already exists
                url = item.get('url') or f"https://www.youtube.com/watch?v={item['id']['videoId']}" if platform == 'youtube' else item.get('url')

                cursor.execute("SELECT id FROM content_items WHERE url = %s", (url,))
                existing = cursor.fetchone()

                if existing:
                    content_id = existing['id']
                else:
                    # Get or create creator
                    creator_name = item.get('creator_name') or (item.get('snippet', {}).get('channelTitle') if platform == 'youtube' else 'Unknown')

                    cursor.execute("""
                        INSERT INTO creators (name, platform, platform_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (platform, platform_id) DO UPDATE SET name = EXCLUDED.name
                        RETURNING id
                    """, (creator_name, platform, creator_name))
                    creator_id = cursor.fetchone()['id']

                    # Build content data
                    if platform == 'youtube':
                        video_id = item['id']['videoId']
                        stats = item.get('stats', {})
                        content_data = {
                            'title': item['snippet']['title'],
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'description': item['snippet'].get('description', ''),
                            'thumbnail_url': item['snippet']['thumbnails'].get('high', {}).get('url'),
                            'published_date': item['snippet'].get('publishedAt'),
                            'view_count': stats.get('view_count', 0),
                            'like_count': stats.get('like_count', 0),
                            'comment_count': stats.get('comment_count', 0),
                            'duration_seconds': self._parse_duration(stats.get('duration', 'PT0S')),
                        }
                    else:
                        content_data = {
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'description': item.get('description', ''),
                            'thumbnail_url': item.get('thumbnail_url'),
                            'published_date': item.get('published_date'),
                            'duration_seconds': item.get('duration_seconds'),
                        }

                    # Insert content
                    cursor.execute("""
                        INSERT INTO content_items
                        (title, url, platform, creator_id, description, thumbnail_url,
                         published_date, view_count, like_count, comment_count, duration_seconds, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'discovered')
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                    """, (
                        content_data['title'],
                        content_data['url'],
                        platform,
                        creator_id,
                        content_data.get('description'),
                        content_data.get('thumbnail_url'),
                        content_data.get('published_date'),
                        content_data.get('view_count', 0),
                        content_data.get('like_count', 0),
                        content_data.get('comment_count', 0),
                        content_data.get('duration_seconds'),
                    ))

                    result = cursor.fetchone()
                    if not result:
                        continue
                    content_id = result['id']

                # Link to athlete (if not already linked)
                cursor.execute("""
                    INSERT INTO athlete_content (athlete_id, content_id, status, content_type)
                    VALUES (%s, %s, 'discovered', %s)
                    ON CONFLICT (athlete_id, content_id) DO NOTHING
                """, (self.athlete_id, content_id, platform))

                saved_count += 1

            except Exception as e:
                print(f"   ⚠️ Error saving item: {e}")
                self.db.rollback()
                cursor = self.db.connect()

        self.db.commit()
        return saved_count

    def run_discovery(self, platforms=None):
        """Run discovery for specified platforms"""
        if platforms is None:
            platforms = ['youtube', 'podcast', 'article']

        self.load_athlete()

        results = {'found': 0, 'saved': 0}

        for platform in platforms:
            if platform == 'youtube':
                items = self.discover_youtube()
            elif platform == 'podcast':
                items = self.discover_podcasts()
            elif platform == 'article':
                items = self.discover_articles()
            else:
                continue

            results['found'] += len(items)

            if items:
                saved = self.save_content(items, platform)
                results['saved'] += saved
                print(f"   💾 Saved {saved} {platform} items")

        self.db.close()

        print(f"\n✅ Discovery complete: {results['found']} found, {results['saved']} saved")
        return results


class TopicDiscovery:
    """Discover content related to a performance topic"""

    def __init__(self, topic_id):
        self.topic_id = topic_id
        self.db = DatabaseManager()
        self.topic = None
        self.search_terms = []
        self.youtube = None

    def load_topic(self):
        """Load topic from database"""
        cursor = self.db.connect()
        cursor.execute("""
            SELECT id, name, slug, category, search_terms
            FROM performance_topics WHERE id = %s
        """, (self.topic_id,))
        self.topic = cursor.fetchone()

        if not self.topic:
            raise ValueError(f"Topic {self.topic_id} not found")

        # Build search terms
        if self.topic.get('search_terms'):
            self.search_terms = list(self.topic['search_terms'])
        else:
            # Default: topic name + hyrox
            self.search_terms = [f"hyrox {self.topic['name'].lower()}"]

        print(f"📈 Topic: {self.topic['name']}")
        print(f"🔍 Search terms: {self.search_terms}")

        return self.topic

    def discover_youtube(self, max_results=20):
        """Search YouTube for videos related to the topic"""
        if not self.youtube:
            self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

        print(f"\n▶️ Discovering YouTube videos...")

        all_videos = []
        video_ids_seen = set()

        for term in self.search_terms[:3]:
            try:
                response = self.youtube.search().list(
                    q=term,
                    type='video',
                    part='id,snippet',
                    maxResults=max_results,
                    order='relevance',
                    relevanceLanguage='en',
                ).execute()

                for item in response.get('items', []):
                    video_id = item['id']['videoId']
                    if video_id not in video_ids_seen:
                        video_ids_seen.add(video_id)
                        all_videos.append(item)

                print(f"   '{term}': {len(response.get('items', []))} videos")

            except HttpError as e:
                print(f"   ❌ Error: {e}")

        # Get stats
        if all_videos:
            video_ids = [v['id']['videoId'] for v in all_videos]
            stats = self._get_video_stats(video_ids)
            for video in all_videos:
                video['stats'] = stats.get(video['id']['videoId'], {})

            # Filter out videos shorter than minimum duration
            if YOUTUBE_MIN_DURATION > 0:
                before_count = len(all_videos)
                all_videos = [
                    v for v in all_videos
                    if self._parse_duration(v.get('stats', {}).get('duration', 'PT0S')) >= YOUTUBE_MIN_DURATION
                ]
                filtered_count = before_count - len(all_videos)
                if filtered_count > 0:
                    print(f"   🔇 Filtered out {filtered_count} videos shorter than {YOUTUBE_MIN_DURATION}s")

        print(f"   ✅ Total: {len(all_videos)} videos")
        return all_videos

    def _get_video_stats(self, video_ids):
        """Get video statistics"""
        stats = {}
        try:
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                response = self.youtube.videos().list(
                    part='statistics,contentDetails',
                    id=','.join(batch)
                ).execute()

                for item in response.get('items', []):
                    vid = item['id']
                    stats[vid] = {
                        'view_count': int(item['statistics'].get('viewCount', 0)),
                        'like_count': int(item['statistics'].get('likeCount', 0)),
                        'comment_count': int(item['statistics'].get('commentCount', 0)),
                        'duration': item['contentDetails'].get('duration', 'PT0S'),
                    }
        except HttpError as e:
            print(f"   ⚠️ Error: {e}")
        return stats

    def _parse_duration(self, duration_str):
        """Convert ISO 8601 duration to seconds"""
        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds
        return 0

    def discover_podcasts(self, max_results=20):
        """Search for podcast episodes about the topic"""
        print(f"\n🎙️ Discovering podcasts...")

        all_episodes = []
        seen_urls = set()

        for term in self.search_terms[:2]:
            try:
                search_url = f"https://itunes.apple.com/search?term={quote(term)}&entity=podcastEpisode&limit={max_results}"
                resp = requests.get(search_url, timeout=15)

                if resp.status_code == 200:
                    for ep in resp.json().get('results', []):
                        url = ep.get('episodeUrl') or ep.get('trackViewUrl')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_episodes.append({
                                'title': ep.get('trackName', ''),
                                'url': url,
                                'thumbnail_url': ep.get('artworkUrl160', '').replace('160x160', '600x600'),
                                'description': ep.get('description', ''),
                                'published_date': ep.get('releaseDate'),
                                'duration_seconds': ep.get('trackTimeMillis', 0) // 1000,
                                'creator_name': ep.get('collectionName', ''),
                            })

                    print(f"   '{term}': {len(resp.json().get('results', []))} episodes")

            except Exception as e:
                print(f"   ❌ Error: {e}")

        print(f"   ✅ Total: {len(all_episodes)} episodes")
        return all_episodes

    def discover_articles(self, max_results=20):
        """Search for articles about the topic"""
        print(f"\n📰 Discovering articles...")

        all_articles = []
        seen_urls = set()

        for term in self.search_terms[:2]:
            try:
                rss_url = f"https://news.google.com/rss/search?q={quote(term)}&hl=en-US&gl=US&ceid=US:en"
                feed = feedparser.parse(rss_url)

                for entry in feed.entries[:max_results]:
                    url = entry.get('link', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        source = entry.get('source', {})
                        source_name = source.get('title', 'Unknown') if isinstance(source, dict) else 'Unknown'

                        # Decode Google News URL to get actual article URL
                        actual_url = decode_google_news_url(url)

                        # Extract thumbnail from actual article
                        thumbnail = None
                        if actual_url != url:
                            thumbnail = extract_thumbnail(actual_url)
                            print(f"      📷 Extracted thumbnail for: {entry.get('title', '')[:40]}...")

                        all_articles.append({
                            'title': entry.get('title', ''),
                            'url': actual_url,
                            'description': entry.get('summary', ''),
                            'published_date': entry.get('published'),
                            'creator_name': source_name,
                            'thumbnail_url': thumbnail,
                        })

                print(f"   '{term}': {len(feed.entries)} articles")

            except Exception as e:
                print(f"   ❌ Error: {e}")

        print(f"   ✅ Total: {len(all_articles)} articles")
        return all_articles

    def discover_reddit(self, max_results=30):
        """Search Reddit for discussions about the topic"""
        print(f"\n💬 Discovering Reddit posts...")

        all_posts = []
        seen_urls = set()

        # Search r/hyrox and general fitness subreddits
        subreddits = ['hyrox', 'fitness', 'crossfit']

        for term in self.search_terms[:2]:
            for subreddit in subreddits:
                try:
                    # Reddit search JSON endpoint
                    url = f"https://www.reddit.com/r/{subreddit}/search.json?q={quote(term)}&restrict_sr=1&sort=relevance&limit={max_results}"
                    headers = {'User-Agent': 'HyroxWeekly/1.0'}
                    resp = requests.get(url, headers=headers, timeout=15)

                    if resp.status_code == 200:
                        data = resp.json()
                        posts = data.get('data', {}).get('children', [])

                        for post in posts:
                            post_data = post.get('data', {})
                            post_url = f"https://reddit.com{post_data.get('permalink', '')}"

                            if post_url and post_url not in seen_urls:
                                seen_urls.add(post_url)
                                all_posts.append({
                                    'title': post_data.get('title', ''),
                                    'url': post_url,
                                    'description': post_data.get('selftext', '')[:500],
                                    'published_date': datetime.fromtimestamp(post_data.get('created_utc', 0)).isoformat(),
                                    'creator_name': f"r/{subreddit}",
                                    'view_count': post_data.get('score', 0),
                                    'comment_count': post_data.get('num_comments', 0),
                                })

                except Exception as e:
                    print(f"   ⚠️ Error searching r/{subreddit}: {e}")

        print(f"   ✅ Total: {len(all_posts)} posts")
        return all_posts

    def save_content(self, items, platform):
        """Save content and link to topic"""
        cursor = self.db.connect()
        saved_count = 0

        for item in items:
            try:
                url = item.get('url') or f"https://www.youtube.com/watch?v={item['id']['videoId']}" if platform == 'youtube' else item.get('url')

                cursor.execute("SELECT id FROM content_items WHERE url = %s", (url,))
                existing = cursor.fetchone()

                if existing:
                    content_id = existing['id']
                else:
                    # Get or create creator
                    creator_name = item.get('creator_name') or (item.get('snippet', {}).get('channelTitle') if platform == 'youtube' else 'Unknown')

                    cursor.execute("""
                        INSERT INTO creators (name, platform, platform_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (platform, platform_id) DO UPDATE SET name = EXCLUDED.name
                        RETURNING id
                    """, (creator_name, platform, creator_name))
                    creator_id = cursor.fetchone()['id']

                    # Build content data
                    if platform == 'youtube':
                        video_id = item['id']['videoId']
                        stats = item.get('stats', {})
                        content_data = {
                            'title': item['snippet']['title'],
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'description': item['snippet'].get('description', ''),
                            'thumbnail_url': item['snippet']['thumbnails'].get('high', {}).get('url'),
                            'published_date': item['snippet'].get('publishedAt'),
                            'view_count': stats.get('view_count', 0),
                            'like_count': stats.get('like_count', 0),
                            'comment_count': stats.get('comment_count', 0),
                            'duration_seconds': self._parse_duration(stats.get('duration', 'PT0S')),
                        }
                    else:
                        content_data = {
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'description': item.get('description', ''),
                            'thumbnail_url': item.get('thumbnail_url'),
                            'published_date': item.get('published_date'),
                            'duration_seconds': item.get('duration_seconds'),
                            'view_count': item.get('view_count', 0),
                            'comment_count': item.get('comment_count', 0),
                        }

                    # Insert content
                    cursor.execute("""
                        INSERT INTO content_items
                        (title, url, platform, creator_id, description, thumbnail_url,
                         published_date, view_count, like_count, comment_count, duration_seconds, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'discovered')
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                    """, (
                        content_data['title'],
                        content_data['url'],
                        platform,
                        creator_id,
                        content_data.get('description'),
                        content_data.get('thumbnail_url'),
                        content_data.get('published_date'),
                        content_data.get('view_count', 0),
                        content_data.get('like_count', 0),
                        content_data.get('comment_count', 0),
                        content_data.get('duration_seconds'),
                    ))

                    result = cursor.fetchone()
                    if not result:
                        continue
                    content_id = result['id']

                # Link to topic
                cursor.execute("""
                    INSERT INTO performance_content (topic_id, content_id, status)
                    VALUES (%s, %s, 'discovered')
                    ON CONFLICT (topic_id, content_id) DO NOTHING
                """, (self.topic_id, content_id))

                saved_count += 1

            except Exception as e:
                print(f"   ⚠️ Error: {e}")
                self.db.rollback()
                cursor = self.db.connect()

        self.db.commit()
        return saved_count

    def run_discovery(self, platforms=None):
        """Run discovery for specified platforms"""
        if platforms is None:
            platforms = ['youtube', 'podcast', 'article', 'reddit']

        self.load_topic()

        results = {'found': 0, 'saved': 0}

        for platform in platforms:
            if platform == 'youtube':
                items = self.discover_youtube()
            elif platform == 'podcast':
                items = self.discover_podcasts()
            elif platform == 'article':
                items = self.discover_articles()
            elif platform == 'reddit':
                items = self.discover_reddit()
            else:
                continue

            results['found'] += len(items)

            if items:
                saved = self.save_content(items, platform)
                results['saved'] += saved
                print(f"   💾 Saved {saved} {platform} items")

        self.db.close()

        print(f"\n✅ Discovery complete: {results['found']} found, {results['saved']} saved")
        return results


def main():
    """Main entry point - run from command line or dashboard"""
    if not ENTITY_TYPE or not ENTITY_ID:
        print("❌ Missing PREMIUM_ENTITY_TYPE or PREMIUM_ENTITY_ID environment variables")
        return

    entity_id = int(ENTITY_ID)
    platforms = [PLATFORM] if PLATFORM and PLATFORM != 'all' else None

    if ENTITY_TYPE == 'athlete':
        discovery = AthleteDiscovery(entity_id)
        results = discovery.run_discovery(platforms)
    elif ENTITY_TYPE == 'topic':
        discovery = TopicDiscovery(entity_id)
        results = discovery.run_discovery(platforms)
    else:
        print(f"❌ Unknown entity type: {ENTITY_TYPE}")
        return

    # Output for dashboard parsing
    print(f"\n[DISCOVERY_RESULTS]")
    print(f"found={results['found']}")
    print(f"saved={results['saved']}")


if __name__ == '__main__':
    main()
