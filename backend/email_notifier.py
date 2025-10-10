#!/usr/bin/env python3
"""
Email Notification Module
Sends SMTP notifications for system events
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
import os
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(self, smtp_config: Optional[Dict[str, Any]] = None):
        """
        Initialize email notifier with SMTP configuration
        
        Args:
            smtp_config: Dictionary with SMTP settings, or None to use defaults
        """
        if smtp_config is None:
            smtp_config = {}
        
        self.smtp_server = smtp_config.get('smtp_server', 'mail.smtp2go.com')
        self.smtp_port = smtp_config.get('smtp_port', 2525)
        self.smtp_username = smtp_config.get('smtp_username', 'alerts@atl26.atlantaga.gov')
        self.smtp_password = smtp_config.get('smtp_password', os.getenv('SMTP_PASSWORD', ''))
        self.from_email = smtp_config.get('from_email', 'alerts@atl26.atlantaga.gov')
        self.use_tls = smtp_config.get('use_tls', True)
        self.use_ssl = smtp_config.get('use_ssl', False)
        
    def send_test_email(self, to_email: str) -> bool:
        """
        Send a test email to verify SMTP configuration
        
        Args:
            to_email: Recipient email address
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "FTP Media Sync - Test Notification"
        body = f"""
This is a test notification from the FTP Media Sync system.

Configuration:
- SMTP Server: {self.smtp_server}
- SMTP Port: {self.smtp_port}
- Username: {self.smtp_username}
- TLS Enabled: {self.use_tls}
- SSL Enabled: {self.use_ssl}

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

If you received this email, your SMTP configuration is working correctly!
"""
        
        return self.send_email(
            to_emails=[to_email],
            subject=subject,
            body=body
        )
    
    def send_sync_report(self, to_emails: List[str], sync_results: Dict[str, Any]) -> bool:
        """
        Send sync completion report
        
        Args:
            to_emails: List of recipient email addresses
            sync_results: Dictionary with sync results
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = f"FTP Media Sync - Sync Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        # Format the sync results
        total_files = sync_results.get('total_synced', 0)
        total_updated = sync_results.get('total_updated', 0)
        total_errors = sync_results.get('total_errors', 0)
        
        body = f"""
FTP Media Sync - Automatic Sync Report

Sync completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Summary:
- Total files processed: {total_files}
- Expiration dates updated: {total_updated}
- Errors encountered: {total_errors}

"""
        
        # Add content type breakdown if available
        if 'by_type' in sync_results:
            body += "Content Type Breakdown:\n"
            for content_type, type_results in sync_results['by_type'].items():
                body += f"- {content_type}: {type_results.get('synced', 0)} files, "
                body += f"{type_results.get('updated', 0)} updated, "
                body += f"{type_results.get('errors', 0)} errors\n"
        
        # Add changes list if available
        if 'total_changes' in sync_results and sync_results['total_changes']:
            body += f"\nChanges Made ({len(sync_results['total_changes'])} total):\n"
            for i, change in enumerate(sync_results['total_changes'][:20]):  # Show first 20
                body += f"{i+1}. {change['file']}: {change['old']} → {change['new']} ({change['source']})\n"
            
            if len(sync_results['total_changes']) > 20:
                body += f"\n... and {len(sync_results['total_changes']) - 20} more changes\n"
        
        return self.send_email(
            to_emails=to_emails,
            subject=subject,
            body=body
        )
    
    def send_error_alert(self, to_emails: List[str], error_message: str, error_details: str = "") -> bool:
        """
        Send error alert notification
        
        Args:
            to_emails: List of recipient email addresses
            error_message: Brief error message
            error_details: Detailed error information
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = f"FTP Media Sync - ERROR Alert - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        body = f"""
FTP Media Sync - Error Alert

An error occurred during sync operation:

Error: {error_message}

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""
        
        if error_details:
            body += f"Details:\n{error_details}\n"
        
        body += "\nPlease check the system logs for more information."
        
        return self.send_email(
            to_emails=to_emails,
            subject=subject,
            body=body
        )
    
    def send_email(self, to_emails: List[str], subject: str, body: str, html_body: Optional[str] = None) -> bool:
        """
        Send an email using configured SMTP settings
        
        Args:
            to_emails: List of recipient email addresses
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.from_email
            message["To"] = ", ".join(to_emails)
            
            # Add plain text part
            text_part = MIMEText(body, "plain")
            message.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, "html")
                message.attach(html_part)
            
            # Connect to server and send
            if self.use_ssl:
                # SSL connection
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                    if self.smtp_password:
                        server.login(self.smtp_username, self.smtp_password)
                    server.send_message(message)
            else:
                # Regular SMTP with optional TLS
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    if self.use_tls:
                        server.starttls()
                    if self.smtp_password:
                        server.login(self.smtp_username, self.smtp_password)
                    server.send_message(message)
            
            logger.info(f"Email sent successfully to {', '.join(to_emails)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False


def test_smtp_connection():
    """
    Test SMTP connection with configured settings
    """
    print("Testing SMTP connection...")
    print(f"Server: mail.smtp2go.com")
    print(f"Port: 2525")
    print(f"Username: alerts@atl26.atlantaga.gov")
    
    # Check if password is set
    smtp_password = os.getenv('SMTP_PASSWORD')
    if not smtp_password:
        print("\nWARNING: SMTP_PASSWORD environment variable not set!")
        print("Set it with: export SMTP_PASSWORD='your_password_here'")
        return False
    
    # Create notifier
    notifier = EmailNotifier()
    
    # Get test recipient
    test_recipient = input("\nEnter recipient email for test: ").strip()
    if not test_recipient:
        print("No recipient provided, cancelling test.")
        return False
    
    # Send test email
    print(f"\nSending test email to {test_recipient}...")
    if notifier.send_test_email(test_recipient):
        print("✅ Test email sent successfully!")
        return True
    else:
        print("❌ Failed to send test email. Check logs for details.")
        return False


if __name__ == '__main__':
    # Run test when executed directly
    test_smtp_connection()