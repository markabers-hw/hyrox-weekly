"""
Hyrox Weekly Newsletter Generator

This script:
1. Pulls selected content from the database (YouTube + Podcasts)
2. Generates a beautiful HTML newsletter
3. Creates a preview for review
4. Saves edition to database
5. Outputs HTML for manual upload to Beehiiv
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from jinja2 import Template

load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}


# Newsletter HTML Template with Podcast Support
NEWSLETTER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hyrox Weekly - {{ edition_date }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a1a1a;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 640px;
            margin: 0 auto;
            background-color: #ffffff;
        }
        
        .header {
            background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
            padding: 40px 30px;
            text-align: center;
        }
        
        .header h1 {
            color: #ffffff;
            font-size: 36px;
            font-weight: 800;
            letter-spacing: -1px;
            margin-bottom: 8px;
        }
        
        .header .tagline {
            color: rgba(255, 255, 255, 0.9);
            font-size: 16px;
            font-weight: 400;
        }
        
        .header .edition-date {
            color: rgba(255, 255, 255, 0.8);
            font-size: 14px;
            margin-top: 12px;
        }
        
        .intro {
            padding: 30px;
            background-color: #fafafa;
            border-bottom: 1px solid #eee;
        }
        
        .intro p {
            font-size: 16px;
            color: #444;
        }
        
        .section {
            padding: 30px;
            border-bottom: 1px solid #eee;
        }
        
        .section-title {
            font-size: 14px;
            font-weight: 700;
            color: #ff6b35;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #ff6b35;
        }
        
        .content-item {
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
            padding-bottom: 24px;
            border-bottom: 1px solid #f0f0f0;
        }
        
        .content-item:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }
        
        .content-thumbnail {
            flex-shrink: 0;
            width: 120px;
            height: 90px;
            border-radius: 8px;
            overflow: hidden;
        }
        
        .content-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .content-details {
            flex-grow: 1;
        }
        
        .content-title {
            font-size: 16px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 6px;
            line-height: 1.3;
        }
        
        .content-title a {
            color: #1a1a1a;
            text-decoration: none;
        }
        
        .content-title a:hover {
            color: #ff6b35;
        }
        
        .content-creator {
            font-size: 13px;
            color: #666;
            margin-bottom: 8px;
        }
        
        .content-stats {
            font-size: 12px;
            color: #888;
            margin-bottom: 8px;
        }
        
        .platform-links {
            margin-top: 10px;
        }
        
        .platform-link {
            display: inline-block;
            padding: 6px 12px;
            margin-right: 8px;
            margin-bottom: 4px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-decoration: none;
            color: #fff;
        }
        
        .platform-link.spotify {
            background-color: #1DB954;
        }
        
        .platform-link.apple {
            background-color: #8e44ad;
        }
        
        .platform-link.youtube {
            background-color: #FF0000;
        }
        
        .content-note {
            margin-top: 10px;
            padding: 10px 12px;
            background-color: #f8f9fa;
            border-left: 3px solid #ff6b35;
            font-size: 14px;
            color: #555;
            font-style: italic;
        }
        
        .podcast-section {
            background-color: #f9f5ff;
        }
        
        .podcast-section .section-title {
            color: #8e44ad;
            border-bottom-color: #8e44ad;
        }
        
        .cta-section {
            padding: 40px 30px;
            text-align: center;
            background: linear-gradient(135deg, #1a1a1a 0%, #333 100%);
        }
        
        .cta-section h3 {
            color: #ffffff;
            font-size: 20px;
            margin-bottom: 12px;
        }
        
        .cta-section p {
            color: rgba(255, 255, 255, 0.8);
            font-size: 14px;
            margin-bottom: 20px;
        }
        
        .cta-button {
            display: inline-block;
            padding: 12px 28px;
            background-color: #ff6b35;
            color: #ffffff;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 14px;
        }
        
        .footer {
            padding: 30px;
            text-align: center;
            background-color: #1a1a1a;
            color: rgba(255, 255, 255, 0.6);
            font-size: 12px;
        }
        
        .footer a {
            color: #ff6b35;
            text-decoration: none;
        }
        
        .social-links {
            margin-bottom: 16px;
        }
        
        .social-links a {
            display: inline-block;
            margin: 0 8px;
            color: rgba(255, 255, 255, 0.8);
            text-decoration: none;
        }
        
        /* Mobile responsive */
        @media (max-width: 480px) {
            .header {
                padding: 30px 20px;
            }
            
            .header h1 {
                font-size: 28px;
            }
            
            .section {
                padding: 20px;
            }
            
            .content-item {
                flex-direction: column;
            }
            
            .content-thumbnail {
                width: 100%;
                height: 180px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>HYROX WEEKLY</h1>
            <div class="tagline">Your Weekly Dose of Hybrid Fitness</div>
            <div class="edition-date">Edition {{ edition_number }} • {{ edition_date }}</div>
        </div>
        
        <!-- Introduction -->
        <div class="intro">
            <p>{{ intro_text }}</p>
        </div>
        
        <!-- Video Sections -->
        {% for category, items in video_content.items() %}
        {% if items %}
        <div class="section">
            <h2 class="section-title">{{ category }}</h2>
            
            {% for item in items %}
            <div class="content-item">
                {% if item.thumbnail_url %}
                <div class="content-thumbnail">
                    <a href="{{ item.url }}" target="_blank">
                        <img src="{{ item.thumbnail_url }}" alt="{{ item.title }}">
                    </a>
                </div>
                {% endif %}
                <div class="content-details">
                    <h3 class="content-title">
                        <a href="{{ item.url }}" target="_blank">{{ item.title }}</a>
                    </h3>
                    <div class="content-creator">
                        by {{ item.creator_name }} • YouTube
                    </div>
                    <div class="content-stats">
                        {{ "{:,}".format(item.view_count or 0) }} views • {{ "{:,}".format(item.like_count or 0) }} likes
                    </div>
                    <div class="platform-links">
                        <a href="{{ item.url }}" target="_blank" class="platform-link youtube">▶️ Watch on YouTube</a>
                    </div>
                    {% if item.clean_note %}
                    <div class="content-note">
                        {{ item.clean_note }}
                    </div>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
        {% endfor %}
        
        <!-- Podcast Section -->
        {% if podcasts %}
        <div class="section podcast-section">
            <h2 class="section-title">🎙️ Podcasts We're Listening To</h2>
            
            {% for item in podcasts %}
            <div class="content-item">
                {% if item.thumbnail_url %}
                <div class="content-thumbnail">
                    <a href="{{ item.url }}" target="_blank">
                        <img src="{{ item.thumbnail_url }}" alt="{{ item.title }}">
                    </a>
                </div>
                {% endif %}
                <div class="content-details">
                    <h3 class="content-title">
                        {{ item.title }}
                    </h3>
                    <div class="content-creator">
                        {{ item.creator_name }}
                    </div>
                    <div class="content-stats">
                        {% if item.duration_display %}⏱️ {{ item.duration_display }}{% endif %}
                    </div>
                    <div class="platform-links">
                        {% if item.spotify_url %}
                        <a href="{{ item.spotify_url }}" target="_blank" class="platform-link spotify">🎧 Spotify</a>
                        {% endif %}
                        {% if item.apple_url %}
                        <a href="{{ item.apple_url }}" target="_blank" class="platform-link apple">🍎 Apple Podcasts</a>
                        {% endif %}
                    </div>
                    {% if item.clean_note %}
                    <div class="content-note">
                        {{ item.clean_note }}
                    </div>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
        
        <!-- CTA Section -->
        <div class="cta-section">
            <h3>Never Miss an Edition</h3>
            <p>Get the best Hyrox content delivered to your inbox every week.</p>
            <a href="https://hyroxweekly.com" class="cta-button">Subscribe Now</a>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <div class="social-links">
                <a href="https://instagram.com/hyroxweekly">Instagram</a>
                <a href="https://hyroxweekly.com">Website</a>
            </div>
            <p>
                You're receiving this because you subscribed to Hyrox Weekly.<br>
                <a href="#">Unsubscribe</a> • <a href="#">Preferences</a>
            </p>
            <p style="margin-top: 12px;">© {{ current_year }} Hyrox Weekly. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""


def get_selected_content():
    """Fetch all content marked as 'selected' for the current edition."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            ci.id,
            ci.title,
            ci.url,
            ci.platform,
            ci.thumbnail_url,
            ci.view_count,
            ci.like_count,
            ci.comment_count,
            ci.duration_seconds,
            ci.category,
            ci.editorial_note,
            ci.published_date,
            ci.engagement_score,
            c.name as creator_name,
            c.follower_count as creator_followers
        FROM content_items ci
        LEFT JOIN creators c ON ci.creator_id = c.id
        WHERE ci.status = 'selected'
        ORDER BY 
            ci.platform,
            CASE ci.category
                WHEN 'race_recap' THEN 1
                WHEN 'training' THEN 2
                WHEN 'nutrition' THEN 3
                WHEN 'athlete_profile' THEN 4
                WHEN 'gear' THEN 5
                ELSE 6
            END,
            ci.engagement_score DESC
    """)
    
    content = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return content


def parse_podcast_links(editorial_note):
    """Extract Spotify and Apple links from editorial note."""
    spotify_url = ""
    apple_url = ""
    clean_note = editorial_note or ""
    
    if editorial_note and "Spotify:" in editorial_note:
        try:
            parts = editorial_note.split("|")
            for part in parts:
                if "Spotify:" in part:
                    spotify_url = part.replace("Spotify:", "").strip()
                elif "Apple:" in part:
                    apple_url = part.replace("Apple:", "").strip()
            # The note was just links, clear it
            clean_note = ""
        except:
            pass
    
    return spotify_url, apple_url, clean_note


def format_duration(seconds):
    """Format duration in seconds to human readable string."""
    if not seconds:
        return ""
    
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} sec"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} min"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def organize_content(content):
    """Organize content into videos and podcasts."""
    category_names = {
        'race_recap': '🏆 Race Recaps',
        'training': '💪 Training & Workouts',
        'nutrition': '🥗 Nutrition & Recovery',
        'athlete_profile': '🌟 Athlete Spotlights',
        'gear': '⚙️ Gear & Equipment',
        'other': '📺 Best of YouTube'
    }
    
    video_content = {}
    podcasts = []
    
    for item in content:
        # Parse podcast links if applicable
        spotify_url, apple_url, clean_note = parse_podcast_links(item.get('editorial_note'))
        item['spotify_url'] = spotify_url
        item['apple_url'] = apple_url
        item['clean_note'] = clean_note
        item['duration_display'] = format_duration(item.get('duration_seconds'))
        
        if item['platform'] == 'podcast':
            podcasts.append(item)
        else:
            # YouTube or other video content
            category = item.get('category') or 'other'
            display_name = category_names.get(category, category_names['other'])
            
            if display_name not in video_content:
                video_content[display_name] = []
            
            video_content[display_name].append(item)
    
    return video_content, podcasts


def generate_intro_text(video_count, podcast_count):
    """Generate intro text for the newsletter."""
    today = datetime.now()
    total = video_count + podcast_count
    
    if podcast_count > 0:
        intro = f"Welcome to this week's edition! We've curated {video_count} videos and {podcast_count} podcast episodes featuring the best Hyrox content from across the internet."
    else:
        intro = f"Welcome to this week's edition! We've curated {total} pieces of the best Hyrox content from across the internet."
    
    intro += " From race recaps to training tips, we've got you covered."
    
    return intro


def get_next_edition_number():
    """Get the next edition number from the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COALESCE(MAX(edition_number), 0) + 1 FROM weekly_editions")
    next_num = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return next_num


