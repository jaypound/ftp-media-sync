#!/usr/bin/env python3
"""
Test manual sync execution
"""
import os
import sys
from datetime import datetime

# Set environment variable to use PostgreSQL before importing
os.environ['USE_POSTGRESQL'] = 'true'

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from database import db_manager
from scheduler_jobs import SchedulerJobs

# Setup
print("Setting up manual sync test...")
config_manager = ConfigManager()

# Check db_manager type
print(f"Database manager type: {type(db_manager)}")
print(f"Database manager instance: {db_manager}")

# Create scheduler instance
scheduler = SchedulerJobs(db_manager, config_manager)

# Check configuration
scheduling_config = config_manager.get_scheduling_settings()
content_expiration = scheduling_config.get('content_expiration', {})
print("\nContent Expiration Configuration:")
print(f"  MTG: {content_expiration.get('MTG', 'NOT SET')} days")

# Clear any existing locks
print("\nClearing any existing locks...")
conn = db_manager._get_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE sync_jobs 
            SET lock_acquired_at = NULL,
                lock_expires_at = NULL,
                last_run_status = 'idle'
            WHERE job_name = 'castus_expiration_sync_all'
        """)
        conn.commit()
        print(f"Cleared {cursor.rowcount} locks")
except Exception as e:
    print(f"Error clearing locks: {e}")
finally:
    db_manager._put_connection(conn)

# Run sync manually
print(f"\nStarting manual sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
print("Check the logs folder for detailed output")
print("-" * 80)

try:
    scheduler.sync_all_expirations_from_castus()
    print("\nSync completed successfully!")
except Exception as e:
    print(f"\nSync failed with error: {e}")

print("\nDone. Check the latest log file in backend/logs/ for details.")