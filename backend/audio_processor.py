import os
import tempfile
import logging
import ffmpeg
from faster_whisper import WhisperModel
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Create dedicated logger for transcription
transcription_logger = logging.getLogger('ai_transcription')

# Set up file handler for transcription logs if not already setup
if not transcription_logger.handlers:
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    trans_handler = logging.FileHandler(os.path.join(logs_dir, f'ai_transcription_{datetime.now().strftime("%Y%m%d")}.log'))
    trans_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    transcription_logger.addHandler(trans_handler)
    transcription_logger.setLevel(logging.INFO)

def validate_language(detected_language):
    """
    Validate detected language and ensure it's only English or Spanish.
    Default to English for any invalid or unsupported languages.
    """
    # Supported languages mapping
    valid_languages = {
        'en': 'en',
        'english': 'en', 
        'es': 'es',
        'spanish': 'es',
        'spa': 'es'
    }
    
    # Common invalid/unsupported language codes that should default to English
    invalid_languages = {
        'nn',  # Norwegian Nynorsk (often misdetected)
        'no',  # Norwegian 
        'nb',  # Norwegian Bokmål
        'und', # Undetermined
        'unknown',
        'auto',
        'detect'
    }
    
    if not detected_language:
        logger.warning("No language detected, defaulting to English")
        return 'en'
    
    # Convert to lowercase for comparison
    lang_lower = detected_language.lower().strip()
    
    # Check for known invalid languages that should default to English
    if lang_lower in invalid_languages:
        logger.warning(f"Invalid/unsupported language '{detected_language}' detected, defaulting to English")
        return 'en'
    
    # Check if it's a valid supported language
    if lang_lower in valid_languages:
        validated_lang = valid_languages[lang_lower]
        logger.info(f"Language '{detected_language}' validated as '{validated_lang}'")
        return validated_lang
    
    # Check for partial matches or common variations
    if lang_lower.startswith('en'):
        logger.info(f"Language '{detected_language}' starts with 'en', treating as English")
        return 'en'
    elif lang_lower.startswith('es') or lang_lower.startswith('spa'):
        logger.info(f"Language '{detected_language}' starts with 'es'/'spa', treating as Spanish")
        return 'es'
    
    # Default to English for any unrecognized language
    logger.warning(f"Unrecognized language '{detected_language}', defaulting to English")
    return 'en'

