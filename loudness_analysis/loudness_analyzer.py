#!/usr/bin/env python3
"""
BS.1770-5 Loudness Analyzer
Measures loudness and true-peak levels according to ITU-R BS.1770-5 standard
"""

import os
import json
import subprocess
import re
from datetime import datetime
from typing import Dict, Optional, Union
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoudnessAnalyzer:
    """Analyzes audio loudness according to ITU-R BS.1770-5 standard"""
    
    def __init__(self):
        self.ffmpeg_path = 'ffmpeg'
        self._verify_ffmpeg()
    
    def _verify_ffmpeg(self):
        """Verify ffmpeg is available and has ebur128 filter"""
        try:
            result = subprocess.run([self.ffmpeg_path, '-filters'], 
                                  capture_output=True, text=True)
            if 'ebur128' not in result.stdout:
                raise RuntimeError("ffmpeg does not have ebur128 filter support")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Please install ffmpeg with libebur128 support")
    
    def analyze(self, file_path: str, target_lufs: float = -24.0) -> Dict:
        """
        Analyze audio loudness of a media file
        
        Args:
            file_path: Path to the media file
            target_lufs: Target loudness for normalization calculations (default: -24 LKFS for ATSC A/85)
        
        Returns:
            Dictionary containing loudness measurements and metadata
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Analyzing: {file_path}")
        
        # Get file info
        file_info = self._get_file_info(file_path)
        
        # Perform loudness analysis
        loudness_data = self._analyze_loudness(file_path)
        
        # Calculate additional metrics
        loudness_data['target_offset'] = loudness_data['integrated_lufs'] - target_lufs
        # ATSC A/85 allows ±2 dB tolerance
        loudness_data['atsc_compliant'] = abs(loudness_data['target_offset']) <= 2.0
        # EBU R128 allows ±1 dB tolerance (for reference)
        loudness_data['ebu_compliant'] = abs(loudness_data['target_offset'] - 1.0) <= 1.0
        
        # Combine results
        results = {
            'file': os.path.basename(file_path),
            'path': file_path,
            'analyzed_at': datetime.now().isoformat(),
            'file_info': file_info,
            'loudness': loudness_data,
            'target_lufs': target_lufs
        }
        
        return results
    
    def _get_file_info(self, file_path: str) -> Dict:
        """Get basic file information using ffprobe"""
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_format', '-show_streams',
            '-print_format', 'json',
            file_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(result.stdout)
            
            # Extract relevant info
            format_info = probe_data.get('format', {})
            audio_streams = [s for s in probe_data.get('streams', []) 
                           if s.get('codec_type') == 'audio']
            
            return {
                'duration': float(format_info.get('duration', 0)),
                'size_bytes': int(format_info.get('size', 0)),
                'bit_rate': int(format_info.get('bit_rate', 0)),
                'format_name': format_info.get('format_name', ''),
                'audio_codec': audio_streams[0].get('codec_name', '') if audio_streams else '',
                'sample_rate': int(audio_streams[0].get('sample_rate', 0)) if audio_streams else 0,
                'channels': int(audio_streams[0].get('channels', 0)) if audio_streams else 0
            }
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error getting file info: {e}")
            return {}
    
    def _analyze_loudness(self, file_path: str) -> Dict:
        """Perform loudness analysis using ffmpeg ebur128 filter"""
        cmd = [
            self.ffmpeg_path, '-i', file_path,
            '-filter_complex', 'ebur128=peak=true:framelog=quiet',
            '-f', 'null', '-'
        ]
        
        logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stderr
            
            # Log the raw output for debugging
            logger.debug(f"FFmpeg output length: {len(output)} characters")
            if len(output) < 5000:  # Only log if reasonably short
                logger.debug(f"FFmpeg output:\n{output}")
            
            # Parse the output
            loudness_data = self._parse_ebur128_output(output)
            return loudness_data
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error analyzing loudness: {e.stderr}")
            raise
    
    def _parse_ebur128_output(self, output: str) -> Dict:
        """Parse the output from ffmpeg ebur128 filter"""
        data = {
            'integrated_lufs': None,
            'integrated_thresh': None,
            'loudness_range': None,
            'lra_low': None,
            'lra_high': None,
            'true_peak': None,
            'max_momentary': None,
            'max_short_term': None
        }
        
        # Regular expressions for parsing
        patterns = {
            'integrated_lufs': r'I:\s+(-?\d+\.?\d*)\s+LUFS',
            'integrated_thresh': r'Threshold:\s+(-?\d+\.?\d*)\s+LUFS',
            'loudness_range': r'LRA:\s+(\d+\.?\d*)\s+LU',
            'lra_low': r'LRA low:\s+(-?\d+\.?\d*)\s+LUFS',
            'lra_high': r'LRA high:\s+(-?\d+\.?\d*)\s+LUFS',
            'true_peak': r'Peak:\s+(-?\d+\.?\d*)\s+dBFS',
            'max_momentary': r'Max momentary:\s+(-?\d+\.?\d*)\s+LUFS',
            'max_short_term': r'Max short term:\s+(-?\d+\.?\d*)\s+LUFS'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                data[key] = float(match.group(1))
        
        # Check if we got the essential measurements
        if data['integrated_lufs'] is None:
            raise ValueError("Could not parse integrated loudness from output")
        
        return data
    
    def generate_report(self, results: Dict, output_format: str = 'json') -> str:
        """Generate a report from analysis results"""
        if output_format == 'json':
            return json.dumps(results, indent=2)
        elif output_format == 'text':
            return self._format_text_report(results)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
    
    def _format_text_report(self, results: Dict) -> str:
        """Format results as human-readable text"""
        loudness = results['loudness']
        file_info = results['file_info']
        
        # Helper function to format values safely
        def fmt_val(value, decimals=1, suffix=''):
            if value is None:
                return 'N/A'
            return f"{value:.{decimals}f}{suffix}"
        
        report = f"""
