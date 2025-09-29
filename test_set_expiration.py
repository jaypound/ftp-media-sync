#!/usr/bin/env python3
"""
Test setting expiration dates for a specific category
"""
import requests
import json

# API endpoint
SET_URL = "http://127.0.0.1:5000/api/set-category-expiration"

# Test setting expiration for MTG (Meetings) category
# Note: PostgreSQL enum values are lowercase
test_data = {
    "content_type": "mtg",  # lowercase for PostgreSQL enum
    "expiration_days": 14  # 14 days for meetings
}

print("Testing category expiration setting...")
print(f"Category: {test_data['content_type']}")
print(f"Days: {test_data['expiration_days']}")
print("-" * 60)

try:
    response = requests.post(SET_URL, json=test_data)
    result = response.json()
    
    print("\nAPI Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('status') == 'success':
        print(f"\n✅ SUCCESS!")
        print(f"Updated {result.get('updated_count', 0)} items")
    else:
        print(f"\n❌ Error: {result.get('message')}")
        
except Exception as e:
    print(f"Error calling API: {str(e)}")
    print("\nMake sure the backend server is running on port 5000")