#!/usr/bin/env python3
"""
Summary test of Castus metadata extraction
Shows only the important results without debug logging
"""

import sys
import logging
from datetime import datetime
from castus_metadata import CastusMetadataHandler
from ftp_manager import FTPManager
from config_manager import ConfigManager

# Suppress debug logging
logging.getLogger('ftp_manager').setLevel(logging.ERROR)
logging.getLogger('castus_metadata').setLevel(logging.ERROR)
logging.getLogger('config_manager').setLevel(logging.ERROR)


def test_files():
    """Test metadata extraction and show summary"""
    # Load configuration
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    server_config = all_config['servers']['source']
    
    print("🚀 Castus Metadata Extraction Test")
    print(f"📡 Server: {server_config['host']}")
    print("=" * 80)
    
    # Create connection
    ftp = FTPManager(server_config)
    if not ftp.connect():
        print("❌ Failed to connect to FTP server")
        return
    
    handler = CastusMetadataHandler(ftp)
    
    # Test files
    test_files = [
        "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250827_AN_Mayors Cup Golf Tournament_v3.mp4",
        "/mnt/md127/ATL26 On-Air Content/MEETINGS/250903_MTG_City Council Meeting.mp4",
        "/mnt/md127/ATL26 On-Air Content/ATLANTA NOW/250901_AN_Labor Day Special.mp4",
    ]
    
    results = []
    
    for file_path in test_files:
        filename = file_path.split('/')[-1]
        print(f"\n📄 {filename}")
        
        try:
            expiration = handler.get_content_window_close(file_path)
            
            if expiration:
                # Handle timezone
                if expiration.tzinfo:
                    now = datetime.now(expiration.tzinfo)
                else:
                    now = datetime.now()
                    
                days_left = (expiration - now).days
                
                print(f"   ✅ Expiration: {expiration.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   📅 Days until expiration: {days_left}")
                
                if days_left < 0:
                    print("   ⚠️  EXPIRED!")
                elif days_left < 7:
                    print("   ⚠️  Expiring soon!")
                    
                results.append({
                    'file': filename,
                    'expiration': expiration,
                    'days_left': days_left,
                    'status': 'found'
                })
            else:
                print("   ❌ No metadata file found")
                results.append({
                    'file': filename,
                    'expiration': None,
                    'days_left': None,
                    'status': 'not_found'
                })
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            results.append({
                'file': filename,
                'expiration': None,
                'days_left': None,
                'status': 'error'
            })
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    found = len([r for r in results if r['status'] == 'found'])
    not_found = len([r for r in results if r['status'] == 'not_found'])
    errors = len([r for r in results if r['status'] == 'error'])
    
    print(f"Total files tested: {len(test_files)}")
    print(f"✅ Metadata found: {found}")
    print(f"❌ Metadata not found: {not_found}")
    print(f"⚠️  Errors: {errors}")
    
    # Show files with upcoming expirations
    upcoming = [r for r in results if r['status'] == 'found' and r['days_left'] is not None and r['days_left'] < 30]
    if upcoming:
        print(f"\n⏰ Files expiring within 30 days:")
        for r in sorted(upcoming, key=lambda x: x['days_left']):
            print(f"   - {r['file']}: {r['days_left']} days")
    
    ftp.disconnect()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    test_files()