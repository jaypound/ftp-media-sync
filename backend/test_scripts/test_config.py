#!/usr/bin/env python3
"""
Test configuration loading
"""
from config_manager import ConfigManager

# Create config manager instance
config_manager = ConfigManager()

# Get scheduling settings
scheduling_config = config_manager.get_scheduling_settings()
content_expiration = scheduling_config.get('content_expiration', {})

print("Content Expiration Configuration:")
print(f"MTG days: {content_expiration.get('MTG', 'NOT FOUND')}")
print("\nFull content_expiration config:")
for ct, days in content_expiration.items():
    print(f"  {ct}: {days} days")
    
print("\nFull scheduling config keys:")
print(list(scheduling_config.keys()))