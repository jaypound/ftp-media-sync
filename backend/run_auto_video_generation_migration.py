#!/usr/bin/env python3
"""
Run the auto video generation migration
This creates tables needed for automatic fill graphics video generation during meetings
"""
import os
import sys
import logging
from pathlib import Path

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from database import db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the auto video generation migration"""
    try:
        # Check if database is connected
        if not db_manager.connected:
            logger.info("Connecting to database...")
            db_manager.connect()
        
        if not db_manager.connected:
            logger.error("Failed to connect to database")
            return False
        
        # Read migration file
        migration_path = Path(__file__).parent / 'migrations' / 'add_auto_video_generation_tables.sql'
        logger.info(f"Reading migration from: {migration_path}")
        
        with open(migration_path, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            logger.info("Executing migration...")
            cursor.execute(migration_sql)
            
            # Commit the migration first
            conn.commit()
            
            # Verify tables were created
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('auto_generation_config', 'meeting_video_generations')
                ORDER BY table_name
            """)
            
            created_tables = [row['table_name'] for row in cursor.fetchall()]
            logger.info(f"Created tables: {created_tables}")
            
            # Check if columns were added to generated_default_videos
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'generated_default_videos' 
                AND column_name IN ('generation_status', 'auto_generated', 'meeting_id')
                ORDER BY column_name
            """)
            
            added_columns = [row['column_name'] for row in cursor.fetchall()]
            logger.info(f"Added columns to generated_default_videos: {added_columns}")
            
            # Check default config
            cursor.execute("""
                SELECT enabled, start_hour, end_hour, weekdays_only, delay_minutes 
                FROM auto_generation_config 
                LIMIT 1
            """)
            config = cursor.fetchone()
            if config:
                logger.info("Default configuration created successfully")
                logger.info(f"  Enabled: {config['enabled']}")
                logger.info(f"  Hours: {config['start_hour']}:00 - {config['end_hour']}:00")
                logger.info(f"  Weekdays only: {config['weekdays_only']}")
                logger.info(f"  Delay: {config['delay_minutes']} minutes after meeting start")
            
            cursor.close()
            
            logger.info("Migration completed successfully!")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration failed: {str(e)}", exc_info=True)
            import traceback
            traceback.print_exc()
            raise
        finally:
            db_manager._put_connection(conn)
            
    except Exception as e:
        logger.error(f"Error running migration: {str(e)}")
        return False

if __name__ == "__main__":
    print("\n=== Auto Video Generation Migration ===")
    print("This will create tables for automatic fill graphics video generation.")
    print()
    
    response = input("Do you want to proceed? (y/n): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        sys.exit(0)
    
    print("\nRunning migration...")
    success = run_migration()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("\nCreated tables:")
        print("  - auto_generation_config")
        print("  - meeting_video_generations")
        print("\nAdded columns to generated_default_videos:")
        print("  - generation_status")
        print("  - auto_generated") 
        print("  - meeting_id")
        print("\nYou can now use the automatic video generation features.")
    else:
        print("\n❌ Migration failed! Check the logs for details.")
        print("\nTo manually run the migration, execute:")
        print("  psql -U your_user -d your_database -f migrations/add_auto_video_generation_tables.sql")