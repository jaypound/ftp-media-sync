"""
Castus Metadata Handler

This module handles reading metadata from Castus servers, specifically
the expiration date information stored in hidden metadata files.

Example metadata file path structure:
/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/.castusmeta.250827_AN_Mayors Cup Golf Tournament_v3.mp4/metadata
"""

import json
import os
import tempfile
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from ftp_manager import FTPManager

logger = logging.getLogger(__name__)


class CastusMetadataHandler:
    """Handles reading and processing Castus metadata files"""
    
    def __init__(self, ftp_manager: FTPManager):
        """
        Initialize metadata handler with an FTP manager instance
        
        Args:
            ftp_manager: Configured FTPManager instance for server access
        """
        self.ftp = ftp_manager
    
    def get_content_window_open(self, file_path: str) -> Optional[datetime]:
        """
        Extract 'content window open' date from Castus metadata file
        
        Args:
            file_path: Path to the content file on the server
        
        Returns:
            datetime object with go live date, or None if not found
        """
        # Construct metadata file path
        metadata_path = self._construct_metadata_path(file_path)
        logger.info(f"Attempting to read metadata from: {metadata_path}")
        
        # Download and read metadata file
        metadata_content = self._download_metadata_file(metadata_path)
        if not metadata_content:
            logger.warning(f"Could not retrieve metadata for: {file_path}")
            return None
        
        # Parse metadata and extract go live date
        return self._extract_content_window_open(metadata_content, file_path)
    
    def get_content_window_close(self, file_path: str) -> Optional[datetime]:
        """
        Extract 'content window close' date from Castus metadata file
        
        Args:
            file_path: Path to the content file on the server
                      e.g., "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250827_AN_Mayors Cup Golf Tournament_v3.mp4"
        
        Returns:
            datetime object with expiration date, or None if not found
        """
        # Construct metadata file path
        metadata_path = self._construct_metadata_path(file_path)
        logger.info(f"Attempting to read metadata from: {metadata_path}")
        
        # Download and read metadata file
        metadata_content = self._download_metadata_file(metadata_path)
        if not metadata_content:
            logger.warning(f"Could not retrieve metadata for: {file_path}")
            return None
        
        # Parse metadata and extract expiration
        return self._extract_content_window_close(metadata_content, file_path)
    
    def _construct_metadata_path(self, file_path: str) -> str:
        """
        Construct the metadata file path from content file path
        
        Castus stores metadata in hidden directories with specific naming:
        - Directory name: .castusmeta.{filename}
        - Metadata file: metadata (inside the directory)
        """
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Don't add quotes - let the FTP manager handle path quoting if needed
        # The directory should be used as-is from the file_path
        
        # Construct metadata path
        metadata_dir = f".castusmeta.{filename}"
        metadata_path = f"{directory}/{metadata_dir}/metadata"
        
        return metadata_path
    
    def _download_metadata_file(self, metadata_path: str) -> Optional[str]:
        """
        Download metadata file from server and return its content
        
        Args:
            metadata_path: Full path to metadata file on server
        
        Returns:
            Content of metadata file as string, or None if download fails
        """
        temp_path = None
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.metadata')
            os.close(temp_fd)
            
            # Try to download the file
            logger.debug(f"Downloading metadata file to: {temp_path}")
            success = self.ftp.download_file(metadata_path, temp_path)
            
            if not success:
                logger.error(f"Failed to download metadata file: {metadata_path}")
                return None
            
            # Read the content
            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return content
            
        except Exception as e:
            logger.error(f"Error reading metadata file: {str(e)}")
            return None
        finally:
            # Cleanup temp file
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
    
    def _extract_content_window_open(self, metadata_content: str, file_path: str) -> Optional[datetime]:
        """
        Extract 'content window open' field from metadata content
        
        Args:
            metadata_content: Raw content of metadata file
            file_path: Original file path (for logging)
        
        Returns:
            datetime object with go live date, or None if not found
        """
        try:
            # First, try parsing as JSON
            try:
                data = json.loads(metadata_content)
                if isinstance(data, dict):
                    # Look for content window open field (case-insensitive)
                    for key, value in data.items():
                        if key.lower() == 'content window open' or key.lower() == 'contentwindowopen':
                            return self._parse_date_string(value)
            except json.JSONDecodeError:
                logger.debug("Metadata is not valid JSON, trying other formats")
            
            # Try parsing as key-value pairs (one per line)
            lines = metadata_content.strip().split('\n')
            for line in lines:
                if '=' in line or ':' in line:
                    # Handle both = and : as separators
                    separator = '=' if '=' in line else ':'
                    parts = line.split(separator, 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        value = parts[1].strip()
                        
                        if 'content window open' in key or 'contentwindowopen' in key:
                            return self._parse_date_string(value)
            
            # Try XML format (simple parsing)
            if '<contentWindowOpen>' in metadata_content or '<content_window_open>' in metadata_content:
                import re
                # Extract value between XML tags
                pattern = r'<(?:contentWindowOpen|content_window_open)>(.*?)</(?:contentWindowOpen|content_window_open)>'
                match = re.search(pattern, metadata_content, re.IGNORECASE)
                if match:
                    return self._parse_date_string(match.group(1))
            
            logger.warning(f"Could not find 'content window open' in metadata for: {file_path}")
            logger.debug(f"Metadata content sample: {metadata_content[:200]}...")
            
        except Exception as e:
            logger.error(f"Error parsing metadata content: {str(e)}")
        
        return None
    
    def _extract_content_window_close(self, metadata_content: str, file_path: str) -> Optional[datetime]:
        """
        Extract 'content window close' field from metadata content
        
        The metadata might be in various formats (JSON, XML, or key-value pairs)
        This function attempts to parse and extract the expiration date.
        
        Args:
            metadata_content: Raw content of metadata file
            file_path: Original file path (for logging)
        
        Returns:
            datetime object with expiration date, or None if not found
        """
        try:
            # First, try parsing as JSON
            try:
                data = json.loads(metadata_content)
                if isinstance(data, dict):
                    # Look for content window close field (case-insensitive)
                    for key, value in data.items():
                        if key.lower() == 'content window close' or key.lower() == 'contentwindowclose':
                            return self._parse_date_string(value)
            except json.JSONDecodeError:
                logger.debug("Metadata is not valid JSON, trying other formats")
            
            # Try parsing as key-value pairs (one per line)
            lines = metadata_content.strip().split('\n')
            for line in lines:
                if '=' in line or ':' in line:
                    # Handle both = and : as separators
                    separator = '=' if '=' in line else ':'
                    parts = line.split(separator, 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        value = parts[1].strip()
                        
                        if 'content window close' in key or 'contentwindowclose' in key:
                            return self._parse_date_string(value)
            
            # Try XML format (simple parsing)
            if '<contentWindowClose>' in metadata_content or '<content_window_close>' in metadata_content:
                import re
                # Extract value between XML tags
                pattern = r'<(?:contentWindowClose|content_window_close)>(.*?)</(?:contentWindowClose|content_window_close)>'
                match = re.search(pattern, metadata_content, re.IGNORECASE)
                if match:
                    return self._parse_date_string(match.group(1))
            
            logger.warning(f"Could not find 'content window close' in metadata for: {file_path}")
            logger.debug(f"Metadata content sample: {metadata_content[:200]}...")
            
        except Exception as e:
            logger.error(f"Error parsing metadata content: {str(e)}")
        
        return None
    
    def _parse_date_string(self, date_str: str) -> Optional[datetime]:
        """
        Parse various date string formats into datetime object
        
        Castus might use different date formats, so we try multiple parsers
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Common date formats to try
        date_formats = [
            "%Y-%m-%d %H:%M:%S",      # 2025-12-31 23:59:59
            "%Y-%m-%d",               # 2025-12-31
            "%Y/%m/%d %H:%M:%S",      # 2025/12/31 23:59:59
            "%Y/%m/%d",               # 2025/12/31
            "%m/%d/%Y %H:%M:%S",      # 12/31/2025 23:59:59
            "%m/%d/%Y",               # 12/31/2025
            "%m-%d-%Y %H:%M:%S",      # 12-31-2025 23:59:59
            "%m-%d-%Y",               # 12-31-2025
            "%d-%b-%Y %H:%M:%S",      # 31-Dec-2025 23:59:59
            "%d-%b-%Y",               # 31-Dec-2025
            "%Y%m%d%H%M%S",           # 20251231235959
            "%Y%m%d",                 # 20251231
            "%Y-%m-%dT%H:%M:%S",      # ISO format: 2025-12-31T23:59:59
            "%Y-%m-%dT%H:%M:%SZ",     # ISO format with Z
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Try parsing ISO format with timezone info
        try:
            # Handle ISO format with timezone offset (e.g., 2025-12-31T23:59:59+00:00)
            from dateutil import parser
            return parser.parse(date_str)
        except:
            pass
        
        logger.error(f"Could not parse date string: {date_str}")
        return None
    
    def write_content_window_open(self, file_path: str, go_live_date: Optional[datetime]) -> bool:
        """
        Write 'content window open' date to Castus metadata file
        
        Args:
            file_path: Path to the content file on the server
            go_live_date: Go live datetime to write, or None to remove
        
        Returns:
            True if successfully written, False otherwise
        """
        # Construct metadata file path
        metadata_path = self._construct_metadata_path(file_path)
        logger.info(f"Writing go live metadata to: {metadata_path}")
        
        try:
            # First, try to read existing metadata
            existing_content = self._download_metadata_file(metadata_path)
            
            # Prepare the new content with go live date
            new_content = self._prepare_metadata_content_with_go_live(existing_content, go_live_date)
            
            # Write the metadata file
            return self._upload_metadata_file(metadata_path, new_content)
            
        except Exception as e:
            logger.error(f"Error writing go live metadata: {str(e)}")
            return False
    
    def write_content_window_close(self, file_path: str, expiration_date: Optional[datetime]) -> bool:
        """
        Write 'content window close' date to Castus metadata file
        
        Args:
            file_path: Path to the content file on the server
            expiration_date: Expiration datetime to write, or None to remove
        
        Returns:
            True if successfully written, False otherwise
        """
        # Construct metadata file path
        metadata_path = self._construct_metadata_path(file_path)
        logger.info(f"Writing metadata to: {metadata_path}")
        
        try:
            # First, try to read existing metadata
            existing_content = self._download_metadata_file(metadata_path)
            
            # Prepare the new content
            new_content = self._prepare_metadata_content(existing_content, expiration_date)
            
            # Write the metadata file
            return self._upload_metadata_file(metadata_path, new_content)
            
        except Exception as e:
            logger.error(f"Error writing metadata: {str(e)}")
            return False
    
    def write_content_windows(self, file_path: str, go_live_date: Optional[datetime], expiration_date: Optional[datetime]) -> bool:
        """
        Write both 'content window open' and 'content window close' dates to Castus metadata file
        
        Args:
            file_path: Path to the content file on the server
            go_live_date: Go live datetime to write, or None to remove
            expiration_date: Expiration datetime to write, or None to remove
        
        Returns:
            True if successfully written, False otherwise
        """
        # Construct metadata file path
        metadata_path = self._construct_metadata_path(file_path)
        logger.info(f"Writing content windows metadata to: {metadata_path}")
        
        try:
            # First, try to read existing metadata
            existing_content = self._download_metadata_file(metadata_path)
            
            # Prepare the new content with both dates
            new_content = self._prepare_metadata_content_with_both_dates(existing_content, go_live_date, expiration_date)
            
            # Write the metadata file
            return self._upload_metadata_file(metadata_path, new_content)
            
        except Exception as e:
            logger.error(f"Error writing content windows metadata: {str(e)}")
            return False
    
    def _prepare_metadata_content(self, existing_content: Optional[str], expiration_date: Optional[datetime]) -> str:
        """
        Prepare metadata content with updated expiration date
        
        Args:
            existing_content: Existing metadata content (if any)
            expiration_date: New expiration date to set
        
        Returns:
            Updated metadata content
        """
        metadata_lines = []
        
        # Parse existing content if available
        if existing_content:
            lines = existing_content.strip().split('\n')
            for line in lines:
                # Skip existing content window close lines (we'll add our own)
                # But preserve all other metadata including content window open (go live)
                if 'content window close' not in line.lower():
                    metadata_lines.append(line)
        
        # Add new expiration date if provided
        if expiration_date:
            # Convert to UTC and format
            try:
                from zoneinfo import ZoneInfo
                utc_tz = ZoneInfo('UTC')
                et_tz = ZoneInfo('America/New_York')
            except ImportError:
                # Fallback for Python < 3.9
                import pytz
                utc_tz = pytz.UTC
                et_tz = pytz.timezone('America/New_York')
            
            if expiration_date.tzinfo is None:
                # Assume Eastern Time as per user's note
                if hasattr(et_tz, 'localize'):
                    # pytz style
                    expiration_date = et_tz.localize(expiration_date)
                else:
                    # zoneinfo style
                    expiration_date = expiration_date.replace(tzinfo=et_tz)
            
            # Convert to UTC
            utc_date = expiration_date.astimezone(utc_tz)
            formatted_date = utc_date.strftime('%Y-%m-%d %H:%M:%S UTC')
            
            metadata_lines.append(f'content window close={formatted_date}')
        
        return '\n'.join(metadata_lines) + '\n' if metadata_lines else ''
    
    def _prepare_metadata_content_with_go_live(self, existing_content: Optional[str], go_live_date: Optional[datetime]) -> str:
        """
        Prepare metadata content with updated go live date
        """
        metadata_lines = []
        
        # Parse existing content if available
        if existing_content:
            lines = existing_content.strip().split('\n')
            for line in lines:
                # Skip existing content window open lines (we'll add our own)
                if 'content window open' not in line.lower():
                    metadata_lines.append(line)
        
        # Add new go live date if provided
        if go_live_date:
            formatted_date = self._format_date_for_metadata(go_live_date)
            metadata_lines.insert(0, f'content window open={formatted_date}')  # Insert at beginning
        
        return '\n'.join(metadata_lines) + '\n' if metadata_lines else ''
    
    def _prepare_metadata_content_with_both_dates(self, existing_content: Optional[str], go_live_date: Optional[datetime], expiration_date: Optional[datetime]) -> str:
        """
        Prepare metadata content with both go live and expiration dates
        """
        metadata_lines = []
        
        # Parse existing content if available
        if existing_content:
            lines = existing_content.strip().split('\n')
            for line in lines:
                # Skip existing content window lines (we'll add our own)
                if 'content window open' not in line.lower() and 'content window close' not in line.lower():
                    metadata_lines.append(line)
        
        # Add dates if provided (go live first, then expiration)
        if go_live_date:
            formatted_date = self._format_date_for_metadata(go_live_date)
            metadata_lines.insert(0, f'content window open={formatted_date}')
        
        if expiration_date:
            formatted_date = self._format_date_for_metadata(expiration_date)
            # Insert after go live if it exists, otherwise at beginning
            insert_pos = 1 if go_live_date else 0
            metadata_lines.insert(insert_pos, f'content window close={formatted_date}')
        
        return '\n'.join(metadata_lines) + '\n' if metadata_lines else ''
    
    def _format_date_for_metadata(self, date: datetime) -> str:
        """
        Format a date for metadata storage (convert to UTC)
        """
        # Convert to UTC and format
        try:
            from zoneinfo import ZoneInfo
            utc_tz = ZoneInfo('UTC')
            et_tz = ZoneInfo('America/New_York')
        except ImportError:
            # Fallback for Python < 3.9
            import pytz
            utc_tz = pytz.UTC
            et_tz = pytz.timezone('America/New_York')
        
        if date.tzinfo is None:
            # Assume Eastern Time as per user's note
            if hasattr(et_tz, 'localize'):
                # pytz style
                date = et_tz.localize(date)
            else:
                # zoneinfo style
                date = date.replace(tzinfo=et_tz)
        
        # Convert to UTC
        utc_date = date.astimezone(utc_tz)
        return utc_date.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    def _upload_metadata_file(self, metadata_path: str, content: str) -> bool:
        """
        Upload metadata content to server
        
        Args:
            metadata_path: Full path to metadata file on server
            content: Content to write to metadata file
        
        Returns:
            True if upload successful, False otherwise
        """
        temp_path = None
        try:
            # Create temporary file with content
            temp_fd, temp_path = tempfile.mkstemp(suffix='.metadata')
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Upload the file
            logger.debug(f"Uploading metadata from {temp_path} to {metadata_path}")
            success = self.ftp.upload_file(temp_path, metadata_path)
            
            if not success:
                # The metadata directory should always exist
                logger.error(f"Failed to upload metadata to: {metadata_path}")
                return False
            
            if success:
                logger.info(f"Successfully uploaded metadata to {metadata_path}")
            else:
                logger.error(f"Failed to upload metadata to {metadata_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error uploading metadata file: {str(e)}")
            return False
        finally:
            # Cleanup temp file
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
    
    def update_content_expiration(self, file_path: str, asset_id: int) -> bool:
        """
        Read expiration from Castus metadata and update database
        
        This is the main function that:
        1. Reads metadata from Castus server
        2. Extracts content window close date
        3. Updates the database record
        
        Args:
            file_path: Path to content file on Castus server
            asset_id: Database asset ID to update
        
        Returns:
            True if successfully updated, False otherwise
        """
        # Get expiration date from metadata
        expiration_date = self.get_content_window_close(file_path)
        
        if not expiration_date:
            logger.warning(f"No expiration date found for: {file_path}")
            return False
        
        # Update database
        try:
            from database import db, AnalyzedContent
            
            asset = db.session.query(AnalyzedContent).filter_by(id=asset_id).first()
            if not asset:
                logger.error(f"Asset not found in database: ID {asset_id}")
                return False
            
            # Update expiration date
            asset.expiration_date = expiration_date
            db.session.commit()
            
            logger.info(f"Updated expiration date for asset {asset_id} to {expiration_date}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update database: {str(e)}")
            db.session.rollback()
            return False


def test_metadata_write():
    """Test function to verify metadata writing works"""
    from config_manager import ConfigManager
    from datetime import datetime, timedelta
    
    # Setup
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    server_config = all_config['servers']['source']  # or 'target'
    
    ftp = FTPManager(server_config)
    
    if not ftp.connect():
        print("Failed to connect to FTP server")
        return
    
    print(f"Connected to {server_config['host']}")
    
    handler = CastusMetadataHandler(ftp)
    
    # Test file
    test_file = "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250827_AN_Mayors Cup Golf Tournament_v3.mp4"
    print(f"\nTesting write for file: {test_file}")
    print("-" * 80)
    
    # Test writing an expiration date
    test_expiration = datetime.now() + timedelta(days=30)
    print(f"Writing expiration date: {test_expiration}")
    
    success = handler.write_content_window_close(test_file, test_expiration)
    
    if success:
        print("✅ Successfully wrote expiration date!")
        
        # Now read it back to verify
        print("\nVerifying by reading back...")
        read_expiration = handler.get_content_window_close(test_file)
        
        if read_expiration:
            print(f"✅ Read back expiration: {read_expiration}")
            print(f"   Formatted: {read_expiration.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("❌ Failed to read back expiration")
    else:
        print("❌ Failed to write expiration date")
    
    ftp.disconnect()


def test_metadata_extraction():
    """Test function to verify metadata extraction works"""
    from config_manager import ConfigManager
    
    # Setup
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    server_config = all_config['servers']['source']  # or 'target'
    
    ftp = FTPManager(server_config)
    
    if not ftp.connect():
        print("Failed to connect to FTP server")
        return
    
    print(f"Connected to {server_config['host']}")
    
    handler = CastusMetadataHandler(ftp)
    
    # Test with the example file
    test_file = "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250827_AN_Mayors Cup Golf Tournament_v3.mp4"
    print(f"\nTesting file: {test_file}")
    print("-" * 80)
    
    expiration = handler.get_content_window_close(test_file)
    
    if expiration:
        print(f"✅ Success! Expiration date: {expiration}")
        print(f"   Formatted: {expiration.strftime('%Y-%m-%d %H:%M:%S')}")
        # Handle both timezone-aware and naive datetimes
        if expiration.tzinfo is not None:
            now = datetime.now(expiration.tzinfo)
        else:
            now = datetime.now()
        print(f"   Days until expiration: {(expiration - now).days}")
    else:
        print("❌ Failed to extract expiration date")
    
    ftp.disconnect()


if __name__ == "__main__":
    # Run test if executed directly
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'write':
        test_metadata_write()
    else:
        print("Usage:")
        print("  python castus_metadata.py        # Test reading metadata")
        print("  python castus_metadata.py write  # Test writing metadata")
        test_metadata_extraction()