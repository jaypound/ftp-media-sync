#!/usr/bin/env python3
"""Test creating a schedule and trace daily assignment creation"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

import logging
from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("=== Creating Test Schedule with Tracing ===\n")

# Connect to database
db_manager.connect()

# Create scheduler instance
scheduler = PostgreSQLScheduler()

# Create a test date far in the future
test_date = "2026-12-20"  # A Sunday far in the future

print(f"Creating weekly schedule for {test_date}...")

# Monkey-patch the daily assignment creation to add tracing
original_method = scheduler.create_weekly_schedule

def traced_create_weekly_schedule(start_date):
    print(f"\n>>> TRACE: create_weekly_schedule called with {start_date}")
    
    # Check initial state
    print(f">>> TRACE: holiday_integration exists: {hasattr(scheduler, 'holiday_integration')}")
    if hasattr(scheduler, 'holiday_integration'):
        print(f">>> TRACE: holiday_integration.enabled: {scheduler.holiday_integration.enabled}")
    
    # Call original method
    result = original_method(start_date)
    
    print(f">>> TRACE: Schedule creation result: {result}")
    
    if result['success']:
        # Check if daily assignments were created
        conn = db_manager._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM holiday_greetings_days 
            WHERE schedule_id = %s
        """, (result['schedule_id'],))
        assignment_count = cursor.fetchone()['count']
        cursor.close()
        db_manager._put_connection(conn)
        
        print(f">>> TRACE: Daily assignments created: {assignment_count}")
    
    return result

# Apply the traced method
scheduler.create_weekly_schedule = traced_create_weekly_schedule

# Create the schedule
result = scheduler.create_weekly_schedule(test_date)

if result['success']:
    print(f"\n✅ Schedule created: ID {result['schedule_id']}")
    
    # Clean up test schedule
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM holiday_greetings_days WHERE schedule_id = %s", (result['schedule_id'],))
    cursor.execute("DELETE FROM scheduled_items WHERE schedule_id = %s", (result['schedule_id'],))
    cursor.execute("DELETE FROM schedules WHERE id = %s", (result['schedule_id'],))
    conn.commit()
    cursor.close()
    db_manager._put_connection(conn)
    print("✅ Test schedule cleaned up")
else:
    print(f"\n❌ Failed to create schedule: {result['message']}")