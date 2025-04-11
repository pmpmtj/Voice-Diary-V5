"""
Gmail API Email Sender

This script uses the Gmail API to send emails. It requires:
1. OAuth2 credentials (credentials_gmail.json)
2. Email configuration (conf_send_email.json)

The script will:
1. Load email settings from conf_send_email.json
2. Authenticate with Gmail API using Gmail-specific credentials
3. Send the configured email with optional attachments
"""

import os
import json
import base64
import re
import sys
import logging
from logging.handlers import RotatingFileHandler
import pickle
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from googleapiclient import errors as google_errors
from cryptography.fernet import Fernet
import io
from tqdm import tqdm

# Initialize paths - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    SCRIPT_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    SCRIPT_DIR = Path(__file__).parent.absolute()

# Create a global logger that will be configured in setup_logging
logger = logging.getLogger("voice_diary.email")

# Define log directory relative to the script
LOGS_DIR = SCRIPT_DIR / "logs"

# Required Gmail API scopes
REQUIRED_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Configure basic logging until we can load the full config
def setup_basic_logging():
    """Set up basic logging configuration before loading the full config."""
    # Create logs directory if it doesn't exist
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Configure basic logger
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    # Add a basic file handler
    file_handler = RotatingFileHandler(
        LOGS_DIR / "send_email.log", 
        maxBytes=1048576,
        backupCount=3
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)
    
    logger.info("Basic logging configured. Loading full configuration...")

# Configure basic logging first so we can log during initialization
setup_basic_logging()

# Define configuration search paths in priority order
def get_config_path() -> Optional[Path]:
    """
    Find configuration file checking multiple locations in priority order.
    
    Returns:
        Path to config file if found, None otherwise
    """
    # Ensure config directory exists
    config_dir = SCRIPT_DIR / "config"
    if not config_dir.exists():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created config directory: {config_dir}")
        except Exception as e:
            logger.warning(f"Failed to create config directory: {str(e)}")
    
    # Module-specific config (highest priority)
    module_config = config_dir / "conf_send_email.json"
    if module_config.exists():
        logger.info(f"Using module-specific config: {module_config}")
        return module_config
        
    # Check for config passed as environment variable
    if os.environ.get("EMAIL_SENDER_CONFIG"):
        env_config = Path(os.environ.get("EMAIL_SENDER_CONFIG"))
        if env_config.exists():
            logger.info(f"Using config from environment variable: {env_config}")
            return env_config
    
    # Check parent directory (project structure) as fallback
    project_root = SCRIPT_DIR.parent
    project_config = project_root / "project_fallback_config" / "config_send_email" / "conf_send_email.json"
    if project_config.exists():
        logger.info(f"Using project-level config: {project_config}")
        return project_config
    
    # Default config in the module directory
    default_config = SCRIPT_DIR / "conf_send_email.json"
    if default_config.exists():
        logger.info(f"Using default config: {default_config}")
        return default_config
    
    # No valid config found - return module config path for potential creation
    logger.warning("No configuration file found in any expected locations")
    return module_config

# Get configuration file path after get_config_path is defined
CONFIG_FILE = get_config_path()

@dataclass
class EmailConfig:
    """Email configuration data class"""
    to: str
    subject: str
    message: str
    default_message: str
    attachment: Optional[str] = None

@dataclass
class AuthConfig:
    """Authentication configuration data class"""
    credentials_file: str
    token_file: str
    token_dir: Optional[str] = None
    port: int = 0
    credentials_path: Optional[str] = None

@dataclass
class LoggingFileConfig:
    """File logging configuration data class"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    filename: str = "send_email.log"
    max_size_bytes: int = 1048576
    backup_count: int = 3
    encoding: str = "utf-8"

@dataclass
class LoggingConsoleConfig:
    """Console logging configuration data class"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(levelname)s - %(message)s"

@dataclass
class LoggingConfig:
    """Logging configuration data class"""
    file: LoggingFileConfig = field(default_factory=LoggingFileConfig)
    console: LoggingConsoleConfig = field(default_factory=LoggingConsoleConfig)
    logs_dir: str = "logs"
    logger_name: str = "voice_diary.email"
    validate_format: bool = False

@dataclass
class ApiConfig:
    """API configuration data class"""
    scopes: List[str]

@dataclass
class TestingConfig:
    """Testing configuration data class"""
    dry_run: bool = False
    mock_responses: bool = False

@dataclass
class AppConfig:
    """Application configuration data class"""
    send_email: bool = True
    validate_email: bool = True
    api: ApiConfig = field(default_factory=lambda: ApiConfig([]))
    auth: AuthConfig = field(default_factory=lambda: AuthConfig("credentials_gmail.json", "token_gmail.pickle"))
    email: EmailConfig = field(default_factory=lambda: EmailConfig("", "", "", ""))
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    testing: TestingConfig = field(default_factory=TestingConfig)
    version: str = "1.0.0"

@dataclass
class EmailStatistics:
    """Statistics for email operations"""
    attempts: int = 0
    success: bool = False
    auth_success: bool = False
    email_generated: bool = False
    attachment_added: bool = False
    dry_run: bool = False
    error_message: Optional[str] = None
    message_id: Optional[str] = None

class EmailError(Exception):
    """Base exception for email-related errors"""
    pass

class ConfigError(EmailError):
    """Configuration-related errors"""
    pass

class AuthenticationError(EmailError):
    """Authentication-related errors"""
    pass

class EmailSendError(EmailError):
    """Email sending errors"""
    pass

