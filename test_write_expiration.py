#!/usr/bin/env python3
"""
Test script to write expiration date from PostgreSQL to Castus metadata on target server
"""
import requests
import json

# API endpoint
API_URL = "http://127.0.0.1:5000/api/test-copy-expiration-to-castus"

# Test data
test_data = {
    "filename": "250908_MTG_Zoning_Committee.mp4",
    "server": "target"  # Write to target server
}

print(f"Testing expiration copy to Castus metadata...")
print(f"File: {test_data['filename']}")
print(f"Server: {test_data['server']}")
print("-" * 60)

try:
    response = requests.post(API_URL, json=test_data)
    result = response.json()
    
    print("\nAPI Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('status') == 'success':
        print("\n✅ SUCCESS!")
        data = result.get('data', {})
        print(f"Asset ID: {data.get('asset_id')}")
        print(f"Expiration Date: {data.get('expiration_date')}")
        print(f"Metadata Path: {data.get('metadata_path')}")
        print(f"Server: {data.get('server')}")
        if data.get('created_new'):
            print("Note: Created new metadata file (didn't exist)")
    else:
        print(f"\n❌ Error: {result.get('message')}")
        
except Exception as e:
    print(f"Error calling API: {str(e)}")
    print("\nMake sure:")
    print("1. The backend server is running on port 5000")
    print("2. The target FTP server is configured and accessible")
    print("3. The file exists in the database")