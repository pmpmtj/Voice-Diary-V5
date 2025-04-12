#!/usr/bin/env python3
import json
import os
import sys
import webbrowser
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import pickle
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from voice_diary.transcribe_raw_audio.logger_setup import setup_logger, ENCODING, SCRIPT_DIR

# Configurable fallback paths
DEFAULT_FALLBACK_CONFIG_PATH = "src/voice_diary/project_fallback_config/config_transcribe_raw_audio"
DEFAULT_FALLBACK_CONFIG_FILENAME = "config_transcribe_raw_audio.json"
# Module-specific values
MODULE_CREDENTIALS_FILENAME = "credentials.json"

# Set up logger
logger = setup_logger("transcribe_raw_audio")

logger.info(f"SCRIPT_DIR: {SCRIPT_DIR}")

def load_config(fallback_config_path: Optional[str] = None, 
                fallback_config_filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Load the configuration from the JSON config file following a specific order:
    1. Look in SCRIPT_DIR/config for config.json (hardcoded directory name and filename)
    2. Look in fallback_config_path for fallback_config_filename (configurable)
    3. Fallback to SCRIPT_DIR/config (ensure directory exists and return None)
    
    Args:
        fallback_config_path: Optional path to the fallback config directory
        fallback_config_filename: Optional filename of the fallback config file
    
    Returns:
        Optional[Dict[str, Any]]: The configuration as a dictionary or None if no config was found
    
    Raises:
        json.JSONDecodeError: If a found config file is not valid JSON
    """
    # Use provided fallback paths or defaults
    fallback_path = fallback_config_path or DEFAULT_FALLBACK_CONFIG_PATH
    fallback_filename = fallback_config_filename or DEFAULT_FALLBACK_CONFIG_FILENAME
    
    # 1. Look in SCRIPT_DIR/config for config.json (hardcoded directory name and filename)
    PRIMARY_CONFIG_DIR = SCRIPT_DIR / "config"  # Hardcoded directory name
    PRIMARY_CONFIG_FILE = PRIMARY_CONFIG_DIR / "config.json"  # Hardcoded filename
    
    if PRIMARY_CONFIG_DIR.exists() and PRIMARY_CONFIG_FILE.exists():
        try:
            with open(PRIMARY_CONFIG_FILE, "r", encoding=ENCODING) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing primary config file: {e.msg}")
            raise json.JSONDecodeError(f"Error parsing primary config file: {e.msg}", e.doc, e.pos)
    
    # 2. Look in fallback_path for fallback_filename
    fallback_dir = Path(fallback_path)
    fallback_file = fallback_dir / fallback_filename
    
    if fallback_dir.exists() and fallback_file.exists():
        try:
            with open(fallback_file, "r", encoding=ENCODING) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing fallback config file: {e.msg}")
            raise json.JSONDecodeError(f"Error parsing fallback config file: {e.msg}", e.doc, e.pos)
    
    # 3. Fallback to SCRIPT_DIR/config - ensure directory exists and return None
    if not PRIMARY_CONFIG_DIR.exists():
        os.makedirs(PRIMARY_CONFIG_DIR, exist_ok=True)
        logger.info(f"Created primary config directory at: {PRIMARY_CONFIG_DIR}")
    
    return None


def convert_string_booleans(config_dict):
    """
    Recursively converts string 'true' and 'false' to boolean values in a dictionary
    """
    for key, value in config_dict.items():
        if isinstance(value, dict):
            convert_string_booleans(value)
        elif isinstance(value, str) and value.lower() in ['true', 'false']:
            config_dict[key] = value.lower() == 'true'
    return config_dict

def create_sample_config(config_path):
    """
    Create a sample configuration file with default values.
    
    Args:
        config_path: Path where to save the sample config
        
    Returns:
        dict: Dictionary containing default configuration values
    """
    # Generate a default config template with boolean values as strings
    default_config = { 
  "logging": {
  "level": "INFO",
  "format": "%(asctime)s - %(levelname)s - %(message)s",
  "log_file": "transcribe_audio_for_diary.log",
  "max_size_bytes": 1048576,
  "backup_count": 3
  },
  "transcriptions_dir": "C:/Users/pmpmt/voice_diary_app/transcriptions",
  "output_file": "diary_transcription.txt"
}
    
    # Ensure the directory exists
    config_dir = Path(config_path).parent
    if not config_dir.exists():
        os.makedirs(config_dir, exist_ok=True)
        logger.info(f"Created config directory at: {config_dir}")
    
    # Convert string booleans to actual booleans before writing to JSON
    config_to_write = convert_string_booleans(default_config.copy())
    
    # Write the configuration to the file
    with open(config_path, 'w', encoding=ENCODING) as f:
        json.dump(config_to_write, f, indent=4)
    
    logger.info(f"Created sample config file at: {config_path}")
    return default_config

def main():
    """
    Main function to transcribe audio files.
    This function can be imported and called from other modules.
    """
    config = load_config()
    if config:
        logger.info("Configuration loaded successfully")
        # Add your processing logic here
    else:
        logger.warning("No configuration found. Please create a config.json file.")
if __name__ == "__main__":
    main()