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
                                # Modification time available
                                mod_time = datetime.strptime(facts['modify'], "%Y%m%d%H%M%S")
                                file_info['mtime'] = mod_time.timestamp()
                                file_info['modified'] = mod_time.isoformat()
                                # Use as creation time too
                                file_info['ctime'] = file_info['mtime']
                                file_info['created'] = file_info['modified']
                            else:
                                # No timestamp available
                                file_info['mtime'] = time.time()
                                file_info['modified'] = datetime.now().isoformat()
                                file_info['ctime'] = file_info['mtime']
                                file_info['created'] = file_info['modified']
                            
                            files.append(file_info)
                    
                    logger.info(f"MLSD processed {mlsd_count} entries, found {len(files)} files")
                except Exception as e:
                    logger.error(f"Error during MLSD listing: {str(e)}")
                    use_mlsd = False  # Fall back to LIST
                    files = []  # Clear any partial results
            
            # Use LIST command if MLSD failed or is not supported
            if not use_mlsd:
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
                        
            logger.debug(f"Found {len(files)} files in {path}")
            if files:
                logger.debug(f"Sample files: {[f['name'] for f in files[:3]]}")
            
            return files
            
        except Exception as e:
            logger.error(f"Error listing files in {path}: {str(e)}")
            return []