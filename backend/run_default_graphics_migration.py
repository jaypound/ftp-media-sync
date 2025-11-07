#!/usr/bin/env python3
"""
Run the default graphics tables migration
"""
import psycopg2
from database_postgres import PostgreSQLDatabaseManager
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the default graphics tables migration"""
    try:
        # Initialize database connection
        db = PostgreSQLDatabaseManager()
        db.connect()
        
        if not db.connected:
            logger.error("Failed to connect to database")
            return False
        
        # Get a direct connection for the migration
        conn = db._get_connection()
        cursor = conn.cursor()
        
        try:
            # Read and execute the migration SQL
            migration_path = os.path.join(os.path.dirname(__file__), 'migrations', 'add_default_graphics_tables.sql')
            with open(migration_path, 'r') as f:
                migration_sql = f.read()
            
            logger.info("Executing default graphics tables migration...")
            cursor.execute(migration_sql)
            
            # Verify tables were created
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('default_graphics', 'generated_default_videos', 'default_graphics_usage')
                ORDER BY table_name
            """)
            
            created_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Created tables: {created_tables}")
            
            # Check if trigger was created
            cursor.execute("""
                SELECT trigger_name 
                FROM information_schema.triggers 
                WHERE trigger_schema = 'public' 
                AND trigger_name = 'update_default_graphic_status'
            """)
            
            triggers = cursor.fetchall()
            if triggers:
                logger.info("Trigger 'update_default_graphic_status' created successfully")
            
            conn.commit()
            logger.info("Migration completed successfully!")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration failed: {str(e)}")
            return False
            
        finally:
            db._put_connection(conn)
            
    except Exception as e:
        logger.error(f"Error running migration: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Starting default graphics tables migration...")
    
    success = run_migration()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("\nCreated tables:")
        print("  - default_graphics")
        print("  - generated_default_videos")
        print("  - default_graphics_usage")
        print("\nYou can now use the Fill Graphics database features.")
    else:
        print("\n❌ Migration failed! Check the logs for details.")
        print("\nIf the tables already exist, you may need to drop them first.")
        print("To drop existing tables, run:")
        print("  DROP TABLE IF EXISTS default_graphics_usage CASCADE;")
        print("  DROP TABLE IF EXISTS generated_default_videos CASCADE;")
        print("  DROP TABLE IF EXISTS default_graphics CASCADE;")
        print("  DROP FUNCTION IF EXISTS update_graphic_status() CASCADE;")