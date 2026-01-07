#!/usr/bin/env python3
"""Debug script to trace schedule creation with daily assignments"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

import logging
from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("=== Testing Schedule Creation with Daily Assignments ===\n")

# Connect to database
db_manager.connect()

# Create scheduler instance
scheduler = PostgreSQLScheduler()

# Check holiday integration
print(f"Holiday integration enabled: {scheduler.holiday_integration.enabled}")
print(f"Holiday integration has scheduler: {scheduler.holiday_integration.scheduler is not None}")

# Get next Sunday as test date
today = datetime.now()
days_until_sunday = (6 - today.weekday()) % 7
if days_until_sunday == 0:
    days_until_sunday = 7  # Next Sunday
test_date = (today + timedelta(days=days_until_sunday)).strftime('%Y-%m-%d')

print(f"\nCreating test weekly schedule for {test_date}...")

# Create a test schedule (but don't fill it)
try:
    # Just check what would happen during schedule creation
    print("\nChecking daily assignment setup...")
    
    if hasattr(scheduler, 'holiday_integration') and scheduler.holiday_integration.enabled:
        print("✓ Holiday integration is available and enabled")
        
        # Check if we can import the daily assignments module
        try:
            from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
            print("✓ Successfully imported HolidayGreetingDailyAssignments")
            
            # Create instance
            daily_assignments = HolidayGreetingDailyAssignments(db_manager)
            print("✓ Created daily assignments instance")
            
            # Check if we have holiday greetings available
            conn = db_manager._get_connection()
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT COUNT(*) as count FROM holiday_greeting_rotation")
            result = cursor.fetchone()
            count = result['count']
            cursor.close()
            db_manager._put_connection(conn)
            
            print(f"✓ Found {count} holiday greetings in rotation table")
            
        except Exception as e:
            print(f"✗ Error with daily assignments: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("✗ Holiday integration not enabled or not available")
        
except Exception as e:
    print(f"\nError during test: {e}")
    import traceback
    traceback.print_exc()

print("\n=== Test Complete ===")