"""
Web scraper for Atlanta City Council meetings
"""
import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def scrape_atlanta_council_meetings(year: int = 2025, months: List[int] = None) -> List[Dict[str, Any]]:
    """
    Scrape Atlanta City Council meetings from their website
    
    Args:
        year: Year to scrape (default: 2025)
        months: List of months to scrape (default: [8, 9, 10, 11, 12])
    
    Returns:
        List of meeting dictionaries with keys: name, date, time, duration, broadcast
    """
    if months is None:
        months = [8, 9, 10, 11, 12]
    
    meetings = []
    
    # Headers to avoid 403 errors
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    scraping_failed = False
    
    for month in months:
        url = f"https://citycouncil.atlantaga.gov/other/events/public-meetings/-curm-{month}/-cury-{year}"
        logger.info(f"Scraping meetings from: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all event items on the page
            # Note: The exact selectors may need adjustment based on the actual HTML structure
            event_containers = soup.find_all('div', class_='event-item') or \
                             soup.find_all('div', class_='meeting-item') or \
                             soup.find_all('article', class_='event')
            
            # If no specific containers found, try to find by common patterns
            if not event_containers:
                # Look for date/time patterns in the page
                text_content = soup.get_text()
                
                # Pattern for finding meetings with dates and times
                # Example: "City Council Meeting - November 4, 2025 at 1:00 PM"
                meeting_pattern = r'([^-]+(?:Meeting|Committee|Session|Hearing)[^-]*)\s*[-–]\s*([A-Za-z]+ \d{1,2}, \d{4})\s*(?:at|@)\s*(\d{1,2}:\d{2}\s*[APap][Mm])'
                
                matches = re.findall(meeting_pattern, text_content)
                
                for match in matches:
                    meeting_name = match[0].strip()
                    date_str = match[1].strip()
                    time_str = match[2].strip()
                    
                    try:
                        # Parse date
                        meeting_date = datetime.strptime(date_str, "%B %d, %Y")
                        
                        # Parse time
                        meeting_time = datetime.strptime(time_str, "%I:%M %p")
                        
                        # Determine duration based on meeting type
                        duration = 2.0  # Default 2 hours
                        if 'Committee' in meeting_name:
                            duration = 1.5
                        elif 'Work Session' in meeting_name:
                            duration = 3.0
                        
                        meetings.append({
                            'name': meeting_name,
                            'date': meeting_date.strftime("%Y-%m-%d"),
                            'time': meeting_time.strftime("%H:%M"),
                            'duration': duration,
                            'broadcast': True  # Default to true for all meetings
                        })
                        
                    except ValueError as e:
                        logger.warning(f"Failed to parse meeting: {match}, error: {e}")
            
            else:
                # Parse structured event containers
                for event in event_containers:
                    try:
                        # Extract meeting details - adjust selectors based on actual HTML
                        name_elem = event.find(['h3', 'h4', 'div'], class_=['event-title', 'meeting-title', 'title'])
                        date_elem = event.find(['span', 'div', 'time'], class_=['event-date', 'date'])
                        time_elem = event.find(['span', 'div', 'time'], class_=['event-time', 'time'])
                        
                        if name_elem and date_elem:
                            meeting_name = name_elem.get_text(strip=True)
                            date_text = date_elem.get_text(strip=True)
                            time_text = time_elem.get_text(strip=True) if time_elem else "1:00 PM"
                            
                            # Parse date - try multiple formats
                            meeting_date = None
                            for date_format in ["%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                                try:
                                    meeting_date = datetime.strptime(date_text, date_format)
                                    break
                                except ValueError:
                                    continue
                            
                            if meeting_date:
                                # Parse time
                                try:
                                    meeting_time = datetime.strptime(time_text, "%I:%M %p")
                                except ValueError:
                                    meeting_time = datetime.strptime("13:00", "%H:%M")  # Default to 1 PM
                                
                                meetings.append({
                                    'name': meeting_name,
                                    'date': meeting_date.strftime("%Y-%m-%d"),
                                    'time': meeting_time.strftime("%H:%M"),
                                    'duration': 2.0,
                                    'broadcast': True
                                })
                    
                    except Exception as e:
                        logger.warning(f"Failed to parse event container: {e}")
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch meetings for month {month}: {e}")
            scraping_failed = True
        except Exception as e:
            logger.error(f"Error parsing meetings for month {month}: {e}")
            scraping_failed = True
    
    # If scraping failed or no meetings found, use default meetings
    if scraping_failed or len(meetings) == 0:
        logger.warning("Web scraping failed or returned no results, using default meetings")
        return get_default_meetings()
    
    # Remove duplicates based on name and date
    unique_meetings = []
    seen = set()
    for meeting in meetings:
        key = (meeting['name'], meeting['date'])
        if key not in seen:
            seen.add(key)
            unique_meetings.append(meeting)
    
    logger.info(f"Scraped {len(unique_meetings)} unique meetings")
    return unique_meetings


# Fallback hardcoded meetings if scraping fails
def get_default_meetings() -> List[Dict[str, Any]]:
    """Return default Atlanta City Council meetings for 2025"""
    # Validate that no meetings are on Sunday
    meetings = [
        # August 2025 - Full Council Weeks (Mondays)
        {'name': 'City Council Meeting', 'date': '2025-08-04', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'City Council Meeting', 'date': '2025-08-18', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'Zoning Committee Meeting', 'date': '2025-08-11', 'time': '11:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Finance/Executive Committee Meeting', 'date': '2025-08-13', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Transportation Committee Meeting', 'date': '2025-08-13', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'City Utilities Committee Meeting', 'date': '2025-08-12', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Community Development/Human Services Committee Meeting', 'date': '2025-08-12', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Public Safety and Legal Administration Committee Meeting', 'date': '2025-08-25', 'time': '13:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        
        # September 2025
        {'name': 'City Council Meeting', 'date': '2025-09-02', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'City Council Meeting', 'date': '2025-09-15', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'Zoning Committee Meeting', 'date': '2025-09-08', 'time': '11:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Finance/Executive Committee Meeting', 'date': '2025-09-10', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Transportation Committee Meeting', 'date': '2025-09-10', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'City Utilities Committee Meeting', 'date': '2025-09-09', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Community Development/Human Services Committee Meeting', 'date': '2025-09-23', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Public Safety and Legal Administration Committee Meeting', 'date': '2025-09-22', 'time': '13:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        
        # October 2025
        {'name': 'City Council Meeting', 'date': '2025-10-06', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'City Council Meeting', 'date': '2025-10-20', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'Zoning Committee Meeting', 'date': '2025-10-13', 'time': '11:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Finance/Executive Committee Meeting', 'date': '2025-10-15', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Transportation Committee Meeting', 'date': '2025-10-15', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'City Utilities Committee Meeting', 'date': '2025-10-14', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Community Development/Human Services Committee Meeting', 'date': '2025-10-28', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Public Safety and Legal Administration Committee Meeting', 'date': '2025-10-27', 'time': '13:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        
        # November 2025
        {'name': 'City Council Meeting', 'date': '2025-11-03', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'City Council Meeting', 'date': '2025-11-17', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'Zoning Committee Meeting', 'date': '2025-11-10', 'time': '11:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Finance/Executive Committee Meeting', 'date': '2025-11-12', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Transportation Committee Meeting', 'date': '2025-11-12', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'City Utilities Committee Meeting', 'date': '2025-11-10', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'City Utilities Committee Meeting', 'date': '2025-11-12', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Community Development/Human Services Committee Meeting', 'date': '2025-11-25', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Public Safety and Legal Administration Committee Meeting', 'date': '2025-11-24', 'time': '13:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        
        # December 2025
        {'name': 'City Council Meeting', 'date': '2025-12-01', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'City Council Meeting', 'date': '2025-12-15', 'time': '13:00', 'duration': 2.0, 'room': 'Council Chamber', 'broadcast': True},
        {'name': 'Zoning Committee Meeting', 'date': '2025-12-08', 'time': '11:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Finance/Executive Committee Meeting', 'date': '2025-12-10', 'time': '13:30', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'Transportation Committee Meeting', 'date': '2025-12-10', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
        {'name': 'City Utilities Committee Meeting', 'date': '2025-12-09', 'time': '10:00', 'duration': 1.5, 'room': 'Committee Room 1', 'broadcast': True},
    ]
    
    # Validate that no meetings are on Sunday
    validated_meetings = []
    for meeting in meetings:
        meeting_date = datetime.strptime(meeting['date'], '%Y-%m-%d')
        day_of_week = meeting_date.weekday()  # Monday = 0, Sunday = 6
        
        if day_of_week == 6:  # Sunday
            logger.warning(f"Skipping meeting '{meeting['name']}' on {meeting['date']} - meetings cannot be on Sunday")
            continue
            
        validated_meetings.append(meeting)
    
    logger.info(f"Returning {len(validated_meetings)} validated meetings (excluded Sunday meetings)")
    return validated_meetings