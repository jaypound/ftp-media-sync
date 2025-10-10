#!/usr/bin/env python3
"""
Meeting Schedule Logger
Logs all meeting schedule changes to a dedicated log file
"""
import os
import logging
from datetime import datetime
import json
from typing import Dict, Optional, Any

class MeetingLogger:
    def __init__(self, log_dir: str = None):
        """
        Initialize the meeting logger
        
        Args:
            log_dir: Directory for log files (defaults to 'logs/meetings')
        """
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(__file__), 'logs', 'meetings')
        
        # Create directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log filename with date
        log_filename = f"meeting_schedules_{datetime.now().strftime('%Y%m')}.log"
        log_path = os.path.join(log_dir, log_filename)
        
        # Setup logger
        self.logger = logging.getLogger('meeting_schedules')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers = []
        
        # Create file handler
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Add handler to logger
        self.logger.addHandler(file_handler)
        
    def log_meeting_change(self, 
                          action: str, 
                          meeting_data: Dict[str, Any], 
                          client_ip: str,
                          email_sent: bool,
                          email_error: Optional[str] = None,
                          old_data: Optional[Dict[str, Any]] = None):
        """
        Log a meeting schedule change
        
        Args:
            action: 'created', 'updated', or 'deleted'
            meeting_data: Current meeting data
            client_ip: IP address of the client making the change
            email_sent: Whether email notification was sent successfully
            email_error: Error message if email failed
            old_data: Previous meeting data (for updates)
        """
        try:
            log_entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'action': action.upper(),
                'client_ip': client_ip,
                'email_notification_sent': email_sent,
                'meeting_id': meeting_data.get('id', 'unknown'),
                'meeting_name': meeting_data.get('meeting_name', 'unknown'),
                'meeting_date': meeting_data.get('meeting_date', 'unknown'),
                'start_time': meeting_data.get('start_time', 'unknown'),
                'end_time': meeting_data.get('end_time', meeting_data.get('start_time', 'unknown')),
                'room': meeting_data.get('room', 'unknown'),
                'atl26_broadcast': meeting_data.get('atl26_broadcast', False)
            }
            
            # Add changes for updates
            if action == 'updated' and old_data:
                changes = {}
                for field in ['meeting_name', 'meeting_date', 'start_time', 'end_time', 'room', 'atl26_broadcast']:
                    old_val = old_data.get(field)
                    new_val = meeting_data.get(field)
                    if old_val != new_val:
                        changes[field] = {'old': old_val, 'new': new_val}
                log_entry['changes'] = changes
            
            # Add email error if present
            if email_error:
                log_entry['email_error'] = email_error
            
            # Format the log message
            msg_parts = [
                f"ACTION={action}",
                f"IP={client_ip}",
                f"MEETING_ID={log_entry['meeting_id']}",
                f"MEETING_NAME='{log_entry['meeting_name']}'",
                f"DATE={log_entry['meeting_date']}",
                f"TIME={log_entry['start_time']}-{log_entry['end_time']}",
                f"EMAIL_SENT={email_sent}"
            ]
            
            if action == 'updated' and 'changes' in log_entry:
                changes_str = json.dumps(log_entry['changes'], separators=(',', ':'))
                msg_parts.append(f"CHANGES={changes_str}")
            
            if email_error:
                msg_parts.append(f"EMAIL_ERROR='{email_error}'")
            
            # Log the entry
            self.logger.info(" | ".join(msg_parts))
            
            # Also log as JSON for easier parsing
            self.logger.info(f"JSON_DATA: {json.dumps(log_entry, separators=(',', ':'))}")
            
        except Exception as e:
            self.logger.error(f"Failed to log meeting change: {str(e)}")
    
    def log_error(self, action: str, error_msg: str, client_ip: str = 'unknown'):
        """
        Log an error during meeting operations
        
        Args:
            action: The action that failed
            error_msg: Error message
            client_ip: Client IP address
        """
        self.logger.error(f"ACTION={action} | IP={client_ip} | ERROR='{error_msg}'")