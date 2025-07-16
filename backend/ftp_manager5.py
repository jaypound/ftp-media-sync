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
            
            # Get current working directory before we start
            try:
                current_dir = self.ftp.pwd()
                logger.debug(f"Current FTP directory before upload: {current_dir}")
            except Exception as e:
                logger.debug(f"Could not get current directory: {e}")
            
            # Change to the base directory (from config)
            base_path = self.config.get('path', '/')
            logger.debug(f"Changing to base directory: {base_path}")
            try:
                self.ftp.cwd(base_path)
                new_dir = self.ftp.pwd()
                logger.debug(f"Now in directory: {new_dir}")
            except Exception as e:
                logger.error(f"Failed to change to base directory {base_path}: {e}")
                return False
            
            # Create directory if it doesn't exist
            remote_dir = os.path.dirname(remote_path)
            logger.debug(f"Remote directory to create: {remote_dir}")
            
            if remote_dir and remote_dir != '/' and remote_dir != '.':
                logger.debug(f"Creating remote directory: {remote_dir}")
                success = self.create_directory(remote_dir)
                if not success:
                    logger.error(f"Failed to create directory: {remote_dir}")
                    return False
                    
                # Change to the target directory for upload
                try:
                    self.ftp.cwd(os.path.join(base_path, remote_dir).replace('\\', '/'))
                    upload_dir = self.ftp.pwd()
                    logger.debug(f"Changed to upload directory: {upload_dir}")
                    # Upload just the filename since we're in the right directory
                    upload_filename = os.path.basename(remote_path)
                except Exception as e:
                    logger.error(f"Failed to change to upload directory: {e}")
                    return False
            else:
                # Uploading to root directory
                upload_filename = remote_path
            
            # Upload the file
            logger.debug(f"Starting upload with STOR command for: {upload_filename}")
            with open(local_path, 'rb') as local_file:
                result = self.ftp.storbinary(f'STOR {upload_filename}', local_file)
                logger.debug(f"STOR command result: {result}")
            
            # Verify the upload by checking if file exists
            try:
                logger.debug(f"Verifying upload by checking file size...")
                remote_size = self.ftp.size(upload_filename)
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
                    self.ftp.retrlines(f'LIST {upload_filename}', file_list.append)
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
    
    def copy_file_to(self, file_info, target_ftp):
        """Copy file to another FTP server"""
        try:
            # Use the full_path for download, but path for upload (relative path)
            source_path = file_info.get('full_path', file_info.get('path', file_info['name']))
            target_path = file_info.get('path', file_info['name'])
            
            logger.debug(f"Copying file: {source_path} -> {target_path}")
            
            # Download to temp file
            temp_path = f"/tmp/{file_info['name']}"
            
            if self.download_file(source_path, temp_path):
                success = target_ftp.upload_file(temp_path, target_path)
                try:
                    os.remove(temp_path)  # Clean up temp file
                except:
                    pass
                return success
            
            return False
            
        except Exception as e:
            logger.error(f"Copy failed: {str(e)}")
            return False
    
    def update_file_to(self, file_info, target_ftp, keep_temp=False):
        """Update file on another FTP server"""
        return self.copy_file_to(file_info, target_ftp, keep_temp)  # Same as copy for now