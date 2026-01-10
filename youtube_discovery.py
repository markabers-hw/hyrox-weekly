"""
Hyrox Weekly - YouTube Content Discovery
Searches for Hyrox content and stores in database
"""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dateutil import parser as date_parser

load_dotenv()

# Get week range from environment (set by dashboard) or default to past 14 days
week_start_str = os.getenv('DISCOVERY_WEEK_START')
week_end_str = os.getenv('DISCOVERY_WEEK_END')

if week_start_str and week_end_str:
    WEEK_START = datetime.fromisoformat(week_start_str)
    WEEK_END = datetime.fromisoformat(week_end_str) + timedelta(days=1)
else:
    WEEK_END = datetime.now()
    WEEK_START = WEEK_END - timedelta(days=14)

# Minimum video duration in seconds (from Settings page, default 60)
MIN_DURATION_SECONDS = int(os.getenv('YOUTUBE_MIN_DURATION', '60'))

# YouTube region code - leave empty for global/unbiased results
# Options: 'US', 'GB', 'DE', 'AU', or '' for no region filter
YOUTUBE_REGION = os.getenv('YOUTUBE_REGION', '')  # Default to no region filter

# Configuration
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

class YouTubeDiscovery:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        self.conn = None
    
    def connect_db(self):
        """Connect to database"""
        self.conn = psycopg2.connect(**DB_CONFIG)
        return self.conn.cursor(cursor_factory=RealDictCursor)
    
    def search_hyrox_videos(self, max_results=50):
        """
        Search for Hyrox videos from the selected week
        
        Args:
            max_results: Maximum number of results to return
        """
        # Use the global week range
        published_after = WEEK_START.isoformat() + 'Z'
        published_before = WEEK_END.isoformat() + 'Z'
        
        print(f"📅 Week: {WEEK_START.strftime('%Y-%m-%d')} to {WEEK_END.strftime('%Y-%m-%d')}")
        print(f"⏱️ Minimum duration: {MIN_DURATION_SECONDS} seconds")
        if YOUTUBE_REGION:
            print(f"🌍 Region filter: {YOUTUBE_REGION}")
        else:
            print(f"🌍 Region filter: Global (no region bias)")
        print(f"\n🔍 Searching YouTube for 'Hyrox' videos (English only)...")
        
        try:
            # Build search parameters
            search_params = {
                'q': 'Hyrox',
                'type': 'video',
                'part': 'id,snippet',
                'maxResults': max_results,
                'publishedAfter': published_after,
                'publishedBefore': published_before,
                'order': 'viewCount',
                'relevanceLanguage': 'en',
            }
            
            # Only add regionCode if specified (empty = global/unbiased)
            if YOUTUBE_REGION:
                search_params['regionCode'] = YOUTUBE_REGION
            
            search_response = self.youtube.search().list(**search_params).execute()
            
            videos = search_response.get('items', [])
            print(f"   ✅ Found {len(videos)} videos")
            
            return videos
            
        except HttpError as e:
            print(f"   ❌ YouTube API error: {e}")
            return []
    
    def search_channel_videos(self, channel_name, channel_id=None, max_results=10):
        """
        Search for recent videos from a specific channel
        
        Args:
            channel_name: Name of the channel to search
            channel_id: YouTube channel ID (if available, more accurate)
            max_results: Maximum number of results
        """
        published_after = WEEK_START.isoformat() + 'Z'
        published_before = WEEK_END.isoformat() + 'Z'
        
        try:
            # Build search params
            search_params = {
                'type': 'video',
                'part': 'id,snippet',
                'maxResults': max_results,
                'publishedAfter': published_after,
                'publishedBefore': published_before,
                'order': 'date',
            }
            
            # If we have a channel ID, use it for precise results
            if channel_id:
                search_params['channelId'] = channel_id
            else:
                # Fall back to searching by channel name
                search_params['q'] = channel_name
            
            search_response = self.youtube.search().list(**search_params).execute()
            return search_response.get('items', [])
            
        except HttpError as e:
            print(f"   ❌ Error searching channel '{channel_name}': {e}")
            return []
    
    def get_priority_youtube_sources(self):
        """Get priority YouTube sources from database"""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT source_name, source_id FROM priority_sources 
                WHERE platform = 'youtube' AND is_active = true
            """)
            sources = cursor.fetchall()
            cursor.close()
            conn.close()
            return sources
        except Exception as e:
            print(f"   ⚠️ Could not load priority sources: {e}")
            return []
    
    def get_video_statistics(self, video_ids):
        """
        Get detailed statistics for a list of video IDs
        
        Args:
            video_ids: List of YouTube video IDs
        """
        if not video_ids:
            return {}
        
        try:
            # Get statistics in batches of 50 (API limit)
            stats = {}
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                
                response = self.youtube.videos().list(
                    part='statistics,contentDetails,snippet',
                    id=','.join(batch)
                ).execute()
                
                for item in response.get('items', []):
                    video_id = item['id']
                    # Get default language from snippet
                    default_language = item.get('snippet', {}).get('defaultLanguage', '')
                    default_audio_language = item.get('snippet', {}).get('defaultAudioLanguage', '')
                    
                    stats[video_id] = {
                        'view_count': int(item['statistics'].get('viewCount', 0)),
                        'like_count': int(item['statistics'].get('likeCount', 0)),
                        'comment_count': int(item['statistics'].get('commentCount', 0)),
                        'duration': item['contentDetails'].get('duration', 'PT0S'),
                        'language': default_audio_language or default_language or ''
                    }
            
            return stats
            
        except HttpError as e:
            print(f"   ❌ Error fetching statistics: {e}")
            return {}
    
    def get_channel_info(self, channel_id):
        """Get channel information"""
        try:
            response = self.youtube.channels().list(
                part='snippet,statistics',
                id=channel_id
            ).execute()
            
            if response.get('items'):
                channel = response['items'][0]
                return {
                    'name': channel['snippet']['title'],
                    'subscriber_count': int(channel['statistics'].get('subscriberCount', 0)),
                    'avatar_url': channel['snippet']['thumbnails']['default']['url']
                }
        except HttpError as e:
            print(f"✗ Error fetching channel info: {e}")
        
        return None
    
    def parse_duration(self, duration_str):
        """Convert ISO 8601 duration to seconds (PT1H2M10S -> 3730)"""
        import re
        
        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(duration_str)
        
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds
        
        return 0
    
    def save_creator(self, cursor, channel_id, channel_info):
        """Save or update creator in database"""
        if not channel_info:
            return None
        
        cursor.execute("""
            INSERT INTO creators (name, platform, platform_id, follower_count, avatar_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (platform, platform_id) 
            DO UPDATE SET 
                follower_count = EXCLUDED.follower_count,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
        """, (
            channel_info['name'],
            'youtube',
            channel_id,
            channel_info['subscriber_count'],
            channel_info['avatar_url']
        ))
        
        result = cursor.fetchone()
        return result['id'] if result else None
    
    def save_content(self, cursor, video, stats, creator_id):
        """Save video content to database"""
        snippet = video['snippet']
        video_id = video['id']['videoId']
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Parse published date
        published_date = date_parser.parse(snippet['publishedAt'])
        
        # Get statistics
        view_count = stats.get('view_count', 0)
        like_count = stats.get('like_count', 0)
        comment_count = stats.get('comment_count', 0)
        duration_seconds = self.parse_duration(stats.get('duration', 'PT0S'))
        
        # Check if already exists
        cursor.execute("""
            SELECT id FROM content_items WHERE url = %s;
        """, (url,))
        
        if cursor.fetchone():
            print(f"  ⊙ Already exists: {snippet['title'][:50]}...")
            return None
        
        # Insert new content
        cursor.execute("""
            INSERT INTO content_items 
            (creator_id, url, title, description, platform, content_type,
             published_date, duration_seconds, thumbnail_url,
             view_count, like_count, comment_count, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            creator_id,
            url,
            snippet['title'],
            snippet['description'][:1000],  # Truncate long descriptions
            'youtube',
            'video',
            published_date,
            duration_seconds,
            snippet['thumbnails']['high']['url'],
            view_count,
            like_count,
            comment_count,
            'discovered'
        ))
        
        result = cursor.fetchone()
        print(f"  ✓ Saved: {snippet['title'][:50]}... ({view_count:,} views)")
        return result['id'] if result else None
    
    def discover_and_save(self, max_results=50):
        """Main function: discover videos and save to database"""
        print("\n" + "="*70)
        print("YOUTUBE DISCOVERY - Hyrox Content")
        print("="*70 + "\n")
        
        # Search for videos
        videos = self.search_hyrox_videos(max_results)
        
        # Also search priority channels
        priority_sources = self.get_priority_youtube_sources()
        if priority_sources:
            print(f"\n⭐ Checking {len(priority_sources)} priority YouTube channels...")
            for source in priority_sources:
                channel_name = source['source_name']
                channel_id = source.get('source_id')  # May be None
                print(f"   ⭐ Searching: '{channel_name}'{'  (ID: ' + channel_id + ')' if channel_id else ''}...")
                channel_videos = self.search_channel_videos(channel_name, channel_id=channel_id, max_results=10)
                if channel_videos:
                    print(f"      Found {len(channel_videos)} videos")
                    videos.extend(channel_videos)
        
        # Remove duplicates by video ID
        seen_ids = set()
        unique_videos = []
        for video in videos:
            vid_id = video['id']['videoId']
            if vid_id not in seen_ids:
                seen_ids.add(vid_id)
                unique_videos.append(video)
        videos = unique_videos
        print(f"\n   ✅ Total unique videos: {len(videos)}")
        
        if not videos:
            print("No videos found for selected week.")
            return
        
        # Get video IDs
        video_ids = [v['id']['videoId'] for v in videos]
        
        # Get statistics
        print("\n📊 Fetching video statistics...")
        video_stats = self.get_video_statistics(video_ids)
        
        # Filter to English videos only and by minimum duration
        filtered_videos = []
        non_english_count = 0
        too_short_count = 0
        
        for video in videos:
            video_id = video['id']['videoId']
            stats = video_stats.get(video_id, {})
            language = stats.get('language', '').lower()
            duration_seconds = self.parse_duration(stats.get('duration', 'PT0S'))
            
            # Check language
            if language not in ['', 'en', 'en-us', 'en-gb', 'en-au', 'en-ca']:
                non_english_count += 1
                continue
            
            # Check minimum duration
            if duration_seconds < MIN_DURATION_SECONDS:
                too_short_count += 1
                continue
            
            filtered_videos.append(video)
        
        if non_english_count > 0:
            print(f"   🌐 Filtered out {non_english_count} non-English videos")
        if too_short_count > 0:
            print(f"   ⏱️ Filtered out {too_short_count} videos shorter than {MIN_DURATION_SECONDS} seconds")
        print(f"   ✅ {len(filtered_videos)} videos to process")
        
        if not filtered_videos:
            print("No videos found matching criteria for selected week.")
            return
        
        # Connect to database
        cursor = self.connect_db()
        
        # Process each video
        print(f"\n💾 Processing {len(filtered_videos)} videos...\n")
        saved_count = 0
        skipped_count = 0
        
        for video in filtered_videos:
            video_id = video['id']['videoId']
            channel_id = video['snippet']['channelId']
            
            # Get channel info
            channel_info = self.get_channel_info(channel_id)
            
            # Save creator
            creator_id = self.save_creator(cursor, channel_id, channel_info)
            
            # Save content
            stats = video_stats.get(video_id, {})
            content_id = self.save_content(cursor, video, stats, creator_id)
            
            if content_id:
                saved_count += 1
            else:
                skipped_count += 1
        
        # Commit changes
        self.conn.commit()
        cursor.close()
        self.conn.close()
        
        print("\n" + "="*70)
        print(f"✅ Discovery complete!")
        print(f"  - New videos saved: {saved_count}")
        print(f"  - Already in database: {skipped_count}")
        print(f"  - Total processed: {len(videos)}")
        print("="*70 + "\n")
        
        return saved_count
    
    def log_discovery_run(self, cursor, platform, items_discovered, status, error_msg=None, exec_time=0):
        """Log discovery run to database"""
        cursor.execute("""
            INSERT INTO discovery_runs 
            (platform, items_discovered, status, error_message, execution_time_seconds)
            VALUES (%s, %s, %s, %s, %s);
        """, (platform, items_discovered, status, error_msg, exec_time))

def main():
    """Run YouTube discovery"""
    # Check API key
    if not YOUTUBE_API_KEY:
        print("❌ Error: YOUTUBE_API_KEY not found in .env file")
        print("\nPlease add your YouTube API key to .env:")
        print("YOUTUBE_API_KEY=your-api-key-here")
        return
    
    try:
        discovery = YouTubeDiscovery()
        discovery.discover_and_save(max_results=50)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()