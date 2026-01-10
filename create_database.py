"""
Create the hyrox_weekly database
Run this once to create the database, then update .env to use it
"""

import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# Connect to default postgres database
conn_params = {
    'host': os.getenv('DB_HOST'),
    'database': 'postgres',  # Connect to default database
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

print("Connecting to PostgreSQL server...")
print(f"Host: {conn_params['host']}")

try:
    # Connect to default database
    conn = psycopg2.connect(**conn_params)
    conn.autocommit = True  # Required for CREATE DATABASE
    cursor = conn.cursor()
    
    # Check if database exists
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='hyrox_weekly'")
    exists = cursor.fetchone()
    
    if exists:
        print("✓ Database 'hyrox_weekly' already exists")
    else:
        print("Creating database 'hyrox_weekly'...")
        cursor.execute("CREATE DATABASE hyrox_weekly")
        print("✓ Database 'hyrox_weekly' created successfully")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*50)
    print("✓ Setup complete!")
    print("\nNext steps:")
    print("1. Update your .env file:")
    print("   Change: DB_NAME=postgres")
    print("   To:     DB_NAME=hyrox_weekly")
    print("2. Run: python db_setup.py")
    
except Exception as e:
    print(f"✗ Error: {e}")
    print("\nTroubleshooting:")
    print("1. Make sure DB_NAME=postgres in your .env")
    print("2. Verify your RDS endpoint, username, and password")