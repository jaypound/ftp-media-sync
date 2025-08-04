import os
import logging
import tempfile
from datetime import datetime
from typing import Dict, List, Any, Optional
from audio_processor import audio_processor
from ai_analyzer import ai_analyzer
from database import db_manager
import uuid

logger = logging.getLogger(__name__)

class FileAnalyzer:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        self.analysis_in_progress = {}
        
    def is_video_file(self, file_path: str) -> bool:
        """Check if file is a video file"""
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.flv']
        return any(file_path.lower().endswith(ext) for ext in video_extensions)
    
    def parse_filename_metadata(self, filename: str) -> Dict[str, str]:
        """Parse metadata from filename following format: YYMMDD_ABC_Description.ext
        
        Args:
            filename: The filename to parse (e.g., '250705_PSA_Public Service Announcement.mp4')
            
        Returns:
            dict: Contains 'content_type' and 'content_title' or empty strings if parsing fails
        """
        try:
            # Remove file extension
            name_without_ext = os.path.splitext(filename)[0]
            
            # Split by underscore
            parts = name_without_ext.split('_', 2)  # Split into max 3 parts
            
            if len(parts) >= 3:
                # parts[0] = date (YYMMDD)
                # parts[1] = content_type (3 characters)
                # parts[2] = content_title (rest of filename)
                content_type = parts[1].strip()
                content_title = parts[2].strip()
                
                logger.debug(f"Parsed filename '{filename}': content_type='{content_type}', content_title='{content_title}'")
                
                return {
                    'content_type': content_type,
                    'content_title': content_title
                }
            else:
                logger.warning(f"Filename '{filename}' does not follow expected format (YYMMDD_ABC_Title.ext)")
                return {
                    'content_type': '',
                    'content_title': ''
                }
                
        except Exception as e:
            logger.warning(f"Error parsing filename '{filename}': {str(e)}")
            return {
                'content_type': '',
                'content_title': ''
            }
    
    def analyze_file(self, file_info: Dict[str, Any], ftp_manager, ai_config: Dict[str, Any] = None, force_reanalysis: bool = False) -> Dict[str, Any]:
        """Analyze a single file completely"""
        try:
            file_name = file_info.get('name', '')
            file_path = file_info.get('path', file_name)
            file_size = file_info.get('size', 0)
            
            logger.info(f"Starting analysis of file: {file_name}")
            
            # Check if file is a video
            if not self.is_video_file(file_name):
                logger.warning(f"File {file_name} is not a video file, skipping analysis")
                return {
                    "success": False,
                    "error": "File is not a video file",
                    "file_name": file_name
                }
            
            # Check if already analyzed (unless forced reanalysis)
            existing_analysis = db_manager.get_analysis_by_path(file_path)
            if existing_analysis and not force_reanalysis:
                logger.info(f"File {file_name} already analyzed, skipping")
                return {
                    "success": True,
                    "message": "File already analyzed",
                    "file_name": file_name,
                    "analysis": existing_analysis
                }
            elif existing_analysis and force_reanalysis:
                logger.info(f"File {file_name} already analyzed, but forcing reanalysis")
            
            # Mark analysis as in progress
            self.analysis_in_progress[file_path] = True
            
            # Step 1: Download file temporarily
            temp_file_path = self.download_temp_file(file_info, ftp_manager)
            if not temp_file_path:
                return {
                    "success": False,
                    "error": "Failed to download file",
                    "file_name": file_name
                }
            
            try:
                # Step 2: Process audio and get transcription
                audio_result = audio_processor.process_video_file(temp_file_path, keep_audio=False)
                if not audio_result:
                    return {
                        "success": False,
                        "error": "Failed to process audio/transcription",
                        "file_name": file_name
                    }
                
                # Step 3: Analyze transcript with AI
                ai_result = None
                if ai_config and ai_config.get('enabled', False):
                    # Configure AI analyzer
                    provider = ai_config.get('provider', 'openai')
                    ai_analyzer.api_provider = provider
                    
                    # Get the correct API key based on provider
                    if provider == 'openai':
                        ai_analyzer.api_key = ai_config.get('openai_api_key')
                    else:
                        ai_analyzer.api_key = ai_config.get('anthropic_api_key')
                    
                    ai_analyzer.model = ai_config.get('model')
                    ai_analyzer.setup_client()
                    
                    # Analyze transcript
                    max_chunk_size = ai_config.get('max_chunk_size', 4000)
                    ai_result = ai_analyzer.analyze_transcript(
                        audio_result['transcript'], 
                        max_chunk_size=max_chunk_size
                    )
                
                # Step 4: Parse filename metadata
                filename_metadata = self.parse_filename_metadata(file_name)
                
                # Step 5: Calculate duration category and add scheduling metadata
                duration_category = self.get_duration_category(audio_result['duration'])
                
                # Step 6: Compile final analysis
                analysis_data = {
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_size": file_size,
                    "file_duration": audio_result['duration'],
                    "duration_category": duration_category,
                    "encoded_date": audio_result.get('encoded_date'),
                    "content_type": filename_metadata.get('content_type', ''),
                    "content_title": filename_metadata.get('content_title', ''),
                    "transcript": audio_result['transcript'],
                    "language": audio_result.get('language', 'en'),
                    "summary": ai_result.get('summary', '') if ai_result else '',
                    "topics": ai_result.get('topics', []) if ai_result else [],
                    "locations": ai_result.get('locations', []) if ai_result else [],
                    "people": ai_result.get('people', []) if ai_result else [],
                    "events": ai_result.get('events', []) if ai_result else [],
                    "engagement_score": ai_result.get('engagement_score', 0) if ai_result else 0,
                    "engagement_score_reasons": ai_result.get('engagement_score_reasons', '') if ai_result else '',
                    "shelf_life_score": ai_result.get('shelf_life_score', 'medium') if ai_result else 'medium',
                    "shelf_life_reasons": ai_result.get('shelf_life_reasons', '') if ai_result else '',
                    "analysis_completed": True,
                    "ai_analysis_enabled": ai_config.get('enabled', False) if ai_config else False,
                    
                    # Scheduling metadata fields
                    "scheduling": {
                        "available_for_scheduling": True,
                        "content_expiry_date": self.calculate_expiry_date(duration_category, ai_result.get('shelf_life_score', 'medium') if ai_result else 'medium'),
                        "last_scheduled_date": None,
                        "total_airings": 0,
                        "created_for_scheduling": datetime.utcnow(),
                        
                        # Timeslot scheduling tracking
                        "last_scheduled_in_overnight": None,
                        "last_scheduled_in_early_morning": None,
                        "last_scheduled_in_morning": None,
                        "last_scheduled_in_afternoon": None,
                        "last_scheduled_in_prime_time": None,
                        "last_scheduled_in_evening": None,
                        
                        # Replay count tracking per timeslot
                        "replay_count_for_overnight": 0,
                        "replay_count_for_early_morning": 0,
                        "replay_count_for_morning": 0,
                        "replay_count_for_afternoon": 0,
                        "replay_count_for_prime_time": 0,
                        "replay_count_for_evening": 0,
                        
                        # Engagement and priority scoring
                        "priority_score": self.calculate_priority_score(ai_result.get('engagement_score', 0) if ai_result else 0, duration_category),
                        "optimal_timeslots": self.get_optimal_timeslots(filename_metadata.get('content_type', ''), duration_category)
                    }
                }
                
                # Step 6: Save to database
                success = db_manager.upsert_analysis(analysis_data)
                if success:
                    logger.info(f"Successfully analyzed and saved: {file_name}")
                    # Get the saved analysis back from database (this will have ObjectId converted)
                    saved_analysis = db_manager.get_analysis_by_path(file_path)
                    return {
                        "success": True,
                        "message": "File analysis completed successfully",
                        "file_name": file_name,
                        "analysis": saved_analysis
                    }
                else:
                    logger.error(f"Failed to save analysis for: {file_name}")
                    return {
                        "success": False,
                        "error": "Failed to save analysis to database",
                        "file_name": file_name
                    }
                    
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        logger.info(f"Cleaned up temporary file: {temp_file_path}")
                    except Exception as e:
                        logger.warning(f"Could not clean up temporary file: {str(e)}")
                
                # Remove from in-progress tracking
                if file_path in self.analysis_in_progress:
                    del self.analysis_in_progress[file_path]
                    
        except Exception as e:
            logger.error(f"Error analyzing file {file_name}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "file_name": file_name
            }
    
    def download_temp_file(self, file_info: Dict[str, Any], ftp_manager) -> Optional[str]:
        """Download file to temporary location"""
        try:
            file_name = file_info.get('name', '')
            file_path = file_info.get('path', file_name)
            folder = file_info.get('folder', 'on-air')  # Get folder type
            
            # Create temporary file path with safe filename
            # Keep original extension but create shorter base name to avoid path length issues
            file_ext = os.path.splitext(file_name)[1]
            safe_base_name = f"analysis_{uuid.uuid4().hex[:8]}"  # Shorter UUID
            temp_file_path = os.path.join(self.temp_dir, f"{safe_base_name}{file_ext}")
            
            # If filename is still too long, truncate further
            if len(temp_file_path) > 240:  # Leave room for system limits
                safe_base_name = f"analysis_{uuid.uuid4().hex[:6]}"
                temp_file_path = os.path.join(self.temp_dir, f"{safe_base_name}{file_ext}")
            
            logger.info(f"Downloading {file_name} from path: {file_path}")
            logger.info(f"Temporary file location: {temp_file_path}")
            logger.info(f"Temp file path length: {len(temp_file_path)} characters")
            
            # Ensure temp directory exists
            os.makedirs(self.temp_dir, exist_ok=True)
            
            # Log additional debugging info for troublesome files
            logger.info(f"File path characters: {[ord(c) for c in file_path if ord(c) > 127]}")
            logger.info(f"File name length: {len(file_name)} characters")
            
            # Check if we need a different FTP connection for Recordings folder
            actual_ftp_manager = ftp_manager
            if folder == 'recordings':
                logger.info(f"File is from Recordings folder, creating specialized FTP connection")
                # Create a new FTP manager with Recordings path
                from ftp_manager import FTPManager
                from config_manager import ConfigManager
                
                config_mgr = ConfigManager()
                server_config = config_mgr.get_all_config()['servers']['source'].copy()
                server_config['path'] = '/mnt/main/Recordings'
                
                recordings_ftp = FTPManager(server_config)
                if recordings_ftp.connect():
                    actual_ftp_manager = recordings_ftp
                    logger.info("Connected to FTP with Recordings path")
                else:
                    logger.error("Failed to connect to FTP with Recordings path")
                    return None
            
            # Download file using FTP manager with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                logger.info(f"Download attempt {attempt + 1}/{max_retries} for {file_name}")
                success = actual_ftp_manager.download_file(file_path, temp_file_path)
                
                if success and os.path.exists(temp_file_path):
                    file_size = os.path.getsize(temp_file_path)
                    if file_size > 0:
                        logger.info(f"Successfully downloaded {file_name} ({file_size} bytes)")
                        # Clean up recordings FTP connection if we created one
                        if folder == 'recordings' and actual_ftp_manager != ftp_manager:
                            try:
                                actual_ftp_manager.disconnect()
                                logger.info("Disconnected Recordings FTP connection")
                            except:
                                pass
                        return temp_file_path
                    else:
                        logger.warning(f"Downloaded file is empty: {file_name}")
                        # Remove empty file and try again
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                
                if attempt < max_retries - 1:
                    logger.warning(f"Download attempt {attempt + 1} failed, retrying...")
                    import time
                    time.sleep(2)  # Wait 2 seconds before retry
                else:
                    logger.error(f"Failed to download {file_name} after {max_retries} attempts")
                    logger.error(f"FTP success: {success}, File exists: {os.path.exists(temp_file_path)}")
            
            # Clean up recordings FTP connection if we created one
            if folder == 'recordings' and actual_ftp_manager != ftp_manager:
                try:
                    actual_ftp_manager.disconnect()
                    logger.info("Disconnected Recordings FTP connection")
                except:
                    pass
            
            return None
                
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            # Clean up recordings FTP connection if we created one
            if 'folder' in locals() and folder == 'recordings' and 'actual_ftp_manager' in locals() and actual_ftp_manager != ftp_manager:
                try:
                    actual_ftp_manager.disconnect()
                    logger.info("Disconnected Recordings FTP connection after error")
                except:
                    pass
            return None
    
    def analyze_batch(self, file_list: List[Dict[str, Any]], ftp_manager, ai_config: Dict[str, Any] = None, force_reanalysis: bool = False) -> List[Dict[str, Any]]:
        """Analyze multiple files in batch"""
        results = []
        
        logger.info(f"Starting batch analysis of {len(file_list)} files")
        
        for i, file_info in enumerate(file_list):
            logger.info(f"Processing file {i+1}/{len(file_list)}: {file_info.get('name', 'unknown')}")
            
            result = self.analyze_file(file_info, ftp_manager, ai_config, force_reanalysis)
            results.append(result)
            
            # Log progress
            if result.get('success'):
                logger.info(f"✅ Successfully analyzed: {result.get('file_name', 'unknown')}")
            else:
                logger.error(f"❌ Failed to analyze: {result.get('file_name', 'unknown')} - {result.get('error', 'unknown error')}")
        
        logger.info(f"Batch analysis completed. {sum(1 for r in results if r.get('success'))} successful, {sum(1 for r in results if not r.get('success'))} failed")
        return results
    
    def get_analysis_status(self, file_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get analysis status for a list of files"""
        try:
            analyzed_files = db_manager.check_analysis_status(file_list)
            
            # Create lookup map
            analyzed_map = {af['file_path']: af for af in analyzed_files}
            
            status_list = []
            for file_info in file_list:
                file_path = file_info.get('path', file_info.get('name', ''))
                is_analyzed = file_path in analyzed_map
                is_in_progress = file_path in self.analysis_in_progress
                
                status_list.append({
                    "file_name": file_info.get('name', ''),
                    "file_path": file_path,
                    "is_analyzed": is_analyzed,
                    "is_in_progress": is_in_progress,
                    "analysis_data": analyzed_map.get(file_path) if is_analyzed else None
                })
            
            return {
                "success": True,
                "files": status_list,
                "analyzed_count": len(analyzed_files),
                "total_count": len(file_list)
            }
            
        except Exception as e:
            logger.error(f"Error getting analysis status: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_duration_category(self, duration_seconds: float) -> str:
        """Determine duration category based on seconds"""
        if duration_seconds < 16:
            return 'id'
        elif duration_seconds < 120:
            return 'spots'
        elif duration_seconds < 1200:
            return 'short_form'
        else:
            return 'long_form'
    
    def calculate_expiry_date(self, duration_category: str, shelf_life_score: str) -> datetime:
        """Calculate content expiry date based on category and AI shelf life score"""
        from datetime import timedelta
        
        # Base expiration periods (in days)
        base_expiry = {
            'id': 30,
            'spots': 60,
            'short_form': 90,
            'long_form': 180
        }
        
        # Shelf life multipliers
        shelf_life_multipliers = {
            'short': 0.5,    # Content becomes stale quickly
            'medium': 1.0,   # Normal expiration
            'long': 2.0      # Evergreen content
        }
        
        base_days = base_expiry.get(duration_category, 90)
        multiplier = shelf_life_multipliers.get(shelf_life_score, 1.0)
        
        expiry_days = int(base_days * multiplier)
        return datetime.utcnow() + timedelta(days=expiry_days)
    
    def calculate_priority_score(self, engagement_score: float, duration_category: str) -> float:
        """Calculate priority score for scheduling (0-100)"""
        # Base score from engagement (0-10 -> 0-70)
        base_score = min(engagement_score * 7, 70)
        
        # Category bonuses
        category_bonus = {
            'id': 20,        # IDs are important for branding
            'spots': 15,     # PSAs and commercials are valuable
            'short_form': 10, # Good content fill
            'long_form': 5   # Harder to schedule
        }
        
        bonus = category_bonus.get(duration_category, 0)
        return min(base_score + bonus, 100)
    
    def get_optimal_timeslots(self, content_type: str, duration_category: str) -> List[str]:
        """Determine optimal timeslots for content based on type and duration"""
        
        # Content type preferences
        type_preferences = {
            'AN': ['morning', 'afternoon', 'prime_time', 'evening'],  # Atlanta Now - news/current events
            'BMP': ['overnight', 'early_morning', 'morning', 'afternoon', 'prime_time', 'evening'],  # Bumps can go anywhere
            'IMOW': ['prime_time', 'evening', 'afternoon'],  # In My Own Words - personal stories
            'IM': ['morning', 'afternoon', 'early_morning'],  # Inclusion Months - educational
            'IA': ['morning', 'afternoon', 'prime_time', 'evening'],  # Inside Atlanta - local news
            'LM': ['morning', 'early_morning', 'evening'],  # Legislative Minute - government content
            'MTG': ['morning', 'afternoon'],  # Meetings - government content
            'MAF': ['morning', 'afternoon', 'prime_time'],  # Moving Atlanta Forward - city initiatives
            'PKG': ['prime_time', 'evening', 'afternoon'],  # Packages - general content
            'PMO': ['prime_time', 'evening', 'afternoon'],  # Promos - promotional content
            'SZL': ['prime_time', 'evening', 'afternoon'],  # Sizzle - promotional content
            'SPP': ['prime_time', 'evening', 'afternoon'],  # Special Projects
            'OTH': ['afternoon', 'evening']  # Other - default placement
        }
        
        # Duration preferences
        duration_preferences = {
            'id': ['overnight', 'early_morning', 'morning', 'afternoon', 'prime_time', 'evening'],
            'spots': ['morning', 'afternoon', 'prime_time', 'evening'],
            'short_form': ['morning', 'afternoon', 'evening'],
            'long_form': ['prime_time', 'evening', 'overnight']
        }
        
        # Get preferences for content type and duration
        type_slots = type_preferences.get(content_type, ['afternoon', 'evening'])
        duration_slots = duration_preferences.get(duration_category, ['afternoon', 'evening'])
        
        # Find intersection, maintaining order of type preferences
        optimal_slots = []
        for slot in type_slots:
            if slot in duration_slots and slot not in optimal_slots:
                optimal_slots.append(slot)
        
        # Add remaining duration slots if we don't have enough
        for slot in duration_slots:
            if slot not in optimal_slots:
                optimal_slots.append(slot)
        
        return optimal_slots[:3]  # Return top 3 optimal slots

# Global file analyzer instance
file_analyzer = FileAnalyzer()