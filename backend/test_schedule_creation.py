#!/usr/bin/env python3
"""Test schedule creation with the fixed SQL"""

from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database connection
print("Initializing database connection...")
db_manager.connect()

# Create scheduler
scheduler = PostgreSQLScheduler()

# Get tomorrow's date
tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

print(f"Creating schedule for {tomorrow}...")
print("This should now work with progressive delay relaxation...")

# Delete any existing schedule for tomorrow
existing = scheduler.get_schedule_by_date(tomorrow)
if existing:
    print(f"Deleting existing schedule for {tomorrow}")
    scheduler.delete_schedule(existing['id'])

# Create new schedule
result = scheduler.create_daily_schedule(
    schedule_date=tomorrow,
    schedule_name=f"Test Schedule with Fixed SQL - {tomorrow}"
)

if result['success']:
    print(f"\n✅ SUCCESS! Schedule created successfully!")
    print(f"Schedule ID: {result['schedule_id']}")
    print(f"Total duration: {result['total_duration_hours']:.2f} hours")
    print(f"Total items: {result['total_items']}")
    
    # Show delay statistics
    if 'delay_stats' in result:
        print("\nDelay reduction statistics:")
        for key, value in result['delay_stats'].items():
            print(f"  {key}: {value}")
else:
    print(f"\n❌ FAILED: {result['message']}")
    if 'error' in result:
        print(f"Error type: {result['error']}")
    if 'iterations_without_progress' in result:
        print(f"Iterations without progress: {result['iterations_without_progress']}")