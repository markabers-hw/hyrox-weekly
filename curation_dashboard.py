"""
Hyrox Weekly Curation Dashboard

Supports: YouTube, Podcasts, Articles, Reddit
"""

import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

CATEGORIES = [
    ('other', '📺 Other'),
    ('race_recap', '🏆 Race Recap'),
    ('training', '💪 Training'),
    ('nutrition', '🥗 Nutrition'),
    ('athlete_profile', '🌟 Athlete Profile'),
    ('gear', '⚙️ Gear'),
]

PLATFORM_CONFIG = {
    'youtube': {'emoji': '🎬', 'name': 'YouTube'},
    'podcast': {'emoji': '🎙️', 'name': 'Podcasts'},
    'article': {'emoji': '📰', 'name': 'Articles'},
    'reddit': {'emoji': '🔗', 'name': 'Reddit'},
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_content(platform_filter='all', status_filter='discovered'):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT ci.id, ci.title, ci.url, ci.platform, ci.thumbnail_url, ci.description,
               ci.view_count, ci.like_count, ci.comment_count, ci.duration_seconds,
               ci.published_date, ci.engagement_score, ci.status, ci.category, ci.editorial_note,
               c.name as creator_name, c.follower_count as creator_followers
        FROM content_items ci
        LEFT JOIN creators c ON ci.creator_id = c.id
        WHERE 1=1
    """
    params = []
    
    if platform_filter != 'all':
        query += " AND ci.platform = %s"
        params.append(platform_filter)
    
    if status_filter != 'all':
        query += " AND ci.status = %s"
        params.append(status_filter)
    
    query += " ORDER BY ci.engagement_score DESC NULLS LAST, ci.published_date DESC"
    
    cursor.execute(query, params)
    content = cursor.fetchall()
    cursor.close()
    conn.close()
    return content


def update_status(content_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE content_items SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (status, content_id))
    conn.commit()
    cursor.close()
    conn.close()


def update_category(content_id, category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE content_items SET category = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (category, content_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT platform, status, COUNT(*) as count FROM content_items GROUP BY platform, status")
    stats = cursor.fetchall()
    cursor.close()
    conn.close()
    return stats


def format_duration(seconds):
    if not seconds: return ""
    seconds = int(seconds)
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600: return f"{seconds // 60} min"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def format_number(num):
    if not num: return "0"
    num = int(num)
    if num >= 1000000: return f"{num/1000000:.1f}M"
    if num >= 1000: return f"{num/1000:.1f}K"
    return str(num)


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


def main():
    st.set_page_config(page_title="Hyrox Weekly - Curation", page_icon="🏋️", layout="wide")
    
    st.title("🏋️ Hyrox Weekly - Content Curation")
    st.markdown("Review and select content for this week's newsletter")
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Dashboard")
        
        stats = get_stats()
        
        discovered = sum(s['count'] for s in stats if s['status'] == 'discovered')
        selected = sum(s['count'] for s in stats if s['status'] == 'selected')
        rejected = sum(s['count'] for s in stats if s['status'] == 'rejected')
        
        st.metric("📥 To Review", discovered)
        st.metric("✅ Selected", selected)
        st.metric("❌ Rejected", rejected)
        
        st.divider()
        st.subheader("Content by Platform")
        
        for platform, config in PLATFORM_CONFIG.items():
            count = sum(s['count'] for s in stats if s['platform'] == platform)
            st.write(f"{config['emoji']} {config['name']}: {count}")
        
        st.divider()
        st.subheader("🔍 Filters")
        
        platform_options = ['all'] + list(PLATFORM_CONFIG.keys())
        platform_filter = st.selectbox(
            "Platform",
            options=platform_options,
            format_func=lambda x: "📺 All Platforms" if x == 'all' else f"{PLATFORM_CONFIG[x]['emoji']} {PLATFORM_CONFIG[x]['name']}"
        )
        
        status_filter = st.selectbox(
            "Status",
            options=['discovered', 'selected', 'rejected', 'all'],
            format_func=lambda x: {'discovered': '📥 To Review', 'selected': '✅ Selected', 'rejected': '❌ Rejected', 'all': '📋 All'}[x]
        )
        
        st.divider()
        if st.button("🔄 Refresh"): st.rerun()
        
        st.divider()
        st.markdown("### 🔧 Discovery Commands")
        st.code("python youtube_discovery.py")
        st.code("python podcast_discovery.py")
        st.code("python article_discovery.py")
        st.code("python reddit_discovery.py")
    
    # Main content
    content = get_content(platform_filter, status_filter)
    
    if not content:
        st.info("No content found. Adjust filters or run discovery scripts.")
        return
    
    st.write(f"Showing {len(content)} items")
    
    for item in content:
        with st.container():
            col1, col2, col3 = st.columns([1, 3, 1])
            
            platform = item['platform']
            config = PLATFORM_CONFIG.get(platform, {'emoji': '📺', 'name': platform})
            
            # Thumbnail
            with col1:
                if item['thumbnail_url']:
                    st.image(item['thumbnail_url'], width=200)
                else:
                    st.markdown(f"### {config['emoji']}")
            
            # Details
            with col2:
                st.markdown(f"### {config['emoji']} [{item['title']}]({item['url']})")
                
                creator = item['creator_name'] or 'Unknown'
                if item['creator_followers']:
                    creator += f" ({format_number(item['creator_followers'])} followers)"
                st.write(f"**{creator}**")
                
                # Platform-specific stats
                if platform == 'youtube':
                    st.write(f"👁️ {format_number(item['view_count'])} views • 👍 {format_number(item['like_count'])} • 💬 {format_number(item['comment_count'])}")
                    if item['duration_seconds']:
                        st.write(f"⏱️ {format_duration(item['duration_seconds'])}")
                
                elif platform == 'podcast':
                    if item['duration_seconds']:
                        st.write(f"⏱️ {format_duration(item['duration_seconds'])}")
                    spotify, apple = parse_podcast_links(item['editorial_note'])
                    cols = st.columns(4)
                    if spotify: cols[0].markdown(f"[🟢 Spotify]({spotify})")
                    if apple: cols[1].markdown(f"[🍎 Apple]({apple})")
                
                elif platform == 'reddit':
                    score = item['view_count'] or 0
                    comments = item['comment_count'] or 0
                    st.write(f"⬆️ {format_number(score)} points • 💬 {format_number(comments)} comments")
                    
                    author, external = parse_reddit_info(item['editorial_note'])
                    if author: st.write(f"Posted by {author}")
                    if external: st.markdown(f"[🔗 External Link]({external})")
                
                elif platform == 'article':
                    if item['published_date']:
                        pub = item['published_date'].strftime('%b %d, %Y') if hasattr(item['published_date'], 'strftime') else str(item['published_date'])[:10]
                        st.write(f"📅 {pub}")
                
                # Engagement score
                score = float(item['engagement_score']) if item['engagement_score'] else 0
                if score > 0:
                    st.progress(min(score / 100000, 1.0), text=f"Score: {score:,.0f}")
                
                # Description
                if item['description']:
                    with st.expander("📝 Description"):
                        st.write(item['description'][:300] + "..." if len(item['description'] or '') > 300 else item['description'])
            
            # Actions
            with col3:
                status_icons = {'discovered': '📥 To Review', 'selected': '✅ Selected', 'rejected': '❌ Rejected', 'published': '📤 Published'}
                st.write(f"**{status_icons.get(item['status'], item['status'])}**")
                
                if item['status'] != 'selected':
                    if st.button("✅ Select", key=f"sel_{item['id']}"):
                        update_status(item['id'], 'selected')
                        st.rerun()
                
                if item['status'] != 'rejected':
                    if st.button("❌ Reject", key=f"rej_{item['id']}"):
                        update_status(item['id'], 'rejected')
                        st.rerun()
                
                if item['status'] in ['selected', 'rejected']:
                    if st.button("↩️ Reset", key=f"res_{item['id']}"):
                        update_status(item['id'], 'discovered')
                        st.rerun()
                
                # Category
                st.write("**Category:**")
                current = item['category'] or 'other'
                cat_opts = [c[0] for c in CATEGORIES]
                cat_labels = {c[0]: c[1] for c in CATEGORIES}
                
                new_cat = st.selectbox(
                    "Cat", options=cat_opts,
                    index=cat_opts.index(current) if current in cat_opts else 0,
                    format_func=lambda x: cat_labels[x],
                    key=f"cat_{item['id']}",
                    label_visibility="collapsed"
                )
                if new_cat != current:
                    update_category(item['id'], new_cat)
                    st.rerun()
            
            st.divider()
    
    st.markdown("---")
    st.markdown("### 🚀 Generate Newsletter")
    st.code("python newsletter_generator.py")


if __name__ == "__main__":
    main()
