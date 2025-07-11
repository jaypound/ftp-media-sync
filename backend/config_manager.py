import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.config = self._load_default_config()
        self.load_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration"""
        return {
            "servers": {
                "source": {
                    "name": "Source Server",
                    "host": "",
                    "port": 21,
                    "user": "",
                    "password": "",
                    "path": "/media/videos"
                },
                "target": {
                    "name": "Target Server", 
                    "host": "",
                    "port": 21,
                    "user": "",
                    "password": "",
                    "path": "/media/videos"
                }
            },
            "sync_settings": {
                "file_extensions": ["mp4", "mkv", "avi", "mov", "wmv", "m4v", "flv"],
                "min_file_size_mb": 1,
                "max_file_size_gb": 50,
                "include_subdirs": True,
                "overwrite_existing": False,
                "dry_run_default": True,
                "connection_timeout": 30,
                "transfer_timeout": 300
            },
            "ui_settings": {
                "auto_save_config": True,
                "show_file_paths": True,
                "max_files_display": 1000
            }
        }
    
    def load_config(self) -> bool:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    self._merge_config(self.config, loaded_config)
                    logger.info(f"Configuration loaded from {self.config_file}")
                    return True
            else:
                logger.info(f"No config file found, using defaults")
                return False
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            return False
    
    def save_config(self) -> bool:
        """Save current configuration to file"""
        try:
            # Don't save passwords in plain text - remove them
            config_to_save = json.loads(json.dumps(self.config))  # Deep copy
            config_to_save["servers"]["source"]["password"] = ""
            config_to_save["servers"]["target"]["password"] = ""
            
            with open(self.config_file, 'w') as f:
                json.dump(config_to_save, f, indent=4)
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
            return False
    
    def _merge_config(self, default: Dict, loaded: Dict):
        """Recursively merge loaded config with defaults"""
        for key, value in loaded.items():
            if key in default:
                if isinstance(value, dict) and isinstance(default[key], dict):
                    self._merge_config(default[key], value)
                else:
                    default[key] = value
    
    def get_server_config(self, server_type: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific server"""
        return self.config.get("servers", {}).get(server_type)
    
    def update_server_config(self, server_type: str, config: Dict[str, Any]):
        """Update configuration for a specific server"""
        if "servers" not in self.config:
            self.config["servers"] = {}
        if server_type not in self.config["servers"]:
            self.config["servers"][server_type] = {}
        
        self.config["servers"][server_type].update(config)
        
        if self.config.get("ui_settings", {}).get("auto_save_config", True):
            self.save_config()
    
    def get_sync_settings(self) -> Dict[str, Any]:
        """Get sync settings"""
        return self.config.get("sync_settings", {})
    
    def update_sync_settings(self, settings: Dict[str, Any]):
        """Update sync settings"""
        if "sync_settings" not in self.config:
            self.config["sync_settings"] = {}
        
        self.config["sync_settings"].update(settings)
        
        if self.config.get("ui_settings", {}).get("auto_save_config", True):
            self.save_config()
    
    def get_ui_settings(self) -> Dict[str, Any]:
        """Get UI settings"""
        return self.config.get("ui_settings", {})
    
    def create_sample_config(self, filename="config.sample.json"):
        """Create a sample configuration file with examples"""
        sample_config = {
            "servers": {
                "source": {
                    "name": "Main Media Server",
                    "host": "192.168.1.100",
                    "port": 21,
                    "user": "mediauser",
                    "password": "",
                    "path": "/media/movies"
                },
                "target": {
                    "name": "Backup Media Server",
                    "host": "192.168.1.101", 
                    "port": 21,
                    "user": "backupuser",
                    "password": "",
                    "path": "/backup/movies"
                }
            },
            "sync_settings": {
                "file_extensions": ["mp4", "mkv", "avi", "mov", "wmv"],
                "min_file_size_mb": 10,
                "max_file_size_gb": 100,
                "include_subdirs": True,
                "overwrite_existing": False,
                "dry_run_default": True,
                "connection_timeout": 30,
                "transfer_timeout": 600
            },
            "ui_settings": {
                "auto_save_config": True,
                "show_file_paths": True,
                "max_files_display": 1000
            }
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(sample_config, f, indent=4)
            logger.info(f"Sample configuration created: {filename}")
            return True
        except Exception as e:
            logger.error(f"Error creating sample config: {str(e)}")
            return False
    
    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = self._load_default_config()
        logger.info("Configuration reset to defaults")
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get the complete configuration"""
        return self.config.copy()