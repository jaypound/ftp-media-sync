#!/usr/bin/env python3
"""
Debug script to check expiration date discrepancy
"""
import requests
import json

# API endpoint
API_URL = "http://127.0.0.1:5000/api/test-expiration-debug"

# Test data
test_data = {
    "filename": "250908_MTG_Zoning_Committee.mp4",
    "asset_id": 370
}

print("Debugging expiration date discrepancy...")
print(f"File: {test_data['filename']}")
print(f"Known Asset ID: {test_data['asset_id']}")
print("-" * 50)

try:
    response = requests.post(API_URL, json=test_data)
    result = response.json()
    
    if result.get('status') == 'success':
        print("\nResults:")
        print(json.dumps(result.get('data', {}), indent=2))
    else:
        print(f"\nError: {result.get('message')}")
        
except Exception as e:
    print(f"Error calling API: {str(e)}")
    print("\nMake sure the backend server is running on port 5000")