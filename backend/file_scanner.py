import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class FileScanner:
    def __init__(self, ftp_manager):
        self.ftp_manager = ftp_manager
    
    def scan_directory(self, path, filters=None):
        """Scan directory for files matching filters"""
        if filters is None:
            filters = {}
        
        # Store the base path for relative path calculation
        base_path = path.rstrip('/')
        files = []
        
        logger.info(f"Starting scan of: {path} (base: {base_path})")
        logger.info(f"Filters: include_subdirs={filters.get('include_subdirs', True)}, extensions={filters.get('extensions', [])}")
        
        try:
            # Get files from current directory
            current_files = self.ftp_manager.list_files(path)
            logger.info(f"Found {len(current_files)} files in root directory: {path}")
            
            for file_info in current_files:
                if self._should_include_file(file_info, filters):
                    # Add relative path information
                    file_info = self._add_relative_path(file_info, path, base_path)
                    files.append(file_info)
            
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
            return files
            
        except Exception as e:
            logger.error(f"Scan error in {path}: {str(e)}")
            return []
    
    def _scan_directory_recursive(self, current_path, base_path, filters):
        """Recursively scan a subdirectory"""
        files = []
        
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
                return False
        
        # File size filters
        min_size = filters.get('min_size', 0)
        max_size = filters.get('max_size', float('inf'))
        
        if file_info['size'] < min_size:
            logger.debug(f"Excluding {filename} - size {file_info['size']} < min {min_size}")
            return False
        if file_info['size'] > max_size:
            logger.debug(f"Excluding {filename} - size {file_info['size']} > max {max_size}")
            return False
        
        logger.debug(f"Including {filename} - passed all filters")
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
            
            for line in file_list:
                parts = line.split()
                if len(parts) >= 9:
                    permissions = parts[0]
                    name = ' '.join(parts[8:])
                    
                    # Directory starts with 'd'
                    if permissions.startswith('d') and name not in ['.', '..']:
                        subdirs.append(name)
                        logger.debug(f"Found subdirectory: {name}")
            
            logger.info(f"Found {len(subdirs)} subdirectories in {path}: {subdirs}")
            return subdirs
            
        except Exception as e:
            logger.error(f"Error getting subdirectories: {str(e)}")
            return []
    
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