class AudioProcessor:
    def __init__(self, model_size="base", device="cpu", compute_type="int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type  # Add compute_type attribute
        self.model = None
        self.temp_dir = tempfile.gettempdir()
        
    def load_model(self):
        """Load the Whisper model"""
        try:
            if not self.model:
                logger.info(f"Loading Whisper model: {self.model_size}, device: {self.device}, compute_type: {self.compute_type}")
                self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
                logger.info("Whisper model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error loading Whisper model: {str(e)}")
            return False
    
    def extract_audio(self, video_path, audio_path=None):
        """Extract audio from MP4 file to WAV"""
        try:
            if not audio_path:
                # Create temporary WAV file
                base_name = os.path.splitext(os.path.basename(video_path))[0]
                audio_path = os.path.join(self.temp_dir, f"{base_name}.wav")
            
            logger.info(f"Extracting audio from {video_path} to {audio_path}")
            
            # Check if input file exists
            if not os.path.exists(video_path):
                logger.error(f"Input video file does not exist: {video_path}")
                return None
            
            # Check file size
            file_size = os.path.getsize(video_path)
            logger.info(f"Input video file size: {file_size} bytes")
            
            if file_size == 0:
                logger.error(f"Input video file is empty: {video_path}")
                return None
            
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(audio_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            # Use ffmpeg to extract audio
            (
                ffmpeg
                .input(video_path)
                .output(audio_path, acodec='pcm_s16le', ac=1, ar='16000')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            # Verify the output file was created
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                logger.info(f"Audio extracted successfully to {audio_path} ({os.path.getsize(audio_path)} bytes)")
                return audio_path
            else:
                logger.error(f"Audio extraction failed - output file not created or empty: {audio_path}")
                return None
                
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error: {e.stderr.decode()}")
            return None
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            return None
    
    def get_duration(self, file_path):
        """Get file duration in seconds"""
        try:
            probe = ffmpeg.probe(file_path)
            duration = float(probe['format']['duration'])
            return round(duration, 3)  # Round to 1/1000 second
        except Exception as e:
            logger.error(f"Error getting duration: {str(e)}")
            return 0.0
    
    def get_media_metadata(self, file_path):
        """Get media metadata including encoded date"""
        try:
            probe = ffmpeg.probe(file_path)
            metadata = probe.get('format', {}).get('tags', {})
            
            # Look for creation date/encoded date in various fields
            encoded_date = None
            date_fields = ['creation_time', 'date', 'encoded_date', 'DATE', 'CREATION_TIME']
            
            for field in date_fields:
                if field in metadata:
                    encoded_date = metadata[field]
                    break
            
            # Try to parse the date if found
            if encoded_date:
                try:
                    # Handle ISO format dates (e.g., '2025-07-05T10:30:00.000000Z')
                    if 'T' in encoded_date:
                        parsed_date = datetime.fromisoformat(encoded_date.replace('Z', '+00:00'))
                        encoded_date = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                except Exception as e:
                    logger.warning(f"Could not parse encoded date '{encoded_date}': {str(e)}")
                    # Keep the original value if parsing fails
            
            return {
                'encoded_date': encoded_date,
                'all_metadata': metadata
            }
        except Exception as e:
            logger.error(f"Error getting media metadata: {str(e)}")
            return {
                'encoded_date': None,
                'all_metadata': {}
            }
    
    def transcribe_audio(self, audio_path):
        """Transcribe audio to text using Whisper"""
        try:
            if not self.model:
                logger.info("Whisper model not loaded, attempting to load...")
                if not self.load_model():
                    logger.error("Failed to load Whisper model")
                    return None
            
            logger.info(f"Transcribing audio: {audio_path}")
            
            # Check if audio file exists
            if not os.path.exists(audio_path):
                logger.error(f"Audio file does not exist: {audio_path}")
                return None
            
            # Check audio file size
            audio_size = os.path.getsize(audio_path)
            logger.info(f"Audio file size: {audio_size} bytes")
            
            if audio_size == 0:
                logger.error(f"Audio file is empty: {audio_path}")
                return None
            
            # Extract filename for logging
            file_name = os.path.basename(audio_path)
            file_dir = os.path.dirname(audio_path)
            
            # Log transcription request details
            transcription_logger.info(f"{'='*80}")
            transcription_logger.info(f"WHISPER TRANSCRIPTION REQUEST - {datetime.now().isoformat()}")
            transcription_logger.info(f"File Name: {file_name}")
            transcription_logger.info(f"Full Path: {audio_path}")
            transcription_logger.info(f"Directory: {file_dir}")
            transcription_logger.info(f"File Size: {audio_size:,} bytes ({audio_size/1024/1024:.2f} MB)")
            transcription_logger.info(f"Whisper Model: {self.model_size}")
            transcription_logger.info(f"Device: {self.device}")
            transcription_logger.info(f"Compute Type: {self.compute_type}")
            transcription_logger.info(f"Beam Size: 5")
            
            start_time = datetime.now()
            
            # Transcribe with Whisper
            logger.info("Starting Whisper transcription...")
            segments, info = self.model.transcribe(audio_path, beam_size=5)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # Collect all segments
            transcript_segments = []
            for segment in segments:
                transcript_segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip()
                })
            
            # Create full transcript
            full_transcript = " ".join([seg["text"] for seg in transcript_segments])
            
            # Validate and clean the detected language
            validated_language = validate_language(info.language)
            
            logger.info(f"Transcription completed. Detected language: {info.language}, Validated language: {validated_language}, Duration: {info.duration:.2f}s")
            logger.info(f"Transcript length: {len(full_transcript)} characters")
            
            # Log transcription response details
            transcription_logger.info(f"WHISPER TRANSCRIPTION RESPONSE - {end_time.isoformat()}")
            transcription_logger.info(f"File Name: {file_name}")
            transcription_logger.info(f"Processing Duration: {duration:.2f} seconds")
            transcription_logger.info(f"Audio Duration: {info.duration:.2f} seconds")
            transcription_logger.info(f"Processing Speed: {info.duration/duration:.2f}x realtime")
            transcription_logger.info(f"Detected Language: {info.language}")
            transcription_logger.info(f"Validated Language: {validated_language}")
            transcription_logger.info(f"Number of Segments: {len(transcript_segments)}")
            transcription_logger.info(f"Transcript Length: {len(full_transcript)} characters")
            transcription_logger.info(f"First 500 chars: {full_transcript[:500]}..." if len(full_transcript) > 500 else f"Full transcript: {full_transcript}")
            transcription_logger.info(f"{'='*80}\n")
            
            if len(full_transcript) == 0:
                logger.warning("Transcription resulted in empty text")
                transcription_logger.warning(f"EMPTY TRANSCRIPT for file: {file_name}")
            
            return {
                "transcript": full_transcript,
                "segments": transcript_segments,
                "language": validated_language,
                "duration": info.duration
            }
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {str(e)}")
            # Log transcription error
            if 'file_name' in locals():
                transcription_logger.error(f"{'='*80}")
                transcription_logger.error(f"WHISPER TRANSCRIPTION ERROR - {datetime.now().isoformat()}")
                transcription_logger.error(f"File Name: {file_name}")
                transcription_logger.error(f"Full Path: {audio_path}")
                transcription_logger.error(f"Error: {str(e)}")
                transcription_logger.error(f"Error Type: {type(e).__name__}")
                transcription_logger.error(f"{'='*80}\n")
            return None
    
    def process_video_file(self, video_path, keep_audio=False):
        """Complete processing: extract audio, transcribe, get duration and metadata"""
        try:
            logger.info(f"Processing video file: {video_path}")
            
            # Get video duration and metadata
            duration = self.get_duration(video_path)
            metadata_result = self.get_media_metadata(video_path)
            
            # Extract audio
            audio_path = self.extract_audio(video_path)
            if not audio_path:
                return None
            
            # Transcribe audio
            transcription_result = self.transcribe_audio(audio_path)
            
            # Clean up temporary audio file unless keeping it
            if not keep_audio and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.info(f"Cleaned up temporary audio file: {audio_path}")
                except Exception as e:
                    logger.warning(f"Could not clean up audio file: {str(e)}")
            
            if transcription_result:
                return {
                    "duration": duration,
                    "transcript": transcription_result["transcript"],
                    "segments": transcription_result["segments"],
                    "language": transcription_result["language"],
                    "encoded_date": metadata_result.get('encoded_date'),
                    "metadata": metadata_result.get('all_metadata', {}),
                    "audio_path": audio_path if keep_audio else None
                }
            else:
                # Return basic metadata with default language if transcription fails
                logger.warning("Transcription failed, returning basic metadata with default language")
                return {
                    "duration": duration,
                    "transcript": "",
                    "segments": [],
                    "language": "en",  # Default to English
                    "encoded_date": metadata_result.get('encoded_date'),
                    "metadata": metadata_result.get('all_metadata', {}),
                    "audio_path": None
                }
                
        except Exception as e:
            logger.error(f"Error processing video file: {str(e)}")
            return None
    
    def save_transcript(self, transcript, file_path):
        """Save transcript to text file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            logger.info(f"Transcript saved to: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving transcript: {str(e)}")
            return False

# Global audio processor instance
audio_processor = AudioProcessor()