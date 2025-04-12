#!/usr/bin/env python3
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any

# Constants
ENCODING = "utf-8"
DEFAULT_CONFIG_FILE = "module_config.json"

# Initialize paths - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    SCRIPT_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    SCRIPT_DIR = Path(__file__).parent.absolute()

# Define log directory
LOGS_DIR = SCRIPT_DIR / "logs"

# Parent directory where module_config.json is located
PARENT_DIR = SCRIPT_DIR.parent

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load logging configuration from the specified path or default location.
    
    Args:
        config_path: Optional path to the config file
        
    Returns:
        Dict containing the logging configuration
    """
    if config_path is None:
        # Look for config in the parent directory first
        parent_config_path = PARENT_DIR / DEFAULT_CONFIG_FILE
        if parent_config_path.exists():
            config_path = parent_config_path
        else:
            # Fall back to the script directory
            config_path = SCRIPT_DIR / DEFAULT_CONFIG_FILE
    
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
    
    # Set up log directory
    logs_dir = Path(log_dir) if log_dir else LOGS_DIR
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

# Example usage in other scripts:
if __name__ == "__main__":
    # Test the logger
    logger = setup_logger("test_module")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message") 