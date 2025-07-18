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
    
    def analyze_file(self, file_info: Dict[str, Any], ftp_manager, ai_config: Dict[str, Any] = None) -> Dict[str, Any]:
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
            
            # Check if already analyzed
            existing_analysis = db_manager.get_analysis_by_path(file_path)
            if existing_analysis:
                logger.info(f"File {file_name} already analyzed, skipping")
                return {
                    "success": True,
                    "message": "File already analyzed",
                    "file_name": file_name,
                    "analysis": existing_analysis
                }
            
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
                
                # Step 4: Compile final analysis
                analysis_data = {
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_size": file_size,
                    "file_duration": audio_result['duration'],
                    "transcript": audio_result['transcript'],
                    "language": audio_result.get('language', 'unknown'),
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
                    "ai_analysis_enabled": ai_config.get('enabled', False) if ai_config else False
                }
                
                # Step 5: Save to database
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
            
            # Create temporary file path
            temp_file_path = os.path.join(self.temp_dir, f"analysis_{uuid.uuid4().hex}_{file_name}")
            
            logger.info(f"Downloading {file_name} from path: {file_path}")
            logger.info(f"Temporary file location: {temp_file_path}")
            
            # Download file using FTP manager
            success = ftp_manager.download_file(file_path, temp_file_path)
            
            if success and os.path.exists(temp_file_path):
                logger.info(f"Successfully downloaded {file_name}")
                return temp_file_path
            else:
                logger.error(f"Failed to download {file_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            return None
    
    def analyze_batch(self, file_list: List[Dict[str, Any]], ftp_manager, ai_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Analyze multiple files in batch"""
        results = []
        
        logger.info(f"Starting batch analysis of {len(file_list)} files")
        
        for i, file_info in enumerate(file_list):
            logger.info(f"Processing file {i+1}/{len(file_list)}: {file_info.get('name', 'unknown')}")
            
            result = self.analyze_file(file_info, ftp_manager, ai_config)
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

# Global file analyzer instance
file_analyzer = FileAnalyzer()