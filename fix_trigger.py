"""
Fix the engagement score trigger for PostgreSQL 17
"""

import psycopg2
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

def fix_trigger():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    print("Fixing engagement score trigger...")
    
    # Drop old trigger and function
    cursor.execute("DROP TRIGGER IF EXISTS content_engagement_trigger ON content_items;")
    cursor.execute("DROP FUNCTION IF EXISTS update_engagement_score();")
    cursor.execute("DROP FUNCTION IF EXISTS calculate_engagement_score(INTEGER, INTEGER, INTEGER, DECIMAL, INTEGER);")
    
    print("✓ Dropped old trigger and functions")
    
    # Recreate function with proper type casting
    sql1 = """
        CREATE OR REPLACE FUNCTION calculate_engagement_score(
            views INTEGER,
            likes INTEGER,
            comments INTEGER,
            creator_credibility DECIMAL,
            days_old INTEGER
        )
        RETURNS DECIMAL AS $$
        BEGIN
            RETURN (
                (views * 1.0) + 
                (likes * 5.0) + 
                (comments * 10.0)
            ) * creator_credibility * (1.0 / (1.0 + days_old * 0.1));
        END;
        $$ LANGUAGE plpgsql;
    """
    cursor.execute(sql1)
    print("✓ Created calculate_engagement_score function")
    
    # Recreate trigger function - FIXED VERSION
    sql2 = """
        CREATE OR REPLACE FUNCTION update_engagement_score()
        RETURNS TRIGGER AS $$
        DECLARE
            days_since_publish INTEGER;
        BEGIN
            -- Calculate days since publication - correct syntax for PostgreSQL 17
            days_since_publish := (CURRENT_DATE - NEW.published_date::DATE);
            
            NEW.engagement_score := calculate_engagement_score(
                NEW.view_count,
                NEW.like_count,
                NEW.comment_count,
                COALESCE((SELECT credibility_score FROM creators WHERE id = NEW.creator_id), 0.5),
                days_since_publish
            );
            NEW.updated_at := CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    cursor.execute(sql2)
    print("✓ Created update_engagement_score trigger function")
    
    # Recreate trigger
    sql3 = """
        CREATE TRIGGER content_engagement_trigger
        BEFORE INSERT OR UPDATE OF view_count, like_count, comment_count
        ON content_items
        FOR EACH ROW
        EXECUTE FUNCTION update_engagement_score();
    """
    cursor.execute(sql3)
    print("✓ Created trigger on content_items table")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\n" + "="*50)
    print("✓ Trigger fixed successfully!")
    print("="*50)
    print("\nYou can now run: python youtube_discovery.py")

if __name__ == "__main__":
    try:
        fix_trigger()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()