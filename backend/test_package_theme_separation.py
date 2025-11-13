#!/usr/bin/env python3
"""Test script to verify package theme separation in content rotation"""

import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')
load_dotenv(env_path)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/test_pkg_theme_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',  # Use localhost for local development
    'database': 'ftp_media_sync',
    'user': os.getenv('USER', 'jaypound'),
    'password': '',  # Usually no password for local development
    'port': 5432
}

def get_db_connection():
    """Get a database connection"""
    # Check if we should use PostgreSQL from env
    use_postgresql = os.getenv('USE_POSTGRESQL', '').lower() == 'true'
    if not use_postgresql:
        logger.error("PostgreSQL is not enabled in environment variables")
        return None
    
    # First try using db_manager if it exists
    try:
        from db_manager import DatabaseManager
        db_manager = DatabaseManager()
        conn = db_manager._get_connection()
        logger.info("Successfully connected using DatabaseManager")
        return conn
    except Exception as e:
        logger.debug(f"Could not use DatabaseManager: {e}")
    
    # Fallback to direct connection
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        conn.set_session(autocommit=False)
        logger.info("Successfully connected directly to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None

def analyze_schedule_for_pkg_themes(conn, schedule_date=None):
    """Analyze a schedule for package theme conflicts"""
    try:
        cursor = conn.cursor()
        
        # Use today's schedule if not specified
        if schedule_date is None:
            schedule_date = datetime.now().date()
        
        # Get all scheduled items for the date
        query = """
            SELECT 
                si.id,
                si.scheduled_start_time,
                si.scheduled_duration_seconds as duration_seconds,
                si.sequence_number,
                a.content_title as title,
                a.content_type,
                a.theme,
                a.duration_category
            FROM scheduled_items si
            JOIN assets a ON si.asset_id = a.id
            JOIN schedules sc ON si.schedule_id = sc.id
            WHERE sc.air_date = %s
            ORDER BY si.sequence_number
        """
        
        cursor.execute(query, (schedule_date,))
        items = cursor.fetchall()
        
        if not items:
            logger.info(f"No scheduled items found for {schedule_date}")
            return
        
        logger.info(f"\nAnalyzing schedule for {schedule_date}")
        logger.info(f"Total items: {len(items)}")
        
        # Track package themes and check for conflicts
        pkg_conflicts = []
        last_pkg_theme = None
        last_pkg_index = -1
        
        for i, item in enumerate(items):
            # Use scheduled_start_time if available, otherwise just show sequence
            if item['scheduled_start_time']:
                time_str = str(item['scheduled_start_time'])
            else:
                time_str = f"Seq #{item['sequence_number']:04d}"
            
            # Log the item details
            logger.info(f"{time_str} - {item['content_type']:4} - {item['duration_category']:10} - "
                       f"{item['theme'] or 'NO_THEME':20} - {item['title'][:50]}")
            
            # Check for package theme conflicts
            if item['content_type'] == 'pkg' and item['theme']:
                if last_pkg_theme and last_pkg_theme.lower() == item['theme'].lower():
                    # Check if there's a long_form between them
                    has_longform = False
                    for j in range(last_pkg_index + 1, i):
                        if items[j]['duration_category'] == 'long_form':
                            has_longform = True
                            break
                    
                    if not has_longform:
                        conflict_info = {
                            'first_pkg': items[last_pkg_index],
                            'second_pkg': item,
                            'items_between': i - last_pkg_index - 1
                        }
                        pkg_conflicts.append(conflict_info)
                        logger.warning(f"❌ CONFLICT: Packages with theme '{item['theme']}' not separated by long_form!")
                
                last_pkg_theme = item['theme']
                last_pkg_index = i
        
        # Report conflicts
        if pkg_conflicts:
            logger.error(f"\n🚨 Found {len(pkg_conflicts)} package theme conflicts!")
            for conflict in pkg_conflicts:
                logger.error(f"  - Theme '{conflict['second_pkg']['theme']}' appears twice with "
                           f"{conflict['items_between']} items between (no long_form)")
        else:
            logger.info(f"\n✅ No package theme conflicts found! All packages with same theme "
                       f"are properly separated by long_form content.")
        
        # Count packages by theme
        cursor.execute("""
            SELECT 
                a.theme,
                COUNT(*) as count
            FROM scheduled_items si
            JOIN assets a ON si.asset_id = a.id
            JOIN schedules sc ON si.schedule_id = sc.id
            WHERE sc.air_date = %s
                AND a.content_type = 'pkg'
                AND a.theme IS NOT NULL
            GROUP BY a.theme
            ORDER BY count DESC, a.theme
        """, (schedule_date,))
        
        theme_counts = cursor.fetchall()
        if theme_counts:
            logger.info("\nPackage themes in schedule:")
            for tc in theme_counts:
                logger.info(f"  - {tc['theme']}: {tc['count']} occurrences")
        
        cursor.close()
        
    except Exception as e:
        logger.error(f"Error analyzing schedule: {e}")

def test_create_schedule_with_packages():
    """Test creating a schedule to verify package theme separation works"""
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        # Import the scheduler - db_manager is already initialized
        from scheduler_postgres import PostgreSQLScheduler
        scheduler = PostgreSQLScheduler()
        
        # Get tomorrow's date - create as datetime for the scheduler
        test_date = datetime.now() + timedelta(days=1)
        
        logger.info(f"\nCreating test schedule for {test_date.date()} to verify package theme separation...")
        
        # Create a daily schedule
        result = scheduler.create_daily_schedule(
            schedule_date=test_date.strftime('%Y-%m-%d'),
            schedule_name=f"Package Theme Test - {test_date.date()}"
        )
        success = result.get('success', False)
        
        if success:
            logger.info(f"✅ Successfully created test schedule for {test_date.date()}")
            # Analyze the created schedule
            analyze_schedule_for_pkg_themes(conn, test_date.date())
        else:
            logger.error(f"❌ Failed to create test schedule")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in test: {e}")

def main():
    """Main test function"""
    logger.info("=" * 80)
    logger.info("Testing Package Theme Separation in Content Rotation")
    logger.info("=" * 80)
    
    # Connect to database
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        return
    
    # Get a schedule with packages
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            sc.id, 
            sc.air_date, 
            COUNT(DISTINCT a.content_type) as content_types,
            COUNT(CASE WHEN a.content_type = 'pkg' THEN 1 END) as pkg_count
        FROM schedules sc
        JOIN scheduled_items si ON si.schedule_id = sc.id
        JOIN assets a ON si.asset_id = a.id
        WHERE sc.air_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY sc.id
        HAVING COUNT(CASE WHEN a.content_type = 'pkg' THEN 1 END) > 0
        ORDER BY sc.air_date DESC, pkg_count DESC
        LIMIT 1
    """)
    result = cursor.fetchone()
    cursor.close()
    
    if result:
        schedule_date = result['air_date']
        logger.info(f"Analyzing schedule from {schedule_date} with {result['pkg_count']} packages")
        analyze_schedule_for_pkg_themes(conn, schedule_date)
    else:
        logger.info("No schedules found in database")
    
    # Optionally create and test a new schedule
    response = input("\nDo you want to create a test schedule for tomorrow? (y/n): ")
    if response.lower() == 'y':
        test_create_schedule_with_packages()
    
    conn.close()
    logger.info("\nTest completed!")

if __name__ == "__main__":
    main()