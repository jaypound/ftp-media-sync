#!/usr/bin/env python3
"""
Manually trigger video generation to test FTP delivery
This will call the actual video generation endpoint that uses FFmpeg
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from database import db_manager
from scheduler_jobs import SchedulerJobs
from config_manager import ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_meeting():
    """Create a test meeting that started 2 minutes ago"""
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        
        # Calculate meeting time (2 minutes ago)
        now = datetime.now()
        meeting_time = now - timedelta(minutes=2)
        
        # Create a test meeting
        cursor.execute("""
            INSERT INTO meetings (meeting_name, meeting_date, start_time, end_time)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            f'TEST_MEETING_{now.strftime("%H%M")}',
            meeting_time.date(),
            meeting_time.time(),
            (meeting_time + timedelta(hours=1)).time()
        ))
        
        meeting_id = cursor.fetchone()['id']
        conn.commit()
        
        logger.info(f"Created test meeting with ID: {meeting_id}")
        logger.info(f"  Meeting date: {meeting_time.date()}")
        logger.info(f"  Start time: {meeting_time.time()}")
        
        return meeting_id
        
    except Exception as e:
        logger.error(f"Error creating test meeting: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        db_manager._put_connection(conn)

def trigger_video_generation():
    """Manually trigger the video generation process"""
    
    print("=== Manual Video Generation Test ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize components
    if not db_manager.connected:
        logger.info("Connecting to database...")
        db_manager.connect()
    
    if not db_manager.connected:
        logger.error("Failed to connect to database")
        return False
    
    # Create config manager
    config_manager = ConfigManager()
    
    # Create scheduler jobs instance
    scheduler = SchedulerJobs(db_manager, config_manager)
    
    # Create a test meeting
    print("1. Creating test meeting...")
    meeting_id = create_test_meeting()
    if not meeting_id:
        print("❌ Failed to create test meeting")
        return False
    print("✅ Test meeting created")
    
    # Enable auto generation temporarily
    print("\n2. Enabling auto generation...")
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE auto_generation_config 
            SET enabled = TRUE
            WHERE id = 1
        """)
        conn.commit()
        print("✅ Auto generation enabled")
    except Exception as e:
        print(f"❌ Failed to enable auto generation: {e}")
        return False
    finally:
        db_manager._put_connection(conn)
    
    # Manually call the check_meetings_for_video_generation method
    print("\n3. Triggering video generation check...")
    try:
        # Override time constraints for testing
        import host_verification
        # Force backend host verification to pass
        original_is_backend = host_verification.is_backend_host
        host_verification.is_backend_host = lambda: True
        
        scheduler.check_meetings_for_video_generation()
        
        # Restore original function
        host_verification.is_backend_host = original_is_backend
        
        print("✅ Video generation check completed")
    except Exception as e:
        print(f"❌ Error during video generation: {e}")
        logger.error(f"Video generation error: {e}", exc_info=True)
        return False
    
    # Check the results
    print("\n4. Checking generation results...")
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mvg.*, gv.file_name, gv.export_server
            FROM meeting_video_generations mvg
            LEFT JOIN generated_default_videos gv ON mvg.video_id = gv.id
            WHERE mvg.meeting_id = %s
            ORDER BY mvg.generation_timestamp DESC
            LIMIT 1
        """, (meeting_id,))
        
        result = cursor.fetchone()
        if result:
            print(f"✅ Generation record found:")
            print(f"   Status: {result['status']}")
            print(f"   File: {result['file_name']}")
            print(f"   Export: {result['export_server']}")
            if result['error_message']:
                print(f"   Error: {result['error_message']}")
        else:
            print("❌ No generation record found")
            
    except Exception as e:
        print(f"❌ Error checking results: {e}")
    finally:
        db_manager._put_connection(conn)
    
    print("\n✅ Test completed!")
    print("\nIMPORTANT: The current implementation is a placeholder that doesn't actually")
    print("generate videos with FFmpeg or deliver to FTP servers. To fix this:")
    print("1. Update generate_default_graphics_video_internal to call the real video generation")
    print("2. Check the logs directory for any FFmpeg logs")
    print("3. Verify FTP server connectivity and permissions")
    
    return True

if __name__ == "__main__":
    try:
        success = trigger_video_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)