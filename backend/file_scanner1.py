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
        
        files = []
        
        try:
            # Get files from current directory
            current_files = self.ftp_manager.list_files(path)
            
            for file_info in current_files:
                if self._should_include_file(file_info, filters):
                    files.append(file_info)
            
            # Recursively scan subdirectories if enabled
            if filters.get('include_subdirs', True):
                subdirs = self._get_subdirectories(path)
                for subdir in subdirs:
                    subdir_path = os.path.join(path, subdir).replace('\\', '/')
                    files.extend(self.scan_directory(subdir_path, filters))
            
            return files
            
        except Exception as e:
            logger.error(f"Scan error: {str(e)}")
            return []
    
    def _should_include_file(self, file_info, filters):
        """Check if file should be included based on filters"""
        # File extension filter
        extensions = filters.get('extensions', [])
        if extensions:
            file_ext = os.path.splitext(file_info['name'])[1].lower().lstrip('.')
            if file_ext not in [ext.lower() for ext in extensions]:
                return False
        
        # File size filters
        min_size = filters.get('min_size', 0)
        max_size = filters.get('max_size', float('inf'))
        
        if file_info['size'] < min_size or file_info['size'] > max_size:
            return False
        
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
            
            for line in file_list:
                parts = line.split()
                if len(parts) >= 9:
                    permissions = parts[0]
                    name = ' '.join(parts[8:])
                    
                    # Directory starts with 'd'
                    if permissions.startswith('d') and name not in ['.', '..']:
                        subdirs.append(name)
            
            return subdirs
            
        except Exception as e:
            logger.error(f"Error getting subdirectories: {str(e)}")
            return []