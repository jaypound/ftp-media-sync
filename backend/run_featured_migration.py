#!/usr/bin/env python3
"""
Run the featured field migration for scheduling_metadata table
"""

import psycopg2
import os
import getpass
from pathlib import Path

# Database connection parameters - use same approach as database_postgres.py
DATABASE_URL = os.getenv('DATABASE_URL', f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync')

def run_migration():
    """Run the featured field migration"""
    
    # Get the migration SQL file path
    migration_file = Path(__file__).parent / 'migrations' / 'add_featured_field.sql'
    
    if not migration_file.exists():
        print(f"Error: Migration file not found at {migration_file}")
        return False
    
    try:
        # Connect to the database
        print(f"Connecting to PostgreSQL database...")
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Read and execute the migration SQL
        print("Reading migration SQL...")
        with open(migration_file, 'r') as f:
            sql = f.read()
        
        print("Executing migration...")
        cursor.execute(sql)
        
        # Verify the column was added
        cursor.execute("""
            SELECT column_name, data_type, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'scheduling_metadata' 
            AND column_name = 'featured'
        """)
        
        result = cursor.fetchone()
        if result:
            print(f"✓ Migration successful! Featured column added: {result}")
        else:
            print("⚠ Warning: Could not verify featured column was added")
        
        cursor.close()
        conn.close()
        print("Migration completed successfully!")
        return True
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)