"""
View content discovered in database
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

def view_recent_content(limit=20):
    """View recent content from database"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get content with creator info, sorted by engagement score
    cursor.execute("""
        SELECT 
            ci.id,
            ci.title,
            ci.platform,
            ci.view_count,
            ci.like_count,
            ci.comment_count,
            ci.engagement_score,
            ci.published_date,
            ci.url,
            c.name as creator_name,
            c.follower_count
        FROM content_items ci
        LEFT JOIN creators c ON ci.creator_id = c.id
        WHERE ci.status = 'discovered'
        ORDER BY ci.engagement_score DESC NULLS LAST
        LIMIT %s;
    """, (limit,))
    
    items = cursor.fetchall()
    
    print("\n" + "="*100)
    print(f"TOP {limit} HYROX VIDEOS BY ENGAGEMENT SCORE")
    print("="*100 + "\n")
    
    for i, item in enumerate(items, 1):
        print(f"{i}. {item['title'][:60]}")
        print(f"   Creator: {item['creator_name']} ({item['follower_count']:,} subscribers)")
        print(f"   Views: {item['view_count']:,} | Likes: {item['like_count']:,} | Comments: {item['comment_count']:,}")
        engagement = item['engagement_score'] if item['engagement_score'] else 0
        print(f"   Engagement Score: {engagement:,.2f}")
        print(f"   Published: {item['published_date'].strftime('%Y-%m-%d')}")
        print(f"   URL: {item['url']}")
        print()
    
    # Summary stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total_videos,
            COUNT(DISTINCT creator_id) as total_creators,
            SUM(view_count) as total_views,
            AVG(view_count) as avg_views
        FROM content_items
        WHERE platform = 'youtube' AND status = 'discovered';
    """)
    
    stats = cursor.fetchone()
    
    print("="*100)
    print("DATABASE SUMMARY")
    print("="*100)
    print(f"Total videos: {stats['total_videos']}")
    print(f"Unique creators: {stats['total_creators']}")
    print(f"Total views: {stats['total_views']:,}")
    print(f"Average views per video: {stats['avg_views']:,.0f}")
    print("="*100 + "\n")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    view_recent_content(limit=20)