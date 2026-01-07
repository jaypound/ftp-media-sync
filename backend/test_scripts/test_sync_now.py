#!/usr/bin/env python3
"""
Trigger sync now via API
"""
import requests
import json

# API endpoint
url = "http://127.0.0.1:5000/api/scheduler/run-now"

print("Triggering manual sync via API...")
try:
    response = requests.post(url)
    data = response.json()
    
    if data.get('success'):
        print("✓ Sync started successfully!")
        print(f"Message: {data.get('message')}")
    else:
        print("✗ Sync failed to start")
        print(f"Message: {data.get('message')}")
        
except Exception as e:
    print(f"Error calling API: {e}")
    print("Make sure the Flask server is running on port 5000")

print("\nCheck the latest log file in backend/logs/ for details.")