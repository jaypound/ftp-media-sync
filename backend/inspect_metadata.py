#!/usr/bin/env python3
"""
Inspect the raw content of a Castus metadata file
"""

import tempfile
from ftp_manager import FTPManager
from config_manager import ConfigManager

def inspect_metadata_file():
    """Download and display raw metadata file content"""
    # Setup
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    server_config = all_config['servers']['source']
    
    ftp = FTPManager(server_config)
    
    if not ftp.connect():
        print("Failed to connect to FTP server")
        return
    
    print(f"Connected to {server_config['host']}")
    
    # Test file that we know has metadata
    test_path = "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/.castusmeta.250827_AN_Mayors Cup Golf Tournament_v3.mp4/metadata"
    
    print(f"\nInspecting metadata file: {test_path}")
    print("-" * 80)
    
    # Download to temp file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.metadata')
    import os
    os.close(temp_fd)
    
    try:
        success = ftp.download_file(test_path, temp_path)
        
        if success:
            print("✅ Successfully downloaded metadata file")
            print("\n📄 Raw metadata content:")
            print("=" * 80)
            
            with open(temp_path, 'r') as f:
                content = f.read()
                print(content)
                
            print("=" * 80)
            print(f"\nFile size: {len(content)} bytes")
            print(f"Number of lines: {len(content.splitlines())}")
            
            # Try to identify format
            print("\n🔍 Format detection:")
            if content.strip().startswith('{'):
                print("  - Looks like JSON format")
            elif '=' in content or ':' in content:
                print("  - Looks like key-value pairs")
            elif '<' in content and '>' in content:
                print("  - Looks like XML format")
            else:
                print("  - Unknown format")
                
        else:
            print("❌ Failed to download metadata file")
            
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)
        ftp.disconnect()

if __name__ == "__main__":
    inspect_metadata_file()