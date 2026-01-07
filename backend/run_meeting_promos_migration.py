#!/usr/bin/env python3
"""
Run the meeting promos migration
"""

import os
import psycopg2
from database import db_manager

def run_migration():
    """Run the meeting promos migration"""
    migration_file = os.path.join(os.path.dirname(__file__), 'migrations', 'add_meeting_promos_table.sql')
    
    if not os.path.exists(migration_file):
        print(f"Migration file not found: {migration_file}")
        return False
        
    # Read the migration SQL
    with open(migration_file, 'r') as f:
        migration_sql = f.read()
    
    try:
        # Get a connection from the database manager
        conn = db_manager._get_connection()
        cursor = conn.cursor()
        
        print("Running meeting promos migration...")
        
        # Execute the migration
        cursor.execute(migration_sql)
        
        # Commit the changes
        conn.commit()
        
        print("Migration completed successfully!")
        print("Created tables:")
        print("  - meeting_promos")
        print("  - meeting_promo_settings")
        print("Added initial promo: 260107_PMO_ATL DIRECT.mp4")
        
        # Verify the tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('meeting_promos', 'meeting_promo_settings')
        """)
        
        tables = cursor.fetchall()
        print(f"\nVerified tables exist: {[t[0] for t in tables]}")
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"Error running migration: {e}")
        return False
    finally:
        if conn:
            db_manager._put_connection(conn)

if __name__ == "__main__":
    # Ensure we're using PostgreSQL
    os.environ['USE_POSTGRESQL'] = 'true'
    
    success = run_migration()
    exit(0 if success else 1)