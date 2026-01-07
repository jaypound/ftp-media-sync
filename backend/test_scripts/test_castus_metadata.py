#!/usr/bin/env python3
"""
Test script for Castus metadata extraction - dry run
This script tests reading expiration dates from Castus metadata files
without making any database changes.
"""

import sys
import logging
from datetime import datetime
from castus_metadata import CastusMetadataHandler
from ftp_manager import FTPManager
from config_manager import ConfigManager

# Setup logging to see all details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_single_file(file_path: str, server_config: dict):
    """Test metadata extraction for a single file"""
    print(f"\n{'='*80}")
    print(f"Testing file: {file_path}")
    print('='*80)
    
    # Create FTP connection
    ftp = FTPManager(server_config)
    if not ftp.connect():
        print("❌ Failed to connect to FTP server")
        return False
    
    try:
        # Create metadata handler
        handler = CastusMetadataHandler(ftp)
        
        # Try to get content window close date
        print("🔍 Searching for metadata file...")
        expiration_date = handler.get_content_window_close(file_path)
        
        if expiration_date:
            print(f"✅ SUCCESS! Found expiration date: {expiration_date}")
            print(f"   Format: {expiration_date.strftime('%Y-%m-%d %H:%M:%S')}")
            # Handle both timezone-aware and naive datetimes
            if expiration_date.tzinfo is not None:
                now = datetime.now(expiration_date.tzinfo)
            else:
                now = datetime.now()
            print(f"   Days until expiration: {(expiration_date - now).days}")
        else:
            print("❌ No expiration date found in metadata")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during metadata extraction: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        ftp.disconnect()


def test_multiple_files(server_name: str = 'source'):
    """Test metadata extraction on multiple sample files"""
    # Load configuration
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    
    if server_name not in all_config['servers']:
        print(f"❌ Server '{server_name}' not found in configuration")
        return
    
    server_config = all_config['servers'][server_name]
    print(f"\n🚀 Starting Castus Metadata Dry Run")
    print(f"📡 Server: {server_config['host']}")
    print(f"📁 Path: {server_config.get('path', '/')}")
    
    # Test files - you can modify these paths based on your actual files
    test_files = [
        "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250827_AN_Mayors Cup Golf Tournament_v3.mp4",
        "/mnt/md127/ATL26 On-Air Content/MEETINGS/250903_MTG_City Council Meeting.mp4",
        "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250901_AN_Labor Day Special.mp4",
        # Add more test file paths here
    ]
    
    # If no predefined test files, let's scan for some files to test
    if not any(test_files):
        print("\n📂 No test files specified. Scanning for files to test...")
        ftp = FTPManager(server_config)
        if ftp.connect():
            try:
                # List files in a directory
                files = ftp.list_files("/mnt/md127/ATL26 On-Air Content/ATLANTA NOW")
                # Take first 5 MP4 files
                test_files = [f['path'] for f in files if f['name'].endswith('.mp4')][:5]
                print(f"Found {len(test_files)} test files")
            except Exception as e:
                print(f"Error scanning for files: {e}")
            finally:
                ftp.disconnect()
    
    # Test each file
    success_count = 0
    for file_path in test_files:
        if test_single_file(file_path, server_config):
            success_count += 1
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    print(f"Total files tested: {len(test_files)}")
    print(f"Successful extractions: {success_count}")
    print(f"Failed extractions: {len(test_files) - success_count}")


def test_specific_file(file_path: str, server_name: str = 'source'):
    """Test a specific file path"""
    # Load configuration
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    
    if server_name not in all_config['servers']:
        print(f"❌ Server '{server_name}' not found in configuration")
        return
    
    server_config = all_config['servers'][server_name]
    test_single_file(file_path, server_config)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Test specific file from command line
        file_path = sys.argv[1]
        server = sys.argv[2] if len(sys.argv) > 2 else 'source'
        print(f"Testing specific file: {file_path}")
        test_specific_file(file_path, server)
    else:
        # Test multiple files
        test_multiple_files('source')
        
        # Also test target server if you want
        # print("\n\n🔄 Testing TARGET server...")
        # test_multiple_files('target')