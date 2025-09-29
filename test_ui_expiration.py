#!/usr/bin/env python3
"""
Test the UI expiration functionality by simulating UI interactions
"""
import requests
import json

# API endpoints
BASE_URL = "http://127.0.0.1:5000"

print("Testing UI Expiration Functionality")
print("=" * 60)

# Test 1: Set expiration for meetings (MTG)
print("\n1. Testing Set Expiration for Meetings (14 days)...")
response = requests.post(f"{BASE_URL}/api/set-category-expiration", 
    json={
        "content_type": "MTG",  # Frontend sends uppercase
        "expiration_days": 14
    }
)
result = response.json()
print(f"Response: {json.dumps(result, indent=2)}")

# Test 2: Clear expiration for a category
print("\n2. Testing Clear Expiration for Promos...")
response = requests.post(f"{BASE_URL}/api/set-category-expiration",
    json={
        "content_type": "PMO",  # Promos
        "expiration_days": 0  # 0 means clear
    }
)
result = response.json()
print(f"Response: {json.dumps(result, indent=2)}")

# Test 3: Set expiration for multiple categories
print("\n3. Testing Set Expiration for Multiple Categories...")
categories = [
    ("PSA", 60),  # PSAs - 60 days
    ("PKG", 45),  # Packages - 45 days
    ("IA", 30),   # Inside Atlanta - 30 days
]

for content_type, days in categories:
    print(f"\n   Setting {content_type} to {days} days...")
    response = requests.post(f"{BASE_URL}/api/set-category-expiration",
        json={
            "content_type": content_type,
            "expiration_days": days
        }
    )
    result = response.json()
    if result.get('status') == 'success':
        count = result.get('updated_count', 0)
        print(f"   ✅ Updated {count} items")
    else:
        print(f"   ❌ Error: {result.get('message')}")

print("\n" + "=" * 60)
print("UI Expiration Testing Complete")