BS.1770-5 Loudness Analysis Report
==================================
File: {results['file']}
Date: {results['analyzed_at']}

File Information:
  Duration: {fmt_val(file_info.get('duration'), 1, ' seconds')}
  Format: {file_info.get('format_name', 'Unknown')}
  Audio: {file_info.get('audio_codec', 'Unknown')} {file_info.get('sample_rate', 0)} Hz, {file_info.get('channels', 0)} channels

Loudness Measurements:
  Integrated Loudness: {fmt_val(loudness.get('integrated_lufs'), 1, ' LUFS')}
  Loudness Range: {fmt_val(loudness.get('loudness_range'), 1, ' LU')}
  True Peak: {fmt_val(loudness.get('true_peak'), 1, ' dBTP')}
  Max Short-term: {fmt_val(loudness.get('max_short_term'), 1, ' LUFS')}
  Max Momentary: {fmt_val(loudness.get('max_momentary'), 1, ' LUFS')}

Compliance:
  Target: {fmt_val(results.get('target_lufs'), 1, ' LUFS')}
  Offset: {fmt_val(loudness.get('target_offset'), 1, ' LU') if loudness.get('target_offset') is not None else 'N/A'}
  ATSC A/85: {'✓ COMPLIANT' if loudness.get('atsc_compliant') else '✗ NON-COMPLIANT' if loudness.get('atsc_compliant') is not None else 'N/A'}
  EBU R128: {'✓ COMPLIANT' if loudness.get('ebu_compliant') else '✗ NON-COMPLIANT' if loudness.get('ebu_compliant') is not None else 'N/A'}
"""
        return report


def analyze_loudness(file_path: str, target_lufs: float = -24.0) -> Dict:
    """Convenience function to analyze a single file"""
    analyzer = LoudnessAnalyzer()
    return analyzer.analyze(file_path, target_lufs)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python loudness_analyzer.py <media_file>")
        sys.exit(1)
    
    try:
        results = analyze_loudness(sys.argv[1])
        analyzer = LoudnessAnalyzer()
        print(analyzer.generate_report(results, 'text'))
        
        # Save JSON report
        json_file = os.path.splitext(sys.argv[1])[0] + '_loudness.json'
        with open(json_file, 'w') as f:
            f.write(analyzer.generate_report(results, 'json'))
        print(f"\nJSON report saved to: {json_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)