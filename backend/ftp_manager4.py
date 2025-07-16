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
            
            # Debug logging
            logger.debug(f"Listing files in path: {path}")
            
            self.ftp.cwd(path)
            
            # Get detailed file listing
            file_list = []
            self.ftp.retrlines('LIST', file_list.append)
            
            logger.debug(f"Raw FTP listing for {path}:")
            for line in file_list[:5]:  # Log first 5 lines
                logger.debug(f"  {line}")
            
            for line in file_list:
                parts = line.split()
                if len(parts) >= 9:
                    permissions = parts[0]
                    size = int(parts[4]) if parts[4].isdigit() else 0
                    name = ' '.join(parts[8:])
                    
                    # Skip directories (starting with 'd') and special entries
                    if not permissions.startswith('d') and name not in ['.', '..']:
                        file_info = {
                            'name': name,
                            'size': size,
                            'permissions': permissions,
                            # Don't set path here - let the scanner handle relative paths
                            'full_path': os.path.join(path, name).replace('\\', '/')
                        }
                        files.append(file_info)
                        
            logger.debug(f"Found {len(files)} files in {path}")
            if files:
                logger.debug(f"Sample files: {[f['name'] for f in files[:3]]}")
            
            return files
            
        except Exception as e:
            logger.error(f"Error listing files in {path}: {str(e)}")
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
            logger.debug(f"=== UPLOAD DEBUG ===")
            logger.debug(f"Local file: {local_path}")
            logger.debug(f"Remote path: {remote_path}")
            logger.debug(f"Local file exists: {os.path.exists(local_path)}")
            if os.path.exists(local_path):
                logger.debug(f"Local file size: {os.path.getsize(local_path)} bytes")
            
            # Create directory if it doesn't exist
            remote_dir = os.path.dirname(remote_path)
            logger.debug(f"Remote directory: {remote_dir}")
            
            if remote_dir and remote_dir != '/' and remote_dir != '.':
                logger.debug(f"Creating remote directory: {remote_dir}")
                success = self.create_directory(remote_dir)
                if not success:
                    logger.error(f"Failed to create directory: {remote_dir}")
                    return False
            
            # Get current working directory
            try:
                current_dir = self.ftp.pwd()
                logger.debug(f"Current FTP directory: {current_dir}")
            except Exception as e:
                logger.debug(f"Could not get current directory: {e}")
            
            # Upload the file
            logger.debug(f"Starting upload with STOR command...")
            with open(local_path, 'rb') as local_file:
                result = self.ftp.storbinary(f'STOR {remote_path}', local_file)
                logger.debug(f"STOR command result: {result}")
            
            # Verify the upload by checking if file exists
            try:
                logger.debug(f"Verifying upload by checking file size...")
                remote_size = self.ftp.size(remote_path)
                local_size = os.path.getsize(local_path)
                logger.debug(f"Remote file size: {remote_size}, Local file size: {local_size}")
                
                if remote_size == local_size:
                    logger.debug(f"Upload verification successful!")
                    return True
                else:
                    logger.error(f"Upload verification failed! Size mismatch.")
                    return False
                    
            except Exception as verify_error:
                logger.error(f"Upload verification failed: {verify_error}")
                # Try alternative verification
                try:
                    logger.debug(f"Trying alternative verification with LIST...")
                    file_list = []
                    self.ftp.retrlines(f'LIST {remote_path}', file_list.append)
                    if file_list:
                        logger.debug(f"File exists in LIST: {file_list[0]}")
                        return True
                    else:
                        logger.error(f"File not found in LIST")
                        return False
                except Exception as alt_verify_error:
                    logger.error(f"Alternative verification also failed: {alt_verify_error}")
                    return False
            
        except Exception as e:
            logger.error(f"Upload failed: {str(e)}", exc_info=True)
            return False
    
    def create_directory(self, path):
        """Create directory if it doesn't exist"""
        if not self.connected:
            if not self.connect():
                return False
        
        try:
            # Split path into parts and create each level
            parts = path.strip('/').split('/')
            current_path = ''
            
            for part in parts:
                if part:  # Skip empty parts
                    current_path += '/' + part
                    try:
                        self.ftp.mkd(current_path)
                        logger.debug(f"Created directory: {current_path}")
                    except ftplib.error_perm as e:
                        # Directory might already exist
                        if "550" in str(e):  # Directory exists
                            logger.debug(f"Directory already exists: {current_path}")
                        else:
                            logger.error(f"Error creating directory {current_path}: {str(e)}")
                            return False
            return True
        except Exception as e:
            logger.error(f"Error creating directory {path}: {str(e)}")
            return False
    
    def copy_file_to(self, file_info, target_ftp, keep_temp=False):
        """Copy file to another FTP server"""
        try:
            # Use the full_path for download, but path for upload (relative path)
            source_path = file_info.get('full_path', file_info.get('path', file_info['name']))
            target_path = file_info.get('path', file_info['name'])
            
            logger.debug(f"=== COPY FILE DEBUG ===")
            logger.debug(f"Source path: {source_path}")
            logger.debug(f"Target path: {target_path}")
            logger.debug(f"File info: {file_info}")
            logger.debug(f"Keep temp file: {keep_temp}")
            
            # Download to temp file
            temp_path = f"/tmp/{file_info['name']}"
            logger.debug(f"Temp file path: {temp_path}")
            
            logger.debug(f"Starting download from source...")
            if self.download_file(source_path, temp_path):
                logger.debug(f"Download successful, starting upload to target...")
                success = target_ftp.upload_file(temp_path, target_path)
                logger.debug(f"Upload result: {success}")
                
                if not keep_temp:
                    try:
                        os.remove(temp_path)  # Clean up temp file
                        logger.debug(f"Cleaned up temp file")
                    except:
                        pass
                else:
                    logger.debug(f"Keeping temp file for debugging: {temp_path}")
                    
                return success
            else:
                logger.error(f"Download failed for {source_path}")
                return False
            
        except Exception as e:
            logger.error(f"Copy failed: {str(e)}", exc_info=True)
            return False
    
    def update_file_to(self, file_info, target_ftp, keep_temp=False):
        """Update file on another FTP server"""
        return self.copy_file_to(file_info, target_ftp, keep_temp)  # Same as copy for now