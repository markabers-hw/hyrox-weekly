"""
Hyrox Weekly Article Discovery Script

Discovers articles from RSS feeds of fitness/Hyrox sites.
Reddit is handled separately by reddit_discovery.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import requests
import xml.etree.ElementTree as ET
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse
from bs4 import BeautifulSoup

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

# RSS Feeds - Only sources that regularly cover Hyrox
RSS_FEEDS = [
    # Hyrox-specific (always check)
    {'name': 'Hyrox Official', 'url': 'https://hyrox.com/feed/', 'category': 'race_recap'},

    # Functional Fitness sites that cover Hyrox regularly
    {'name': 'Morning Chalk Up', 'url': 'https://morningchalkup.com/feed/', 'category': 'training'},
    {'name': 'BoxRox', 'url': 'https://www.boxrox.com/feed/', 'category': 'training'},
    {'name': 'BarBend', 'url': 'https://barbend.com/feed/', 'category': 'training'},

    # UK sites (Hyrox is popular in UK/Europe)
    {'name': 'Coach Mag', 'url': 'https://www.coachmag.co.uk/feed', 'category': 'training'},
]

# Keywords for relevance matching - strict Hyrox focus
# Primary keywords (strong signal)
HYROX_PRIMARY_KEYWORDS = [
    'hyrox',
    'hybrid fitness race',
    'hunter mcintyre',
    'lauren weeks',
    'roxzone',
    'deka fit',
    'deka mile',
]

# Secondary keywords (only count if combined with fitness context)
HYROX_SECONDARY_KEYWORDS = [
    'hybrid athlete',
    'functional fitness race',
]


class ArticleDiscovery:
    def __init__(self):
        self.headers = {'User-Agent': 'HyroxWeekly/1.0'}
    
    def fetch_rss_feed(self, feed_url, feed_name):
        articles = []
        try:
            response = requests.get(feed_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
            
            if not items:
                print(f"      ⚠️ No items found in feed (might be wrong URL format)")
            
            for item in items:
                article = self._parse_rss_item(item, feed_name)
                if article:
                    articles.append(article)
            
            if articles:
                print(f"      Found {len(articles)} articles")
                
        except ET.ParseError as e:
            print(f"      ❌ XML parse error for {feed_name}: {e} (URL might not be an RSS feed)")
        except Exception as e:
            print(f"      ❌ Error fetching {feed_name}: {e}")
        return articles
    
    def _parse_rss_item(self, item, feed_name):
        try:
            title = self._get_text(item, 'title') or self._get_text(item, '{http://www.w3.org/2005/Atom}title')
            link = self._get_text(item, 'link')
            if not link:
                link_elem = item.find('{http://www.w3.org/2005/Atom}link')
                if link_elem is not None:
                    link = link_elem.get('href', '')
            
            description = self._get_text(item, 'description') or self._get_text(item, '{http://www.w3.org/2005/Atom}summary')
            pub_date = self._get_text(item, 'pubDate') or self._get_text(item, '{http://www.w3.org/2005/Atom}published')
            
            thumbnail = ''
            media = item.find('.//{http://search.yahoo.com/mrss/}content')
            if media is not None:
                thumbnail = media.get('url', '')
            
            if title and link:
                return {
                    'title': self._clean_text(title),
                    'url': link,
                    'description': self._clean_text(description)[:500] if description else '',
                    'published_date': self._parse_date(pub_date),
                    'source': feed_name,
                    'thumbnail_url': thumbnail,
                    'platform': 'article',
                }
        except:
            pass
        return None
    
    def _get_text(self, element, tag):
        child = element.find(tag)
        return child.text if child is not None and child.text else ''
    
    def _clean_text(self, text):
        if not text: return ''
        text = re.sub(r'<[^>]+>', '', text)
        return ' '.join(text.split())
    
    def _parse_date(self, date_str):
        if not date_str: return datetime.now()
        formats = ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z',
                   '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except: pass
        return datetime.now()
    
    def extract_thumbnail(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            og = soup.find('meta', property='og:image')
            if og: return og.get('content', '')
            tw = soup.find('meta', attrs={'name': 'twitter:image'})
            if tw: return tw.get('content', '')
        except: pass
        return ''


class ArticleDatabaseManager:
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
    
    def get_or_create_creator(self, source_name):
        self.cursor.execute("SELECT id FROM creators WHERE name = %s AND platform = 'article'", (source_name,))
        result = self.cursor.fetchone()
        if result: return result['id']
        
        cols, vals = ['name', 'platform'], [source_name, 'article']
        if 'platform_id' in self.creator_columns: cols.append('platform_id'); vals.append(source_name)
        if 'credibility_score' in self.creator_columns: 
            cols.append('credibility_score')
            vals.append(0.7 if any(s in source_name.lower() for s in ['hyrox', 'barbend', 'boxrox']) else 0.5)
        
        self.cursor.execute(f"INSERT INTO creators ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id", vals)
        self.conn.commit()
        return self.cursor.fetchone()['id']
    
    def article_exists(self, url):
        self.cursor.execute("SELECT id FROM content_items WHERE url = %s", (url,))
        return self.cursor.fetchone() is not None
    
    def save_article(self, article, creator_id, category='other'):
        cols = ['title', 'url', 'platform', 'creator_id', 'status']
        vals = [article['title'], article['url'], 'article', creator_id, 'discovered']
        
        if 'thumbnail_url' in self.content_columns: cols.append('thumbnail_url'); vals.append(article.get('thumbnail_url', ''))
        if 'description' in self.content_columns: cols.append('description'); vals.append(article.get('description', ''))
        if 'published_date' in self.content_columns: cols.append('published_date'); vals.append(article.get('published_date'))
        if 'view_count' in self.content_columns: cols.append('view_count'); vals.append(0)
        if 'like_count' in self.content_columns: cols.append('like_count'); vals.append(0)
        if 'comment_count' in self.content_columns: cols.append('comment_count'); vals.append(0)
        if 'category' in self.content_columns: cols.append('category'); vals.append(category)
        if 'editorial_note' in self.content_columns: cols.append('editorial_note'); vals.append(f"Source: {article.get('source', 'Web')}")
        
        self.cursor.execute(f"INSERT INTO content_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))}) RETURNING id", vals)
        self.conn.commit()
        return self.cursor.fetchone()['id']


def is_hyrox_relevant(article):
    """Check if article is relevant to Hyrox - strict matching."""
    text = f"{article.get('title', '')} {article.get('description', '')}".lower()

    # Primary keywords are strong signals - any match is relevant
    if any(kw in text for kw in HYROX_PRIMARY_KEYWORDS):
        return True

    # Secondary keywords need additional context
    if any(kw in text for kw in HYROX_SECONDARY_KEYWORDS):
        # Must also mention race/competition/training context
        context_words = ['race', 'competition', 'training', 'workout', 'fitness']
        if any(ctx in text for ctx in context_words):
            return True

    return False


def get_priority_article_sources():
    """Get priority article sources (RSS feeds) from database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT source_name, source_url FROM priority_sources 
            WHERE platform = 'article' AND is_active = true
        """)
        sources = cursor.fetchall()
        cursor.close()
        conn.close()
        return sources
    except Exception as e:
        print(f"   ⚠️ Could not load priority sources: {e}")
        return []


def main():
    print("=" * 70)
    print("ARTICLE DISCOVERY - Hyrox Content (RSS Feeds)")
    print("=" * 70)
    
    print(f"\n📅 Week: {WEEK_START.strftime('%Y-%m-%d')} to {WEEK_END.strftime('%Y-%m-%d')}")
    
    discovery = ArticleDiscovery()
    db = ArticleDatabaseManager()
    all_articles = []
    
    # Combine default RSS feeds with priority sources
    feeds_to_check = list(RSS_FEEDS)
    
    # Get priority sources from database
    priority_sources = get_priority_article_sources()
    if priority_sources:
        print(f"\n⭐ Priority article sources: {', '.join(s['source_name'] for s in priority_sources)}")
        for source in priority_sources:
            if source.get('source_url'):
                feed_url = source['source_url'].strip()
                
                # Auto-fix common URL patterns
                original_url = feed_url
                
                # Substack URLs - ensure they end with /feed
                if 'substack.com' in feed_url or any(x in feed_url.lower() for x in ['hybridletter', 'newsletter']):
                    if not feed_url.endswith('/feed') and '/feed' not in feed_url:
                        feed_url = feed_url.rstrip('/') + '/feed'
                
                # Generic URLs that don't look like RSS feeds - try appending /feed
                elif not any(pattern in feed_url.lower() for pattern in ['/feed', '/rss', '.xml', 'atom']):
                    if feed_url.count('/') <= 3:  # Likely a homepage URL
                        feed_url = feed_url.rstrip('/') + '/feed'
                
                if feed_url != original_url:
                    print(f"   🔧 Auto-fixed URL: {original_url} → {feed_url}")
                
                feeds_to_check.append({
                    'name': source['source_name'],
                    'url': feed_url,
                    'category': 'other',
                    'is_priority': True
                })
    
    print("\n📥 Fetching RSS feeds...")
    for feed in feeds_to_check:
        is_priority = feed.get('is_priority', False)
        prefix = "⭐" if is_priority else "  "
        print(f"{prefix} -> {feed['name']}...")
        articles = discovery.fetch_rss_feed(feed['url'], feed['name'])
        for a in articles:
            a['default_category'] = feed.get('category', 'other')
            a['is_priority'] = is_priority  # Mark articles from priority sources
        all_articles.extend(articles)
        time.sleep(0.3)
    
    print(f"   Found {len(all_articles)} articles from RSS feeds")
    
    # Deduplicate
    seen = set()
    unique = [a for a in all_articles if a['url'] not in seen and not seen.add(a['url'])]
    print(f"   {len(unique)} unique articles")
    
    # Filter to selected week
    recent = [a for a in unique if WEEK_START <= a.get('published_date', datetime.now()) <= WEEK_END]
    print(f"   {len(recent)} from selected week")
    
    # Filter relevant - BUT priority sources bypass this filter
    relevant = []
    for a in recent:
        if a.get('is_priority'):
            relevant.append(a)  # Priority sources always included
        elif 'hyrox' in a.get('source', '').lower() or is_hyrox_relevant(a):
            relevant.append(a)
    
    priority_count = sum(1 for a in relevant if a.get('is_priority'))
    print(f"   {len(relevant)} Hyrox-relevant articles ({priority_count} from priority sources)")

    if not relevant:
        print("\n   No Hyrox-relevant articles found this week.")
        print("   (This is normal - not every week has Hyrox coverage)")
        return

    print(f"\n💾 Saving {len(relevant)} articles...")
    db.connect()
    
    saved, skipped = 0, 0
    for article in relevant:
        if db.article_exists(article['url']):
            skipped += 1
            continue
        
        creator_id = db.get_or_create_creator(article['source'])
        if not article.get('thumbnail_url'):
            article['thumbnail_url'] = discovery.extract_thumbnail(article['url'])
        
        try:
            db.save_article(article, creator_id, article.get('default_category', 'other'))
            saved += 1
            print(f"   ✅ Saved: {article['title'][:50]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    db.close()
    
    print("\n" + "=" * 70)
    print(f"Article discovery complete! Saved: {saved}, Skipped: {skipped}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
