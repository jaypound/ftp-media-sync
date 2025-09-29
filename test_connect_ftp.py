#!/usr/bin/env python3
"""
Test script to connect to FTP servers
"""
import requests
import json

# API endpoints
CONFIG_URL = "http://127.0.0.1:5000/api/config"
CONNECT_URL = "http://127.0.0.1:5000/api/scan-files"

print("Attempting to connect to FTP servers...")
print("-" * 60)

# First get the current config
response = requests.get(CONFIG_URL)
config_response = response.json()
config = config_response.get('config', {})

# Test scan (which will trigger connection)
scan_data = {
    "source": {
        "path": config.get('servers', {}).get('source', {}).get('path', '/'),
        "subdirs": config.get('filters', {}).get('include_subdirectories', True)
    },
    "target": {
        "path": config.get('servers', {}).get('target', {}).get('path', '/'),
        "subdirs": config.get('filters', {}).get('include_subdirectories', True)
    }
}

print("Scanning files (this will establish FTP connections)...")
scan_response = requests.post(CONNECT_URL, json=scan_data)
scan_result = scan_response.json()

if scan_result.get('success'):
    print("✅ FTP connections established")
    print(f"Source files: {len(scan_result.get('source', {}).get('files', []))}")
    print(f"Target files: {len(scan_result.get('target', {}).get('files', []))}")
else:
    print(f"❌ Failed to establish connections: {scan_result.get('message', 'Unknown error')}")