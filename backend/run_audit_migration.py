#!/usr/bin/env python3
"""Run the metadata audit log migration"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import getpass
from pathlib import Path

# Use the same connection approach as the app
default_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
connection_string = os.getenv('DATABASE_URL', default_conn)

def run_migration():
    """Run the metadata audit log migration"""
    
    migration_file = Path(__file__).parent / 'migrations' / 'add_metadata_audit_log.sql'
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    try:
        # Connect to database
        print("Connecting to database...")
        print(f"Connection string: {connection_string}")
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        
        # Read migration file
        print(f"Reading migration file: {migration_file}")
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        print("Executing migration...")
        cursor.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        
        # Verify objects were created
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_name = 'metadata_audit_log'
        """)
        if cursor.fetchone():
            print("✓ Table 'metadata_audit_log' created")
            
        cursor.execute("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_name = 'log_metadata_change'
        """)
        if cursor.fetchone():
            print("✓ Function 'log_metadata_change' created")
            
        cursor.execute("""
            SELECT table_name FROM information_schema.views 
            WHERE table_name = 'v_metadata_audit_log'
        """)
        if cursor.fetchone():
            print("✓ View 'v_metadata_audit_log' created")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.errors.DuplicateObject as e:
        print(f"⚠️  Some objects already exist: {e}")
        print("This is normal if the migration was partially applied.")
        return True
        
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        return False

if __name__ == "__main__":
    if run_migration():
        print("\n✅ Metadata audit log migration completed!")
        print("The system will now track all changes to expiration and go-live dates.")
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above and try again.")