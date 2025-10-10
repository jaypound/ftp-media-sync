#!/usr/bin/env python3
"""
Test meeting notification functionality
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_notifier import EmailNotifier
from datetime import datetime

def test_meeting_notifications():
    """Test meeting change notifications"""
    print("=== Testing Meeting Schedule Notifications ===")
    
    # Check if SMTP password is set
    smtp_password = os.getenv('SMTP_PASSWORD')
    if not smtp_password:
        print("❌ ERROR: SMTP_PASSWORD not set in environment")
        print("Set it with: export SMTP_PASSWORD='DKrd75oQBowRIQXw'")
        return
    
    # Initialize notifier
    notifier = EmailNotifier({'smtp_password': smtp_password})
    
    # Test meeting update notification
    print("\n1. Testing Meeting Update Notification...")
    subject = "Meeting Schedule Updated: City Council Regular Meeting"
    body = f"""
Meeting Schedule Notification

Action: UPDATED
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Client IP Address: 192.168.1.100 (Test)

Meeting Details:
- Name: City Council Regular Meeting
- Date: 2025-10-15
- Time: 14:00 - 17:00
- Room: Council Chambers
- ATL26 Broadcast: Yes

Changes Made:
- start_time: 13:00 → 14:00
- end_time: 16:00 → 17:00

This notification was sent automatically by the FTP Media Sync system.
"""
    
    if notifier.send_email(['jpound@atlantaga.gov'], subject, body):
        print("✅ Update notification sent successfully!")
    else:
        print("❌ Failed to send update notification")
    
    # Test meeting deletion notification
    print("\n2. Testing Meeting Deletion Notification...")
    subject = "Meeting Schedule Deleted: Planning Commission Meeting"
    body = f"""
Meeting Schedule Notification

Action: DELETED
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Client IP Address: 10.0.0.50 (Test)

Meeting Details:
- Name: Planning Commission Meeting
- Date: 2025-10-20
- Time: 09:00 - 11:00
- Room: Room 1900
- ATL26 Broadcast: No

This notification was sent automatically by the FTP Media Sync system.
"""
    
    if notifier.send_email(['jpound@atlantaga.gov'], subject, body):
        print("✅ Deletion notification sent successfully!")
    else:
        print("❌ Failed to send deletion notification")
    
    print("\n=== Test Complete ===")
    print("\nThe meeting notification system will:")
    print("- Send emails to jpound@atlantaga.gov")
    print("- Include client IP address")
    print("- Show meeting details and changes")
    print("- Trigger on UPDATE and DELETE operations only")
    print("- NOT send notifications for new meetings (INSERT)")

if __name__ == '__main__':
    test_meeting_notifications()