#!/usr/bin/env python3
"""
Test what the API returns for available content
"""
import requests
import json

# API endpoint
API_URL = "http://127.0.0.1:5000/api/analyzed-content"

# Search for our specific file
test_data = {
    "search": "250908_MTG_Zoning_Committee"
}

print("Checking what the API returns for available content...")
print("-" * 50)

try:
    response = requests.post(API_URL, json=test_data)
    result = response.json()
    
    if result.get('success'):
        content_list = result.get('content', [])
        print(f"Found {len(content_list)} matching items\n")
        
        for content in content_list:
            if '250908_MTG_Zoning_Committee' in content.get('file_name', ''):
                print(f"File: {content.get('file_name')}")
                print(f"ID: {content.get('id')}")
                
                # Check scheduling data
                scheduling = content.get('scheduling', {})
                print(f"\nScheduling data:")
                print(f"  content_expiry_date: {scheduling.get('content_expiry_date')}")
                print(f"  castus_metadata_synced: {scheduling.get('castus_metadata_synced')}")
                print(f"  featured: {scheduling.get('featured')}")
                
                # Show all date-related fields
                print(f"\nOther date fields:")
                for key, value in content.items():
                    if 'date' in key.lower() or 'expir' in key.lower():
                        print(f"  {key}: {value}")
                        
                print("\nFull scheduling object:")
                print(json.dumps(scheduling, indent=2))
                print("-" * 50)
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")
        
except Exception as e:
    print(f"Error calling API: {str(e)}")
    print("\nMake sure the backend server is running on port 5000")