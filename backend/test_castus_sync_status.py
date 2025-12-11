#!/usr/bin/env python3
"""
Test script to verify Castus expiration sync configuration and status
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from database_postgres import DatabaseManager
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def check_sync_status():
    """Check the current status of Castus expiration sync"""
    
    # Load configuration
    config = ConfigManager()
    scheduling_config = config.get_scheduling_settings()
    
    print("="*60)
    print("CASTUS EXPIRATION SYNC STATUS CHECK")
    print("="*60)
    
    # Check configuration
    auto_sync_enabled = scheduling_config.get('auto_sync_enabled', False)
    print(f"\n1. Configuration:")
    print(f"   Auto Sync Enabled: {auto_sync_enabled}")
    
    # Check content expiration rules
    content_expiration = scheduling_config.get('content_expiration', {})
    print(f"\n2. Content Expiration Rules:")
    for content_type, days in sorted(content_expiration.items()):
        if days == 0:
            print(f"   {content_type}: Copy from Castus")
        else:
            print(f"   {content_type}: {days} days from creation")
    
    # Check database job status
    db = DatabaseManager()
    if db.connect():
        conn = db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                job_name,
                last_run_at,
                last_run_status,
                lock_acquired_at,
                lock_expires_at,
                last_run_details
            FROM sync_jobs
            WHERE job_name = 'castus_expiration_sync_all'
        """)
        
        job = cursor.fetchone()
        if job:
            print(f"\n3. Database Job Status:")
            print(f"   Job Name: {job['job_name']}")
            print(f"   Last Run: {job['last_run_at'] or 'Never'}")
            print(f"   Status: {job['last_run_status']}")
            print(f"   Lock Acquired: {job['lock_acquired_at'] or 'Not locked'}")
            print(f"   Lock Expires: {job['lock_expires_at'] or 'N/A'}")
            
            # Check if currently locked
            if job['lock_expires_at'] and job['lock_expires_at'] > datetime.now():
                print(f"   ⚠️  Job is currently LOCKED until {job['lock_expires_at']}")
            
            # Parse last run details
            if job['last_run_details']:
                details = job['last_run_details']
                if isinstance(details, dict):
                    print(f"\n4. Last Run Results:")
                    print(f"   Total Synced: {details.get('total_synced', 0)}")
                    print(f"   Total Updated: {details.get('total_updated', 0)}")
                    print(f"   Total Errors: {details.get('total_errors', 0)}")
                    
                    if 'by_type' in details:
                        print(f"\n   By Content Type:")
                        for ct, stats in sorted(details['by_type'].items()):
                            if stats['synced'] > 0:
                                print(f"     {ct}: {stats['synced']} synced, {stats['updated']} updated")
        
        # Check recent sync activity
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                MAX(metadata_synced_at) as last_sync
            FROM scheduling_metadata
            WHERE metadata_synced_at IS NOT NULL
        """)
        
        sync_stats = cursor.fetchone()
        if sync_stats:
            print(f"\n5. Metadata Sync Statistics:")
            print(f"   Total Content with Sync Dates: {sync_stats['count']}")
            print(f"   Most Recent Sync: {sync_stats['last_sync'] or 'Never'}")
        
        cursor.close()
        db._put_connection(conn)
    
    print("\n6. Schedule:")
    print("   The job is scheduled to run at: 9:00 AM, 12:00 PM, 3:00 PM, 6:00 PM")
    print("   (Every 3 business hours during work day)")
    
    print("\n" + "="*60)
    
    # Check if scheduler is running
    print("\nNOTE: Make sure the scheduler service is running for automatic sync.")
    print("To manually trigger a sync, run: python test_manual_sync.py")
    print("="*60)

if __name__ == "__main__":
    check_sync_status()