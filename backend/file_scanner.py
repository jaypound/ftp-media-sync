import os
import logging
from datetime import datetime
import logging.handlers

# Set up module logger
logger = logging.getLogger(__name__)

# Create a separate file logger for detailed file scanning logs
def setup_file_scanner_logger():
    """Set up a dedicated file logger for file scanner with timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f'logs/file_scanner_{timestamp}.log'
    
    # Create file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Create formatter with timestamp
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # Create a separate logger for file scanning details
    file_scanner_logger = logging.getLogger('file_scanner_detailed')
    file_scanner_logger.setLevel(logging.DEBUG)
    file_scanner_logger.addHandler(file_handler)
    
    return file_scanner_logger

# Initialize the file scanner logger
file_logger = setup_file_scanner_logger()

class FileScanner:
    def __init__(self, ftp_manager):
        self.ftp_manager = ftp_manager
    
    def scan_directory(self, path, filters=None):
        """Scan directory for files matching filters"""
        if filters is None:
            filters = {}
        
        # Log to both console and file
        logger.info(f"Starting scan of: {path}")
        file_logger.info("="*80)
        file_logger.info(f"NEW SCAN STARTED - Path: {path}")
        file_logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        file_logger.info(f"Filters: {filters}")
        file_logger.info("="*80)
        
        # Check if trying to scan Recordings directory
        if 'Recordings' in path or 'recordings' in path:
            logger.warning(f"Skipping scan of Recordings directory: {path}")
            file_logger.warning(f"SKIPPED: Recordings directory detected: {path}")
            return []
        
        # Store the base path for relative path calculation
        base_path = path.rstrip('/')
        files = []
        
        logger.info(f"Starting scan of: {path} (base: {base_path})")
        logger.info(f"Filters: include_subdirs={filters.get('include_subdirs', True)}, extensions={filters.get('extensions', [])}")
        
        try:
            # Get files from current directory
            current_files = self.ftp_manager.list_files(path)
            logger.info(f"Found {len(current_files)} files in root directory: {path}")
            file_logger.info(f"\nScanning directory: {path}")
            file_logger.info(f"Total files found: {len(current_files)}")
            
            for file_info in current_files:
                file_name = file_info.get('name', 'unknown')
                file_logger.debug(f"Checking file: {file_name} - Size: {file_info.get('size', 0)}")
                
                # Special logging for LM files
                if '_LM_' in file_name:
                    logger.info(f"Found LM file: {file_name} in {path}")
                    file_logger.info(f"LM FILE FOUND: {file_name} in {path}")
                
                if self._should_include_file(file_info, filters):
                    # Add relative path information
                    file_info = self._add_relative_path(file_info, path, base_path)
                    files.append(file_info)
                    file_logger.info(f"INCLUDED: {file_name} - Matches filters")
                else:
                    file_logger.debug(f"EXCLUDED: {file_name} - Does not match filters")
            
            # Recursively scan subdirectories if enabled
            if filters.get('include_subdirs', True):
                subdirs = self._get_subdirectories(path)
                logger.debug(f"Found subdirectories in {path}: {subdirs}")
                for subdir in subdirs:
                    subdir_path = os.path.join(path, subdir).replace('\\', '/')
                    logger.info(f"Recursively scanning subdirectory: {subdir_path}")
                    try:
                        subdir_files = self._scan_directory_recursive(subdir_path, base_path, filters)
                        logger.info(f"Found {len(subdir_files)} files in subdirectory: {subdir_path}")
                        files.extend(subdir_files)
                    except Exception as e:
                        logger.error(f"Error scanning subdirectory {subdir_path}: {str(e)}")
            
            logger.debug(f"Total files found in scan: {len(files)}")
            
            # Log summary to file
            file_logger.info("\n" + "="*80)
            file_logger.info("SCAN COMPLETED")
            file_logger.info(f"Total files included: {len(files)}")
            file_logger.info(f"Scan completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if files:
                file_logger.info("\nIncluded files:")
                for f in files[:20]:  # Show first 20 files
                    file_logger.info(f"  - {f.get('name', 'unknown')} ({f.get('size', 0)} bytes)")
                if len(files) > 20:
                    file_logger.info(f"  ... and {len(files) - 20} more files")
            file_logger.info("="*80 + "\n")
            
            return files
            
        except Exception as e:
            logger.error(f"Scan error in {path}: {str(e)}")
            return []
    
    def _scan_directory_recursive(self, current_path, base_path, filters):
        """Recursively scan a subdirectory"""
        files = []
        
        # Skip Recordings directories
        if 'Recordings' in current_path or 'recordings' in current_path:
            logger.info(f"Skipping Recordings directory in recursive scan: {current_path}")
            return []
        
        logger.debug(f"Recursive scan: {current_path} (base: {base_path})")
        
        try:
            # Get files from current directory
            current_files = self.ftp_manager.list_files(current_path)
            logger.info(f"Found {len(current_files)} total files in {current_path}")
            
            # Log sample files for debugging
            if current_files:
                logger.info(f"Sample files in {current_path}: {[f['name'] for f in current_files[:3]]}")
            
            included_count = 0
            for file_info in current_files:
                file_name = file_info.get('name', 'unknown')
                
                # Special logging for LM files
                if '_LM_' in file_name:
                    logger.info(f"Found LM file in recursive scan: {file_name} in {current_path}")
                    file_logger.info(f"LM FILE IN RECURSIVE: {file_name} in {current_path}")
                
                if self._should_include_file(file_info, filters):
                    # Add relative path information
                    file_info = self._add_relative_path(file_info, current_path, base_path)
                    files.append(file_info)
                    included_count += 1
            
            logger.info(f"Included {included_count} files from {current_path} after filtering")
            
            # Continue recursively scanning subdirectories
            subdirs = self._get_subdirectories(current_path)
            logger.debug(f"Found subdirectories in {current_path}: {subdirs}")
            for subdir in subdirs:
                subdir_path = os.path.join(current_path, subdir).replace('\\', '/')
                subdir_files = self._scan_directory_recursive(subdir_path, base_path, filters)
                files.extend(subdir_files)
                
        except Exception as e:
            logger.error(f"Recursive scan error in {current_path}: {str(e)}")
            
        logger.debug(f"Recursive scan of {current_path} found {len(files)} files")
        return files
    
    def _add_relative_path(self, file_info, current_path, base_path):
        """Add relative path information to file_info"""
        # Calculate relative path from base directory
        current_path_clean = current_path.rstrip('/')
        base_path_clean = base_path.rstrip('/')
        
        if current_path_clean == base_path_clean:
            # File is in the root directory
            relative_path = file_info['name']
        else:
            # File is in a subdirectory
            # Remove the base path to get the relative directory
            if current_path_clean.startswith(base_path_clean + '/'):
                relative_dir = current_path_clean[len(base_path_clean + '/'):]
                relative_path = os.path.join(relative_dir, file_info['name']).replace('\\', '/')
            else:
                # Fallback if path calculation fails
                logger.warning(f"Path calculation failed for {file_info['name']} in {current_path}")
                relative_path = file_info['name']
        
        # Create a new file_info dict with path information
        updated_file_info = file_info.copy()
        updated_file_info['path'] = relative_path
        updated_file_info['full_path'] = current_path_clean + '/' + file_info['name']
        
        # Detect content type from filename
        content_type = self._detect_content_type(file_info['name'])
        if content_type:
            updated_file_info['content_type'] = content_type
            # Log every file with detected content type for debugging
            logger.info(f"File: {file_info['name']} - Detected type: {content_type} - Path: {current_path_clean}")
            
            # Check if file is in correct folder
            is_misplaced = self._check_if_misplaced(content_type, current_path_clean)
            updated_file_info['is_misplaced'] = is_misplaced
            
            # Debug logging for misplaced files
            if is_misplaced:
                logger.warning(f"MISPLACED FILE DETECTED: {file_info['name']} (type: {content_type}) in {current_path_clean}")
                file_logger.warning(f"MISPLACED: {file_info['name']} - Type: {content_type} - Path: {current_path_clean}")
        
        # Debug logging
        logger.debug(f"File: {file_info['name']} -> Relative path: {relative_path}")
        
        return updated_file_info
    
    def _should_include_file(self, file_info, filters):
        """Check if file should be included based on filters"""
        filename = file_info['name']
        
        # File extension filter
        extensions = filters.get('extensions', [])
        if extensions:
            file_ext = os.path.splitext(filename)[1].lower().lstrip('.')
            if file_ext not in [ext.lower() for ext in extensions]:
                logger.debug(f"Excluding {filename} - extension '{file_ext}' not in {extensions}")
                file_logger.debug(f"  Extension filter: '{file_ext}' not in {extensions}")
                return False
            else:
                file_logger.debug(f"  Extension filter: '{file_ext}' matched in {extensions}")
        
        # File size filters
        min_size = filters.get('min_size', 0)
        max_size = filters.get('max_size', float('inf'))
        
        if file_info['size'] < min_size:
            logger.debug(f"Excluding {filename} - size {file_info['size']} < min {min_size}")
            file_logger.debug(f"  Size filter: {file_info['size']} bytes < minimum {min_size} bytes")
            return False
        if file_info['size'] > max_size:
            logger.debug(f"Excluding {filename} - size {file_info['size']} > max {max_size}")
            file_logger.debug(f"  Size filter: {file_info['size']} bytes > maximum {max_size} bytes")
            return False
        
        logger.debug(f"Including {filename} - passed all filters")
        file_logger.debug(f"  All filters passed - File will be included")
        return True
    
    def _get_subdirectories(self, path):
        """Get list of subdirectories"""
        if not self.ftp_manager.connected:
            if not self.ftp_manager.connect():
                return []
        
        try:
            subdirs = []
            self.ftp_manager.ftp.cwd(path)
            
            file_list = []
            self.ftp_manager.ftp.retrlines('LIST', file_list.append)
            
            logger.debug(f"Getting subdirectories for {path}, found {len(file_list)} entries")
            
            # Directories to exclude from scanning
            excluded_dirs = ['Recordings', 'recordings']
            
            # Also exclude SDI directories if we're in the main directory
            if path == '/mnt/main' or path == '/mnt/md127':
                excluded_dirs.extend(['1-SDI in', '2-SDI in', '3-SDI in'])
                logger.info(f"In main directory, also excluding SDI directories")
            
            for line in file_list:
                parts = line.split()
                if len(parts) >= 9:
                    permissions = parts[0]
                    name = ' '.join(parts[8:])
                    
                    # Directory starts with 'd'
                    if permissions.startswith('d') and name not in ['.', '..']:
                        # Skip excluded directories
                        if name in excluded_dirs:
                            logger.info(f"Excluding directory from scan: {name}")
                            continue
                        subdirs.append(name)
                        logger.debug(f"Found subdirectory: {name}")
            
            logger.info(f"Found {len(subdirs)} subdirectories in {path}: {subdirs}")
            return subdirs
            
        except Exception as e:
            logger.error(f"Error getting subdirectories: {str(e)}")
            return []
    
    def _detect_content_type(self, filename):
        """Detect content type from filename patterns like _MTG_, _PKG_, etc."""
        import re
        
        # Common content type patterns in filenames
        content_types = [
            'AN', 'ATLD', 'BMP', 'IM', 'IMOW', 'IA', 'LM', 'MTG', 
            'MAF', 'PKG', 'PMO', 'PSA', 'SZL', 'SPP', 'SSP'
        ]
        
        # Look for pattern like _TYPE_ in filename
        for content_type in content_types:
            pattern = f'_{content_type}_'
            if pattern in filename.upper():
                return content_type
        
        # Also check for pattern at start like 251210_SPP_
        match = re.match(r'^\d{6}_([A-Z]+)_', filename)
        if match and match.group(1) in content_types:
            return match.group(1)
        
        return None
    
    def _check_if_misplaced(self, content_type, folder_path):
        """Check if a file with given content type is in the wrong folder"""
        # Skip checking files in FILL folders and all subfolders
        folder_lower = folder_path.lower()
        if '/fill/' in folder_lower or folder_lower.endswith('/fill'):
            return False
            
        # Map content types to expected folder patterns based on actual folder structure
        folder_mappings = {
            'AN': ['atlanta now'],  # ATLANTA NOW folder
            'ATLD': ['atl direct'],  # ATL DIRECT folder
            'BMP': ['bumps'],  # BUMPS folder
            'IM': ['interstitials', 'interstitial'],  # Not seen in folder list
            'IMOW': ['imow'],  # IMOW folder
            'IA': ['inside atlanta'],  # INSIDE ATLANTA folder
            'LM': ['legislative minute'],  # LEGISLATIVE MINUTE folder
            'MTG': ['meetings'],  # MEETINGS folder
            'MAF': ['moving atlanta forward'],  # MOVING ATLANTA FORWARD folder
            'PKG': ['pkgs'],  # PKGS folder
            'PMO': ['promos'],  # PROMOS folder
            'PSA': ['psas'],  # PSAs folder
            'SZL': ['sizzles'],  # SIZZLES folder
            'SPP': ['special projects'],  # SPECIAL PROJECTS folder
            'SSP': ['special projects']  # Also SPECIAL PROJECTS folder
        }
        
        # Get expected folders for this content type
        expected_folders = folder_mappings.get(content_type, [])
        if not expected_folders:
            return False
        
        # Check if current folder contains any of the expected folder names
        folder_lower = folder_path.lower()
        
        # Debug logging
        logger.debug(f"Checking if {content_type} file is misplaced in: {folder_path}")
        logger.debug(f"Expected folders: {expected_folders}")
        logger.debug(f"Folder path (lowercase): {folder_lower}")
        
        # Check if any expected folder name is in the path
        for expected in expected_folders:
            if expected in folder_lower:
                logger.debug(f"Found expected folder '{expected}' in path - file is correctly placed")
                return False  # File is in correct folder
        
        # Additional check: if file is ONLY in a generic content folder (not in a specific content type folder)
        # Don't allow generic folders to override specific content type checks
        # For example: /ATL26 On-Air Content/PKGS should still check for correct content type
        generic_folders = ['media', 'videos', 'files', 'archive']
        
        # Special handling: if path ends with a content-specific folder like PKGS, don't allow generic override
        path_parts = folder_lower.split('/')
        # Filter out empty parts from path
        path_parts = [p for p in path_parts if p]
        last_folder = path_parts[-1] if path_parts else ''
        
        # More debug logging with path parts
        logger.debug(f"Path parts: {path_parts}")
        logger.debug(f"Last folder: '{last_folder}'")
        
        # If the last folder in path is a known content folder, enforce strict checking
        known_content_folders = ['pkgs', 'meetings', 'legislative minute', 'promos', 'psas', 
                                'bumps', 'inside atlanta', 'moving atlanta forward', 'special projects']
        
        # Log detailed debug info for LM files
        if content_type == 'LM':
            logger.warning(f"LM FILE CHECK: path={folder_path}, last_folder={last_folder}, expected={expected_folders}")
        
        if last_folder in known_content_folders:
            logger.debug(f"In specific content folder '{last_folder}' - strict checking enforced")
            # Don't check generic folders, enforce content type match
        else:
            # Check generic folders only if not in a specific content folder
            for generic in generic_folders:
                if generic in folder_lower:
                    logger.debug(f"Found generic folder '{generic}' - allowing file placement")
                    return False
        
        # File appears to be misplaced
        logger.info(f"FILE IS MISPLACED: {content_type} file not in any of these folders: {expected_folders}")
        return True
    
    def get_file_info(self, file_path, base_path):
        """Get file information for a specific file path"""
        try:
            # Split the path to get directory and filename
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            
            # If directory is empty, use base_path
            if not directory:
                directory = base_path
            else:
                directory = os.path.join(base_path, directory).replace('\\', '/')
            
            # Get file listing from the directory
            files = self.ftp_manager.list_files(directory)
            
            # Find the specific file
            for file_info in files:
                if file_info['name'] == filename:
                    # Add relative path information
                    file_info = self._add_relative_path(file_info, directory, base_path)
                    return file_info
            
            logger.warning(f"File not found: {file_path}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {str(e)}")
            return None