def ensure_directory_exists(directory_path: Union[str, Path], purpose: str = "directory", logger_obj: Optional[logging.Logger] = None) -> bool:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory_path: Path to the directory to ensure exists
        purpose: Description of the directory for logging messages
        logger_obj: Logger object to use instead of print
        
    Returns:
        True if directory exists or was created successfully
    
    Raises:
        ConfigError: If directory creation fails
    """
    dir_path = Path(directory_path)
    if dir_path.exists():
        return True
        
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        
        msg = f"Created {purpose}: {dir_path}"
        if logger_obj:
            logger_obj.info(msg)
        else:
            print(msg)
            
        return True
    except Exception as e:
        error_msg = f"Failed to create {purpose}: {dir_path}. Error: {str(e)}"
        if logger_obj:
            logger_obj.error(error_msg)
        else:
            print(f"ERROR: {error_msg}")
            
        raise ConfigError(error_msg)

def validate_config(config: AppConfig) -> List[str]:
    """
    Validate the configuration with detailed error messages.
    
    Args:
        config: Application configuration object
        
    Returns:
        List of validation error messages (empty if config is valid)
    """
    validation_errors = []
    
    # Check email settings if email sending is enabled
    if config.send_email:
        if not config.email.to:
            validation_errors.append("Email recipient ('to' field) is missing")
        elif config.validate_email and not validate_email_format(config.email.to):
            validation_errors.append(f"Invalid email format: {config.email.to}")
            
        if not config.email.subject:
            validation_errors.append("Email subject is missing")
            
        if not config.email.message and not config.email.default_message:
            validation_errors.append("Both email message and default message are missing")
    
    # Validate attachment path if provided
    if config.email.attachment and not Path(config.email.attachment).exists():
        validation_errors.append(f"Attachment file does not exist: {config.email.attachment}")
    
    # Check API scopes
    if not config.api.scopes:
        validation_errors.append("API scopes list is empty")
    elif not all(isinstance(scope, str) for scope in config.api.scopes):
        validation_errors.append("All API scopes must be strings")
    elif not all(scope in config.api.scopes for scope in REQUIRED_SCOPES):
        validation_errors.append(f"Missing required scopes: {REQUIRED_SCOPES}")
    
    # Validate logging configuration
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.logging.file.level not in valid_levels:
        validation_errors.append(f"Invalid file logging level: {config.logging.file.level}")
        
    if config.logging.console.level not in valid_levels:
        validation_errors.append(f"Invalid console logging level: {config.logging.console.level}")
        
    if config.logging.file.max_size_bytes <= 0:
        validation_errors.append(f"Invalid max_size_bytes: {config.logging.file.max_size_bytes}")
        
    if config.logging.file.backup_count < 0:
        validation_errors.append(f"Invalid backup_count: {config.logging.file.backup_count}")
    
    return validation_errors

def create_sample_config(config_path: Optional[Path] = None) -> Dict:
    """
    Create a sample configuration file with default values.
    
    This function generates a complete configuration template with default settings.
    If a path is provided, it saves the configuration to that location.
    Otherwise, it just returns the configuration dictionary.
    
    The configuration includes settings for:
    - Email sending preferences
    - API authentication and scopes
    - Email content (to, subject, message)
    - Attachment options
    - Comprehensive logging setup
    
    Usage:
        # Generate config dictionary only
        config = create_sample_config()
        
        # Generate and save to specific location
        create_sample_config(Path("path/to/config.json"))
        
        # From command line
        # python send_email.py --create-config [optional_path]
    
    Args:
        config_path: Path where to save the sample config, if not provided no file is created
        
    Returns:
        Dictionary containing default configuration values
    """
    # Generate a default config template with documentation
    default_config = {
        "version": "1.0.0",
        "send_email": True,
        "validate_email": True,
        "api": {
            "scopes": [
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.compose",
      "https://www.googleapis.com/auth/gmail.modify",
      "https://mail.google.com/"
    ]
        },
        "auth": {
            "credentials_file": "credentials_gmail.json",
            "token_file": "token_gmail.pickle",
            "credentials_path": "credentials",   # use relative or absolute path
            "port": 0  # Use 0 for automatic port selection
        },
        "email": {
            "to": "pmpmtj@hotmail.com",
            "subject": "Voice Diary Notification",
            "message": "=== THIS IS A TEST MESSAGE ===",
            "default_message": "=== THIS IS A TEST MESSAGE ==="
        },
        "logging": {
            "file": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "filename": "send_email.log",
                "max_size_bytes": 1048576,
                "backup_count": 3,
                "encoding": "utf-8"
            },
            "console": {
                "level": "INFO",
                "format": "%(asctime)s - %(levelname)s - %(message)s"
            },
            "logs_dir": "logs"
        }
    }
    
    # If a path is provided, create the file
    if config_path:
        try:
            # Ensure parent directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write config file
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
                
            logger.info(f"Created sample configuration file at: {config_path}")
        except Exception as e:
            logger.error(f"Failed to create sample configuration file: {str(e)}")
    
    return default_config

def load_config() -> AppConfig:
    """
    Load application configuration from conf_send_email.json file with enhanced validation
    
    Returns:
        AppConfig object with parsed configuration
        
    Raises:
        ConfigError: If configuration cannot be loaded or is invalid
    """
    try:
        # If we have a project-level config but no local config, copy it to local
        if CONFIG_FILE and CONFIG_FILE.exists():
            config_path = Path(CONFIG_FILE)
            
            # Check if it's the project-level config
            project_root = SCRIPT_DIR.parent
            project_config_path = project_root / "project_fallback_config" / "config_send_email" / "conf_send_email.json"
            
            # If we're using the project config, create a local copy in the module config directory
            if str(config_path) == str(project_config_path):
                # Create local config directory if it doesn't exist
                local_config_dir = SCRIPT_DIR / "config"
                try:
                    if not local_config_dir.exists():
                        local_config_dir.mkdir(parents=True, exist_ok=True)
                        logger.info(f"Created local config directory at {local_config_dir}")
                    
                    local_config_path = local_config_dir / "conf_send_email.json"
                    
                    # Only create a local copy if it doesn't already exist
                    if not local_config_path.exists():
                        # Read the project config
                        with open(config_path, 'r', encoding='utf-8') as src_file:
                            config_data = json.load(src_file)
                        
                        # Write to local config
                        with open(local_config_path, 'w', encoding='utf-8') as dest_file:
                            json.dump(config_data, dest_file, indent=2)
                        
                        logger.info(f"Created local copy of project configuration at: {local_config_path}")
                except Exception as e:
                    logger.warning(f"Failed to create local config copy: {str(e)}")
        
        if not CONFIG_FILE or not CONFIG_FILE.exists():
            # Generate default config template
            default_config = create_sample_config()
            
            error_msg = f"Config file not found at {CONFIG_FILE or 'any expected location'}"
            logger.error(error_msg)
            
            # Suggest configuration locations
            module_config = SCRIPT_DIR / "config" / "conf_send_email.json"
            default_module_config = SCRIPT_DIR / "conf_send_email.json"
            
            print(f"ERROR: {error_msg}")
            print("Please create a configuration file using the template below:")
            print(json.dumps(default_config, indent=2))
            print(f"\nPlace this file at one of these locations:")
            print(f"1. {module_config}")
            print(f"2. {default_module_config}")
            print(f"Or set the EMAIL_SENDER_CONFIG environment variable to the path of your config file.")
            print(f"\nAlternatively, run this script with the --create-config option to automatically create a config file:")
            print(f"python {Path(__file__).name} --create-config [optional_path]")
            
            # Try to create a default config file in the module directory
            try:
                # Ensure config directory exists
                config_dir = SCRIPT_DIR / "config"
                if not config_dir.exists():
                    config_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created config directory: {config_dir}")
                
                # Try writing to config directory first
                if os.access(config_dir, os.W_OK):
                    create_sample_config(module_config)
                    print(f"\nA sample configuration has been created at: {module_config}")
                    print("Please edit this file with your settings and run the script again.")
                else:
                    # Log access error
                    logger.warning(f"No write access to config directory: {config_dir}")
                    
                    # Fallback to module directory
                    create_sample_config(default_module_config)
                    print(f"\nA sample configuration has been created at: {default_module_config}")
                    print("Please edit this file with your settings and run the script again.")
            except Exception as e:
                logger.error(f"Could not create sample config file: {str(e)}")
                
            raise ConfigError(error_msg)
            
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            
        # Create configuration objects
        email_config = EmailConfig(
            to=config_data.get('email', {}).get('to', ''),
            subject=config_data.get('email', {}).get('subject', ''),
            message=config_data.get('email', {}).get('message', ''),
            default_message=config_data.get('email', {}).get('default_message', '=== THIS IS A TEST MESSAGE ==='),
            attachment=config_data.get('email', {}).get('attachment')
        )
        
        auth_config = AuthConfig(
            credentials_file=config_data.get('auth', {}).get('credentials_file', 'credentials_gmail.json'),
            token_file=config_data.get('auth', {}).get('token_file', 'token_gmail.pickle'),
            token_dir=config_data.get('auth', {}).get('token_dir'),
            port=config_data.get('auth', {}).get('port', 0),
            credentials_path=config_data.get('auth', {}).get('credentials_path')
        )
        
        # Extract testing config if available
        testing_config = TestingConfig(
            dry_run=config_data.get('testing', {}).get('dry_run', False),
            mock_responses=config_data.get('testing', {}).get('mock_responses', False)
        )
        
        # Process logging config based on new structure (file & console sections)
        logging_section = config_data.get('logging', {})
        
        # Extract file logging config
        file_section = logging_section.get('file', {})
        if not file_section:
            # Fall back to old structure if 'file' section doesn't exist
            file_section = {
                'level': logging_section.get('level', 'INFO'),
                'format': logging_section.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                'filename': logging_section.get('log_file', 'send_email.log'),
                'max_size_bytes': logging_section.get('max_size_bytes', 1048576),
                'backup_count': logging_section.get('backup_count', 3)
            }
        
        file_logging_config = LoggingFileConfig(
            level=file_section.get('level', 'INFO'),
            format=file_section.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            filename=file_section.get('filename', 'send_email.log'),
            max_size_bytes=file_section.get('max_size_bytes', 1048576),
            backup_count=file_section.get('backup_count', 3),
            encoding=file_section.get('encoding', 'utf-8')
        )
        
        # Extract console logging config
        console_section = logging_section.get('console', {})
        if not console_section:
            # Fall back to simplified console config if section doesn't exist
            console_section = {
                'level': logging_section.get('level', 'INFO'),
                'format': '%(asctime)s - %(levelname)s - %(message)s'
            }
            
        console_logging_config = LoggingConsoleConfig(
            level=console_section.get('level', 'INFO'),
            format=console_section.get('format', '%(asctime)s - %(levelname)s - %(message)s')
        )
        
        logging_config = LoggingConfig(
            file=file_logging_config,
            console=console_logging_config,
            logs_dir=logging_section.get('logs_dir', 'logs'),
            logger_name=logging_section.get('logger_name', 'voice_diary.email'),
            validate_format=logging_section.get('validate_format', False)
        )
        
        api_config = ApiConfig(
            scopes=config_data.get('api', {}).get('scopes', [])
        )
        
        app_config = AppConfig(
            send_email=config_data.get('send_email', True),
            validate_email=config_data.get('validate_email', True),
            api=api_config,
            auth=auth_config,
            email=email_config,
            logging=logging_config,
            testing=testing_config,
            version=config_data.get('version', '1.0.0')
        )
        
        # Handle deprecated credentials_path at root level
        if 'credentials_path' in config_data:
            logger.warning("'credentials_path' at root level is deprecated. Please move it to the 'auth' section.")
            if not app_config.auth.credentials_path:
                app_config.auth.credentials_path = config_data.get('credentials_path')
                
        # Validate required scopes
        if not all(scope in app_config.api.scopes for scope in REQUIRED_SCOPES):
            logger.warning(f"Missing required scopes in configuration. Adding required scopes: {REQUIRED_SCOPES}")
            app_config.api.scopes.extend([scope for scope in REQUIRED_SCOPES if scope not in app_config.api.scopes])
        
        # Perform comprehensive validation
        validation_errors = validate_config(app_config)
        if validation_errors:
            logger.error("Configuration validation errors:")
            for error in validation_errors:
                logger.error(f"  - {error}")
            if len(validation_errors) > 5:  # If there are too many errors, it's likely a major problem
                raise ConfigError(f"Multiple configuration errors: {validation_errors[0]} (and {len(validation_errors)-1} more)")
            else:
                # For fewer errors, we can be more specific
                raise ConfigError("; ".join(validation_errors))
        
        return app_config
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in config file {CONFIG_FILE}: {str(e)}"
        logger.error(error_msg)
        raise ConfigError(error_msg)
    except Exception as e:
        if not isinstance(e, ConfigError):
            error_msg = f"Failed to load configuration: {str(e)}"
            logger.error(error_msg)
            raise ConfigError(error_msg)
        raise

def setup_logging(config: LoggingConfig) -> logging.Logger:
    """
    Set up logging with the provided configuration
    
    Args:
        config: Logging configuration
        
    Returns:
        Configured logger
    """
    # Create logs directory using the configuration
    logs_dir = SCRIPT_DIR / config.logs_dir
    ensure_directory_exists(logs_dir, "logs directory")
    
    # Get logger by name - use a new logger instead of the global one to avoid duplicating handlers
    logger_name = config.logger_name
    new_logger = logging.getLogger(logger_name)
    new_logger.setLevel(getattr(logging, config.file.level))
    
    # Remove existing handlers to avoid duplicates
    for handler in new_logger.handlers[:]:
        new_logger.removeHandler(handler)
        handler.close()  # Properly close handlers to avoid file locking issues
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(config.console.format))
    console_handler.setLevel(getattr(logging, config.console.level))
    new_logger.addHandler(console_handler)
    
    # File handler with rotation
    log_path = logs_dir / config.file.filename
    file_handler = RotatingFileHandler(
        log_path, 
        maxBytes=config.file.max_size_bytes, 
        backupCount=config.file.backup_count,
        encoding=config.file.encoding
    )
    file_handler.setFormatter(logging.Formatter(config.file.format))
    file_handler.setLevel(getattr(logging, config.file.level))
    new_logger.addHandler(file_handler)
    
    # Log basic information about the configuration
    new_logger.info("Logging configured successfully")
    
    return new_logger

def validate_email_format(email: str) -> bool:
    """
    Validate email address format using regex
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email format is valid, False otherwise
    """
    # RFC 5322 compliant email regex pattern
    pattern = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    
    # Simplified validation - check basic pattern and common mistakes
    if not re.match(pattern, email):
        return False
    
    # Check for leading dots in username
    username, domain = email.split('@', 1)
    if username.startswith('.'):
        return False
    
    # Check for consecutive dots in domain
    if '..' in domain:
        return False
    
    # Check for trailing dots in domain
    if domain.endswith('.'):
        return False
    
    # Check for leading dots in domain parts
    domain_parts = domain.split('.')
    if any(part.startswith('.') or part == '' for part in domain_parts):
        return False
    
    # Specifically check for overlong domains like example.com.com.com
    if len(domain_parts) > 3 and len(set(domain_parts[-3:])) < 3:
        return False
    
    return True

def check_email_config(config: AppConfig, logger: logging.Logger) -> bool:
    """
    Check if email sending is enabled and validate recipient email if needed
    
    Args:
        config: Application configuration
        logger: Logger instance
        
    Returns:
        True if configuration is valid, False otherwise
    """
    if not config.send_email:
        logger.info("Email sending is disabled in config")
        return False
        
    # Validate email format if enabled
    if config.validate_email and config.email.to:
        recipient = config.email.to
        if not validate_email_format(recipient):
            logger.error(f"Invalid email format: {recipient}")
            return False
            
    return True

def get_credentials_paths(config: AppConfig, logger: logging.Logger) -> tuple:
    """
    Get credentials file paths with mobile/portable support.
    
    Lookup order:
    1. Check module directory (script_dir/credentials)
    2. Check environment variable (EMAIL_CREDENTIALS_DIR)
    3. Check absolute path in config auth.credentials_path 
    4. Check relative path in config auth.credentials_path (relative to SCRIPT_DIR)
    5. Fallback to default location (script_dir/credentials)
    
    Args:
        config: Application configuration
        logger: Logger instance
        
    Returns:
        Tuple of (credentials_file_path, token_file_path)
    """
    # Get filenames from config
    credentials_filename = config.auth.credentials_file
    token_filename = config.auth.token_file
    
    # Make sure credentials directory exists first
    module_creds_dir = SCRIPT_DIR / "credentials"
    if not module_creds_dir.exists():
        try:
            module_creds_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created credentials directory: {module_creds_dir}")
        except Exception as e:
            logger.warning(f"Failed to create credentials directory: {str(e)}")
    
    # First check for credentials directly in the module directory (highest priority)
    module_creds_path = module_creds_dir / credentials_filename
    module_token_path = module_creds_dir / token_filename
    
    if module_creds_path.exists():
        logger.info(f"Using credentials from module directory: {module_creds_dir}")
        return module_creds_path, module_token_path
    
    # Check for environment variable (second priority)
    if os.environ.get("EMAIL_CREDENTIALS_DIR"):
        env_creds_dir = Path(os.environ.get("EMAIL_CREDENTIALS_DIR"))
        env_creds_path = env_creds_dir / credentials_filename
        env_token_path = env_creds_dir / token_filename
        
        if env_creds_path.exists():
            logger.info(f"Using credentials from environment variable: {env_creds_dir}")
            return env_creds_path, env_token_path
    
    # Check for absolute path in config (third priority) - supports packaged apps
    if config.auth.credentials_path:
        creds_path = config.auth.credentials_path
        
        # If it's an absolute path, use it directly
        if os.path.isabs(creds_path):
            abs_creds_dir = Path(creds_path)
            # Create directory if it doesn't exist
            if not abs_creds_dir.exists():
                try:
                    abs_creds_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created credentials directory from config path: {abs_creds_dir}")
                except Exception as e:
                    logger.warning(f"Failed to create credentials directory from config: {str(e)}")
                    
            abs_creds_file = abs_creds_dir / credentials_filename
            abs_token_file = abs_creds_dir / token_filename
            
            if abs_creds_file.exists():
                logger.info(f"Using credentials from absolute path: {abs_creds_dir}")
                return abs_creds_file, abs_token_file
        else:
            # It's a relative path, make it relative to SCRIPT_DIR
            rel_creds_dir = SCRIPT_DIR / Path(creds_path)
            # Create directory if it doesn't exist
            if not rel_creds_dir.exists():
                try:
                    rel_creds_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created relative credentials directory: {rel_creds_dir}")
                except Exception as e:
                    logger.warning(f"Failed to create relative credentials directory: {str(e)}")
                    
            rel_creds_file = rel_creds_dir / credentials_filename
            rel_token_file = rel_creds_dir / token_filename
            
            if rel_creds_file.exists():
                logger.info(f"Using credentials from relative path: {rel_creds_dir}")
                return rel_creds_file, rel_token_file
    
    # Check for token directory in config
    if config.auth.token_dir:
        token_dir_path = Path(config.auth.token_dir)
        if token_dir_path.is_absolute():
            token_dir = token_dir_path 
        else:
            token_dir = SCRIPT_DIR / token_dir_path
            
        # Ensure token directory exists
        try:
            ensure_directory_exists(token_dir, "token directory", logger)
        except Exception as e:
            logger.warning(f"Failed to create token directory: {str(e)}")
        
        token_path = token_dir / token_filename
        
        # Only update token path if credentials exist
        if module_creds_path.exists():
            logger.info(f"Using token directory from config: {token_dir}")
            return module_creds_path, token_path
    
    # Finally, use default location in the module directory
    logger.info(f"Using default credentials location: {module_creds_dir}")
    return module_creds_path, module_token_path

def check_credentials_file(config: AppConfig, logger: logging.Logger) -> bool:
    """
    Check if credentials.json exists and provide help if not.
    
    Args:
        config: Application configuration
        logger: Logger instance
        
    Returns:
        True if credentials file exists, False otherwise
    """
    credentials_file, token_file = get_credentials_paths(config, logger)
    
    if not credentials_file.exists():
        logger.error(f"'{credentials_file}' file not found!")
        
        # Get just the filename without the path
        credentials_filename = Path(credentials_file).name
        credentials_dir = Path(credentials_file).parent
        
        # Try to create credentials directory if it doesn't exist
        if not credentials_dir.exists():
            try:
                credentials_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created credentials directory: {credentials_dir}")
            except Exception as e:
                logger.error(f"Failed to create credentials directory: {str(e)}")
        
        logger.error("\nCredential file not found. Please do one of the following:")
        logger.error(f"1. Create the directory {credentials_dir} if it doesn't exist")
        logger.error(f"2. Place '{credentials_filename}' in: {credentials_dir}")
        logger.error(f"3. Or update the 'credentials_path' in your config file ({CONFIG_FILE})")
        logger.error("\nTo create your Gmail credentials file:")
        logger.error("1. Go to https://console.cloud.google.com/")
        logger.error("2. Create a project or select an existing one")
        logger.error("3. Enable the Gmail API:")
        logger.error("   - Navigate to 'APIs & Services' > 'Library'")
        logger.error("   - Search for 'Gmail API' and enable it")
        logger.error("4. Create OAuth credentials:")
        logger.error("   - Go to 'APIs & Services' > 'Credentials'")
        logger.error("   - Click 'Create Credentials' > 'OAuth client ID'")
        logger.error("   - Select 'Desktop app' as application type")
        logger.error(f"   - Download the JSON file and rename it to '{credentials_filename}'")
        logger.error(f"   - Place it in: {credentials_dir}")
        logger.error("\nThen run this script again.")
        return False
    return True

def encrypt_token(token_data: bytes, token_file_path: Path) -> bytes:
    """
    Encrypt token data using Fernet.
    
    Args:
        token_data: Raw token data to encrypt
        token_file_path: Path to the token file to determine where to store the key
        
    Returns:
        bytes: Encrypted token data
    """
    # Use token file's directory to determine where to store the key
    token_dir = token_file_path.parent
    key_name = f".{token_file_path.name}_key"
    key_file = token_dir / key_name
    
    # Generate a key if it doesn't exist
    if not key_file.exists():
        key = Fernet.generate_key()
        ensure_directory_exists(token_dir, "token key directory")
        with open(key_file, 'wb') as f:
            f.write(key)
    else:
        with open(key_file, 'rb') as f:
            key = f.read()
            
    f = Fernet(key)
    return f.encrypt(token_data)

def decrypt_token(encrypted_data: bytes, token_file_path: Path) -> bytes:
    """
    Decrypt token data using Fernet.
    
    Args:
        encrypted_data: Encrypted token data
        token_file_path: Path to the token file to determine where the key is stored
        
    Returns:
        bytes: Decrypted token data
        
    Raises:
        AuthenticationError: If token cannot be decrypted
    """
    token_dir = token_file_path.parent
    key_name = f".{token_file_path.name}_key"
    key_file = token_dir / key_name
    
    if not key_file.exists():
        raise AuthenticationError(f"Token key file not found: {key_file}")
        
    with open(key_file, 'rb') as f:
        key = f.read()
        
    try:
        f = Fernet(key)
        return f.decrypt(encrypted_data)
    except Exception as e:
        raise AuthenticationError(f"Failed to decrypt token: {str(e)}")

def authenticate_gmail(config: AppConfig, logger: logging.Logger):
    """
    Authenticate with Gmail API using OAuth with encrypted token storage.
    
    Args:
        config: Application configuration
        logger: Logger instance
        
    Returns:
        Gmail API service object if authentication is successful, None otherwise
        
    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        credentials_file, token_file = get_credentials_paths(config, logger)
        logger.info(f"Using credentials from: {credentials_file}")
        logger.info(f"Using token file: {token_file}")
        
        creds = None
        
        # The token file stores the user's access and refresh tokens
        if token_file.exists():
            logger.info(f"Found existing token file")
            try:
                with open(token_file, 'rb') as token:
                    encrypted_data = token.read()
                    token_data = decrypt_token(encrypted_data, token_file)
                    creds = pickle.loads(token_data)
            except (ValueError, pickle.UnpicklingError, AuthenticationError) as e:
                logger.error(f"Error loading token file: {str(e)}")
                # Remove invalid token file
                token_file.unlink(missing_ok=True)
                
        # If no valid credentials are available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Token expired, refreshing...")
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refreshing token: {str(e)}")
                    # Remove invalid token file
                    token_file.unlink(missing_ok=True)
                    creds = None
            else:
                if not check_credentials_file(config, logger):
                    logger.error("Credentials file check failed")
                    raise AuthenticationError("Credentials file not found or invalid")
                
                logger.info("Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_file), config.api.scopes)
                creds = flow.run_local_server(port=config.auth.port)
                
            # Save the credentials for the next run
            token_dir = token_file.parent
            ensure_directory_exists(token_dir, "token directory", logger)
                
            try:
                token_data = pickle.dumps(creds)
                encrypted_data = encrypt_token(token_data, token_file)
                with open(token_file, 'wb') as token:
                    token.write(encrypted_data)
            except Exception as e:
                logger.error(f"Error saving token: {str(e)}")
                raise
        
        # Build the service with the credentials
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        error_msg = f"Authentication error: {str(e)}"
        logger.error(error_msg)
        raise AuthenticationError(error_msg)

def create_message(sender: str, to: str, subject: str, message_text: str) -> Dict[str, str]:
    """
    Create a message for an email.
    
    Args:
        sender: Sender email address
        to: Recipient email address
        subject: Email subject
        message_text: Email body text
        
    Returns:
        Dictionary with encoded email message
    """
    message = MIMEText(message_text)
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')}

def create_message_with_attachment(sender: str, to: str, subject: str, message_text: str, 
                                  attachment_path: Optional[str] = None, 
                                  logger: Optional[logging.Logger] = None) -> Dict[str, str]:
    """
    Create a message for an email with optional attachment and progress tracking for large files.
    
    Args:
        sender: Sender email address
        to: Recipient email address
        subject: Email subject
        message_text: Email body text
        attachment_path: Path to the attachment file
        logger: Optional logger for progress updates
        
    Returns:
        Dictionary with encoded email message
        
    Raises:
        EmailSendError: If there's an error with the attachment
    """
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject

    # Add the message body
    msg = MIMEText(message_text)
    message.attach(msg)

    # Add attachment if provided
    if attachment_path and Path(attachment_path).exists():
        path = Path(attachment_path)
        try:
            file_size = path.stat().st_size
            # Log file info
            if logger:
                logger.info(f"Attaching file: {path.name} ({file_size/1024/1024:.2f} MB)")
            
            # For small files (< 5MB), just read at once
            if file_size < 5 * 1024 * 1024:
                with open(path, 'rb') as f:
                    attachment = MIMEApplication(f.read())
            else:
                # For larger files, read with progress
                if logger:
                    logger.info(f"Large file detected, reading with progress tracking")
                
                # Read large file with progress tracking
                chunk_size = 1024 * 1024  # 1MB chunks
                buffer = io.BytesIO()
                
                with open(path, 'rb') as f:
                    with tqdm(total=file_size, unit='B', unit_scale=True, 
                             desc=f"Reading {path.name}") as pbar:
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            buffer.write(chunk)
                            pbar.update(len(chunk))
                
                attachment = MIMEApplication(buffer.getvalue())
                
            # Add headers
            attachment.add_header(
                'Content-Disposition', 
                'attachment', 
                filename=path.name
            )
            message.attach(attachment)
            
        except PermissionError:
            error_msg = f"Permission denied when reading file {attachment_path}"
            if logger:
                logger.error(error_msg)
            raise EmailSendError(error_msg)
        except MemoryError:
            error_msg = f"File {attachment_path} is too large to attach"
            if logger:
                logger.error(error_msg)
            raise EmailSendError(error_msg)
        except Exception as e:
            error_msg = f"Error attaching file {attachment_path}: {str(e)}"
            if logger:
                logger.error(error_msg)
            raise EmailSendError(error_msg)
    elif attachment_path:
        error_msg = f"Attachment file does not exist: {attachment_path}"
        if logger:
            logger.error(error_msg)
        raise EmailSendError(error_msg)

    # Catch any encoding errors
    try:
        encoded_message = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')}
        return encoded_message
    except Exception as e:
        error_msg = f"Error encoding email message: {str(e)}"
        if logger:
            logger.error(error_msg)
        raise EmailSendError(error_msg)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((google_errors.HttpError, ConnectionError))
)
def send_message(service, user_id: str, message: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """
    Send an email message with retry capability.
    
    Args:
        service: Gmail API service instance
        user_id: User ID ('me' for authenticated user)
        message: Message to send
        logger: Logger instance
        
    Returns:
        Dictionary with information about the sent message
        
    Raises:
        EmailSendError: If sending the email fails after all retries
    """
    try:
        logger.info("Attempting to send email...")
        sent_message = service.users().messages().send(
            userId=user_id,
            body=message
        ).execute()
        logger.info(f'Message sent successfully, Message Id: {sent_message["id"]}')
        return sent_message
    except google_errors.HttpError as e:
        status_code = e.resp.status
        error_msg = f'HTTP error sending message (status {status_code}): {str(e)}'
        logger.error(error_msg)
        
        # If these errors occur, they're permanent and shouldn't be retried
        if status_code in [400, 401, 403]:
            raise EmailSendError(error_msg)
            
        # Otherwise, let tenacity retry
        raise
    except ConnectionError as e:
        # Connection errors are likely transient - let tenacity retry
        logger.warning(f"Connection error: {str(e)} - will retry")
        raise
    except Exception as e:
        error_msg = f'Unexpected error sending message: {e}'
        logger.error(error_msg)
        raise EmailSendError(error_msg)

def update_config_value(config_path: Path, key_path: List[str], value: Any, logger: logging.Logger) -> None:
    """
    Update a specific value in the config file.
    
    Args:
        config_path: Path to the config file
        key_path: List of keys to navigate the config dictionary
        value: Value to set
        logger: Logger instance
    
    Raises:
        ConfigError: If updating the config fails
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Navigate to the nested key
        current = config
        for i, key in enumerate(key_path[:-1]):
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the value
        current[key_path[-1]] = value
        
        # Write updated config back to file
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"Updated config value: {'.'.join(key_path)} = {value}")
    except Exception as e:
        error_msg = f"Error updating config file: {str(e)}"
        logger.error(error_msg)
        raise ConfigError(error_msg)

def restore_default_message(config: AppConfig, logger: logging.Logger) -> None:
    """
    Restore the default message in the email config after sending an email.
    
    Args:
        config: Application configuration
        logger: Logger instance
    """
    try:
        # Get default message from config
        default_message = config.email.default_message
        
        # Check if current message is different from default
        if config.email.message != default_message:
            logger.info("Restoring default email message")
            
            # Update config file
            update_config_value(CONFIG_FILE, ['email', 'message'], default_message, logger)
            
            # Also update in-memory config
            config.email.message = default_message
            
            logger.info("Default email message restored successfully")
        else:
            logger.info("Email message already set to default value")
            
    except Exception as e:
        logger.error(f"Error restoring default email message: {str(e)}")

def validate_file_path(path: Union[str, Path]) -> bool:
    """
    Validate that a file path is safe and within allowed directories.
    
    Args:
        path: Path to validate
        
    Returns:
        bool: True if path is valid, False otherwise
    """
    try:
        path = Path(path).resolve()
        # For email attachments, we need to be more permissive but still validate
        # the path is not dangerous (e.g., not trying to access system files)
        return not any(forbidden in str(path).lower() for forbidden in 
                      ['/etc/', '/var/log/', '/proc/', '/sys/', 
                       'C:\\Windows\\', 'C:\\Program Files\\'])
    except Exception as e:
        logger.error(f"Path validation error: {str(e)}")
        return False

def send_email(to: str = None, subject: str = None, message: str = None, attachment: str = None, config_path: str = None) -> bool:
    """
    Public API function to send email programmatically.
    
    Args:
        to: Email recipient. If None, uses value from config.
        subject: Email subject. If None, uses value from config.
        message: Email message body. If None, uses value from config.
        attachment: Path to attachment file. If None, uses value from config.
        config_path: Optional path to a custom config file.
        
    Returns:
        bool: True if email was sent successfully, False otherwise.
    """
    logger.info("Sending email via API function")
    
    try:
        # Set environment variable if custom config path provided
        if config_path:
            os.environ["EMAIL_SENDER_CONFIG"] = str(config_path)
            
        # Load configuration
        config = load_config()
        
        # Override config values with any provided parameters
        if to:
            config.email.to = to
        if subject:
            config.email.subject = subject
        if message:
            config.email.message = message
        if attachment:
            config.email.attachment = attachment
            
        # Set up full logging with configuration
        configured_logger = setup_logging(config.logging)
        
        # Log the operation
        configured_logger.info(f"Send email API called - To: {config.email.to}, Subject: {config.email.subject}")
        
        # Check for dry run mode
        if config.testing.dry_run:
            configured_logger.info("Running in DRY RUN mode - no emails will be sent")
            
        # Check if email sending is enabled and configuration is valid
        if not check_email_config(config, configured_logger):
            configured_logger.error("Email sending is disabled in config or configuration is invalid")
            return False
        
        # Check if credentials file exists
        if not check_credentials_file(config, configured_logger):
            return False
        
        # Authenticate with Gmail
        configured_logger.info("Authenticating with Gmail...")
        service = None
        if not config.testing.dry_run:
            service = authenticate_gmail(config, configured_logger)
            
            # Get the authenticated user's email address
            user_profile = service.users().getProfile(userId='me').execute()
            sender = user_profile['emailAddress']
            configured_logger.info(f"Authenticated as: {sender}")
        else:
            configured_logger.info("Dry run mode: Skipping authentication")
            sender = "dry-run@example.com"
        
        # Check if we need to send with attachment
        attachment_path = config.email.attachment
        
        # Validate attachment path if provided
        if attachment_path and not validate_file_path(attachment_path):
            configured_logger.error(f"Invalid attachment path: {attachment_path}")
            return False
        
        # Create the email
        try:
            if attachment_path:
                configured_logger.info(f"Creating email with attachment: {attachment_path}")
                if not config.testing.dry_run:
                    message_obj = create_message_with_attachment(
                        sender,
                        config.email.to,
                        config.email.subject,
                        config.email.message,
                        attachment_path,
                        configured_logger
                    )
            else:
                configured_logger.info("Creating plain email message")
                if not config.testing.dry_run:
                    message_obj = create_message(
                        sender,
                        config.email.to,
                        config.email.subject,
                        config.email.message
                    )
            
            # In dry run mode, just log what would happen
            if config.testing.dry_run:
                configured_logger.info(f"Dry run mode: Would send email to: {config.email.to}")
                configured_logger.info(f"Dry run mode: Email subject: {config.email.subject}")
                if attachment_path:
                    configured_logger.info(f"Dry run mode: With attachment: {attachment_path}")
                configured_logger.info("Dry run completed successfully")
                return True
            
            # Send the email
            configured_logger.info(f"Sending email to: {config.email.to}")
            try:
                result = send_message(service, 'me', message_obj, configured_logger)
                configured_logger.info("Email sent successfully!")
                return True
            except EmailSendError as e:
                configured_logger.error(f"Failed to send email: {str(e)}")
                return False
                
        except EmailSendError as e:
            configured_logger.error(f"Error preparing email: {str(e)}")
            return False
            
    except ConfigError as e:
        logger.error(f"Configuration error: {str(e)}")
        return False
    except AuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        return False
    except EmailSendError as e:
        logger.error(f"Email sending error: {str(e)}")
        return False
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")
        return False

def main() -> bool:
    """
    Main function to send email via Gmail API.
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    # Check for help option
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("Gmail API Email Sender for Voice Diary")
        print("\nUsage:")
        print(f"  python {Path(__file__).name} [options]")
        print("\nOptions:")
        print("  --help, -h              Show this help message")
        print("  --create-config [path]  Create a sample configuration file at the specified path")
        print("                          If no path is provided, creates config at the default location")
        print("\nConfiguration search paths (in order of priority):")
        print(f"  1. {SCRIPT_DIR}/config/conf_send_email.json")
        print(f"  2. Environment variable EMAIL_SENDER_CONFIG")
        print(f"  3. {SCRIPT_DIR.parent}/project_fallback_config/config_send_email/conf_send_email.json")
        print(f"  4. {SCRIPT_DIR}/conf_send_email.json")
        return True
    
    # Check if user wants to create a sample config
    if len(sys.argv) > 1 and sys.argv[1] == "--create-config":
        config_path = None
        if len(sys.argv) > 2:
            config_path = Path(sys.argv[2])
        else:
            # Use default location
            config_path = SCRIPT_DIR / "config" / "conf_send_email.json"
            
        print(f"Creating sample configuration file at: {config_path}")
        create_sample_config(config_path)
        return True
        
    # Log start of service with the basic logger
    logger.info("Voice Diary Email Service Starting")
    
    # Initialize statistics
    stats = EmailStatistics()
    
    # Use the API function to send the email
    result = send_email()
    
    # Set statistics based on result
    stats.success = result
    
    return result

if __name__ == "__main__":
    main() 