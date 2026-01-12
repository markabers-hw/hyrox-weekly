"""
Hyrox Weekly Podcast Discovery Script

This script:
1. Searches for Hyrox-related podcast episodes
2. Pulls episode metadata (title, description, duration, links)
3. Gets show follower counts from Spotify API
4. Calculates engagement/relevance scores
5. Stores everything in your database

Uses the iTunes Search API (free, no auth required)
and Spotify API for follower counts
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import requests
import time
import base64
from datetime import datetime, timedelta
from urllib.parse import quote

load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

# Spotify API credentials (optional - for follower counts)
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Get week range from environment (set by dashboard) or default to past 14 days
week_start_str = os.getenv('DISCOVERY_WEEK_START')
week_end_str = os.getenv('DISCOVERY_WEEK_END')

if week_start_str and week_end_str:
    WEEK_START = datetime.fromisoformat(week_start_str)
    WEEK_END = datetime.fromisoformat(week_end_str) + timedelta(days=1)  # Include end day
else:
    # Default: past 14 days, extend end to include full current day
    WEEK_END = datetime.now().replace(hour=23, minute=59, second=59)
    WEEK_START = WEEK_END - timedelta(days=14)

# Search terms for finding Hyrox content
HYROX_SEARCH_TERMS = [
    "hyrox",
    "hyrox training",
    "hyrox race",
    "hybrid fitness racing",
    "hyrox workout",
    # Known Hyrox podcasts - search by show name to ensure discovery
    "Hybrid Coaching Podcast",
    "Rox Lyfe Podcast",
    "HYROX HEROES",
    "TrainHybrd Podcast",
    "UKHXR",
    "fitness racing podcast",
    "hyrox review",
]


class SpotifyAPI:
    """Helper class for Spotify API interactions.
    
    Supports two authentication modes:
    1. Client credentials (if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are set)
    2. Anonymous token (fallback - scrapes token from Spotify web interface)
    """
    
    def __init__(self):
        self.access_token = None
        self.token_expires = None
        self.has_credentials = bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)
        self.enabled = True  # Always enabled now with anonymous fallback
        self.using_anonymous = False
        
        if self.has_credentials:
            print("   🎵 Spotify API credentials found - will fetch follower counts")
        else:
            print("   🎵 Using anonymous Spotify access (no credentials needed)")
            print("      Note: For follower counts, set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")
    
    def get_anonymous_token(self):
        """Get an anonymous access token by scraping the Spotify web interface."""
        try:
            import re
            import json
            
            print("      Attempting to get anonymous Spotify token...")
            
            # Try the get_access_token endpoint that Spotify's web player uses
            # This is a more reliable method
            try:
                token_response = requests.get(
                    'https://open.spotify.com/get_access_token?reason=transport&productType=web_player',
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'application/json',
                        'app-platform': 'WebPlayer',
                    },
                    timeout=10
                )
                
                if token_response.status_code == 200:
                    try:
                        token_data = token_response.json()
                        token = token_data.get('accessToken')
                        if token:
                            self.access_token = token
                            # Token expires based on accessTokenExpirationTimestampMs
                            expires_ms = token_data.get('accessTokenExpirationTimestampMs', 0)
                            if expires_ms:
                                expires_at = datetime.fromtimestamp(expires_ms / 1000)
                                self.token_expires = expires_at - timedelta(minutes=5)  # 5 min buffer
                            else:
                                self.token_expires = datetime.now() + timedelta(minutes=50)
                            self.using_anonymous = True
                            print(f"      ✅ Got anonymous token (direct endpoint): {token[:20]}...")
                            return token
                    except json.JSONDecodeError:
                        print(f"      ⚠️ Token endpoint returned non-JSON response")
                else:
                    print(f"      ⚠️ Token endpoint returned status {token_response.status_code}")
            except Exception as e:
                print(f"      ⚠️ Direct token endpoint failed: {e}")
            
            # Fallback: Try the embed endpoint which sometimes works without auth
            try:
                embed_response = requests.get(
                    'https://open.spotify.com/embed/show/4R9e7KqDb3g6FaG4qVnP1t',  # Any valid show ID
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    },
                    timeout=10
                )
                
                if embed_response.status_code == 200:
                    # Look for accessToken in the embed page
                    match = re.search(r'"accessToken"\s*:\s*"([^"]+)"', embed_response.text)
                    if match:
                        token = match.group(1)
                        self.access_token = token
                        self.token_expires = datetime.now() + timedelta(minutes=50)
                        self.using_anonymous = True
                        print(f"      ✅ Got anonymous token (embed page): {token[:20]}...")
                        return token
            except Exception as e:
                print(f"      ⚠️ Embed endpoint failed: {e}")
            
            # Final fallback: original method
            response = requests.get(
                'https://open.spotify.com/search',
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
                timeout=10
            )
            
            print(f"      Spotify search page status: {response.status_code}, length: {len(response.text)}")
            
            if response.status_code == 200 and len(response.text) > 10000:
                # Look for the session script containing accessToken
                match = re.search(r'<script id="session"[^>]*>({.*?})</script>', response.text)
                
                if match:
                    session_data = json.loads(match.group(1))
                    token = session_data.get('accessToken')
                    if token:
                        self.access_token = token
                        self.token_expires = datetime.now() + timedelta(minutes=50)
                        self.using_anonymous = True
                        print(f"      ✅ Got anonymous token (session script): {token[:20]}...")
                        return token
                
                # Alternative pattern
                match = re.search(r'"accessToken"\s*:\s*"([^"]+)"', response.text)
                if match:
                    token = match.group(1)
                    self.access_token = token
                    self.token_expires = datetime.now() + timedelta(minutes=50)
                    self.using_anonymous = True
                    print(f"      ✅ Got anonymous token (regex): {token[:20]}...")
                    return token
                    
            print("   ⚠️ Could not get anonymous Spotify token - all methods failed")
            return None
        except Exception as e:
            print(f"   ⚠️ Anonymous Spotify auth error: {e}")
            return None
    
    def get_access_token(self):
        """Get Spotify access token using client credentials or anonymous flow."""
        # Check if token is still valid
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        
        # Try client credentials first if available
        if self.has_credentials:
            try:
                credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
                encoded = base64.b64encode(credentials.encode()).decode()
                
                response = requests.post(
                    'https://accounts.spotify.com/api/token',
                    headers={
                        'Authorization': f'Basic {encoded}',
                        'Content-Type': 'application/x-www-form-urlencoded'
                    },
                    data={'grant_type': 'client_credentials'},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.access_token = data['access_token']
                    self.token_expires = datetime.now() + timedelta(seconds=data['expires_in'] - 60)
                    self.using_anonymous = False
                    return self.access_token
                else:
                    print(f"   ⚠️ Spotify credentials auth failed ({response.status_code}), trying anonymous...")
            except Exception as e:
                print(f"   ⚠️ Spotify credentials error: {e}, trying anonymous...")
        
        # Fallback to anonymous token
        return self.get_anonymous_token()
    
    def search_show(self, show_name):
        """Search for a podcast show on Spotify and return its info including followers."""
        token = self.get_access_token()
        if not token:
            return None
        
        try:
            # Search for the show
            # Get market from environment (set by dashboard) or default to empty
            spotify_market = os.getenv('PODCAST_COUNTRY', '')
            
            params = {
                'q': show_name,
                'type': 'show',
                'limit': 1,
            }
            
            # Only add market if specified
            if spotify_market:
                params['market'] = spotify_market
            
            response = requests.get(
                'https://api.spotify.com/v1/search',
                headers={'Authorization': f'Bearer {token}'},
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                shows = data.get('shows', {}).get('items', [])
                
                if shows:
                    show = shows[0]
                    return {
                        'spotify_id': show.get('id'),
                        'name': show.get('name'),
                        'followers': show.get('total_episodes', 0),  # Shows don't expose followers directly in search
                        'spotify_url': show.get('external_urls', {}).get('spotify'),
                        'image_url': show['images'][0]['url'] if show.get('images') else None
                    }
            elif response.status_code == 401:
                # Token expired or invalid, clear it and retry once
                self.access_token = None
                self.token_expires = None
                return self.search_show(show_name)
            
            return None
        except Exception as e:
            print(f"   ⚠️ Spotify search error: {e}")
            return None
    
    def get_show_details(self, show_id):
        """Get detailed show info including follower count."""
        if not show_id:
            return None
            
        token = self.get_access_token()
        if not token:
            return None
        
        try:
            # Get market from environment (set by dashboard) or default to empty
            spotify_market = os.getenv('PODCAST_COUNTRY', '')
            
            params = {}
            if spotify_market:
                params['market'] = spotify_market
            
            response = requests.get(
                f'https://api.spotify.com/v1/shows/{show_id}',
                headers={'Authorization': f'Bearer {token}'},
                params=params if params else None,
                timeout=10
            )
            
            if response.status_code == 200:
                show = response.json()
                # Note: Spotify doesn't expose follower counts for shows via API
                # We'll use total_episodes as a proxy for show maturity/popularity
                return {
                    'spotify_id': show.get('id'),
                    'name': show.get('name'),
                    'total_episodes': show.get('total_episodes', 0),
                    'spotify_url': show.get('external_urls', {}).get('spotify'),
                    'publisher': show.get('publisher'),
                    'description': show.get('description')
                }
            elif response.status_code == 401:
                self.access_token = None
                self.token_expires = None
                return self.get_show_details(show_id)
            
            return None
        except Exception as e:
            print(f"   ⚠️ Spotify show details error: {e}")
            return None
    
    def search_episode(self, episode_title, show_name=None):
        """Search for a specific podcast episode on Spotify and return its direct URL.
        
        Args:
            episode_title: The title of the episode
            show_name: Optional show name to narrow search
            
        Returns:
            dict with 'episode_url' and 'episode_id' or None if not found
        """
        token = self.get_access_token()
        if not token:
            return None
        
        try:
            # Build search query - include show name if provided for better results
            if show_name:
                # Clean up titles for better search
                clean_episode = episode_title.replace('#', '').replace('|', ' ').replace(':', ' ')[:60]
                clean_show = show_name.replace('#', '').replace('|', ' ').replace(':', ' ')[:40]
                search_query = f"{clean_episode} {clean_show}"
            else:
                search_query = episode_title[:80]
            
            # Get market from environment
            spotify_market = os.getenv('PODCAST_COUNTRY', '')
            
            params = {
                'q': search_query,
                'type': 'episode',
                'limit': 5,  # Get a few results to find best match
            }
            
            if spotify_market:
                params['market'] = spotify_market
            
            response = requests.get(
                'https://api.spotify.com/v1/search',
                headers={'Authorization': f'Bearer {token}'},
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                episodes = data.get('episodes', {}).get('items', [])
                
                if episodes:
                    # Try to find the best match
                    episode_title_lower = episode_title.lower()
                    
                    # First, try to find an exact or close title match
                    for ep in episodes:
                        ep_name = ep.get('name', '').lower()
                        # Check if titles are similar (one contains most of the other)
                        if episode_title_lower[:30] in ep_name or ep_name[:30] in episode_title_lower:
                            return {
                                'episode_id': ep.get('id'),
                                'episode_url': ep.get('external_urls', {}).get('spotify'),
                                'name': ep.get('name'),
                                'show_name': ep.get('show', {}).get('name', ''),
                            }
                    
                    # If no close match, return the first result
                    ep = episodes[0]
                    return {
                        'episode_id': ep.get('id'),
                        'episode_url': ep.get('external_urls', {}).get('spotify'),
                        'name': ep.get('name'),
                        'show_name': ep.get('show', {}).get('name', ''),
                    }
            elif response.status_code == 401:
                # Token expired or invalid, clear and retry once
                self.access_token = None
                self.token_expires = None
                return self.search_episode(episode_title, show_name)
            
            return None
        except Exception as e:
            print(f"   ⚠️ Spotify episode search error: {e}")
            return None


class PodcastDiscovery:
    def __init__(self):
        pass
    
    def search_episodes(self, query, max_results=30):
        """Search for podcast episodes using iTunes Search API."""
        # Get country from environment (set by dashboard) or default to empty for global
        podcast_country = os.getenv('PODCAST_COUNTRY', '')
        
        url = "https://itunes.apple.com/search"
        params = {
            "term": query,
            "media": "podcast",
            "entity": "podcastEpisode",
            "limit": max_results,
        }
        
        # Only add country if specified (empty = no country filter)
        if podcast_country:
            params["country"] = podcast_country
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            
            # Transform iTunes format to our standard format
            episodes = []
            for item in results:
                episode = {
                    'title': item.get('trackName', ''),
                    'description': item.get('description', ''),
                    'datePublished': item.get('releaseDate', ''),
                    'duration': item.get('trackTimeMillis', 0) // 1000 if item.get('trackTimeMillis') else 0,
                    'enclosureUrl': item.get('episodeUrl', ''),
                    'link': item.get('trackViewUrl', ''),
                    'image': item.get('artworkUrl600', '') or item.get('artworkUrl160', ''),
                    'podcast_title': item.get('collectionName', ''),
                    'podcast_author': item.get('artistName', ''),
                    'podcast_image': item.get('artworkUrl600', ''),
                    'apple_podcasts_url': item.get('trackViewUrl', ''),
                    'feedId': item.get('collectionId', ''),
                }
                episodes.append(episode)
            
            return episodes
            
        except Exception as e:
            print(f"   ✗ Search failed for '{query}': {e}")
            return []
    
    def generate_spotify_search_url(self, episode_title, podcast_title):
        """Generate a Spotify search URL for the episode.
        
        Uses the spotify: URI scheme which opens the Spotify app directly
        and performs a search, rather than a web search URL which doesn't
        work as well.
        """
        # Clean up the title - remove common problematic characters
        clean_episode = episode_title.replace('#', '').replace('|', '').replace(':', ' ')[:50]
        clean_podcast = podcast_title.replace('#', '').replace('|', '').replace(':', ' ')[:30]
        
        # Create a more focused search query
        search_query = f"{clean_episode} {clean_podcast}"
        encoded_query = quote(search_query)
        
        # Use the Spotify web player search which handles episodes better
        return f"https://open.spotify.com/search/{encoded_query}/episodes"
    
    def generate_apple_podcasts_url(self, episode):
        """Get or generate Apple Podcasts URL."""
        if episode.get('apple_podcasts_url'):
            return episode['apple_podcasts_url']
        
        search_query = f"{episode.get('title', '')} {episode.get('podcast_title', '')}"
        encoded_query = quote(search_query)
        return f"https://podcasts.apple.com/search?term={encoded_query}"


class PodcastDatabaseManager:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.creator_columns = []
        self.content_columns = []
    
    def connect(self):
        """Establish database connection and discover schema."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Discover creators table columns
        self.cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'creators'
        """)
        self.creator_columns = [row['column_name'] for row in self.cursor.fetchall()]
        
        # Discover content_items table columns
        self.cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'content_items'
        """)
        self.content_columns = [row['column_name'] for row in self.cursor.fetchall()]
        
        print(f"   📊 Detected creator columns: {len(self.creator_columns)}")
        print(f"   📊 Detected content columns: {len(self.content_columns)}")
    
    def close(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.commit()
            self.conn.close()
    
    def get_or_create_creator(self, podcast_title, podcast_author, podcast_image=None, follower_count=None, spotify_url=None):
        """Get or create a creator (podcast) record."""
        # Check if exists
        self.cursor.execute("""
            SELECT id FROM creators 
            WHERE name = %s AND platform = 'podcast'
        """, (podcast_title,))
        
        result = self.cursor.fetchone()
        if result:
            # Update follower count if we have a new value
            if follower_count and 'follower_count' in self.creator_columns:
                self.cursor.execute("""
                    UPDATE creators SET follower_count = %s WHERE id = %s
                """, (follower_count, result['id']))
                self.conn.commit()
            return result['id']
        
        # Build dynamic INSERT based on available columns
        insert_cols = ['name', 'platform']
        insert_vals = [podcast_title, 'podcast']
        
        if 'platform_id' in self.creator_columns:
            insert_cols.append('platform_id')
            insert_vals.append(podcast_author or podcast_title)
        
        if 'profile_url' in self.creator_columns:
            insert_cols.append('profile_url')
            insert_vals.append(spotify_url)
        
        if 'avatar_url' in self.creator_columns:
            insert_cols.append('avatar_url')
            insert_vals.append(podcast_image)
        
        if 'follower_count' in self.creator_columns and follower_count:
            insert_cols.append('follower_count')
            insert_vals.append(follower_count)
        
        if 'credibility_score' in self.creator_columns:
            insert_cols.append('credibility_score')
            insert_vals.append(0.5)
        
        cols_str = ', '.join(insert_cols)
        placeholders = ', '.join(['%s'] * len(insert_vals))
        
        query = f"""
            INSERT INTO creators ({cols_str})
            VALUES ({placeholders})
            RETURNING id
        """
        
        self.cursor.execute(query, insert_vals)
        self.conn.commit()
        return self.cursor.fetchone()['id']
    
    def episode_exists(self, title, podcast_title):
        """Check if episode already exists in database."""
        self.cursor.execute("""
            SELECT id FROM content_items 
            WHERE title = %s AND platform = 'podcast'
            AND creator_id IN (SELECT id FROM creators WHERE name = %s)
        """, (title, podcast_title))
        
        return self.cursor.fetchone() is not None
    
    def save_episode(self, episode, creator_id, spotify_url, apple_url, show_followers=0):
        """Save podcast episode to database."""
        # Parse publish date
        date_str = episode.get('datePublished', '')
        try:
            if 'T' in str(date_str):
                published_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                published_date = datetime.now()
        except:
            published_date = datetime.now()
        
        duration_seconds = episode.get('duration', 0)
        description = episode.get('description', '')[:500] if episode.get('description') else ''
        
        # Store Spotify and Apple URLs in editorial_note
        links_info = f"Spotify: {spotify_url} | Apple: {apple_url}"
        
        # Build dynamic INSERT based on available columns
        insert_cols = ['title', 'url', 'platform', 'creator_id', 'status']
        insert_vals = [
            episode.get('title', 'Untitled Episode'),
            episode.get('link', '') or episode.get('enclosureUrl', ''),
            'podcast',
            creator_id,
            'discovered'
        ]
        
        if 'thumbnail_url' in self.content_columns:
            insert_cols.append('thumbnail_url')
            insert_vals.append(episode.get('image', '') or episode.get('podcast_image', ''))
        
        if 'description' in self.content_columns:
            insert_cols.append('description')
            insert_vals.append(description)
        
        if 'published_date' in self.content_columns:
            insert_cols.append('published_date')
            insert_vals.append(published_date)
        
        if 'duration_seconds' in self.content_columns:
            insert_cols.append('duration_seconds')
            insert_vals.append(duration_seconds)
        
        # Use view_count to store show followers for sorting by popularity
        if 'view_count' in self.content_columns:
            insert_cols.append('view_count')
            insert_vals.append(show_followers or 0)
        
        if 'like_count' in self.content_columns:
            insert_cols.append('like_count')
            insert_vals.append(0)
        
        if 'comment_count' in self.content_columns:
            insert_cols.append('comment_count')
            insert_vals.append(0)
        
        if 'editorial_note' in self.content_columns:
            insert_cols.append('editorial_note')
            insert_vals.append(links_info)
        
        cols_str = ', '.join(insert_cols)
        placeholders = ', '.join(['%s'] * len(insert_vals))
        
        query = f"""
            INSERT INTO content_items ({cols_str})
            VALUES ({placeholders})
            RETURNING id
        """
        
        self.cursor.execute(query, insert_vals)
        self.conn.commit()
        return self.cursor.fetchone()['id']


def filter_recent_episodes(episodes, week_start=None, week_end=None):
    """Filter episodes to only include ones from the selected week."""
    if week_start is None:
        week_start = WEEK_START
    if week_end is None:
        week_end = WEEK_END
    
    recent = []
    
    for ep in episodes:
        date_str = ep.get('datePublished', '')
        try:
            if 'T' in str(date_str):
                pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if pub_date.tzinfo:
                    pub_date = pub_date.replace(tzinfo=None)
            else:
                recent.append(ep)
                continue
                
            if week_start <= pub_date <= week_end:
                recent.append(ep)
        except Exception:
            recent.append(ep)
    
    return recent


def is_hyrox_relevant(ep):
    """Check if a single episode is Hyrox-relevant."""
    hyrox_keywords = [
        'hyrox', 'hybrid fitness', 'hybrid athlete', 'functional fitness race',
        'roxzone', 'ski erg', 'sled push', 'sled pull', 'wall balls',
        'hunter mcintyre', 'lauren weeks', 'krypton',
        # Known Hyrox podcasts/channels
        'ukhxr', 'fitness racing podcast',
    ]
    
    title = (ep.get('title', '') or '').lower()
    description = (ep.get('description', '') or '').lower()
    podcast_title = (ep.get('podcast_title', '') or '').lower()
    
    combined_text = f"{title} {description} {podcast_title}"
    
    for keyword in hyrox_keywords:
        if keyword in combined_text:
            return True
    return False


def filter_hyrox_relevant(episodes):
    """Filter episodes to only include Hyrox-relevant content."""
    return [ep for ep in episodes if is_hyrox_relevant(ep)]


def get_priority_podcast_sources():
    """Get priority podcast sources from database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT source_name FROM priority_sources 
            WHERE platform = 'podcast' AND is_active = true
        """)
        sources = cursor.fetchall()
        cursor.close()
        conn.close()
        return [s['source_name'] for s in sources]
    except Exception as e:
        print(f"   ⚠️ Could not load priority sources: {e}")
        return []


