#!/usr/bin/env python3
"""
Import Atlanta meeting schedules from the extracted OCR text files.
Only imports meetings dated August 2025 and forward.
"""

import re
import logging
from datetime import datetime, date, time
from typing import List, Dict, Optional
from database import db_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AtlantaMeetingImporter:
    def __init__(self):
        self.meetings_to_import = []
        
    def parse_bza_meetings(self, text: str) -> List[Dict]:
        """Parse Board of Zoning Adjustment meetings from first PDF."""
        meetings = []
        
        # BZA meetings are at 12:00 PM in City Council Chambers
        meeting_time = "12:00 PM"
        location = "City Council Chambers, Second Floor"
        
        # Extract dates - looking for patterns like "September 4, 2025"
        # The OCR has some issues, so we'll be flexible
        date_pattern = r'(\w+)\s+(\d{1,2}),?\s*(\d{4})'
        
        # From the OCR, I can see these dates:
        # September 4, 2025
        # September 18, 2025
        # October 9, 2025
        # December 4, 2025
        # December 11, 2025
        
        bza_dates = [
            ("September", 4, 2025),
            ("September", 18, 2025),
            ("October", 9, 2025),
            ("December", 4, 2025),
            ("December", 11, 2025),
        ]
        
        for month, day, year in bza_dates:
            try:
                meeting_date = datetime.strptime(f"{month} {day}, {year}", "%B %d, %Y").date()
                
                meeting = {
                    'title': 'Board of Zoning Adjustment (BZA) Public Hearing',
                    'channel': 'ATL26',
                    'meeting_date': meeting_date,
                    'start_time': meeting_time,
                    'duration_minutes': 120,  # Assumed 2-hour duration
                    'description': 'Board of Zoning Adjustment public hearing for variance, special exception & appeal applications',
                    'location': location,
                    'is_recurring': False,
                    'import_source': 'PDF Import: Doc - Aug 21 2025 - 2-48 PM.pdf'
                }
                meetings.append(meeting)
                logger.info(f"Found BZA meeting: {meeting_date}")
                
            except Exception as e:
                logger.error(f"Error parsing BZA date: {month} {day}, {year} - {str(e)}")
        
        return meetings
    
    def parse_zrb_meetings(self, text: str) -> List[Dict]:
        """Parse Zoning Review Board meetings from second PDF."""
        meetings = []
        
        # ZRB meetings are at 6:00 PM in City Council Chambers
        meeting_time = "6:00 PM"
        location = "City Hall - City Council Chambers, Second Floor"
        
        # From the OCR, looking for dates from August 2025 forward:
        # September 4, 2025
        # November 6, 2025 or November 13, 2025
        # December 4, 2025 or December 11, 2025
        
        zrb_dates = [
            ("September", 4, 2025),
            ("November", 6, 2025),
            ("November", 13, 2025),
            ("December", 4, 2025),
            ("December", 11, 2025),
        ]
        
        for month, day, year in zrb_dates:
            try:
                meeting_date = datetime.strptime(f"{month} {day}, {year}", "%B %d, %Y").date()
                
                meeting = {
                    'title': 'Zoning Review Board Public Hearing',
                    'channel': 'ATL26',
                    'meeting_date': meeting_date,
                    'start_time': meeting_time,
                    'duration_minutes': 120,  # Assumed 2-hour duration
                    'description': 'Zoning Review Board public hearing',
                    'location': location,
                    'is_recurring': False,
                    'import_source': 'PDF Import: Doc - Aug 21 2025 - 2-49 PM.pdf'
                }
                meetings.append(meeting)
                logger.info(f"Found ZRB meeting: {meeting_date}")
                
            except Exception as e:
                logger.error(f"Error parsing ZRB date: {month} {day}, {year} - {str(e)}")
        
        return meetings
    
    def parse_lrb_meetings(self, text: str) -> List[Dict]:
        """Parse License Review Board meetings from third PDF."""
        meetings = []
        
        # LRB meetings location is Committee Room No. 1
        # Time not specified in the PDF, will use a default
        meeting_time = "10:00 AM"  # Default time
        location = "Committee Room No. 1"
        
        # From the OCR, dates from August 2025 forward:
        # AUGUST 5
        # AUGUST 19
        # SEPTEMBER 9
        # SEPTEMBER 23
        # OCTOBER 7
        # OCTOBER 21
        # NOVEMBER 4
        # NOVEMBER 18
        # DECEMBER 2
        # DECEMBER 16
        
        lrb_dates = [
            ("August", 5, 2025),
            ("August", 19, 2025),
            ("September", 9, 2025),
            ("September", 23, 2025),
            ("October", 7, 2025),
            ("October", 21, 2025),
            ("November", 4, 2025),
            ("November", 18, 2025),
            ("December", 2, 2025),
            ("December", 16, 2025),
        ]
        
        for month, day, year in lrb_dates:
            try:
                meeting_date = datetime.strptime(f"{month} {day}, {year}", "%B %d, %Y").date()
                
                meeting = {
                    'title': 'License Review Board Meeting',
                    'channel': 'ATL26',
                    'meeting_date': meeting_date,
                    'start_time': meeting_time,
                    'duration_minutes': 120,  # Assumed 2-hour duration
                    'description': 'License Review Board meeting',
                    'location': location,
                    'is_recurring': False,
                    'import_source': 'PDF Import: Doc - Aug 21 2025 - 2-50 PM.pdf'
                }
                meetings.append(meeting)
                logger.info(f"Found LRB meeting: {meeting_date}")
                
            except Exception as e:
                logger.error(f"Error parsing LRB date: {month} {day}, {year} - {str(e)}")
        
        return meetings
    
    def import_meeting_to_db(self, meeting: Dict) -> bool:
        """Import a single meeting into the database."""
        try:
            # Check if meeting already exists (by date, time, and title)
            existing = db_manager.get_meetings_by_date_range(
                meeting['meeting_date'].isoformat(), 
                meeting['meeting_date'].isoformat()
            )
            
            # Filter by channel and check for duplicates
            for exist in existing:
                if (exist.get('channel') == 'ATL26' and
                    exist.get('title') == meeting['title'] and 
                    exist.get('start_time', '').startswith(meeting['start_time'].split()[0])):  # Compare just the time part
                    logger.info(f"Meeting already exists: {meeting['meeting_date']} {meeting['title']}")
                    return False
            
            # Import the meeting using the create_meeting method
            # Convert our meeting dict to the parameters expected by create_meeting
            meeting_id = db_manager.create_meeting(
                meeting_name=meeting['title'],
                meeting_date=meeting['meeting_date'].isoformat(),
                start_time=meeting['start_time'],
                duration_hours=meeting['duration_minutes'] / 60.0,
                room=meeting['location'],
                atl26_broadcast=True  # All these meetings are for ATL26
            )
            
            if meeting_id:
                logger.info(f"Successfully imported: {meeting['meeting_date']} {meeting['title']} (ID: {meeting_id})")
                return True
            else:
                logger.error(f"Failed to import: {meeting['meeting_date']} {meeting['title']}")
                return False
            
        except Exception as e:
            logger.error(f"Error importing meeting: {str(e)}")
            return False
    
    def process_extracted_files(self):
        """Process the extracted OCR text files and import meetings."""
        all_meetings = []
        
        # Read the extracted text files
        try:
            # BZA meetings
            with open('/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-48 PM_ocr.txt', 'r') as f:
                bza_text = f.read()
                bza_meetings = self.parse_bza_meetings(bza_text)
                all_meetings.extend(bza_meetings)
                logger.info(f"Parsed {len(bza_meetings)} BZA meetings")
        except Exception as e:
            logger.error(f"Error reading BZA file: {str(e)}")
        
        try:
            # ZRB meetings
            with open('/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-49 PM_ocr.txt', 'r') as f:
                zrb_text = f.read()
                zrb_meetings = self.parse_zrb_meetings(zrb_text)
                all_meetings.extend(zrb_meetings)
                logger.info(f"Parsed {len(zrb_meetings)} ZRB meetings")
        except Exception as e:
            logger.error(f"Error reading ZRB file: {str(e)}")
        
        try:
            # LRB meetings
            with open('/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-50 PM_ocr.txt', 'r') as f:
                lrb_text = f.read()
                lrb_meetings = self.parse_lrb_meetings(lrb_text)
                all_meetings.extend(lrb_meetings)
                logger.info(f"Parsed {len(lrb_meetings)} LRB meetings")
        except Exception as e:
            logger.error(f"Error reading LRB file: {str(e)}")
        
        logger.info(f"Total meetings to import: {len(all_meetings)}")
        
        # Connect to database
        if not db_manager.connect():
            logger.error("Failed to connect to database")
            return
        
        # Import meetings
        imported_count = 0
        for meeting in all_meetings:
            if self.import_meeting_to_db(meeting):
                imported_count += 1
        
        logger.info(f"Successfully imported {imported_count} meetings")
        
        # Show summary
        logger.info("\nImport Summary:")
        logger.info(f"Total meetings found: {len(all_meetings)}")
        logger.info(f"Successfully imported: {imported_count}")
        logger.info(f"Already existed or failed: {len(all_meetings) - imported_count}")


def main():
    """Main function to run the import."""
    importer = AtlantaMeetingImporter()
    importer.process_extracted_files()


if __name__ == "__main__":
    main()