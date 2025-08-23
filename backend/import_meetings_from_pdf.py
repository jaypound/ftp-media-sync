#!/usr/bin/env python3
"""
Import meetings from PDF files into the meeting schedule table.
Only imports meetings dated August 2025 and forward.
"""

import os
import re
import logging
from datetime import datetime, date
from typing import List, Dict, Optional
import PyPDF2
from database_postgres import db_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeetingPDFImporter:
    def __init__(self):
        self.meetings_to_import = []
        
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text content from a PDF file."""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            logger.error(f"Error reading PDF {pdf_path}: {str(e)}")
            return ""
    
    def parse_meeting_date(self, date_str: str) -> Optional[date]:
        """Parse various date formats from the PDF."""
        # Try common date formats
        date_formats = [
            "%B %d, %Y",  # August 21, 2025
            "%m/%d/%Y",   # 08/21/2025
            "%m-%d-%Y",   # 08-21-2025
            "%Y-%m-%d",   # 2025-08-21
            "%d %B %Y",   # 21 August 2025
            "%b %d, %Y",  # Aug 21, 2025
        ]
        
        date_str = date_str.strip()
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Try regex patterns for more flexible matching
        # Pattern: Month DD, YYYY
        pattern = r'(\w+)\s+(\d{1,2}),?\s+(\d{4})'
        match = re.match(pattern, date_str)
        if match:
            month_str, day, year = match.groups()
            try:
                month_num = datetime.strptime(month_str[:3], '%b').month
                return date(int(year), month_num, int(day))
            except:
                pass
        
        return None
    
    def parse_meetings_from_text(self, text: str, source_file: str) -> List[Dict]:
        """Parse meeting information from extracted text."""
        meetings = []
        
        # Split text into lines for processing
        lines = text.split('\n')
        
        # Common patterns for meeting entries
        # This will need to be adjusted based on actual PDF format
        current_meeting = {}
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Look for date patterns
            date_match = re.search(r'(\w+\s+\d{1,2},?\s+\d{4})', line)
            if date_match:
                meeting_date = self.parse_meeting_date(date_match.group(1))
                if meeting_date:
                    # Save previous meeting if exists
                    if current_meeting and 'date' in current_meeting:
                        meetings.append(current_meeting)
                    
                    # Start new meeting
                    current_meeting = {
                        'date': meeting_date,
                        'source_file': source_file,
                        'raw_text': line
                    }
                    
                    # Extract time if on same line
                    time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', line)
                    if time_match:
                        current_meeting['time'] = time_match.group(1)
                    
                    # Extract title/description - usually after date and time
                    # Remove date and time from line to get description
                    desc_line = line
                    if date_match:
                        desc_line = desc_line.replace(date_match.group(1), '')
                    if time_match:
                        desc_line = desc_line.replace(time_match.group(1), '')
                    desc_line = desc_line.strip(' -,')
                    if desc_line:
                        current_meeting['title'] = desc_line
            
            # Look for time on separate line
            elif current_meeting and 'time' not in current_meeting:
                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', line)
                if time_match:
                    current_meeting['time'] = time_match.group(1)
                elif 'title' not in current_meeting and line:
                    # Might be the title
                    current_meeting['title'] = line
            
            # Additional description lines
            elif current_meeting and 'title' in current_meeting and len(line) > 10:
                # Might be additional description
                if 'description' not in current_meeting:
                    current_meeting['description'] = line
                else:
                    current_meeting['description'] += ' ' + line
        
        # Don't forget the last meeting
        if current_meeting and 'date' in current_meeting:
            meetings.append(current_meeting)
        
        return meetings
    
    def filter_meetings_by_date(self, meetings: List[Dict]) -> List[Dict]:
        """Filter meetings to only include those from August 2025 forward."""
        cutoff_date = date(2025, 8, 1)
        filtered = []
        
        for meeting in meetings:
            if meeting['date'] >= cutoff_date:
                filtered.append(meeting)
                logger.info(f"Including meeting: {meeting['date']} - {meeting.get('title', 'No title')}")
            else:
                logger.debug(f"Skipping meeting before August 2025: {meeting['date']}")
        
        return filtered
    
    def import_meeting_to_db(self, meeting: Dict) -> bool:
        """Import a single meeting into the database."""
        try:
            # Prepare meeting data for database
            meeting_data = {
                'title': meeting.get('title', 'ATL26 Meeting'),
                'channel': 'ATL26',
                'meeting_date': meeting['date'],
                'start_time': meeting.get('time', '00:00'),
                'duration_minutes': 60,  # Default duration if not specified
                'description': meeting.get('description', ''),
                'location': meeting.get('location', ''),
                'is_recurring': False,
                'recurrence_pattern': None,
                'recurrence_end_date': None,
                'import_source': f"PDF Import: {meeting['source_file']}",
                'raw_import_data': meeting.get('raw_text', '')
            }
            
            # Check if meeting already exists (by date, time, and title)
            existing = db_manager.get_meetings_by_date_range(
                meeting['date'], 
                meeting['date'],
                channel='ATL26'
            )
            
            for exist in existing:
                if (exist.get('title') == meeting_data['title'] and 
                    exist.get('start_time') == meeting_data['start_time']):
                    logger.info(f"Meeting already exists: {meeting['date']} {meeting_data['title']}")
                    return False
            
            # Import the meeting
            success = db_manager.create_meeting_schedule(meeting_data)
            if success:
                logger.info(f"Successfully imported: {meeting['date']} {meeting_data['title']}")
            else:
                logger.error(f"Failed to import: {meeting['date']} {meeting_data['title']}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error importing meeting: {str(e)}")
            return False
    
    def process_pdf_files(self, pdf_files: List[str]):
        """Process multiple PDF files and import meetings."""
        all_meetings = []
        
        # Extract meetings from each PDF
        for pdf_file in pdf_files:
            if not os.path.exists(pdf_file):
                logger.error(f"PDF file not found: {pdf_file}")
                continue
            
            logger.info(f"Processing PDF: {pdf_file}")
            text = self.extract_text_from_pdf(pdf_file)
            
            if text:
                meetings = self.parse_meetings_from_text(text, os.path.basename(pdf_file))
                logger.info(f"Found {len(meetings)} meetings in {pdf_file}")
                all_meetings.extend(meetings)
            else:
                logger.warning(f"No text extracted from {pdf_file}")
        
        # Filter meetings by date
        filtered_meetings = self.filter_meetings_by_date(all_meetings)
        logger.info(f"Found {len(filtered_meetings)} meetings from August 2025 forward")
        
        # Connect to database
        if not db_manager.connect():
            logger.error("Failed to connect to database")
            return
        
        # Import meetings
        imported_count = 0
        for meeting in filtered_meetings:
            if self.import_meeting_to_db(meeting):
                imported_count += 1
        
        logger.info(f"Successfully imported {imported_count} meetings")
        
        # Show sample of extracted text for debugging
        if all_meetings:
            logger.info("\nSample of extracted meetings:")
            for meeting in all_meetings[:3]:
                logger.info(f"  Date: {meeting['date']}, Title: {meeting.get('title', 'N/A')}, Time: {meeting.get('time', 'N/A')}")


def main():
    """Main function to run the import."""
    pdf_files = [
        '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-48 PM.pdf',
        '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-49 PM.pdf',
        '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-50 PM.pdf'
    ]
    
    importer = MeetingPDFImporter()
    importer.process_pdf_files(pdf_files)


if __name__ == "__main__":
    main()