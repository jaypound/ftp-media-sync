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
    
    def _quote_path_if_needed(self, path):
        """Quote FTP path if it contains spaces or special characters"""
        # Check for characters that typically need quoting in FTP
        special_chars = [' ', '(', ')', '&', "'", '"']
        needs_quoting = any(char in path for char in special_chars)
        
        if needs_quoting and not (path.startswith('"') and path.endswith('"')):
            return f'"{path}"'
        return path
    
    def _generate_alternative_paths(self, full_remote_path):
        """Generate alternative paths for server with symbolic links and quoted folders"""
        alternatives = []
        
        # Directories that have quotes around them on this server
        quoted_dirs = {
            'ATL26 On-Air Content': "'ATL26 On-Air Content'",
            'ATLANTA NOW': "'ATLANTA NOW'", 
            'DEFAULT ROTATION': "'DEFAULT ROTATION'",
            'INCLUSION MONTHS': "'INCLUSION MONTHS'",
            'INSIDE ATLANTA': "'INSIDE ATLANTA'",
            'LEGISLATIVE MINUTE': "'LEGISLATIVE MINUTE'",
            'MOVING ATLANTA FORWARD': "'MOVING ATLANTA FORWARD'",
            'SPECIAL PROJECTS': "'SPECIAL PROJECTS'"
        }
        
        # Original path
        alternatives.append(("Original", full_remote_path))
        
        # Handle symbolic link: /mnt/main -> /mnt/md127
        if full_remote_path.startswith('/mnt/main/'):
            md127_path = full_remote_path.replace('/mnt/main/', '/mnt/md127/', 1)
            alternatives.append(("Symlink resolved", md127_path))
            
            # Apply quoted folder transformations to symlink resolved path
            quoted_md127_path = md127_path
            for unquoted, quoted in quoted_dirs.items():
                if unquoted in quoted_md127_path:
                    quoted_md127_path = quoted_md127_path.replace(unquoted, quoted)
            
            if quoted_md127_path != md127_path:
                alternatives.append(("Symlink + quoted folders", quoted_md127_path))
        
        # Apply quoted folder transformations to original path
        quoted_original = full_remote_path
        for unquoted, quoted in quoted_dirs.items():
            if unquoted in quoted_original:
                quoted_original = quoted_original.replace(unquoted, quoted)
        
        if quoted_original != full_remote_path:
            alternatives.append(("Original + quoted folders", quoted_original))
        
        return alternatives

    def _download_with_cwd(self, full_remote_path, local_file):
        """Alternative download method using directory change"""
        try:
            # Save current directory
            original_dir = self.ftp.pwd()
            logger.info(f"Current directory: {original_dir}")
            
            # Split path into directory and filename
            remote_dir = os.path.dirname(full_remote_path)
            filename = os.path.basename(full_remote_path)
            
            logger.info(f"Changing to directory: {remote_dir}")
            logger.info(f"Downloading file: {filename}")
            
            # Change to the file's directory
            self.ftp.cwd(remote_dir)
            
            # Download just the filename
            self.ftp.retrbinary(f'RETR {filename}', local_file.write)
            
            # Restore original directory
            self.ftp.cwd(original_dir)
            
            return True
            
        except Exception as e:
            logger.error(f"CWD download method failed: {str(e)}")
            # Try to restore original directory
            try:
                self.ftp.cwd(original_dir)
            except:
                pass
            return False
    
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
            quoted_path = self._quote_path_if_needed(filepath)
            return self.ftp.size(quoted_path)
        except:
            return 0
    
    def download_file(self, remote_path, local_path):
        """Download file from FTP server"""
        if not self.connected:
            logger.info("FTP not connected, attempting to connect...")
            if not self.connect():
                logger.error("Failed to establish FTP connection for download")
                return False
        
        try:
            # Handle relative paths by combining with base path
            base_path = self.config.get('path', '/')
            
            if remote_path.startswith('/'):
                # Already an absolute path
                full_remote_path = remote_path
            else:
                # Relative path - combine with base path
                if base_path.endswith('/'):
                    full_remote_path = base_path + remote_path
                else:
                    full_remote_path = base_path + '/' + remote_path
            
            # Clean up any double slashes
            full_remote_path = full_remote_path.replace('//', '/')
            
            logger.info(f"Downloading from FTP path: {full_remote_path}")
            logger.info(f"Base path: {base_path}, Remote path: {remote_path}")
            
            # Verify file exists first
            try:
                file_size = self.ftp.size(self._quote_path_if_needed(full_remote_path))
                logger.info(f"File exists on server with size: {file_size} bytes")
            except Exception as e:
                logger.error(f"File does not exist or size check failed: {str(e)}")
                # Try listing the directory to see what's there
                try:
                    remote_dir = os.path.dirname(full_remote_path)
                    logger.info(f"Listing contents of directory: {remote_dir}")
                    file_list = []
                    self.ftp.retrlines(f'LIST {self._quote_path_if_needed(remote_dir)}', file_list.append)
                    
                    # Look for similar filenames
                    target_filename = os.path.basename(full_remote_path)
                    logger.info(f"Looking for file: {target_filename}")
                    logger.info(f"Directory listing ({len(file_list)} entries):")
                    
                    # Show all files in directory to help debug
                    for line in file_list:
                        logger.info(f"  {line}")
                        if target_filename.lower() in line.lower():
                            logger.info(f">>> POSSIBLE MATCH: {line}")
                    
                    # Also try exact filename searches with different cases
                    exact_matches = []
                    for line in file_list:
                        # Extract filename from LIST output (usually at the end)
                        parts = line.split()
                        if parts and parts[-1]:
                            filename = parts[-1]
                            if filename == target_filename:
                                exact_matches.append(f"Exact match: {line}")
                            elif filename.lower() == target_filename.lower():
                                exact_matches.append(f"Case-insensitive match: {line}")
                    
                    if exact_matches:
                        for match in exact_matches:
                            logger.info(f">>> {match}")
                    else:
                        logger.warning(f"No exact matches found for: {target_filename}")
                        
                except Exception as list_e:
                    logger.error(f"Could not list directory: {str(list_e)}")
            
            # Create local directory if it doesn't exist
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            
            # Try multiple approaches for problematic files
            # Server has symbolic links (/mnt/main -> /mnt/md127) and quoted folder names
            
            # Generate alternative paths for this server's peculiarities  
            alt_paths = self._generate_alternative_paths(full_remote_path)
            download_attempts = []
            
            # Add attempts for each alternative path
            for path_desc, alt_path in alt_paths:
                download_attempts.extend([
                    # Unquoted approach
                    (f"{path_desc} (unquoted)", lambda p=alt_path: self.ftp.retrbinary(f'RETR {p}', local_file.write)),
                    # CWD approach  
                    (f"{path_desc} (CWD)", lambda p=alt_path: self._download_with_cwd(p, local_file))
                ])
            
            # Original approach as final fallback
            download_attempts.append((
                "Original quoted", 
                lambda: self.ftp.retrbinary(f'RETR "{full_remote_path}"', local_file.write)
            ))
            
            download_success = False
            last_error = None
            
            for i, (method_desc, attempt_func) in enumerate(download_attempts):
                try:
                    logger.info(f"Download method {i+1}: {method_desc}")
                    
                    with open(local_path, 'wb') as local_file:
                        if "CWD" in method_desc:  # CWD approach
                            download_success = attempt_func()
                        else:
                            attempt_func()
                            download_success = True
                    
                    if download_success:
                        logger.info(f"Download method {i+1} succeeded: {method_desc}")
                        break
                        
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Download method {i+1} failed ({method_desc}): {last_error}")
                    # Clean up partial file for next attempt
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    continue
            
            if not download_success:
                raise Exception(f"All download methods failed. Last error: {last_error}")
            
            # Verify the file was downloaded
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                logger.info(f"Successfully downloaded {os.path.getsize(local_path)} bytes")
                return True
            else:
                logger.error(f"Downloaded file is empty or doesn't exist: {local_path}")
                return False
                
        except Exception as e:
            logger.error(f"Download failed for {remote_path}: {str(e)}")
            # Try to clean up partial file
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    logger.info(f"Cleaned up partial download: {local_path}")
                except:
                    pass
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
            logger.debug(f"Config contents: {self.config}")
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
                    target_dir = os.path.join(base_path, remote_dir).replace('\\', '/')
                    logger.debug(f"Changing to target directory: {target_dir}")
                    self.ftp.cwd(target_dir)
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
                remote_size = self.ftp.size(self._quote_path_if_needed(upload_filename))
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
                    self.ftp.retrlines(f'LIST {self._quote_path_if_needed(upload_filename)}', file_list.append)
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
            # Get current directory as base
            base_dir = self.ftp.pwd()
            logger.debug(f"Creating directory '{path}' relative to: {base_dir}")
            
            # Split path into parts and create each level
            parts = path.strip('/').split('/')
            current_path = base_dir.rstrip('/')
            
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
    
    def delete_file(self, remote_path):
        """Delete file from FTP server"""
        if not self.connected:
            logger.info("FTP not connected, attempting to connect...")
            if not self.connect():
                logger.error("Failed to establish FTP connection for deletion")
                return False
        
        try:
            # Handle relative paths by combining with base path
            base_path = self.config.get('path', '/')
            
            if remote_path.startswith('/'):
                # Already an absolute path
                full_remote_path = remote_path
            else:
                # Relative path - combine with base path
                if base_path.endswith('/'):
                    full_remote_path = base_path + remote_path
                else:
                    full_remote_path = base_path + '/' + remote_path
            
            # Clean up any double slashes
            full_remote_path = full_remote_path.replace('//', '/')
            
            logger.info(f"Deleting file from FTP path: {full_remote_path}")
            logger.info(f"Base path: {base_path}, Remote path: {remote_path}")
            
            # Delete the file (quote path if needed)
            quoted_path = self._quote_path_if_needed(full_remote_path)
            self.ftp.delete(quoted_path)
            
            logger.info(f"Successfully deleted file: {full_remote_path}")
            return True
                
        except Exception as e:
            logger.error(f"Delete failed for {remote_path}: {str(e)}")
            return False