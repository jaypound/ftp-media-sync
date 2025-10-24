#!/usr/bin/env python3
"""
Audio Normalizer - Normalize audio to target LKFS using FFmpeg

This module provides functionality to normalize audio files to a target loudness level
(default -24 LKFS for ATSC A/85 compliance) using FFmpeg's loudnorm filter.
"""

import os
import json
import logging
import subprocess
import tempfile
from typing import Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioNormalizer:
    """Normalize audio files to target loudness using FFmpeg"""
    
    def __init__(self, target_lkfs: float = -24.0, target_lra: float = 7.0, target_tp: float = -2.0):
        """
        Initialize the audio normalizer
        
        Args:
            target_lkfs: Target integrated loudness in LKFS (default -24 for ATSC A/85)
            target_lra: Target loudness range in LU (default 7)
            target_tp: Target true peak in dBTP (default -2)
        """
        self.target_lkfs = target_lkfs
        self.target_lra = target_lra
        self.target_tp = target_tp
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg not found. Please install FFmpeg to use audio normalization.")
    
    def analyze_loudness(self, input_file: str) -> Dict[str, float]:
        """
        Analyze the loudness of an audio file (first pass)
        
        Args:
            input_file: Path to the input audio/video file
            
        Returns:
            Dictionary with loudness measurements
        """
        logger.info(f"Analyzing loudness for: {input_file}")
        
        # First pass - analyze current loudness
        cmd = [
            'ffmpeg', '-i', input_file,
            '-af', f'loudnorm=I={self.target_lkfs}:TP={self.target_tp}:LRA={self.target_lra}:print_format=json',
            '-f', 'null', '-'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse the JSON output from stderr
            stderr_lines = result.stderr.split('\n')
            json_start = None
            json_end = None
            
            for i, line in enumerate(stderr_lines):
                if line.strip() == '{':
                    json_start = i
                elif line.strip() == '}' and json_start is not None:
                    json_end = i + 1
                    break
            
            if json_start is not None and json_end is not None:
                json_str = '\n'.join(stderr_lines[json_start:json_end])
                measurements = json.loads(json_str)
                
                logger.info(f"Current loudness - LKFS: {measurements.get('input_i')}, "
                           f"LRA: {measurements.get('input_lra')}, "
                           f"TP: {measurements.get('input_tp')}")
                
                return measurements
            else:
                raise ValueError("Could not find loudness measurements in FFmpeg output")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg analysis failed: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing loudness: {str(e)}")
            raise
    
    def normalize(self, input_file: str, output_file: str = None, 
                  keep_video: bool = True, preview_only: bool = False) -> Tuple[str, Dict[str, any]]:
        """
        Normalize audio to target loudness
        
        Args:
            input_file: Path to the input audio/video file
            output_file: Path for the output file (auto-generated if None)
            keep_video: Whether to keep video stream if present (default True)
            preview_only: If True, only show what would be done without processing
            
        Returns:
            Tuple of (output_file_path, normalization_info)
        """
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")
        
        # Generate output filename if not provided
        if output_file is None:
            output_file = str(input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}")
        
        logger.info(f"Normalizing: {input_file}")
        logger.info(f"Output will be: {output_file}")
        logger.info(f"Target: {self.target_lkfs} LKFS, {self.target_lra} LRA, {self.target_tp} TP")
        
        # First pass - analyze
        measurements = self.analyze_loudness(input_file)
        
        # Calculate normalization parameters
        measured_i = float(measurements.get('input_i', 0))
        measured_tp = float(measurements.get('input_tp', 0))
        measured_lra = float(measurements.get('input_lra', 0))
        measured_thresh = float(measurements.get('input_thresh', 0))
        
        target_offset = float(measurements.get('target_offset', 0))
        
        normalization_info = {
            'input_file': input_file,
            'output_file': output_file,
            'measured': {
                'integrated_lkfs': measured_i,
                'true_peak': measured_tp,
                'loudness_range': measured_lra,
                'threshold': measured_thresh
            },
            'target': {
                'integrated_lkfs': self.target_lkfs,
                'true_peak': self.target_tp,
                'loudness_range': self.target_lra
            },
            'offset': target_offset,
            'will_normalize': abs(measured_i - self.target_lkfs) > 0.5  # Only normalize if > 0.5 dB difference
        }
        
        if preview_only:
            logger.info("Preview mode - no processing will be done")
            return output_file, normalization_info
        
        if not normalization_info['will_normalize']:
            logger.info(f"File is already close to target loudness ({measured_i} LKFS). Skipping normalization.")
            return input_file, normalization_info
        
        # Second pass - normalize
        logger.info("Performing normalization (this may take a while)...")
        
        # Build loudnorm filter with measured values
        loudnorm_filter = (
            f"loudnorm=I={self.target_lkfs}:TP={self.target_tp}:LRA={self.target_lra}:"
            f"measured_I={measured_i}:measured_TP={measured_tp}:"
            f"measured_LRA={measured_lra}:measured_thresh={measured_thresh}:"
            f"offset={target_offset}:linear=true:print_format=summary"
        )
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-i', input_file, '-y']  # -y to overwrite
        
        if keep_video:
            # Copy video stream, normalize audio
            cmd.extend([
                '-c:v', 'copy',  # Copy video codec
                '-c:a', 'aac',   # Use AAC for audio (widely compatible)
                '-b:a', '256k',  # Audio bitrate
                '-af', loudnorm_filter
            ])
        else:
            # Audio only
            cmd.extend([
                '-vn',  # No video
                '-c:a', 'aac',
                '-b:a', '256k',
                '-af', loudnorm_filter
            ])
        
        cmd.append(output_file)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse the summary from stderr
            if 'Output Integrated:' in result.stderr:
                for line in result.stderr.split('\n'):
                    if 'Output Integrated:' in line:
                        output_lkfs = line.split('LUFS')[0].split(':')[-1].strip()
                        normalization_info['output_lkfs'] = float(output_lkfs)
                        logger.info(f"Normalization complete. Output: {output_lkfs} LKFS")
                        break
            
            normalization_info['success'] = True
            return output_file, normalization_info
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg normalization failed: {e.stderr}")
            normalization_info['success'] = False
            normalization_info['error'] = str(e)
            raise
        except Exception as e:
            logger.error(f"Error during normalization: {str(e)}")
            normalization_info['success'] = False
            normalization_info['error'] = str(e)
            raise
    
    def batch_normalize(self, input_files: list, output_dir: str = None,
                       preview_only: bool = False) -> list:
        """
        Normalize multiple files
        
        Args:
            input_files: List of input file paths
            output_dir: Directory for output files (uses input dir if None)
            preview_only: If True, only show what would be done
            
        Returns:
            List of (output_file, normalization_info) tuples
        """
        results = []
        
        for input_file in input_files:
            try:
                input_path = Path(input_file)
                
                if output_dir:
                    output_file = str(Path(output_dir) / f"{input_path.stem}_normalized{input_path.suffix}")
                else:
                    output_file = None
                
                output_path, info = self.normalize(input_file, output_file, preview_only=preview_only)
                results.append((output_path, info))
                
            except Exception as e:
                logger.error(f"Failed to process {input_file}: {str(e)}")
                results.append((None, {
                    'input_file': input_file,
                    'success': False,
                    'error': str(e)
                }))
        
        return results


def main():
    """Command-line interface for audio normalization"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Normalize audio to target LKFS')
    parser.add_argument('input_file', help='Input audio/video file')
    parser.add_argument('-o', '--output', help='Output file (auto-generated if not specified)')
    parser.add_argument('-t', '--target', type=float, default=-24.0,
                       help='Target integrated loudness in LKFS (default: -24)')
    parser.add_argument('-r', '--range', type=float, default=7.0,
                       help='Target loudness range in LU (default: 7)')
    parser.add_argument('-p', '--peak', type=float, default=-2.0,
                       help='Target true peak in dBTP (default: -2)')
    parser.add_argument('--no-video', action='store_true',
                       help='Remove video stream from output')
    parser.add_argument('--preview', action='store_true',
                       help='Preview only - show what would be done without processing')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Create normalizer
        normalizer = AudioNormalizer(
            target_lkfs=args.target,
            target_lra=args.range,
            target_tp=args.peak
        )
        
        # Normalize the file
        output_file, info = normalizer.normalize(
            args.input_file,
            args.output,
            keep_video=not args.no_video,
            preview_only=args.preview
        )
        
        # Print results
        print(f"\nNormalization {'Preview' if args.preview else 'Complete'}:")
        print(f"  Input:  {info['input_file']}")
        print(f"  Output: {info['output_file']}")
        print(f"\nMeasured loudness:")
        print(f"  Integrated: {info['measured']['integrated_lkfs']:.1f} LKFS")
        print(f"  True Peak:  {info['measured']['true_peak']:.1f} dBTP")
        print(f"  Range:      {info['measured']['loudness_range']:.1f} LU")
        print(f"\nTarget loudness:")
        print(f"  Integrated: {info['target']['integrated_lkfs']:.1f} LKFS")
        print(f"  True Peak:  {info['target']['true_peak']:.1f} dBTP")
        print(f"  Range:      {info['target']['loudness_range']:.1f} LU")
        print(f"\nOffset: {info['offset']:.1f} dB")
        
        if not args.preview and info.get('output_lkfs'):
            print(f"\nActual output: {info['output_lkfs']:.1f} LKFS")
        
        if not info['will_normalize']:
            print("\nNo normalization needed - file is already at target loudness")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())