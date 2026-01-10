"""
Run database migrations for Hyrox Weekly
Usage: python run_migration.py [migration_file]
"""

import psycopg2
import os
import sys
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

def run_migration(migration_file):
    """Run a single migration file"""
    print(f"Running migration: {migration_file}")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        with open(migration_file, 'r') as f:
            sql = f.read()

        cursor.execute(sql)
        conn.commit()

        print("Migration completed successfully!")

        # Show created tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        print(f"\nDatabase now has {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    migration_file = sys.argv[1] if len(sys.argv) > 1 else "migrations/001_premium_schema.sql"
    run_migration(migration_file)
