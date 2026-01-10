"""
Hyrox Weekly Instagram Content Manager

Since Instagram doesn't have a public API, this tool allows you to:
1. Manually add Instagram posts by URL
2. The script extracts available metadata
3. Posts are added to the database for curation

Usage:
    python instagram_manager.py                    # Interactive mode
    python instagram_manager.py add <url>          # Add single post
    python instagram_manager.py list               # List saved posts
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import requests
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}


class InstagramManager:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.conn = None
        self.cursor = None
        self.content_columns = []
        self.creator_columns = []
    
    def connect_db(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get column info
        self.cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'creators'")
        self.creator_columns = [r['column_name'] for r in self.cursor.fetchall()]
        
        self.cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'content_items'")
        self.content_columns = [r['column_name'] for r in self.cursor.fetchall()]
    
    def close_db(self):
        if self.cursor: self.cursor.close()
        if self.conn: self.conn.commit(); self.conn.close()
    
    def extract_post_id(self, url):
        """Extract post ID from Instagram URL."""
        # Handle various Instagram URL formats
        patterns = [
            r'instagram\.com/p/([A-Za-z0-9_-]+)',
            r'instagram\.com/reel/([A-Za-z0-9_-]+)',
            r'instagram\.com/tv/([A-Za-z0-9_-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_post_metadata(self, url):
        """
        Try to get basic metadata from Instagram.
        Note: This may not work reliably due to Instagram's restrictions.
        """
        post_id = self.extract_post_id(url)
        if not post_id:
            return None
        
        # Normalize URL
        clean_url = f"https://www.instagram.com/p/{post_id}/"
        
        metadata = {
            'url': clean_url,
            'post_id': post_id,
            'title': '',
            'description': '',
            'thumbnail_url': '',
            'author': '',
            'platform': 'instagram',
        }
        
        # Try to fetch Open Graph data from the page
        try:
            response = requests.get(clean_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                html = response.text
                
                # Extract OG title
                og_title = re.search(r'<meta property="og:title" content="([^"]*)"', html)
                if og_title:
                    metadata['title'] = og_title.group(1)
                
                # Extract OG description
                og_desc = re.search(r'<meta property="og:description" content="([^"]*)"', html)
                if og_desc:
                    metadata['description'] = og_desc.group(1)[:500]
                
                # Extract OG image
                og_image = re.search(r'<meta property="og:image" content="([^"]*)"', html)
                if og_image:
                    metadata['thumbnail_url'] = og_image.group(1)
                
                # Try to extract username from title
                if metadata['title']:
                    # Format is usually "Username on Instagram: caption"
                    username_match = re.match(r'^([^@\s]+) on Instagram', metadata['title'])
                    if username_match:
                        metadata['author'] = username_match.group(1)
                
        except Exception as e:
            print(f"   Warning: Could not fetch metadata: {e}")
        
        return metadata
    
    def post_exists(self, url):
        """Check if post already exists in database."""
        post_id = self.extract_post_id(url)
        if not post_id:
            return False
        
        self.cursor.execute("""
            SELECT id FROM content_items 
            WHERE platform = 'instagram' AND url LIKE %s
        """, (f'%{post_id}%',))
        
        return self.cursor.fetchone() is not None
    
    def get_or_create_creator(self, author):
        """Get or create Instagram creator."""
        if not author:
            author = "Instagram User"
        
        self.cursor.execute("""
            SELECT id FROM creators 
            WHERE name = %s AND platform = 'instagram'
        """, (author,))
        
        result = self.cursor.fetchone()
        if result:
            return result['id']
        
        cols, vals = ['name', 'platform'], [author, 'instagram']
        if 'platform_id' in self.creator_columns:
            cols.append('platform_id')
            vals.append(author)
        if 'credibility_score' in self.creator_columns:
            cols.append('credibility_score')
            vals.append(0.6)
        
        self.cursor.execute(
            f"INSERT INTO creators ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id",
            vals
        )
        self.conn.commit()
        return self.cursor.fetchone()['id']
    
    def add_post(self, url, custom_title=None, custom_description=None, category='other'):
        """Add an Instagram post to the database."""
        
        # Check if exists
        if self.post_exists(url):
            print(f"   Post already exists in database")
            return None
        
        # Get metadata
        print(f"   Fetching metadata...")
        metadata = self.get_post_metadata(url)
        
        if not metadata:
            print(f"   Error: Could not parse Instagram URL")
            return None
        
        # Allow custom overrides
        if custom_title:
            metadata['title'] = custom_title
        if custom_description:
            metadata['description'] = custom_description
        
        # If no title, create one
        if not metadata['title']:
            metadata['title'] = f"Instagram Post by {metadata.get('author', 'Unknown')}"
        
        # Get/create creator
        creator_id = self.get_or_create_creator(metadata.get('author'))
        
        # Build insert
        cols = ['title', 'url', 'platform', 'creator_id', 'status']
        vals = [metadata['title'], metadata['url'], 'instagram', creator_id, 'discovered']
        
        if 'thumbnail_url' in self.content_columns:
            cols.append('thumbnail_url')
            vals.append(metadata.get('thumbnail_url', ''))
        
        if 'description' in self.content_columns:
            cols.append('description')
            vals.append(metadata.get('description', ''))
        
        if 'published_date' in self.content_columns:
            cols.append('published_date')
            vals.append(datetime.now())
        
        if 'view_count' in self.content_columns:
            cols.append('view_count')
            vals.append(0)
        
        if 'like_count' in self.content_columns:
            cols.append('like_count')
            vals.append(0)
        
        if 'comment_count' in self.content_columns:
            cols.append('comment_count')
            vals.append(0)
        
        if 'category' in self.content_columns:
            cols.append('category')
            vals.append(category)
        
        if 'editorial_note' in self.content_columns:
            cols.append('editorial_note')
            vals.append(f"Author: @{metadata.get('author', 'unknown')}")
        
        self.cursor.execute(
            f"INSERT INTO content_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id",
            vals
        )
        self.conn.commit()
        
        post_id = self.cursor.fetchone()['id']
        return post_id
    
    def list_posts(self, status='all'):
        """List Instagram posts in database."""
        query = """
            SELECT ci.id, ci.title, ci.url, ci.status, ci.category,
                   c.name as creator_name
            FROM content_items ci
            LEFT JOIN creators c ON ci.creator_id = c.id
            WHERE ci.platform = 'instagram'
        """
        
        if status != 'all':
            query += f" AND ci.status = '{status}'"
        
        query += " ORDER BY ci.id DESC LIMIT 20"
        
        self.cursor.execute(query)
        return self.cursor.fetchall()


def interactive_mode(manager):
    """Run interactive mode for adding posts."""
    print("\n" + "=" * 60)
    print("INSTAGRAM CONTENT MANAGER - Interactive Mode")
    print("=" * 60)
    print("\nCommands:")
    print("  paste URL    - Add a post")
    print("  list         - Show saved posts")
    print("  quit         - Exit")
    print("-" * 60)
    
    while True:
        try:
            user_input = input("\n📸 Enter Instagram URL (or command): ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if user_input.lower() == 'list':
                posts = manager.list_posts()
                if posts:
                    print(f"\n{'ID':<6} {'Status':<12} {'Creator':<20} {'Title':<30}")
                    print("-" * 70)
                    for p in posts:
                        title = (p['title'] or '')[:28]
                        creator = (p['creator_name'] or '')[:18]
                        print(f"{p['id']:<6} {p['status']:<12} {creator:<20} {title}")
                else:
                    print("No Instagram posts found")
                continue
            
            # Assume it's a URL
            if 'instagram.com' not in user_input:
                print("   Not a valid Instagram URL")
                continue
            
            # Optional: Ask for custom title
            custom_title = input("   Custom title (press Enter to auto-detect): ").strip() or None
            
            # Optional: Ask for category
            print("   Categories: training, race_recap, nutrition, athlete_profile, gear, other")
            category = input("   Category (press Enter for 'other'): ").strip() or 'other'
            
            post_id = manager.add_post(user_input, custom_title=custom_title, category=category)
            
            if post_id:
                print(f"   ✓ Added post (ID: {post_id})")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"   Error: {e}")


def main():
    manager = InstagramManager()
    manager.connect_db()
    
    try:
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()
            
            if command == 'add' and len(sys.argv) > 2:
                url = sys.argv[2]
                print(f"Adding Instagram post: {url}")
                post_id = manager.add_post(url)
                if post_id:
                    print(f"✓ Added (ID: {post_id})")
                    
            elif command == 'list':
                posts = manager.list_posts()
                if posts:
                    print(f"\n{'ID':<6} {'Status':<12} {'Creator':<20} {'Title':<30}")
                    print("-" * 70)
                    for p in posts:
                        title = (p['title'] or '')[:28]
                        creator = (p['creator_name'] or '')[:18]
                        print(f"{p['id']:<6} {p['status']:<12} {creator:<20} {title}")
                else:
                    print("No Instagram posts found")
            else:
                print("Usage:")
                print("  python instagram_manager.py              # Interactive mode")
                print("  python instagram_manager.py add <url>    # Add single post")
                print("  python instagram_manager.py list         # List saved posts")
        else:
            interactive_mode(manager)
    
    finally:
        manager.close_db()


if __name__ == "__main__":
    main()
