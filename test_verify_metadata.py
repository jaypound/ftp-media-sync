#!/usr/bin/env python3
"""
Verify the metadata file was created correctly
"""
import os
import xml.etree.ElementTree as ET
import tempfile
from backend.ftp_manager import FTPManager

# FTP configuration for target server
target_config = {
    "host": "castus2",
    "port": 21,
    "user": "root",
    "password": "Atl#C1a26",
    "path": "/mnt/main/ATL26 On-Air Content"
}

# Create FTP manager
ftp = FTPManager(target_config)

try:
    # Connect to FTP
    print("Connecting to target server...")
    if ftp.connect():
        print("Connected successfully")
        
        # Download the metadata file
        metadata_path = "MEETINGS/250908_MTG_Zoning_Committee.xml"
        temp_file = os.path.join(tempfile.gettempdir(), "test_metadata.xml")
        
        print(f"\nDownloading metadata from: {metadata_path}")
        if ftp.download_file(metadata_path, temp_file):
            print("Metadata downloaded successfully")
            
            # Parse and display the XML
            print("\nMetadata content:")
            print("-" * 60)
            
            with open(temp_file, 'r') as f:
                xml_content = f.read()
                print(xml_content)
            
            print("-" * 60)
            
            # Parse to verify structure
            tree = ET.parse(temp_file)
            root = tree.getroot()
            
            # Find ContentWindowClose element
            content_elem = root.find('.//Content')
            if content_elem is not None:
                window_close_elem = content_elem.find('ContentWindowClose')
                if window_close_elem is not None:
                    print(f"\n✅ Found ContentWindowClose: {window_close_elem.text}")
                else:
                    print("\n❌ ContentWindowClose element not found")
            else:
                print("\n❌ Content element not found")
                
            # Clean up
            os.remove(temp_file)
        else:
            print("Failed to download metadata file")
            
        # Disconnect
        ftp.disconnect()
    else:
        print("Failed to connect to FTP server")
        
except Exception as e:
    print(f"Error: {str(e)}")