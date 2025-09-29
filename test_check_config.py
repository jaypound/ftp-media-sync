#!/usr/bin/env python3
"""
Check current config structure
"""
import requests
import json

# API endpoint
CONFIG_URL = "http://127.0.0.1:5000/api/config"

response = requests.get(CONFIG_URL)
config = response.json()

print("Current config structure:")
print(json.dumps(config, indent=2))