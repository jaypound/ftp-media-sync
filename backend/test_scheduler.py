#!/usr/bin/env python3
"""
Test the scheduler functionality
"""
import requests
import json
import time

BASE_URL = "http://localhost:5000/api"

def check_status():
    """Check scheduler status"""
    print("\n=== Checking Scheduler Status ===")
    try:
        response = requests.get(f"{BASE_URL}/scheduler/status")
        status = response.json()
        print(f"Success: {status.get('success')}")
        print(f"Enabled: {status.get('enabled')}")
        print(f"Running: {status.get('running')}")
        print(f"Schedule: {status.get('schedule')}")
        
        if status.get('last_run'):
            last_run = status['last_run']
            print(f"\nLast Run:")
            print(f"  Job: {last_run.get('job_name')}")
            print(f"  Time: {last_run.get('last_run_at')}")
            print(f"  Status: {last_run.get('last_run_status')}")
            if last_run.get('last_run_details'):
                details = json.loads(last_run['last_run_details'])
                if 'total_synced' in details:
                    print(f"  Synced: {details['total_synced']} files")
                    print(f"  Changed: {details['total_updated']} files")
        
        return status
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def enable_scheduler():
    """Enable the scheduler"""
    print("\n=== Enabling Scheduler ===")
    try:
        response = requests.post(
            f"{BASE_URL}/scheduler/toggle",
            json={"enable": True},
            headers={"Content-Type": "application/json"}
        )
        result = response.json()
        print(f"Success: {result.get('success')}")
        print(f"Message: {result.get('message')}")
        return result
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def run_sync_now():
    """Run sync manually"""
    print("\n=== Running Manual Sync ===")
    print("This may take a few minutes...")
    try:
        response = requests.post(f"{BASE_URL}/scheduler/run-now")
        result = response.json()
        print(f"Success: {result.get('success')}")
        print(f"Message: {result.get('message')}")
        return result
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def main():
    print("Scheduler Test Script")
    print("=" * 50)
    
    # Check initial status
    status = check_status()
    
    if status and not status.get('enabled'):
        print("\nScheduler is disabled. Enabling...")
        enable_result = enable_scheduler()
        if enable_result and enable_result.get('success'):
            time.sleep(2)
            # Check status again
            status = check_status()
    
    if status and status.get('enabled'):
        # Ask if user wants to run manual sync
        print("\nScheduler is enabled and will run every minute (test mode)")
        response = input("\nDo you want to run a manual sync now? (y/n): ")
        if response.lower() == 'y':
            run_sync_now()
            print("\nWait a moment for the sync to complete, then check the log file:")
            print("  tail -f logs/scheduler_*.log")
    else:
        print("\nScheduler could not be enabled. Check app.py is running.")

if __name__ == '__main__':
    main()