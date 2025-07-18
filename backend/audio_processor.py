import os
import tempfile
import logging
import ffmpeg
from faster_whisper import WhisperModel
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self, model_size="base", device="cpu"):
        self.model_size = model_size
        self.device = device
        self.model = None
        self.temp_dir = tempfile.gettempdir()
        
    def load_model(self):
        """Load the Whisper model"""
        try:
            if not self.model:
                logger.info(f"Loading Whisper model: {self.model_size}")
                self.model = WhisperModel(self.model_size, device=self.device)
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
            
            # Transcribe with Whisper
            logger.info("Starting Whisper transcription...")
            segments, info = self.model.transcribe(audio_path, beam_size=5)
            
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
            
            logger.info(f"Transcription completed. Language: {info.language}, Duration: {info.duration:.2f}s")
            logger.info(f"Transcript length: {len(full_transcript)} characters")
            
            if len(full_transcript) == 0:
                logger.warning("Transcription resulted in empty text")
            
            return {
                "transcript": full_transcript,
                "segments": transcript_segments,
                "language": info.language,
                "duration": info.duration
            }
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {str(e)}")
            return None
    
    def process_video_file(self, video_path, keep_audio=False):
        """Complete processing: extract audio, transcribe, and get duration"""
        try:
            logger.info(f"Processing video file: {video_path}")
            
            # Get video duration
            duration = self.get_duration(video_path)
            
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
                    "audio_path": audio_path if keep_audio else None
                }
            else:
                return None
                
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