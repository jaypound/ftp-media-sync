#!/usr/bin/env python3
"""
Test script to copy expiration from PostgreSQL to Castus for a specific file
"""
import requests
import json

# API endpoint
API_URL = "http://127.0.0.1:5000/api/test-copy-expiration-to-castus"

# Test data
test_data = {
    "filename": "250908_MTG_Zoning_Committee.mp4",
    "server": "target"
}

print("Testing copy expiration from PostgreSQL to Castus...")
print(f"File: {test_data['filename']}")
print(f"Server: {test_data['server']}")
print("-" * 50)

try:
    response = requests.post(API_URL, json=test_data)
    result = response.json()
    
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    
    if result.get('status') == 'success':
        print(f"\nDetails:")
        print(f"  Asset ID: {result.get('asset_id')}")
        print(f"  File: {result.get('file')}")
        print(f"  Expiration Date: {result.get('expiration_date')}")
        print(f"  Target Server: {result.get('server')}")
        print(f"  FTP Connected: {result.get('ftp_connected')}")
        print(f"  Note: {result.get('note')}")
    else:
        print(f"\nError: {result.get('message')}")
        
except Exception as e:
    print(f"Error calling API: {str(e)}")
    print("\nMake sure the backend server is running on port 5000")