#!/usr/bin/env python3
"""
Test loudness analysis with FTP download from Castus servers
Downloads a promo file and analyzes its loudness
"""

import os
import sys
import tempfile
import ftplib
from pathlib import Path

# Add parent directory to path to import from backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ftp_manager import FTPManager
from loudness_analyzer import LoudnessAnalyzer


def test_loudness_with_ftp():
    """Download a promo from FTP and analyze its loudness"""
    
    # FTP configuration for Castus1 (source server)
    ftp_config = {
        'host': 'castus1',
        'port': 21,
        'user': 'root',
        'password': 'Atl#C1a26'
    }
    
    # Test files to try
    test_files = [
        # '/mnt/main/ATL26 On-Air Content/PROMOS/250903_PMO_Beltine Third Quarterly Meeting.mp4',
        '/mnt/main/ATL26 On-Air Content/BUMPS/240711_BMP_ Freedom Parkway_DAY_ATL26.mp4',
    ]
    
    # Create temporary directory for downloads
    with tempfile.TemporaryDirectory() as temp_dir:
        print("BS.1770-5 Loudness Analysis with FTP Download")
        print("=" * 50)
        print(f"\nTemporary directory: {temp_dir}")
        
        # Initialize FTP manager with config dictionary
        ftp_manager = FTPManager(ftp_config)
        
        try:
            # Connect to FTP server
            print(f"\nConnecting to {ftp_config['host']}...")
            ftp_manager.connect()
            print("✓ Connected successfully")
            
            # Find first existing file
            remote_file = None
            for test_file in test_files:
                try:
                    # Check if file exists by listing parent directory
                    parent_dir = os.path.dirname(test_file)
                    files = ftp_manager.list_files(parent_dir)
                    file_name = os.path.basename(test_file)
                    
                    if any(f['name'] == file_name for f in files):
                        remote_file = test_file
                        print(f"\n✓ Found file: {remote_file}")
                        break
                except Exception as e:
                    continue
            
            if not remote_file:
                # List available files in PROMOS directory
                print("\nNo test files found. Listing PROMOS directory:")
                try:
                    promo_files = ftp_manager.list_files('/mnt/main/ATL26 On-Air Content/PROMOS')
                    mp4_files = [f for f in promo_files if f['name'].endswith('.mp4')]
                    
                    if mp4_files:
                        print(f"\nFound {len(mp4_files)} MP4 files in PROMOS:")
                        for i, f in enumerate(mp4_files[:5]):  # Show first 5
                            print(f"  {i+1}. {f['name']} ({f['size'] / 1024 / 1024:.1f} MB)")
                        
                        # Use the first file
                        remote_file = f"/mnt/main/ATL26 On-Air Content/PROMOS/{mp4_files[0]['name']}"
                        print(f"\n✓ Using: {mp4_files[0]['name']}")
                except Exception as e:
                    print(f"Error listing PROMOS directory: {e}")
                    return
            
            if not remote_file:
                print("\n✗ No media files found to analyze")
                return
            
            # Download file
            local_file = os.path.join(temp_dir, os.path.basename(remote_file))
            print(f"\nDownloading to: {local_file}")
            
            file_size = None
            for f in files:
                if f['name'] == os.path.basename(remote_file):
                    file_size = f['size']
                    break
            
            if file_size:
                print(f"File size: {file_size / 1024 / 1024:.1f} MB")
            
            # Download with progress
            print("Downloading...", end='', flush=True)
            ftp_manager.download_file(remote_file, local_file)
            print(" ✓ Complete")
            
            # Verify download
            if not os.path.exists(local_file):
                print("✗ Download failed - file not found")
                return
            
            local_size = os.path.getsize(local_file)
            print(f"Downloaded size: {local_size / 1024 / 1024:.1f} MB")
            
            # Analyze loudness
            print("\n" + "=" * 50)
            print("Analyzing Loudness...")
            print("=" * 50)
            
            analyzer = LoudnessAnalyzer()
            results = analyzer.analyze(local_file, target_lufs=-24.0)  # ATSC A/85 target
            
            # Print report
            print(analyzer.generate_report(results, 'text'))
            
            # Save JSON report
            json_file = os.path.join(temp_dir, os.path.basename(remote_file).replace('.mp4', '_loudness.json'))
            with open(json_file, 'w') as f:
                f.write(analyzer.generate_report(results, 'json'))
            print(f"\nJSON report saved to: {json_file}")
            
            # Show integration example
            print("\n" + "=" * 50)
            print("Metadata for Database Storage:")
            print("=" * 50)
            
            loudness = results['loudness']
            print(f"""
Key values to store in metadata table:
- loudness_integrated_lkfs: {loudness['integrated_lufs']:.1f}
- loudness_range_lu: {loudness['loudness_range']:.1f}
- loudness_true_peak_dbtp: {loudness['true_peak']:.1f}
- loudness_atsc_a85_compliant: {loudness['atsc_compliant']}
- loudness_target_offset: {loudness['target_offset']:.1f}

This content is {'✓ COMPLIANT' if loudness['atsc_compliant'] else '✗ NON-COMPLIANT'} with ATSC A/85 standards.
""")
            
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            # Disconnect from FTP
            try:
                ftp_manager.disconnect()
                print("\n✓ Disconnected from FTP server")
            except:
                pass


if __name__ == "__main__":
    test_loudness_with_ftp()