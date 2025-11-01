#!/usr/bin/env python
"""Test the sync functionality directly"""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

from scheduler_jobs import SchedulerJobs
from database_postgres import PostgreSQLDatabaseManager
from config_manager import ConfigManager

try:
    print("Initializing components...")
    
    # Initialize components
    db_manager = PostgreSQLDatabaseManager()
    config_manager = ConfigManager()
    
    # Connect to database
    print("Connecting to database...")
    if not db_manager.connected:
        db_manager.connect()
    
    # Create scheduler jobs instance
    print("Creating scheduler jobs instance...")
    scheduler_jobs = SchedulerJobs(db_manager, config_manager)
    
    # Run the sync
    print("Running sync_all_expirations_from_castus()...")
    print("-" * 80)
    
    scheduler_jobs.sync_all_expirations_from_castus()
    
    print("-" * 80)
    print("Sync completed successfully!")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    if 'db_manager' in locals():
        db_manager.disconnect()