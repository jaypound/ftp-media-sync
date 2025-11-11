import ftplib
import os
import logging
import time
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
        
        # Check if this might be a recording file
        if ('3-SDI in' in full_remote_path or '2-SDI in' in full_remote_path or 
            '1-SDI in' in full_remote_path) and 'ATL26 On-Air Content' in full_remote_path:
            # Try Recordings path
            recordings_path = full_remote_path.replace('/mnt/main/ATL26 On-Air Content/', '/mnt/main/Recordings/')
            alternatives.append(("Recordings directory", recordings_path))
        
        # Handle symbolic link: /mnt/main -> /mnt/md127
        if full_remote_path.startswith('/mnt/main/'):
            md127_path = full_remote_path.replace('/mnt/main/', '/mnt/md127/', 1)
            alternatives.append(("Symlink resolved", md127_path))
            
            # Also add Recordings path with md127
            if ('3-SDI in' in full_remote_path or '2-SDI in' in full_remote_path or 
                '1-SDI in' in full_remote_path) and 'ATL26 On-Air Content' in full_remote_path:
                recordings_md127_path = full_remote_path.replace('/mnt/main/ATL26 On-Air Content/', '/mnt/md127/Recordings/')
                alternatives.append(("Recordings directory (md127)", recordings_md127_path))
            
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
            # Test connection first
            try:
                if self.ftp:
                    self.ftp.voidcmd("NOOP")
                else:
                    raise Exception("FTP connection is None")
            except:
                logger.warning("Connection lost during CWD download attempt")
                return False
                
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
    
    def is_connection_alive(self):
        """Check if FTP connection is still alive"""
        if not self.ftp or not self.connected:
            return False
        
        try:
            self.ftp.voidcmd("NOOP")
            return True
        except:
            self.connected = False
            return False
    
    def list_files(self, path="/"):
        """List files in directory"""
        # Test connection and reconnect if needed
        try:
            if self.connected:
                self.ftp.voidcmd("NOOP")
        except:
            logger.info("FTP connection lost, reconnecting...")
            self.connected = False
        
        if not self.connected:
            if not self.connect():
                return []
        
        try:
            files = []
            
            # Debug logging
            logger.debug(f"Listing files in path: {path}")
            
            self.ftp.cwd(path)
            
            # Check if server supports MLST for better file info
            use_mlsd = False
            try:
                # Test if MLSD is supported
                list(self.ftp.mlsd(path=".", facts=["size", "modify", "create", "type"]))
                use_mlsd = True
                logger.debug("Server supports MLSD command")
            except:
                logger.debug("Server does not support MLSD, using LIST")
            
            mlsd_count = 0  # Initialize counter outside the if block
            
            if use_mlsd:
                # Use MLSD for more accurate file information
                try:
                    for name, facts in self.ftp.mlsd(path=".", facts=["size", "modify", "create", "type"]):
                        mlsd_count += 1
                        # Log files with specific patterns for debugging
                        if 'OCA-Elevate' in name or '251001' in name or name.endswith('.png'):
                            logger.info(f"MLSD entry: {name}, facts: {facts}")
                        
                        # More robust file detection - include files without type or with type=file
                        is_file = (facts.get('type') == 'file' or 
                                  (facts.get('type') is None and 'size' in facts) or
                                  facts.get('type') == '')
                        
                        if is_file and name not in ['.', '..']:
                            file_info = {
                                'name': name,
                                'size': int(facts.get('size', 0)),
                                'permissions': '',
                                'full_path': os.path.join(path, name).replace('\\', '/')
                            }
                        
                        # Get timestamps - prefer create time if available
                        if 'create' in facts:
                            # Creation time available
                            create_time = datetime.strptime(facts['create'], "%Y%m%d%H%M%S")
                            file_info['ctime'] = create_time.timestamp()
                            file_info['created'] = create_time.isoformat()
                            # Also use as mtime for compatibility
                            file_info['mtime'] = file_info['ctime']
                            file_info['modified'] = file_info['created']
                        elif 'modify' in facts:
                            # Only modification time available
                            modify_time = datetime.strptime(facts['modify'], "%Y%m%d%H%M%S")
                            file_info['mtime'] = modify_time.timestamp()
                            file_info['modified'] = modify_time.isoformat()
                            # No creation time available
                            file_info['ctime'] = file_info['mtime']
                            file_info['created'] = file_info['modified']
                        else:
                            # No timestamp available
                            file_info['mtime'] = time.time()
                            file_info['modified'] = datetime.now().isoformat()
                            file_info['ctime'] = file_info['mtime']
                            file_info['created'] = file_info['modified']
                        
                        files.append(file_info)
            else:
                # Fall back to LIST command
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
                        
                        # Parse date/time from parts[5:8]
                        # Format can be either "MMM DD HH:MM" or "MMM DD YYYY"
                        month = parts[5]
                        day = parts[6]
                        time_or_year = parts[7]
                        
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
                            
                            # Try to parse the modification time
                            try:
                                if ':' in time_or_year:
                                    # Current year format: "MMM DD HH:MM"
                                    year = datetime.now().year
                                    datetime_str = f"{month} {day} {year} {time_or_year}"
                                    mtime = datetime.strptime(datetime_str, "%b %d %Y %H:%M")
                                else:
                                    # Previous year format: "MMM DD YYYY"
                                    datetime_str = f"{month} {day} {time_or_year}"
                                    mtime = datetime.strptime(datetime_str, "%b %d %Y")
                                
                                # Add timestamp to file_info
                                file_info['mtime'] = mtime.timestamp()
                                file_info['modified'] = mtime.isoformat()
                                # For LIST command, we only get modification time, use it as creation time too
                                file_info['ctime'] = file_info['mtime']
                                file_info['created'] = file_info['modified']
                            except Exception as e:
                                logger.debug(f"Could not parse date for {name}: {e}")
                                # Use current time as fallback
                                file_info['mtime'] = time.time()
                                file_info['modified'] = datetime.now().isoformat()
                                file_info['ctime'] = file_info['mtime']
                                file_info['created'] = file_info['modified']
                            
                            files.append(file_info)
                    
                    logger.info(f"MLSD processed {mlsd_count} entries, found {len(files)} files")
                except Exception as e:
                    logger.error(f"Error during MLSD listing: {str(e)}")
                    use_mlsd = False  # Fall back to LIST
                    
            if not use_mlsd or len(files) == 0:
            
            return files
            
        except Exception as e:
            logger.error(f"Error listing files in {path}: {str(e)}")
            return []
    
    def get_file_size(self, filepath):
        """Get file size"""
        # Test connection and reconnect if needed
        try:
            if self.connected:
                self.ftp.voidcmd("NOOP")
        except:
            logger.info("FTP connection lost, reconnecting...")
            self.connected = False
        
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
        # Always test the connection before download to handle broken connections
        try:
            # Test if connection is still alive
            self.ftp.voidcmd("NOOP")
        except:
            # Connection is broken, reconnect
            logger.info("FTP connection lost, reconnecting...")
            self.connected = False
            if not self.connect():
                logger.error("Failed to re-establish FTP connection for download")
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
                    # Test connection before each download attempt
                    try:
                        if self.ftp:
                            self.ftp.voidcmd("NOOP")
                    except:
                        logger.info(f"Connection lost before attempt {i+1}, reconnecting...")
                        self.connected = False
                        if not self.connect():
                            logger.error("Failed to reconnect for download attempt")
                            last_error = "Failed to reconnect to FTP server"
                            continue
                    
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
                    
                    # If it's a connection error, try to reconnect
                    if "NoneType" in str(e) or "connection" in str(e).lower():
                        logger.info("Detected connection issue, attempting to reconnect...")
                        self.connected = False
                        self.connect()
                    
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
    
    def upload_file(self, local_path, remote_path, skip_verification=False):
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
            logger.info(f"=== UPLOAD PATH DEBUG ===")
            logger.info(f"Config contents: {self.config}")
            logger.info(f"Base path from config: {base_path}")
            logger.info(f"Remote path parameter: {remote_path}")
            
            try:
                self.ftp.cwd(base_path)
                new_dir = self.ftp.pwd()
                logger.info(f"Changed to directory: {new_dir}")
            except Exception as e:
                logger.error(f"Failed to change to base directory {base_path}: {e}")
                return False
            
            # Create directory if it doesn't exist
            remote_dir = os.path.dirname(remote_path)
            logger.info(f"Remote directory from path: {remote_dir}")
            
            if remote_dir and remote_dir != '/' and remote_dir != '.':
                logger.info(f"Need to create remote directory: {remote_dir}")
                success = self.create_directory(remote_dir)
                if not success:
                    logger.error(f"Failed to create directory: {remote_dir}")
                    return False
                else:
                    logger.info(f"Directory created or already exists: {remote_dir}")
                    
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
            
            # Check if file already exists and try to handle overwrite
            try:
                logger.debug(f"Checking if file exists: {upload_filename}")
                existing_size = self.ftp.size(self._quote_path_if_needed(upload_filename))
                if existing_size is not None:
                    logger.debug(f"File exists with size {existing_size}, attempting to overwrite...")
                    try:
                        # Try to delete the existing file
                        self.ftp.delete(self._quote_path_if_needed(upload_filename))
                        logger.debug(f"Existing file deleted successfully")
                    except Exception as del_e:
                        logger.warning(f"Could not delete existing file: {str(del_e)}")
                        # Some FTP servers don't allow delete but do allow overwrite
                        # We'll continue and try STOR which might overwrite
                        logger.debug("Will attempt to overwrite with STOR command")
            except Exception as e:
                # File doesn't exist, which is fine
                logger.debug(f"File doesn't exist (this is okay): {str(e)}")
            
            # Upload the file
            logger.info(f"=== STARTING UPLOAD ===")
            logger.info(f"Current FTP directory: {self.ftp.pwd()}")
            logger.info(f"Upload filename: {upload_filename}")
            logger.info(f"Full expected path: {os.path.join(self.ftp.pwd(), upload_filename)}")
            
            stor_success = False
            try:
                with open(local_path, 'rb') as local_file:
                    result = self.ftp.storbinary(f'STOR {upload_filename}', local_file)
                    logger.info(f"STOR command result: {result}")
                    
                    # If STOR returns success, we can trust it for most servers
                    if "226" in result or "complete" in result.lower():
                        logger.info("STOR command indicates successful transfer")
                        stor_success = True
            except Exception as stor_e:
                logger.error(f"STOR command failed: {str(stor_e)}")
                # Check if it's a permission or overwrite issue
                if "550" in str(stor_e) or "553" in str(stor_e) or "exists" in str(stor_e).lower():
                    logger.error("File exists error detected, trying alternative approach...")
                    
                    # Try uploading with a temporary name and then rename
                    temp_filename = f"{upload_filename}.tmp_{int(time.time())}"
                    logger.debug(f"Attempting to upload with temporary name: {temp_filename}")
                    
                    try:
                        with open(local_path, 'rb') as local_file:
                            result = self.ftp.storbinary(f'STOR {temp_filename}', local_file)
                            logger.debug(f"Temporary file uploaded successfully")
                        
                        # Now try to delete original and rename temp
                        try:
                            logger.debug(f"Deleting original file: {upload_filename}")
                            self.ftp.delete(self._quote_path_if_needed(upload_filename))
                        except Exception as del_e2:
                            logger.warning(f"Could not delete original: {del_e2}")
                        
                        try:
                            logger.debug(f"Renaming {temp_filename} to {upload_filename}")
                            self.ftp.rename(temp_filename, upload_filename)
                            logger.debug("Rename successful - file overwritten")
                        except Exception as ren_e:
                            logger.error(f"Rename failed: {ren_e}")
                            # Try to clean up temp file
                            try:
                                self.ftp.delete(temp_filename)
                            except:
                                pass
                            raise Exception(f"Could not overwrite existing file: {ren_e}")
                    except Exception as temp_e:
                        logger.error(f"Temporary file approach also failed: {temp_e}")
                        raise
                else:
                    raise
            
            # Skip verification if requested or if STOR was successful for problematic servers
            if skip_verification and stor_success:
                logger.info("Skipping verification due to skip_verification flag and successful STOR")
                return True
            
            # Verify the upload by checking if file exists
            try:
                logger.info(f"=== VERIFYING UPLOAD ===")
                logger.info(f"Checking file: {upload_filename}")
                logger.info(f"In directory: {self.ftp.pwd()}")
                
                # Add a small delay to ensure file is fully written
                time.sleep(1.0)
                
                # Make sure we're still in the right directory
                expected_dir = os.path.dirname(os.path.join(base_path, remote_path)).replace('\\', '/')
                current_pwd = self.ftp.pwd()
                if current_pwd != expected_dir:
                    logger.warning(f"Directory changed after upload! Expected: {expected_dir}, Current: {current_pwd}")
                    try:
                        self.ftp.cwd(expected_dir)
                        logger.info(f"Changed back to expected directory: {expected_dir}")
                    except:
                        logger.error(f"Could not change to expected directory: {expected_dir}")
                
                try:
                    remote_size = self.ftp.size(self._quote_path_if_needed(upload_filename))
                    local_size = os.path.getsize(local_path)
                    logger.info(f"Remote file size: {remote_size}, Local file size: {local_size}")
                    
                    # If remote_size is None, the FTP server doesn't support SIZE or can't determine size
                    if remote_size is None:
                        logger.warning("FTP server returned None for file size - falling back to LIST verification")
                        raise Exception("SIZE command returned None")
                    
                    if remote_size == local_size:
                        logger.info(f"✅ Upload verification successful!")
                        logger.info(f"File uploaded to: {os.path.join(base_path, remote_path)}")
                        return True
                    else:
                        logger.error(f"❌ Upload verification failed! Size mismatch.")
                        return False
                except Exception as size_error:
                    logger.warning(f"SIZE command failed: {size_error}, trying LIST verification...")
                    
                # Try alternative verification with LIST
                try:
                    # Log current directory for debugging
                    current_dir = self.ftp.pwd()
                    logger.info(f"Current directory for LIST: {current_dir}")
                    
                    # First try listing just the file
                    file_list = []
                    try:
                        self.ftp.retrlines(f'LIST {self._quote_path_if_needed(upload_filename)}', file_list.append)
                        logger.debug(f"Direct file LIST succeeded with {len(file_list)} entries")
                    except Exception as direct_list_error:
                        # If that fails, list the directory and look for the file
                        logger.debug(f"Direct file LIST failed ({direct_list_error}), listing current directory...")
                        try:
                            self.ftp.retrlines('LIST', file_list.append)
                            logger.debug(f"Directory LIST returned {len(file_list)} entries")
                        except Exception as dir_list_error:
                            logger.error(f"Directory LIST also failed: {dir_list_error}")
                            # Try changing to parent and back
                            logger.debug("Trying to refresh directory...")
                            parent_dir = os.path.dirname(current_dir)
                            self.ftp.cwd(parent_dir)
                            self.ftp.cwd(current_dir)
                            self.ftp.retrlines('LIST', file_list.append)
                    
                    # Log all files for debugging
                    logger.debug(f"All files in directory ({len(file_list)} total):")
                    for i, line in enumerate(file_list[:10]):  # Show first 10
                        logger.debug(f"  {i+1}: {line}")
                    
                    # Check if our file appears in the listing
                    file_found = False
                    upload_filename_lower = upload_filename.lower()
                    
                    for line in file_list:
                        # Check both exact match and case-insensitive
                        if upload_filename in line or upload_filename_lower in line.lower():
                            logger.info(f"✅ File found in directory listing: {line}")
                            file_found = True
                            break
                    
                    if file_found:
                        logger.info(f"✅ Upload verification successful via LIST!")
                        logger.info(f"File uploaded to: {os.path.join(self.ftp.pwd(), upload_filename)}")
                        return True
                    else:
                        # Last resort - try checking the full path
                        logger.warning(f"File '{upload_filename}' not found in current directory, checking full path...")
                        full_path = os.path.join(base_path, remote_path).replace('\\', '/')
                        logger.info(f"Checking full path: {full_path}")
                        
                        try:
                            # Try to get size of full path
                            self.ftp.size(self._quote_path_if_needed(full_path))
                            logger.info(f"✅ File verified at full path: {full_path}")
                            return True
                        except:
                            # If STOR was successful, trust it
                            if stor_success:
                                logger.warning("Could not verify file, but STOR was successful - trusting STOR result")
                                return True
                            else:
                                logger.error("Could not verify file and STOR status unknown")
                                return False
                        
                except Exception as list_error:
                    logger.error(f"LIST verification also failed: {list_error}")
                    # If we got a successful STOR response, assume success
                    if stor_success:
                        logger.warning("Both verification methods failed, but STOR was successful - trusting STOR result")
                        return True
                    else:
                        logger.error("All verification methods failed and STOR status unclear")
                        return False
                    
            except Exception as verify_error:
                logger.error(f"Upload verification failed: {verify_error}")
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
            # Check if this is an absolute path
            if path.startswith('/'):
                # For absolute paths, create each directory level from root
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
                            if "550" in str(e) or "exist" in str(e).lower():  # Directory exists
                                logger.debug(f"Directory already exists: {current_path}")
                            else:
                                logger.error(f"Error creating directory {current_path}: {str(e)}")
                                return False
            else:
                # For relative paths, use current directory as base
                base_dir = self.ftp.pwd()
                logger.debug(f"Creating directory '{path}' relative to: {base_dir}")
                
                parts = path.split('/')
                current_path = base_dir.rstrip('/')
                
                for part in parts:
                    if part:  # Skip empty parts
                        current_path += '/' + part
                        try:
                            self.ftp.mkd(current_path)
                            logger.debug(f"Created directory: {current_path}")
                        except ftplib.error_perm as e:
                            # Directory might already exist
                            if "550" in str(e) or "exist" in str(e).lower():  # Directory exists
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
            
            logger.info(f"=== COPY FILE DEBUG ===")
            logger.info(f"Source FTP config: {self.config}")
            logger.info(f"Target FTP config: {target_ftp.config}")
            logger.info(f"Source path: {source_path}")
            logger.info(f"Target path: {target_path}")
            logger.info(f"File info: {file_info}")
            logger.info(f"Keep temp file: {keep_temp}")
            
            # Download to temp file
            temp_path = f"/tmp/{file_info['name']}"
            logger.debug(f"Temp file path: {temp_path}")
            
            logger.info(f"Starting download from source...")
            if self.download_file(source_path, temp_path):
                logger.info(f"Download successful, file size: {os.path.getsize(temp_path)} bytes")
                logger.info(f"Starting upload to target path: {target_path}")
                
                # For very large files (>10GB), skip verification as FTP SIZE command may fail
                file_size = os.path.getsize(temp_path)
                skip_verify = file_size > 10 * 1024 * 1024 * 1024  # 10GB
                if skip_verify:
                    logger.warning(f"Large file ({file_size / (1024**3):.1f}GB) - skipping verification to avoid FTP timeouts")
                
                success = target_ftp.upload_file(temp_path, target_path, skip_verification=skip_verify)
                logger.info(f"Upload result: {success}")
                
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
                # Already an absolute path - use as is
                full_remote_path = remote_path
                logger.info(f"Using absolute path for deletion: {full_remote_path}")
            else:
                # Relative path - combine with base path
                if base_path.endswith('/'):
                    full_remote_path = base_path + remote_path
                else:
                    full_remote_path = base_path + '/' + remote_path
                # Clean up any double slashes
                full_remote_path = full_remote_path.replace('//', '/')
                logger.info(f"Using relative path with base: {full_remote_path}")
            
            logger.info(f"Deleting file from FTP path: {full_remote_path}")
            logger.info(f"Base path: {base_path}, Remote path: {remote_path}")
            
            # Delete the file (quote path if needed)
            quoted_path = self._quote_path_if_needed(full_remote_path)
            logger.info(f"Attempting to delete with quoted path: {quoted_path}")
            
            # Try to delete the file
            delete_success = False
            last_error = None
            
            # First try with the quoted path
            try:
                self.ftp.delete(quoted_path)
                delete_success = True
            except Exception as e:
                last_error = e
                if "550" in str(e):
                    # Try alternative paths if the standard path fails
                    alternative_paths = self._generate_alternative_paths(full_remote_path)
                    
                    for alt_desc, alt_path in alternative_paths[1:]:  # Skip the first one (original)
                        try:
                            logger.info(f"Trying alternative path ({alt_desc}): {alt_path}")
                            # Quote the alternative path if needed
                            alt_quoted = self._quote_path_if_needed(alt_path)
                            self.ftp.delete(alt_quoted)
                            delete_success = True
                            logger.info(f"Success with alternative path: {alt_path}")
                            break
                        except Exception as alt_e:
                            logger.debug(f"Alternative path failed: {alt_e}")
                            continue
                            
            if not delete_success:
                raise last_error
            
            logger.info(f"Successfully deleted file: {full_remote_path}")
            return True
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Delete failed for {remote_path}: {error_msg}")
            
            # Provide more specific error information based on FTP error codes
            if "550" in error_msg:
                # Check if file exists
                try:
                    self.ftp.size(quoted_path)
                    # File exists, so it's likely a permission issue
                    logger.error("Error 550: File exists but cannot be deleted - likely a permission issue")
                    logger.error("Possible causes:")
                    logger.error("  1. User lacks delete permissions on the FTP server")
                    logger.error("  2. File is locked or in use by another process")
                    logger.error("  3. Parent directory is write-protected")
                except:
                    # File doesn't exist or can't check size
                    logger.error("Error 550: File may not exist at the specified path")
                    logger.error(f"Attempted to delete: {full_remote_path}")
                    
                # Try to check current directory permissions
                try:
                    current_dir = os.path.dirname(full_remote_path)
                    logger.info(f"Checking permissions for directory: {current_dir}")
                    # Try to list the directory to verify access
                    self.ftp.cwd(current_dir)
                    logger.info(f"Can access directory: {current_dir}")
                    
                    # List files in directory to see what's actually there
                    file_list = []
                    self.ftp.retrlines('LIST', file_list.append)
                    target_filename = os.path.basename(full_remote_path)
                    logger.info(f"Looking for file: {target_filename}")
                    
                    # Check if file exists with different case or encoding
                    found_similar = []
                    for line in file_list:
                        if target_filename.lower() in line.lower():
                            found_similar.append(line)
                    
                    if found_similar:
                        logger.info(f"Found similar files in directory:")
                        for f in found_similar:
                            logger.info(f"  {f}")
                    else:
                        logger.info(f"No files matching '{target_filename}' found in directory")
                        logger.info(f"First 5 files in directory:")
                        for f in file_list[:5]:
                            logger.info(f"  {f}")
                    
                    # Return to original directory
                    self.ftp.cwd(base_path)
                except Exception as perm_e:
                    logger.error(f"Cannot access parent directory: {perm_e}")
            elif "530" in error_msg:
                logger.error("Error 530: Not logged in or authentication failed")
            elif "553" in error_msg:
                logger.error("Error 553: Requested action not taken - file name not allowed")
            else:
                logger.error(f"FTP Error: {error_msg}")
                
            return False