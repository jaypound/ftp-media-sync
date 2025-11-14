#!/usr/bin/env python3
"""
Run the export status tracking migration
"""
import os
import sys

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from database import db_manager

def run_migration():
    """Run the export status tracking migration"""
    try:
        # Check if database is connected
        if not db_manager.connected:
            print("Connecting to database...")
            db_manager.connect()
        
        if not db_manager.connected:
            print("Failed to connect to database")
            return False
        
        # Read migration file
        migration_path = os.path.join(current_dir, 'migrations', 'add_export_status_tracking.sql')
        print(f"Reading migration from: {migration_path}")
        
        with open(migration_path, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            print("Executing migration...")
            cursor.execute(migration_sql)
            
            # Check if columns were added
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'generated_default_videos' 
                AND column_name IN ('source_export_status', 'target_export_status')
                ORDER BY column_name
            """)
            
            added_columns = [row['column_name'] for row in cursor.fetchall()]
            print(f"Added columns: {added_columns}")
            
            conn.commit()
            cursor.close()
            
            print("✅ Migration completed successfully!")
            print("\nAdded columns:")
            print("  - source_export_status")
            print("  - source_export_error")
            print("  - source_export_timestamp")
            print("  - target_export_status")
            print("  - target_export_error")
            print("  - target_export_timestamp")
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Migration failed: {str(e)}")
            raise
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    finally:
        if 'conn' in locals():
            db_manager._put_connection(conn)

if __name__ == "__main__":
    print("\n=== Export Status Tracking Migration ===")
    print("This will add columns to track export success/failure for each server.")
    print()
    
    response = input("Do you want to proceed? (y/n): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        sys.exit(0)
    
    print("\nRunning migration...")
    success = run_migration()
    
    if not success:
        print("\nTo manually run the migration, execute:")
        print("  psql -U your_user -d your_database -f migrations/add_export_status_tracking.sql")