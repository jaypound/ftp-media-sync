#!/usr/bin/env python3
"""
Test email notification functionality
"""
import os
from email_notifier import EmailNotifier

def main():
    print("=== FTP Media Sync - Email Test ===")
    print("\nSMTP Configuration:")
    print("  Server: mail.smtp2go.com")
    print("  Port: 2525 (TLS)")
    print("  Username: alerts@atl26.atlantaga.gov")
    
    # Alternative configurations
    print("\nAlternative configurations available:")
    print("  - Ports with TLS: 2525, 8025, 587, 80, 25")
    print("  - Ports with SSL: 465, 8465, 443")
    
    # Check if password is set
    smtp_password = os.getenv('SMTP_PASSWORD')
    if not smtp_password:
        print("\n❌ ERROR: SMTP_PASSWORD environment variable not set!")
        print("\nTo set the password:")
        print("  export SMTP_PASSWORD='your_password_here'")
        print("\nOr add to your .env file:")
        print("  SMTP_PASSWORD=your_password_here")
        return
    
    print(f"\n✓ SMTP password configured (length: {len(smtp_password)})")
    
    # Get test options
    print("\n\nTest Options:")
    print("1. Send test email")
    print("2. Send sample sync report")
    print("3. Send error alert")
    print("4. Test alternative port (SSL on 465)")
    print("5. Test all notification types")
    
    choice = input("\nSelect option (1-5): ").strip()
    
    if not choice:
        print("No option selected, exiting.")
        return
    
    # Get recipient
    recipient = input("Enter recipient email address: ").strip()
    if not recipient:
        print("No recipient provided, exiting.")
        return
    
    # Create notifier with default config
    notifier = EmailNotifier()
    
    if choice == '1':
        print(f"\nSending test email to {recipient}...")
        if notifier.send_test_email(recipient):
            print("✅ Test email sent successfully!")
        else:
            print("❌ Failed to send test email.")
    
    elif choice == '2':
        print(f"\nSending sample sync report to {recipient}...")
        # Create sample sync results
        sample_results = {
            'total_synced': 277,
            'total_updated': 25,
            'total_errors': 0,
            'by_type': {
                'MTG': {'synced': 27, 'updated': 22, 'errors': 0},
                'PSA': {'synced': 106, 'updated': 0, 'errors': 0},
                'BMP': {'synced': 49, 'updated': 1, 'errors': 0},
                'PMO': {'synced': 8, 'updated': 2, 'errors': 0},
            },
            'total_changes': [
                {'file': '250903_MTG_COMMITTEE.mp4', 'old': '2025-09-20', 'new': '2025-09-21', 'source': 'calculated from 2025-09-03 + 18 days'},
                {'file': '252625_BMP_4TH_July.mp4', 'old': '2026-07-04', 'new': '2026-07-05', 'source': 'Castus metadata'},
                {'file': '250924_PROMO_Beltline.mp4', 'old': '2025-10-06', 'new': '2025-10-07', 'source': 'Castus metadata'},
            ]
        }
        
        if notifier.send_sync_report([recipient], sample_results):
            print("✅ Sync report sent successfully!")
        else:
            print("❌ Failed to send sync report.")
    
    elif choice == '3':
        print(f"\nSending error alert to {recipient}...")
        if notifier.send_error_alert(
            [recipient], 
            "Failed to connect to FTP server",
            "Connection timeout after 30 seconds. Server: ftp.example.com, Port: 21"
        ):
            print("✅ Error alert sent successfully!")
        else:
            print("❌ Failed to send error alert.")
    
    elif choice == '4':
        print(f"\nTesting SSL connection on port 465...")
        # Create notifier with SSL config
        ssl_notifier = EmailNotifier({
            'smtp_server': 'mail.smtp2go.com',
            'smtp_port': 465,
            'smtp_username': 'alerts@atl26.atlantaga.gov',
            'smtp_password': smtp_password,
            'use_tls': False,
            'use_ssl': True
        })
        
        if ssl_notifier.send_test_email(recipient):
            print("✅ SSL test email sent successfully!")
        else:
            print("❌ Failed to send SSL test email.")
    
    elif choice == '5':
        print(f"\nSending all notification types to {recipient}...")
        
        results = []
        
        # Test email
        print("1. Sending test email...")
        results.append(("Test email", notifier.send_test_email(recipient)))
        
        # Sync report
        print("2. Sending sync report...")
        sample_results = {
            'total_synced': 277,
            'total_updated': 25,
            'total_errors': 0
        }
        results.append(("Sync report", notifier.send_sync_report([recipient], sample_results)))
        
        # Error alert
        print("3. Sending error alert...")
        results.append(("Error alert", notifier.send_error_alert([recipient], "Test error")))
        
        print("\n=== Results ===")
        for name, success in results:
            status = "✅ Success" if success else "❌ Failed"
            print(f"{name}: {status}")
    
    else:
        print("Invalid option selected.")

if __name__ == '__main__':
    main()