def get_priority_podcast_rss_feeds():
    """Get priority podcast RSS feed URLs from database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT source_name, source_url FROM priority_sources 
            WHERE platform = 'podcast' AND is_active = true AND source_url IS NOT NULL AND source_url != ''
        """)
        sources = cursor.fetchall()
        cursor.close()
        conn.close()
        return [(s['source_name'], s['source_url']) for s in sources]
    except Exception as e:
        print(f"   ⚠️ Could not load priority RSS feeds: {e}")
        return []


def fetch_episodes_from_rss(feed_url, feed_name):
    """Fetch episodes from an RSS feed URL"""
    try:
        import feedparser
    except ImportError:
        print("   ⚠️ feedparser not installed. Run: pip install feedparser")
        return []
    
    try:
        print(f"   📡 Fetching RSS: {feed_name}...")
        feed = feedparser.parse(feed_url)
        
        if feed.bozo and not feed.entries:
            print(f"   ⚠️ Could not parse RSS feed for {feed_name}")
            return []
        
        episodes = []
        podcast_title = feed.feed.get('title', feed_name)
        podcast_author = feed.feed.get('author', feed.feed.get('itunes_author', ''))
        podcast_image = feed.feed.get('image', {}).get('href', '') or feed.feed.get('itunes_image', {}).get('href', '')
        
        for entry in feed.entries:
            # Parse publish date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6])
            
            # Get duration
            duration = 0
            if hasattr(entry, 'itunes_duration'):
                dur_str = entry.itunes_duration
                if dur_str:
                    try:
                        if ':' in str(dur_str):
                            parts = str(dur_str).split(':')
                            if len(parts) == 3:
                                duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            elif len(parts) == 2:
                                duration = int(parts[0]) * 60 + int(parts[1])
                        else:
                            duration = int(dur_str)
                    except:
                        pass
            
            # Get enclosure URL (audio file)
            enclosure_url = ''
            if hasattr(entry, 'enclosures') and entry.enclosures:
                enclosure_url = entry.enclosures[0].get('href', '')
            
            episode = {
                'title': entry.get('title', ''),
                'description': entry.get('summary', entry.get('description', '')),
                'datePublished': pub_date.isoformat() if pub_date else '',
                'duration': duration,
                'enclosureUrl': enclosure_url,
                'link': entry.get('link', ''),
                'image': entry.get('image', {}).get('href', '') or podcast_image,
                'podcast_title': podcast_title,
                'podcast_author': podcast_author,
                'podcast_image': podcast_image,
                'apple_podcasts_url': entry.get('link', ''),
                'feedId': feed_url,
                'from_priority_rss': True,  # Flag to indicate this came from RSS
            }
            episodes.append(episode)
        
        print(f"   ✓ Found {len(episodes)} episodes from {feed_name}")
        return episodes
        
    except Exception as e:
        print(f"   ⚠️ Error fetching RSS feed {feed_name}: {e}")
        return []