def generate_newsletter_html(content, edition_number):
    """Generate the newsletter HTML from template."""
    video_content, podcasts = organize_content(content)
    
    video_count = sum(len(items) for items in video_content.values())
    podcast_count = len(podcasts)
    
    template = Template(NEWSLETTER_TEMPLATE)
    
    html = template.render(
        edition_number=edition_number,
        edition_date=datetime.now().strftime("%B %d, %Y"),
        intro_text=generate_intro_text(video_count, podcast_count),
        video_content=video_content,
        podcasts=podcasts,
        current_year=datetime.now().year
    )
    
    return html


def save_preview(html, filename="newsletter_preview.html"):
    """Save newsletter preview as HTML file."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    return filename


def get_week_dates():
    """Get the start and end dates for the current week (Monday to Sunday)."""
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def create_edition_record(edition_number, content_ids):
    """Save edition record to database with all required fields."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    week_start, week_end = get_week_dates()
    now = datetime.now()
    
    # Check what columns exist in weekly_editions
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'weekly_editions'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cursor.fetchall()]
    
    print(f"   Available columns: {columns}")
    
    # Build dynamic INSERT based on available columns
    insert_columns = ['edition_number', 'publish_date']
    insert_values = [edition_number, now]
    
    if 'week_start_date' in columns:
        insert_columns.append('week_start_date')
        insert_values.append(week_start)
    
    if 'week_end_date' in columns:
        insert_columns.append('week_end_date')
        insert_values.append(week_end)
    
    if 'status' in columns:
        insert_columns.append('status')
        insert_values.append('published')
    
    if 'theme' in columns:
        insert_columns.append('theme')
        insert_values.append(f"Edition {edition_number}")
    
    columns_str = ', '.join(insert_columns)
    placeholders = ', '.join(['%s'] * len(insert_values))
    
    query = f"""
        INSERT INTO weekly_editions ({columns_str})
        VALUES ({placeholders})
        RETURNING id
    """
    
    cursor.execute(query, insert_values)
    edition_id = cursor.fetchone()[0]
    
    # Check if edition_content table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'edition_content'
        )
    """)
    edition_content_exists = cursor.fetchone()[0]
    
    if edition_content_exists:
        for i, content_id in enumerate(content_ids):
            cursor.execute("""
                INSERT INTO edition_content (edition_id, content_id, position)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (edition_id, content_id, i + 1))
    
    # Update content status to 'published'
    cursor.execute("""
        UPDATE content_items 
        SET status = 'published' 
        WHERE id = ANY(%s)
    """, (content_ids,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return edition_id


def main():
    print("=" * 70)
    print("HYROX WEEKLY - Newsletter Generator")
    print("=" * 70)
    
    # Fetch selected content
    print("\n📥 Fetching selected content...")
    content = get_selected_content()
    
    if not content:
        print("\n⚠️  No content selected for this edition!")
        print("   Run the curation dashboard to select content:")
        print("   streamlit run curation_dashboard.py")
        return
    
    print(f"   ✓ Found {len(content)} selected items")
    
    # Show content summary
    video_content, podcasts = organize_content(content)
    video_count = sum(len(items) for items in video_content.values())
    
    print("\n📋 Content Summary:")
    print(f"   🎬 Videos: {video_count}")
    for category, items in video_content.items():
        print(f"      {category}: {len(items)} items")
    print(f"   🎙️ Podcasts: {len(podcasts)}")
    
    # Get edition number
    edition_number = get_next_edition_number()
    print(f"\n📰 Generating Edition #{edition_number}...")
    
    # Generate HTML
    html = generate_newsletter_html(content, edition_number)
    
    # Save preview
    preview_file = save_preview(html)
    print(f"   ✓ Preview saved: {preview_file}")
    
    # Also save a copy with edition number for archives
    archive_file = f"newsletter_edition_{edition_number}.html"
    save_preview(html, archive_file)
    print(f"   ✓ Archive saved: {archive_file}")
    
    # Open preview
    print(f"\n   Opening preview in browser...")
    os.system(f"open {preview_file}")
    
    # Manual upload instructions
    print("\n" + "=" * 70)
    print("REVIEW YOUR NEWSLETTER")
    print("=" * 70)
    
    print("\n📝 Beehiiv Manual Upload Instructions:")
    print("   1. Log into Beehiiv: https://app.beehiiv.com/")
    print("   2. Go to Posts → Create Post")
    print("   3. Build content using their visual editor")
    print("   4. Or upgrade to Scale plan for HTML snippets")
    print("   5. Set subject line and schedule")
    
    response = input("\n💾 Save edition to database and mark content as published? (yes/no): ").strip().lower()
    
    if response == 'yes':
        print("\n📊 Saving to database...")
        content_ids = [item['id'] for item in content]
        edition_id = create_edition_record(edition_number, content_ids)
        print(f"   ✓ Edition #{edition_number} saved (ID: {edition_id})")
        print(f"   ✓ {len(content_ids)} content items marked as published")
    else:
        print("\n📋 Newsletter saved locally only. Content not marked as published.")
    
    print("\n" + "=" * 70)
    print("✓ Newsletter generation complete!")
    print("=" * 70)
    print(f"\nFiles created:")
    print(f"   • {preview_file} (for Beehiiv upload)")
    print(f"   • {archive_file} (for your records)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
