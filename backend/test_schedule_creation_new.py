#!/usr/bin/env python3
"""Test schedule creation with holiday assignments"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize scheduler
scheduler = PostgreSQLScheduler()

# Check if holiday integration is available
print(f"Has holiday_integration: {hasattr(scheduler, 'holiday_integration')}")
if hasattr(scheduler, 'holiday_integration'):
    print(f"Holiday integration enabled: {scheduler.holiday_integration.enabled}")
    print(f"Holiday integration scheduler: {scheduler.holiday_integration.scheduler}")

# Create a test schedule
print("\n=== Creating test weekly schedule ===")
start_date = datetime.now().strftime('%Y-%m-%d')

result = scheduler.create_weekly_schedule(start_date)

print(f"\nSchedule creation result: {result}")

if result.get('status') == 'success' and result.get('schedule'):
    schedule_id = result['schedule']['id']
    print(f"Created schedule ID: {schedule_id}")
    
    # Check if assignments were created
    import psycopg2
    import getpass
    from psycopg2.extras import RealDictCursor
    
    default_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
    connection_string = os.getenv('DATABASE_URL', default_conn)
    
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM holiday_greetings_days 
        WHERE schedule_id = %s
    """, (schedule_id,))
    
    count = cursor.fetchone()['count']
    print(f"Holiday assignments created: {count}")
    
    cursor.close()
    conn.close()