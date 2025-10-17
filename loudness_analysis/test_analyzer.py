#!/usr/bin/env python3
"""
Test script for BS.1770-5 loudness analyzer
Tests on actual media files and demonstrates metadata storage
"""

import json
from loudness_analyzer import LoudnessAnalyzer


def test_on_promo():
    """Test the analyzer on a Castus promo file"""
    analyzer = LoudnessAnalyzer()
    
    # Test files to look for (update paths as needed)
    test_files = [
        '/mnt/main/ATL26 On-Air Content/PROMOS/250903_PMO_Beltine Third Quarterly Meeting.mp4',
        '/mnt/main/ATL26 On-Air Content/BUMPS/240711_BMP_ Freedom Parkway_DAY_ATL26.mp4',
        # Add actual promo file paths here
    ]
    
    # For testing, let's create a mock result
    print("BS.1770-5 Loudness Analysis Test")
    print("================================\n")
    
    # Example metadata structure for media files
    metadata_schema = {
        "file_id": "unique_file_identifier",
        "filename": "promo_example.mp4",
        "file_path": "/path/to/file",
        "file_size_mb": 25.4,
        "duration_seconds": 30.0,
        "analyzed_timestamp": "2024-10-16T12:45:00Z",
        
        # Technical metadata
        "technical": {
            "video_codec": "h264",
            "audio_codec": "aac",
            "resolution": "1920x1080",
            "frame_rate": 29.97,
            "audio_sample_rate": 48000,
            "audio_channels": 2,
            "bit_rate_kbps": 5000
        },
        
        # BS.1770-5 Loudness measurements
        "loudness_bs1770": {
            "integrated_lkfs": -24.2,  # LKFS = LUFS (same measurement, different naming)
            "integrated_threshold_lkfs": -34.2,
            "loudness_range_lu": 7.5,
            "lra_low_lkfs": -29.5,
            "lra_high_lkfs": -22.0,
            "true_peak_dbtp": -1.2,
            "max_short_term_lkfs": -21.5,
            "max_momentary_lkfs": -19.3,
            
            # Compliance checks
            "target_lkfs": -24.0,  # ATSC A/85 target
            "target_offset_lu": -0.2,
            "atsc_a85_compliant": True,  # Within ±2 dB tolerance
            "ebu_r128_compliant": False,  # Would need -23 ±1 dB
            
            # Additional metrics
            "gating_status": "relative_and_absolute",
            "measurement_duration": 30.0
        },
        
        # Content metadata
        "content": {
            "title": "ATL26 Station Promo",
            "description": "30-second promotional spot",
            "content_type": "PROMO",
            "category": "SPOTS",
            "tags": ["promo", "station", "30s"],
            "language": "en",
            "created_date": "2024-10-15",
            "expiration_date": "2024-12-31"
        },
        
        # Broadcast metadata
        "broadcast": {
            "channel": "ATL26",
            "first_air_date": "2024-10-16",
            "last_air_date": None,
            "play_count": 0,
            "scheduled_slots": [],
            "restrictions": {
                "dayparting": False,
                "max_plays_per_day": None,
                "min_separation_minutes": 60
            }
        },
        
        # Quality control
        "qc": {
            "status": "approved",
            "qc_date": "2024-10-16",
            "qc_by": "system_auto",
            "issues": [],
            "warnings": [],
            "auto_corrections": {
                "loudness_correction_db": 0,
                "true_peak_limiting": False
            }
        },
        
        # Processing history
        "processing": {
            "original_filename": "promo_original.mov",
            "transcoded": True,
            "normalized": False,
            "trimmed": False,
            "processing_date": "2024-10-15T18:30:00Z",
            "processing_system": "ftp-media-sync"
        }
    }
    
    print("Proposed Metadata Schema for Media Files:")
    print(json.dumps(metadata_schema, indent=2))
    
    print("\n\nKey Metadata Categories:")
    print("========================")
    print("\n1. File Information:")
    print("   - Unique identifier, path, size, duration")
    print("   - Technical specs (codecs, resolution, bitrates)")
    
    print("\n2. BS.1770-5 Loudness Measurements:")
    print("   - Integrated loudness (LKFS/LUFS)")
    print("   - Loudness range (LU)")
    print("   - True peak (dBTP)")
    print("   - Short-term and momentary maximums")
    print("   - ATSC A/85 compliance (-24 LKFS ±2 dB)")
    print("   - EBU R128 compliance (-23 LUFS ±1 dB)")
    
    print("\n3. Content Metadata:")
    print("   - Title, description, category")
    print("   - Tags for searchability")
    print("   - Creation and expiration dates")
    
    print("\n4. Broadcast Information:")
    print("   - Channel assignment")
    print("   - Play history and scheduling")
    print("   - Rotation restrictions")
    
    print("\n5. Quality Control:")
    print("   - QC status and history")
    print("   - Detected issues and warnings")
    print("   - Auto-correction records")
    
    print("\n6. Processing History:")
    print("   - Source file tracking")
    print("   - Processing operations performed")
    print("   - System and timestamp tracking")
    
    print("\n\nBenefits of This Metadata Structure:")
    print("====================================")
    print("- Ensures ATSC A/85 broadcast compliance for US television")
    print("- Enables automatic loudness-based playlist generation")
    print("- Prevents viewer complaints about loudness variations")
    print("- Tracks content lifecycle and expiration")
    print("- Supports advanced scheduling with restrictions")
    print("- Maintains full audit trail of processing")
    print("- Facilitates content search and categorization")
    print("- Enables quality control automation")


if __name__ == "__main__":
    test_on_promo()