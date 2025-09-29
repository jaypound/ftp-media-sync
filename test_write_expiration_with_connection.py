#!/usr/bin/env python3
"""
Test script to write expiration date from PostgreSQL to Castus metadata on target server
This version ensures FTP connection is established first
"""
import requests
import json
import time

# API endpoints
TEST_CONNECTION_URL = "http://127.0.0.1:5000/api/test-connection"
COPY_EXPIRATION_URL = "http://127.0.0.1:5000/api/test-copy-expiration-to-castus"

def test_connection(server_type, config):
    """Test FTP connection"""
    data = {
        "server_type": server_type,
        **config
    }
    response = requests.post(TEST_CONNECTION_URL, json=data)
    return response.json()

def main():
    print("Testing expiration copy to Castus metadata with connection...")
    print("-" * 60)
    
    # Server configurations
    source_config = {
        "host": "castus1",
        "port": "21",
        "user": "root",
        "password": "Atl#C1a26",
        "path": "/mnt/main/ATL26 On-Air Content"
    }
    
    target_config = {
        "host": "castus2", 
        "port": "21",
        "user": "root",
        "password": "Atl#C1a26",
        "path": "/mnt/main/ATL26 On-Air Content"
    }
    
    # Test connections
    print("\nTesting connections...")
    
    print("Testing source server...")
    source_result = test_connection("source", source_config)
    print(f"Source: {source_result}")
    
    print("\nTesting target server...")
    target_result = test_connection("target", target_config)
    print(f"Target: {target_result}")
    
    # Wait a bit for connections to stabilize
    time.sleep(1)
    
    # Now test the expiration copy
    print("\n" + "-" * 60)
    print("\nTesting expiration copy to Castus...")
    
    test_data = {
        "filename": "250908_MTG_Zoning_Committee.mp4",
        "server": "target"
    }
    
    response = requests.post(COPY_EXPIRATION_URL, json=test_data)
    result = response.json()
    
    print("\nAPI Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('status') == 'success':
        print("\n✅ SUCCESS!")
        data = result.get('data', {})
        if data:
            print(f"Asset ID: {data.get('asset_id')}")
            print(f"Expiration Date: {data.get('expiration_date')}")
            print(f"Metadata Path: {data.get('metadata_path')}")
            print(f"Server: {data.get('server')}")
            if data.get('created_new'):
                print("Note: Created new metadata file (didn't exist)")
    else:
        print(f"\n❌ Error: {result.get('message')}")

if __name__ == "__main__":
    main()