import ftplib
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class FTPManager:
    def __init__(self, config):
        self.config = config
        self.ftp = None
        self.connected = False
    
    def connect(self):
        """Establish FTP connection"""
        try:
            self.ftp = ftplib.FTP()
            self.ftp.connect(self.config['host'], self.config['port'])
            self.ftp.login(self.config['user'], self.config['password'])
            self.connected = True
            logger.info(f"Connected to {self.config['host']}")
            return True
        except Exception as e:
            logger.error(f"FTP connection failed: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close FTP connection"""
        if self.ftp and self.connected:
            try:
                self.ftp.quit()
            except:
                pass
            self.connected = False
    
    def test_connection(self):
        """Test FTP connection"""
        if self.connect():
            self.disconnect()
            return True
        return False
    
    def list_files(self, path="/"):
        """List files in directory"""
        if not self.connected:
            if not self.connect():
                return []
        
        try:
            files = []
            self.ftp.cwd(path)
            
            # Get detailed file listing
            file_list = []
            self.ftp.retrlines('LIST', file_list.append)
            
            for line in file_list:
                parts = line.split()
                if len(parts) >= 9:
                    permissions = parts[0]
                    size = int(parts[4]) if parts[4].isdigit() else 0
                    name = ' '.join(parts[8:])
                    
                    # Skip directories (starting with 'd')
                    if not permissions.startswith('d'):
                        files.append({
                            'name': name,
                            'size': size,
                            'path': os.path.join(path, name).replace('\\', '/'),
                            'permissions': permissions
                        })
            
            return files
            
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")
            return []
    
    def get_file_size(self, filepath):
        """Get file size"""
        if not self.connected:
            if not self.connect():
                return 0
        
        try:
            return self.ftp.size(filepath)
        except:
            return 0
    
    def download_file(self, remote_path, local_path):
        """Download file from FTP server"""
        if not self.connected:
            if not self.connect():
                return False
        
        try:
            with open(local_path, 'wb') as local_file:
                self.ftp.retrbinary(f'RETR {remote_path}', local_file.write)
            return True
        except Exception as e:
            logger.error(f"Download failed: {str(e)}")
            return False
    
    def upload_file(self, local_path, remote_path):
        """Upload file to FTP server"""
        if not self.connected:
            if not self.connect():
                return False
        
        try:
            with open(local_path, 'rb') as local_file:
                self.ftp.storbinary(f'STOR {remote_path}', local_file)
            return True
        except Exception as e:
            logger.error(f"Upload failed: {str(e)}")
            return False
    
    def copy_file_to(self, file_info, target_ftp):
        """Copy file to another FTP server"""
        try:
            # Download to temp file
            temp_path = f"/tmp/{file_info['name']}"
            
            if self.download_file(file_info['path'], temp_path):
                success = target_ftp.upload_file(temp_path, file_info['path'])
                os.remove(temp_path)  # Clean up temp file
                return success
            
            return False
            
        except Exception as e:
            logger.error(f"Copy failed: {str(e)}")
            return False
    
    def update_file_to(self, file_info, target_ftp):
        """Update file on another FTP server"""
        return self.copy_file_to(file_info, target_ftp)  # Same as copy for now