def main():
    print("=" * 70)
    print("PODCAST DISCOVERY - Hyrox Content")
    print("=" * 70)
    
    print(f"\n📅 Week: {WEEK_START.strftime('%Y-%m-%d')} to {WEEK_END.strftime('%Y-%m-%d')}")
    
    discovery = PodcastDiscovery()
    db = PodcastDatabaseManager()
    spotify = SpotifyAPI()
    
    # Cache for show follower counts to avoid repeated API calls
    show_followers_cache = {}
    
    all_episodes = []
    
    # Get priority sources from database (for search term matching)
    priority_sources = get_priority_podcast_sources()
    if priority_sources:
        print(f"\n⭐ Priority podcast sources: {', '.join(priority_sources)}")
    
    # Get priority RSS feeds from database (for direct feed fetching)
    priority_rss_feeds = get_priority_podcast_rss_feeds()
    if priority_rss_feeds:
        print(f"\n📡 Priority podcast RSS feeds: {len(priority_rss_feeds)} feeds")
        for feed_name, feed_url in priority_rss_feeds:
            rss_episodes = fetch_episodes_from_rss(feed_url, feed_name)
            all_episodes.extend(rss_episodes)
    
    # Combine search terms with priority sources
    search_terms = list(HYROX_SEARCH_TERMS) + priority_sources
    
    print("\n🔍 Searching for Hyrox podcast episodes...")
    
    for term in search_terms:
        is_priority = term in priority_sources
        prefix = "⭐" if is_priority else "  "
        print(f"{prefix} Searching: '{term}'...")
        episodes = discovery.search_episodes(term, max_results=30)
        all_episodes.extend(episodes)
        time.sleep(0.5)  # Be nice to the API
    
    print(f"   ✓ Found {len(all_episodes)} total episodes")
    
    # Remove duplicates (by title)
    seen_titles = set()
    unique_episodes = []
    for ep in all_episodes:
        title = ep.get('title', '')
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique_episodes.append(ep)
    
    print(f"   ✓ {len(unique_episodes)} unique episodes after deduplication")
    
    # Filter to selected week
    recent_episodes = filter_recent_episodes(unique_episodes)
    print(f"   ✓ {len(recent_episodes)} episodes from selected week")
    
    # Filter to Hyrox-relevant content
    # Note: Episodes from priority RSS feeds are automatically considered relevant
    relevant_episodes = []
    for ep in recent_episodes:
        if ep.get('from_priority_rss'):
            relevant_episodes.append(ep)
        elif is_hyrox_relevant(ep):
            relevant_episodes.append(ep)
    
    print(f"   ✓ {len(relevant_episodes)} Hyrox-relevant episodes")
    
    if not relevant_episodes:
        print("\n⚠️  No relevant podcast episodes found.")
        print("   This might happen if:")
        print("   - No new Hyrox episodes in the past 2 weeks")
        print("   - Search terms need adjustment")
        print("\n   Saving all recent fitness episodes instead...")
        relevant_episodes = recent_episodes[:20]
    
    # Save to database
    print(f"\n💾 Saving {len(relevant_episodes)} episodes to database...")
    
    if spotify.enabled:
        print("   🎵 Fetching Spotify show popularity data and episode URLs...")
    
    db.connect()
    
    saved_count = 0
    skipped_count = 0
    
    for ep in relevant_episodes:
        title = ep.get('title', 'Untitled')
        podcast_title = ep.get('podcast_title', 'Unknown Podcast')
        
        # Check if already exists
        if db.episode_exists(title, podcast_title):
            skipped_count += 1
            print(f"   ⊙ Already exists: {title[:50]}...")
            continue
        
        # Get Spotify show info (with caching)
        show_followers = 0
        spotify_show_url = None
        
        if spotify.enabled and podcast_title not in show_followers_cache:
            show_info = spotify.search_show(podcast_title)
            if show_info:
                # Use total_episodes as a proxy for popularity (more episodes = more established)
                show_followers_cache[podcast_title] = {
                    'total_episodes': show_info.get('total_episodes', 0),
                    'spotify_url': show_info.get('spotify_url')
                }
            else:
                show_followers_cache[podcast_title] = {'total_episodes': 0, 'spotify_url': None}
            time.sleep(0.1)  # Rate limiting
        
        if podcast_title in show_followers_cache:
            show_followers = show_followers_cache[podcast_title].get('total_episodes', 0)
            spotify_show_url = show_followers_cache[podcast_title].get('spotify_url')
        
        # Get or create creator with follower count
        creator_id = db.get_or_create_creator(
            podcast_title,
            ep.get('podcast_author', ''),
            ep.get('podcast_image', ''),
            follower_count=show_followers,
            spotify_url=spotify_show_url
        )
        
        # Try to get actual Spotify episode URL (direct link, not search)
        spotify_url = None
        if spotify.enabled:
            episode_info = spotify.search_episode(title, podcast_title)
            if episode_info and episode_info.get('episode_url'):
                spotify_url = episode_info['episode_url']
                print(f"      🔗 Found direct Spotify link for: {title[:40]}...")
            time.sleep(0.1)  # Rate limiting
        
        # Fall back to show URL or search URL if no direct episode link found
        if not spotify_url:
            spotify_url = spotify_show_url or discovery.generate_spotify_search_url(title, podcast_title)
        
        apple_url = ep.get('apple_podcasts_url', '') or discovery.generate_apple_podcasts_url(ep)
        
        # Save episode with show popularity
        try:
            episode_id = db.save_episode(ep, creator_id, spotify_url, apple_url, show_followers=show_followers)
            saved_count += 1
            
            duration_min = (ep.get('duration', 0) or 0) // 60
            popularity_str = f" [Pop: {show_followers}]" if show_followers else ""
            print(f"   ✓ Saved: {title[:45]}...{popularity_str} ({duration_min} min)")
            
        except Exception as e:
            print(f"   ✗ Error saving {title[:30]}: {e}")
    
    db.close()
    
    # Summary
    print("\n" + "=" * 70)
    print("✓ Podcast discovery complete!")
    print("=" * 70)
    print(f"   • New episodes saved: {saved_count}")
    print(f"   • Already in database: {skipped_count}")
    print(f"   • Total processed: {len(relevant_episodes)}")
    print("\n📋 Next steps:")
    print("   1. Run: streamlit run curation_dashboard.py")
    print("   2. Review and select podcast episodes")
    print("   3. Episodes will appear with platform = 'podcast'")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
