#!/usr/bin/env python3
"""
Test direct FTP connection
"""
import requests
import json

# API endpoint for testing connection
TEST_URL = "http://127.0.0.1:5000/api/test-connection"

print("Testing FTP connections...")
print("-" * 60)

# Test source server
source_data = {
    "server": "source",
    "config": {
        "host": "castus1",
        "port": 21,
        "user": "root",
        "password": "Atl#C1a26"
    }
}

print("\nTesting SOURCE server connection...")
response = requests.post(TEST_URL, json=source_data)
result = response.json()
print(f"Result: {result}")

# Test target server
target_data = {
    "server": "target",
    "config": {
        "host": "castus2",
        "port": 21,
        "user": "root",
        "password": "Atl#C1a26"
    }
}

print("\nTesting TARGET server connection...")
response = requests.post(TEST_URL, json=target_data)
result = response.json()
print(f"Result: {result}")

print("\n" + "-" * 60)
print("Connection test complete")