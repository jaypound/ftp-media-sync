#!/usr/bin/env python3
"""
Run the metadata_synced_at migration to add column for tracking
when Castus metadata was last synchronized.
"""

import psycopg2
import os
import getpass
from pathlib import Path

# Database connection parameters - use same approach as database_postgres.py
DATABASE_URL = os.getenv('DATABASE_URL', f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync')

def run_migration():
    """Run the metadata_synced_at migration"""
    
    # Get the migration SQL file path
    migration_file = Path(__file__).parent / 'migrations' / 'add_metadata_synced_at.sql'
    
    if not migration_file.exists():
        print(f"Error: Migration file not found: {migration_file}")
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
            migration_sql = f.read()
        
        print("Executing migration...")
        cursor.execute(migration_sql)
        
        # Verify the column was added
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'scheduling_metadata' 
            AND column_name = 'metadata_synced_at'
        """)
        
        result = cursor.fetchone()
        if result:
            print(f"✅ Successfully added column: {result[0]} ({result[1]})")
        else:
            print("❌ Column was not added successfully")
            return False
        
        # Show current metadata sync status
        cursor.execute("""
            SELECT 
                COUNT(*) as total_assets,
                COUNT(metadata_synced_at) as synced_count,
                COUNT(*) - COUNT(metadata_synced_at) as unsynced_count
            FROM scheduling_metadata
        """)
        
        stats = cursor.fetchone()
        print(f"\nCurrent metadata sync status:")
        print(f"  Total assets in scheduling: {stats[0]}")
        print(f"  Assets with synced metadata: {stats[1]}")
        print(f"  Assets needing sync: {stats[2]}")
        
        # Close the connection
        cursor.close()
        conn.close()
        
        print("\n✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)