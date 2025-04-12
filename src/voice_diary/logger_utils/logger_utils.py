#!/usr/bin/env python3
import json
import logging
import sys
import importlib
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any

# Constants
ENCODING = "utf-8"
DEFAULT_CONFIG_FILE = "module_config.json"

# Initialize paths - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    MODULE_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    MODULE_DIR = Path(__file__).parent.absolute()

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load logging configuration from the specified path or default location.
    Search for the config file in multiple locations for better flexibility.
    
    Args:
        config_path: Optional path to the config file
        
    Returns:
        Dict containing the logging configuration
    """
    if config_path is None:
        # Try multiple possible locations in order of preference
        possible_config_paths = [
            MODULE_DIR / DEFAULT_CONFIG_FILE,  # In logger_utils directory
            MODULE_DIR / "config" / DEFAULT_CONFIG_FILE,  # In logger_utils/config directory
            MODULE_DIR / "config" / "config.json",  # In logger_utils/config as config.json
            MODULE_DIR.parent / DEFAULT_CONFIG_FILE,  # In parent directory
        ]
        
        # Use the first config file that exists
        for path in possible_config_paths:
            if path.exists():
                config_path = path
                break
        
        # If no config file found, default to the module directory
        if config_path is None:
            config_path = MODULE_DIR / DEFAULT_CONFIG_FILE
    
    try:
        with open(config_path, 'r', encoding=ENCODING) as f:
            config_data = json.load(f)
            return config_data
    except Exception as e:
        # If we can't load the config, use basic defaults
        return {
            "logging": {
                "file": {"level": "INFO"},
                "console": {"level": "INFO"}
            }
        }

def get_module_dir(module_name: str) -> Path:
    """
    Get the directory of the specified module.
    
    Args:
        module_name: Name of the module
        
    Returns:
        Path to the module's directory
    """
    try:
        # Try to get the module directory by importing it
        module_parts = module_name.split('.')
        
        # First try with direct module path
        try:
            module = importlib.import_module(f"voice_diary.{module_name}")
            return Path(module.__file__).parent
        except (ModuleNotFoundError, AttributeError):
            # If that fails, try to find the module directory by its name
            # This handles cases where module_name is a subsystem name, not a direct module
            for subdir in MODULE_DIR.iterdir():
                if subdir.is_dir() and subdir.name == module_parts[0]:
                    return subdir
            
            # If both approaches fail, return a subdirectory of MODULE_DIR with the module name
            return MODULE_DIR / module_parts[0]
    except Exception as e:
        # Fallback to a subdirectory of MODULE_DIR with the module name
        return MODULE_DIR / module_name

def setup_logger(
    module_name: str,
    config_path: Optional[Path] = None,
    log_dir: Optional[Path] = None
) -> logging.Logger:
    """
    Set up a logger with both file and console handlers using the configuration.
    
    Args:
        module_name: Name of the module (used for the logger name and module-specific settings)
        config_path: Optional path to the config file
        log_dir: Optional custom log directory path
        
    Returns:
        Configured logger instance
    """
    # Load configuration
    config = load_config(config_path)
    logging_config = config.get("logging", {})
    
    # Determine module directory and set up log directory within the module directory
    module_dir = get_module_dir(module_name)
    logs_dir = Path(log_dir) if log_dir else module_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Get module-specific settings
    module_config = logging_config.get("modules", {}).get(
        module_name,
        logging_config.get("modules", {}).get("default", {})
    )
    
    # Create logger
    logger = logging.getLogger(f"voice_diary.{module_name}")
    logger.setLevel(logging.DEBUG)  # Set to DEBUG to allow all levels, handlers will filter
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Console Handler
    console_config = logging_config.get("console", {})
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_config.get("level", "INFO")))
    console_handler.setFormatter(logging.Formatter(
        console_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        console_config.get("date_format", "%H:%M:%S")
    ))
    logger.addHandler(console_handler)
    
    # File Handler
    file_config = logging_config.get("file", {})
    log_file = logs_dir / module_config.get("log_filename", file_config.get("log_filename", "voice_diary.log"))
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=file_config.get("max_size_bytes", 1048576),
        backupCount=file_config.get("backup_count", 5),
        encoding=file_config.get("encoding", ENCODING)
    )
    file_handler.setLevel(getattr(logging, module_config.get("level", file_config.get("level", "INFO"))))
    file_handler.setFormatter(logging.Formatter(
        file_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s"),
        file_config.get("date_format", "%Y-%m-%d %H:%M:%S")
    ))
    logger.addHandler(file_handler)
    
    # Log file location after logger is configured
    logger.info(f"Using log file: {log_file}")
    
    return logger

# Example usage in other modules:
# from voice_diary.logger_utils import setup_logger
# logger = setup_logger("your_module_name") 