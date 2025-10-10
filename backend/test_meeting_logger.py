#!/usr/bin/env python3
"""
Test meeting logger functionality
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meeting_logger import MeetingLogger

def test_meeting_logger():
    """Test the meeting logger"""
    print("=== Testing Meeting Schedule Logger ===")
    
    # Initialize logger
    logger = MeetingLogger()
    
    # Test 1: Log a meeting creation
    print("\n1. Testing meeting creation log...")
    meeting_data = {
        'id': 123,
        'meeting_name': 'City Council Regular Meeting',
        'meeting_date': '2025-10-15',
        'start_time': '14:00',
        'end_time': '17:00',
        'room': 'Council Chambers',
        'atl26_broadcast': True
    }
    
    logger.log_meeting_change(
        action='created',
        meeting_data=meeting_data,
        client_ip='192.168.1.100',
        email_sent=False,
        email_error="No email sent for new meetings (policy)"
    )
    print("✓ Meeting creation logged")
    
    # Test 2: Log a meeting update with email success
    print("\n2. Testing meeting update log with email success...")
    old_data = meeting_data.copy()
    new_data = meeting_data.copy()
    new_data['start_time'] = '15:00'
    new_data['end_time'] = '18:00'
    
    logger.log_meeting_change(
        action='updated',
        meeting_data=new_data,
        client_ip='10.0.0.50',
        email_sent=True,
        old_data=old_data
    )
    print("✓ Meeting update logged with email success")
    
    # Test 3: Log a meeting deletion with email failure
    print("\n3. Testing meeting deletion log with email failure...")
    logger.log_meeting_change(
        action='deleted',
        meeting_data=meeting_data,
        client_ip='172.16.0.100',
        email_sent=False,
        email_error="SMTP connection failed"
    )
    print("✓ Meeting deletion logged with email failure")
    
    # Test 4: Log an error
    print("\n4. Testing error log...")
    logger.log_error(
        action='update_meeting',
        error_msg='Database connection timeout',
        client_ip='192.168.1.50'
    )
    print("✓ Error logged")
    
    # Show log location
    log_dir = os.path.join(os.path.dirname(__file__), 'logs', 'meetings')
    log_filename = f"meeting_schedules_{datetime.now().strftime('%Y%m')}.log"
    log_path = os.path.join(log_dir, log_filename)
    
    print(f"\n=== Log File Location ===")
    print(f"Path: {log_path}")
    
    # Read and display last few lines
    if os.path.exists(log_path):
        print("\nLast 10 lines from log:")
        print("-" * 80)
        with open(log_path, 'r') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(line.rstrip())
        print("-" * 80)
    
    print("\n=== Test Complete ===")
    print("\nThe meeting logger will:")
    print("- Create monthly log files (meeting_schedules_YYYYMM.log)")
    print("- Log all meeting creates, updates, and deletes")
    print("- Track client IP addresses")
    print("- Record email notification status")
    print("- Show what fields changed in updates")
    print("- Store logs in JSON format for easy parsing")

if __name__ == '__main__':
    test_meeting_logger()