"""
Hyrox Weekly - Database Setup and Connection
Run this after creating your RDS instance
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'your-rds-endpoint.amazonaws.com'),
    'database': os.getenv('DB_NAME', 'postgres'),
    'user': os.getenv('DB_USER', 'hyroxadmin'),
    'password': os.getenv('DB_PASSWORD', 'your-password'),
    'port': os.getenv('DB_PORT', '5432')
}

# Debug: Print what was loaded (hide password)
print(f"Loading DB config from .env file:")
print(f"  DB_HOST: {DB_CONFIG['host']}")
print(f"  DB_NAME: {DB_CONFIG['database']}")
print(f"  DB_USER: {DB_CONFIG['user']}")
print(f"  DB_PASSWORD: {'*' * len(DB_CONFIG['password']) if DB_CONFIG['password'] != 'your-password' else 'NOT SET'}")
print(f"  DB_PORT: {DB_CONFIG['port']}")
print()

def get_connection():
    """Create and return database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise

def initialize_database(schema_file='schema.sql'):
    """Initialize database with schema"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Read and execute schema file
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        cursor.execute(schema_sql)
        conn.commit()
        print("✓ Database schema initialized successfully")
        
        # Verify tables created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        print(f"\n✓ Created {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error initializing database: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def test_connection():
    """Test database connection and basic operations"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✓ Connected to PostgreSQL")
        print(f"  Version: {version['version'][:50]}...")
        
        # Test insert - add a sample creator
        cursor.execute("""
            INSERT INTO creators (name, platform, platform_id, follower_count)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name;
        """, ('Test Creator', 'youtube', 'test123', 10000))
        
        result = cursor.fetchone()
        conn.commit()
        print(f"\n✓ Test insert successful: Created creator #{result['id']}")
        
        # Clean up test data
        cursor.execute("DELETE FROM creators WHERE platform_id = 'test123';")
        conn.commit()
        print("✓ Test cleanup complete")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Connection test failed: {e}")
        return False

def create_env_template():
    """Create .env template file"""
    env_template = """# Hyrox Weekly - Environment Variables
# Copy this to .env and fill in your values

# Database (AWS RDS)
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_NAME=postgres
DB_USER=hyroxadmin
DB_PASSWORD=your-secure-password
DB_PORT=5432

# API Keys (get these later)
YOUTUBE_API_KEY=your-youtube-api-key
PODCAST_INDEX_KEY=your-podcast-index-key
PODCAST_INDEX_SECRET=your-podcast-index-secret
BEEHIIV_API_KEY=your-beehiiv-api-key
BEEHIIV_PUBLICATION_ID=your-publication-id

# AWS (for Lambda deployment)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO
"""
    
    with open('.env.template', 'w') as f:
        f.write(env_template)
    print("✓ Created .env.template - copy to .env and fill in your values")

class DatabaseManager:
    """Helper class for database operations"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        self.conn = get_connection()
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.cursor.close()
        self.conn.close()

# Usage examples
def example_queries():
    """Example queries for common operations"""
    
    with DatabaseManager() as cursor:
        
        # Insert a creator
        cursor.execute("""
            INSERT INTO creators (name, platform, platform_id, follower_count)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, ('Hunter McIntyre', 'youtube', 'UCxxxxx', 50000))
        creator_id = cursor.fetchone()['id']
        
        # Insert content
        cursor.execute("""
            INSERT INTO content_items 
            (creator_id, url, title, platform, content_type, published_date, 
             view_count, like_count, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            creator_id,
            'https://youtube.com/watch?v=xxxxx',
            'Hyrox Training Tips',
            'youtube',
            'video',
            datetime.now(),
            5000,
            250,
            'training'
        ))
        content_id = cursor.fetchone()['id']
        
        # Query content for curation
        cursor.execute("""
            SELECT * FROM content_for_curation
            LIMIT 10;
        """)
        results = cursor.fetchall()
        
        return results

if __name__ == "__main__":
    print("Hyrox Weekly - Database Setup\n")
    print("=" * 50)
    
    # Step 1: Create env template
    print("\n[Step 1] Creating environment template...")
    create_env_template()
    
    # Step 2: Test basic connection
    print("\n[Step 2] Testing database connection...")
    print("(Make sure you've updated .env with your RDS endpoint)")
    input("Press Enter when ready...")
    
    # Just test connection, don't insert yet
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✓ Connected to PostgreSQL")
        print(f"  Version: {version['version'][:50]}...")
        cursor.close()
        conn.close()
        
        print("\n[Step 3] Initializing database schema...")
        input("Press Enter to create tables...")
        
        if initialize_database():
            print("\n[Step 4] Running connection test with sample data...")
            if test_connection():
                print("✓ Full connection test passed")
            
            print("\n" + "=" * 50)
            print("✓ Database setup complete!")
            print("\nNext steps:")
            print("1. Your database is ready for content")
            print("2. Move on to building the YouTube discovery script")
            print("3. Set up your API keys in .env file")
        else:
            print("\n✗ Schema initialization failed")
            
    except Exception as e:
        print(f"\n✗ Connection test failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check your RDS endpoint in .env")
        print("2. Verify security group allows your IP")
        print("3. Confirm username/password are correct")