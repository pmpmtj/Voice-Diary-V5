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
from voice_diary.logger_utils.logger_utils import setup_logger, ENCODING
from voice_diary.download_audio_files.oauth_handler import OAuthCallbackHandler, run_local_server

# Required Google libraries
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import time  # Added for retry logic
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

# Initialize module directory path - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    MODULE_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    MODULE_DIR = Path(__file__).parent.absolute()

# Constants
# Configurable fallback paths
DEFAULT_FALLBACK_CONFIG_PATH = "src/voice_diary/project_fallback_config/config_download_audio_files"
DEFAULT_FALLBACK_CONFIG_FILENAME = "config_download_audio_files.json"
# Module-specific values
MODULE_CREDENTIALS_FILENAME = "credentials.json"
# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2  # seconds

# Set up logger
logger = setup_logger("download_audio_files")

logger.info(f"MODULE_DIR: {MODULE_DIR}")

def load_config(fallback_config_path: Optional[str] = None, 
                fallback_config_filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Load the configuration from the JSON config file following a specific order:
    1. Look in MODULE_DIR/config for config.json (hardcoded directory name and filename)
    2. Look in fallback_config_path for fallback_config_filename (configurable)
    3. Fallback to MODULE_DIR/config (ensure directory exists and return None)
    
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
    
    # 1. Look in MODULE_DIR/config for config.json (hardcoded directory name and filename)
    PRIMARY_CONFIG_DIR = MODULE_DIR / "config"  # Hardcoded directory name
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
    
    # 3. Fallback to MODULE_DIR/config - ensure directory exists and return None
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
        "version": "1.0.0",
        "api": {
            "_description": "Google Drive API configuration and OAuth 2.0 scopes",
            "scopes": [
                "https://www.googleapis.com/auth/drive"
            ],
            "retry": {
                "max_retries": DEFAULT_MAX_RETRIES,
                "retry_delay": DEFAULT_RETRY_DELAY
            }
        },
        "auth": {
            "_description": "Authentication configuration for Google Drive access",
            "credentials_file": MODULE_CREDENTIALS_FILENAME,
            "token_file": "gdrive_token.pickle",
            "credentials_path": "credentials",  # Use OS-agnostic path relative to MODULE_DIR
            "fallback_config_path": DEFAULT_FALLBACK_CONFIG_PATH,
            "fallback_config_filename": DEFAULT_FALLBACK_CONFIG_FILENAME
        },
        "folders": {
            "_description": "Configuration for Google Drive folders to process",
            "target_folders": [
                "a-daily-log",
                "root"
            ]
        },
        "audio_file_types": {
            "_description": "Supported audio file extensions for processing",
            "include": [".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"]
        },
        "download": {
            "_description": "Download behavior settings including timestamp configuration",
            "add_timestamps": "true",
            "timestamp_format": "%Y%m%d_%H%M%S_%f",
            "dry_run": "false",
            "delete_after_download": "true"
        },
        "downloads_path": {
            "_description": "Configuration for download directory location",
            "downloads_dir": "downloaded"
        }
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

def retry_operation(operation, *args, max_retries=DEFAULT_MAX_RETRIES, retry_delay=DEFAULT_RETRY_DELAY, **kwargs):
    """
    Retry an operation with exponential backoff
    
    Args:
        operation: The function to retry
        args: Arguments to pass to the function
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        kwargs: Keyword arguments to pass to the function
        
    Returns:
        The result of the operation if successful
        
    Raises:
        The last exception encountered if all retries fail
    """
    last_exception = None
    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt}/{max_retries} for operation {operation.__name__}")
            return operation(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Operation failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"All retry attempts failed for operation {operation.__name__}: {e}")
    
    # If we get here, all retries failed
    if last_exception:
        raise last_exception
    return None

def get_oauth_credentials(config: Dict[str, Any], credentials_file: Path) -> Optional[Path]:
    """
    Guide the user through the OAuth flow to obtain credentials
    
    Args:
        config: Configuration dictionary containing OAuth settings
        credentials_file: Path to the credentials file (client secrets)
        
    Returns:
        Path to the token file or None if the process failed
    """
    if not GOOGLE_LIBS_AVAILABLE:
        logger.error("Required Google libraries are not installed. Please run:")
        logger.error("pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return None
        
    auth_config = config.get("auth", {})
    api_config = config.get("api", {})
    
    # Get token file path
    token_file_name = auth_config.get("token_file", "gdrive_token.pickle")
    token_file = credentials_file.parent / token_file_name
    
    # Extract retry configuration
    retry_config = api_config.get("retry", {})
    max_retries = retry_config.get("max_retries", DEFAULT_MAX_RETRIES)
    retry_delay = retry_config.get("retry_delay", DEFAULT_RETRY_DELAY)
    
    # Check if token file already exists and is valid
    creds = None
    if token_file.exists():
        try:
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            logger.warning(f"Failed to load existing token: {e}")
    
    # Check if credentials need to be refreshed
    if creds and creds.expired and creds.refresh_token:
        try:
            # Wrap token refresh with retry logic
            def refresh_token(creds):
                creds.refresh(Request())
                return creds
                
            creds = retry_operation(
                refresh_token, 
                creds,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
            
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
            logger.info("Credentials refreshed successfully")
            return token_file
        except Exception as e:
            logger.warning(f"Failed to refresh token: {e}")
            # Continue with new authorization flow
    
    # If no valid credentials exist, start new OAuth flow
    if not creds or not creds.valid:
        try:
            # Extract scopes from config
            scopes = api_config.get("scopes", ["https://www.googleapis.com/auth/drive"])
            
            # Use InstalledAppFlow's run_local_server method instead of manual server handling
            # This handles all the server and browser interaction in a more robust way
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_file),
                scopes=scopes
            )
            
            # The run_local_server method opens a browser, starts a local server,
            # handles the OAuth flow, and returns the credentials
            print("Starting authentication flow. Your browser will open for you to authenticate.")
            
            # Wrap OAuth flow with retry logic
            def run_oauth_flow(flow):
                return flow.run_local_server(
                    port=0,  # Use random available port
                    open_browser=True,
                    authorization_prompt_message="Please complete authentication in your browser.",
                    success_message="Authentication completed! You may close this window."
                )
                
            creds = retry_operation(
                run_oauth_flow,
                flow,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
            
            # Save credentials for future use
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
                
            logger.info(f"Authentication successful. Token saved to {token_file}")
            return token_file
            
        except Exception as e:
            logger.error(f"Error during OAuth flow: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    return token_file


def find_or_create_credentials(config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Locate or create credentials file/folder following a specific order:
    1. Look for credentials file in MODULE_DIR
    2. Look at auth config using credentials_file and credentials_path from config
    3. Ensure path exists and create a "credentials" folder in the MODULE_DIR if needed
    4. If credentials file exists but token is missing/invalid, guide through OAuth flow
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Tuple of (credentials_file, token_file) paths or (None, None) if not found/created
    """
    # Load configuration if not provided
    if config is None:
        config = load_config()
    
    # Get credentials filename from config or use module default
    credentials_filename = MODULE_CREDENTIALS_FILENAME
    if config and "auth" in config:
        auth_config = config["auth"]
        if "credentials_file" in auth_config:
            credentials_filename = auth_config["credentials_file"]
    
    # 1. Look for credentials file in MODULE_DIR
    credentials_file = MODULE_DIR / credentials_filename
    
    if credentials_file.exists():
        logger.info(f"Found credentials file at: {credentials_file}")
        token_file = get_oauth_credentials(config, credentials_file) if config else None
        return credentials_file, token_file
    
    # 2. Look at auth config using credentials_file and credentials_path from config
    if config and "auth" in config:
        auth_config = config["auth"]
        if "credentials_file" in auth_config and "credentials_path" in auth_config:
            credentials_filename = auth_config["credentials_file"]
            credentials_path = Path(auth_config["credentials_path"])
            # Check if path is relative or absolute
            if not credentials_path.is_absolute():
                credentials_path = MODULE_DIR / credentials_path
            fallback_credentials_file = credentials_path / credentials_filename
            
            if fallback_credentials_file.exists():
                logger.info(f"Found credentials file at fallback location: {fallback_credentials_file}")
                token_file = get_oauth_credentials(config, fallback_credentials_file)
                return fallback_credentials_file, token_file
    
    # 3. Ensure path exists and create a "credentials" folder in the MODULE_DIR
    credentials_dir = MODULE_DIR / "credentials"
    if not credentials_dir.exists():
        os.makedirs(credentials_dir, exist_ok=True)
        logger.info(f"Created credentials directory at: {credentials_dir}")
    
    # No credentials file was found, but we've created the directory
    logger.warning(f"No credentials file found. Please obtain a Google API OAuth client ID JSON file from the Google Cloud Console")
    logger.warning(f"and place it at: {credentials_dir / credentials_filename}")
    logger.warning("Visit https://console.cloud.google.com/apis/credentials to create OAuth 2.0 Client ID credentials")
    
    return None, None

# Added functions from download_audio_files.py for downloading files from Google Drive
def ensure_directory_exists(dir_path, dir_description="directory"):
    """
    Ensure a directory exists, create it if it doesn't.
    
    Args:
        dir_path: Path to check/create
        dir_description: Description for logging purposes
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Created {dir_description} at: {dir_path}")

def authenticate_google_drive():
    """
    Authenticate with Google Drive API and build a service.
    
    Returns:
        Google Drive API service instance or None if authentication failed
    """
    if not GOOGLE_LIBS_AVAILABLE:
        logger.error("Google libraries are not available. Please install required dependencies.")
        return None
        
    config = load_config()
    if not config:
        logger.error("Configuration is required for Google Drive authentication.")
        return None
    
    credentials_file, token_file = find_or_create_credentials(config)
    if not token_file:
        logger.error("No valid token file available. Authentication required.")
        return None
    
    try:
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
            
        service = build('drive', 'v3', credentials=creds)
        logger.info("Successfully authenticated with Google Drive API")
        return service
    except Exception as e:
        logger.error(f"Failed to build Drive service: {str(e)}")
        return None

def find_folder_by_name(service, folder_name):
    """Find a folder ID by its name in Google Drive.
    
    Args:
        service: Google Drive API service instance
        folder_name: Name of the folder to find
        
    Returns:
        str: Folder ID if found, None otherwise
    """
    try:
        # Search for folders with the given name
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            logger.warning(f"No folder named '{folder_name}' found.")
            return None
            
        # Return the ID of the first matched folder
        folder_id = items[0]['id']
        logger.info(f"Found folder '{folder_name}' with ID: {folder_id}")
        return folder_id
        
    except Exception as e:
        logger.error(f"Error finding folder '{folder_name}': {str(e)}")
        return None

def list_files_in_folder(service, folder_id, file_extensions=None):
    """List files in a Google Drive folder.
    
    Args:
        service: Google Drive API service instance
        folder_id: ID of the folder to list files from
        file_extensions: Optional dict with 'include' key containing list of file extensions to filter by
        
    Returns:
        list: List of file objects (each containing id, name, mimeType)
    """
    try:
        # The query for files in the specified folder
        query = f"'{folder_id}' in parents and trashed = false"
        
        # Retrieve files with needed fields
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType)'
        ).execute()
        
        items = results.get('files', [])
        
        # Filter out folders
        items = [item for item in items if item.get('mimeType') != 'application/vnd.google-apps.folder']
        
        # Filter by file extensions if specified
        if file_extensions and 'include' in file_extensions:
            extensions = file_extensions['include']
            items = [item for item in items if any(item['name'].lower().endswith(ext.lower()) for ext in extensions)]
        
        return items
        
    except Exception as e:
        logger.error(f"Error listing files in folder {folder_id}: {str(e)}")
        return []

def download_file(service, file_id, file_name=None, download_dir=None):
    """Download a file from Google Drive by ID.
    
    Args:
        service: Google Drive service instance
        file_id: ID of the file to download OR a file object with 'id' and 'name' keys
        file_name: Name of the file to save (optional if file_id is a dict) or full path to save the file to
        download_dir: Optional directory path where to save downloaded file
    
    Returns:
        dict: A dictionary with the download result information
    """
    try:
        # If file_id is a dict (file object), extract the id and name
        if isinstance(file_id, dict):
            file_info = file_id
            file_name = file_info.get('name')
            file_id = file_info.get('id')
        
        # Determine the output path
        if os.path.isabs(file_name) or '/' in file_name or '\\' in file_name:
            # file_name is already a full path
            output_path = Path(file_name)
            # Ensure parent directory exists
            ensure_directory_exists(output_path.parent, "output directory")
            # Extract just the filename for logging
            display_name = output_path.name
        else:
            # file_name is just a filename, use download_dir
            config = load_config()
            if download_dir:
                download_dir_path = Path(download_dir)
            else:
                downloads_dir = config['downloads_path']['downloads_dir']
                
                # If it's a relative path starting with "../", resolve it relative to MODULE_DIR
                if downloads_dir.startswith("../") or downloads_dir.startswith("..\\"):
                    download_dir_path = (MODULE_DIR / downloads_dir).resolve()
                else:
                    # Otherwise, use the path directly but resolve it relative to MODULE_DIR
                    download_dir_path = (MODULE_DIR / downloads_dir).resolve()
            
            # Ensure download directory exists
            ensure_directory_exists(download_dir_path, "download directory")
            
            # Generate filename with timestamp if configured
            if config.get('download', {}).get('add_timestamps', False):
                timestamp_format = config.get('download', {}).get('timestamp_format', '%Y%m%d_%H%M%S_%f')
                output_filename = generate_filename_with_timestamp(file_name, timestamp_format)
            else:
                output_filename = file_name
                
            # Create the full file path
            output_path = download_dir_path / output_filename
            display_name = file_name
            
        logger.info(f"Downloading {display_name} as {output_path}")
        
        # Create a file handler
        with open(output_path, 'wb') as f:
            # Get the file as media content
            request = service.files().get_media(fileId=file_id)
            
            # Download the file
            downloader = MediaIoBaseDownload(f, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Download {int(status.progress() * 100)}% complete.")
        
        logger.info(f"Download complete! Saved as: {output_path}")
        
        return {
            "success": True,
            "original_filename": display_name,
            "saved_as": str(output_path),
            "file_id": file_id
        }
            
    except Exception as e:
        logger.error(f"Error downloading file {file_name}: {str(e)}")
        
        return {
            "success": False,
            "original_filename": file_name,
            "file_id": file_id,
            "error": str(e)
        }

def delete_file(service, file_id, file_name=None):
    """Delete a file from Google Drive.
    
    Args:
        service: Google Drive API service instance
        file_id: ID of the file to delete OR a file object with 'id' and 'name' keys
        file_name: Name of the file (for logging purposes), optional if file_id is a dict
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        # If file_id is a dict (file object), extract the id and name
        if isinstance(file_id, dict):
            file_name = file_id.get('name', 'Unknown file')
            file_id = file_id.get('id')
        
        # Execute the deletion
        logger.info(f"Deleting file: {file_name}")
        service.files().delete(fileId=file_id).execute()
        logger.info(f"File '{file_name}' deleted successfully.")
        return True
    except Exception as e:
        logger.error(f"Error deleting file '{file_name}': {str(e)}")
        return False

def generate_filename_with_timestamp(filename: str, timestamp_format: Optional[str] = None) -> str:
    """
    Generate a filename with a timestamp prefix.
    
    Args:
        filename: The original filename
        timestamp_format: Format string for the timestamp, if None the original filename is returned
    
    Returns:
        The filename with timestamp prefix added
    """
    if not timestamp_format:
        return filename
        
    timestamp = datetime.datetime.now().strftime(timestamp_format)
    return f"{timestamp}_{filename}"

def process_folder(service, folder_id, folder_name, dry_run=False):
    """Process files in a Google Drive folder (non-recursively).
    
    Args:
        service: Google Drive API service instance
        folder_id: ID of the folder to process
        folder_name: Name of the folder (for logging purposes)
        dry_run: If True, only log actions without actually downloading or deleting files
        
    Returns:
        dict: Statistics about processed files
    """
    config = load_config()
    
    try:
        # For the process_folder test, we need to use a different approach
        # The test expects this specific query
        query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType, size, modifiedTime, fileExtension)",
            pageSize=1000
        ).execute()
        all_items = results.get('files', [])
        
        if not all_items:
            logger.info(f"No files found in folder: {folder_name}")
            return {
                'total_files': 0,
                'processed_files': 0,
                'downloaded_files': 0,
                'skipped_files': 0,
                'error_files': 0,
                'deleted_files': 0,
                'audio_files': 0
            }
        
        # Get audio file extensions
        audio_file_types = config.get('audio_file_types', {}).get('include', [])
        
        # Filter for audio files
        if audio_file_types:
            audio_items = [item for item in all_items 
                           if any(item['name'].lower().endswith(ext.lower()) 
                                  for ext in audio_file_types)]
            logger.info(f"Found {len(audio_items)} audio files in folder: {folder_name}")
        else:
            audio_items = []
            logger.info(f"No audio file extensions configured, no audio files will be processed")
            
        # Count metrics
        stats = {
            'total_files': len(all_items),
            'processed_files': len(all_items),  # Process all files in the folder
            'downloaded_files': 0,
            'skipped_files': len(all_items) - len(audio_items),  # Files not downloaded are skipped
            'error_files': 0,
            'deleted_files': 0,
            'audio_files': len(audio_items)
        }
        
        # Setup download directory
        downloads_dir = config['downloads_path']['downloads_dir']
        
        # If it's a relative path starting with "../", resolve it relative to MODULE_DIR
        if downloads_dir.startswith("../") or downloads_dir.startswith("..\\"):
            base_download_dir = (MODULE_DIR / downloads_dir).resolve()
        else:
            # Otherwise, use the path directly but resolve it relative to MODULE_DIR
            base_download_dir = (MODULE_DIR / downloads_dir).resolve()
            
        # Ensure the directory exists
        ensure_directory_exists(base_download_dir, "download directory")
        
        # Process each audio file - only download audio files but count all files
        for item in audio_items:
            item_id = item['id']
            item_name = item['name']
            # We don't have createdTime from list_files_in_folder, so we'll get it another way if needed
            created_time = ''
            
            # If we need creation time for timestamping, we can make an additional API call
            if config.get('download', {}).get('add_timestamps', False):
                try:
                    file_details = service.files().get(fileId=item_id, fields="createdTime").execute()
                    created_time = file_details.get('createdTime', '')
                except Exception as e:
                    logger.warning(f"Couldn't get creation time for {item_name}: {str(e)}")
            
            # Log file with its creation date if available
            if created_time:
                logger.info(f"Processing audio file '{item_name}' (Creation date: {created_time})")
            else:
                logger.info(f"Processing audio file '{item_name}'")
            
            # Generate output path
            if config.get('download', {}).get('add_timestamps', False):
                timestamp_format = config.get('download', {}).get('timestamp_format', '%Y%m%d_%H%M%S_%f')
                
                # Use the file's creation time from Google Drive if available
                if created_time:
                    try:
                        # Parse the ISO timestamp to datetime
                        created_time_dt = datetime.datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                        # Convert to local timezone if needed
                        created_time_dt = created_time_dt.astimezone()
                        timestamped_name = created_time_dt.strftime(timestamp_format) + "_" + item_name
                    except (ValueError, TypeError):
                        # Fallback to current time if parsing fails
                        logger.warning(f"Could not parse creation time for {item_name}, using current time instead")
                        timestamped_name = generate_filename_with_timestamp(item_name, timestamp_format)
                else:
                    # Fallback to current time if createdTime is not available
                    timestamped_name = generate_filename_with_timestamp(item_name, timestamp_format)
                    
                output_path = base_download_dir / timestamped_name
            else:
                output_path = base_download_dir / item_name
            
            # In dry run mode, just log what would happen
            if dry_run:
                print(f"Would download audio file: {item_name} -> {output_path}")
                if config.get('download', {}).get('delete_after_download', False):
                    print(f"Would delete file from Google Drive after download: {item_name}")
                stats['downloaded_files'] += 1
                continue
            
            # Download the file
            try:
                download_result = download_file(service, item_id, str(output_path))
                
                if download_result['success']:
                    stats['downloaded_files'] += 1
                    logger.info(f"Successfully downloaded audio file: {item_name}")
                    
                    # Delete file from Google Drive if configured
                    if config.get('download', {}).get('delete_after_download', False):
                        delete_file(service, item_id, item_name)
                        stats['deleted_files'] += 1
                else:
                    stats['error_files'] += 1
            except Exception as e:
                logger.error(f"Error processing file {item_name}: {str(e)}")
                stats['error_files'] += 1
        
        # Log statistics for this folder
        logger.info(f"Folder '{folder_name}' statistics:")
        logger.info(f"  - Total files: {stats['total_files']}")
        logger.info(f"  - Audio files: {stats['audio_files']}")
        logger.info(f"  - Processed files: {stats['processed_files']}")
        logger.info(f"  - Downloaded files: {stats['downloaded_files']}")
        logger.info(f"  - Deleted files: {stats['deleted_files']}")
        
        return stats
        
    except Exception as e:
        logger.exception(f"Error processing folder '{folder_name}': {str(e)}")
        return {
            'total_files': 0,
            'processed_files': 0,
            'downloaded_files': 0,
            'skipped_files': 0,
            'error_files': 1,
            'deleted_files': 0,
            'audio_files': 0
        }

def main():
    """
    Main function to download audio files from Google Drive.
    This function can be imported and called from other modules.
    """
    # Get fallback config paths from config if available
    fallback_config_path = DEFAULT_FALLBACK_CONFIG_PATH
    fallback_config_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
    
    config = load_config(fallback_config_path, fallback_config_filename)
    if config:
        # Update fallback paths from config if present
        if "auth" in config:
            auth_config = config["auth"]
            if "fallback_config_path" in auth_config:
                fallback_config_path = auth_config["fallback_config_path"]
            if "fallback_config_filename" in auth_config:
                fallback_config_filename = auth_config["fallback_config_filename"]
        
        logger.info("Configuration loaded successfully")
        
        # Always try to create credentials directory and handle OAuth flow
        credentials_file, token_file = find_or_create_credentials(config)
        
        if credentials_file:
            logger.info(f"Using credentials file: {credentials_file}")
            if token_file:
                logger.info(f"Using token file: {token_file}")
                # Authenticate and build the service
                service = authenticate_google_drive()
                if service:
                    # Get target folders from configuration
                    target_folders = config['folders'].get('target_folders', ['root'])
                    
                    # Check if running in dry run mode
                    dry_run = config.get('download', {}).get('dry_run', False)
                    if dry_run:
                        logger.info("Running in DRY RUN mode - no files will be downloaded or deleted")
                        print("\n=== DRY RUN MODE - NO FILES WILL BE DOWNLOADED OR DELETED ===\n")
                    
                    # Process each target folder
                    for folder_name in target_folders:
                        if folder_name.lower() == 'root':
                            # Root folder has a special ID
                            folder_id = 'root'
                            logger.info(f"Processing root folder")
                        else:
                            # Find folder by name
                            logger.info(f"Looking for folder: {folder_name}")
                            folder_id = find_folder_by_name(service, folder_name)
                            
                            if not folder_id:
                                logger.warning(f"Folder '{folder_name}' not found. Skipping.")
                                continue
                            
                            logger.info(f"Processing folder: {folder_name} (ID: {folder_id})")
                        
                        # Process files in the folder
                        process_folder(service, folder_id, folder_name, dry_run=dry_run)
                    
                    logger.info("Google Drive download process completed.")
                    return True
                else:
                    logger.error("Failed to authenticate with Google Drive.")
            else:
                logger.warning("Authentication not completed. Please run the script again to authenticate.")
        else:
            logger.warning(f"No credentials file found. Please place your credentials file in: {MODULE_DIR / 'credentials'}")
    else:
        logger.warning("No configuration found. Creating sample configuration...")
        sample_config_path = MODULE_DIR / "config" / "config.json"  # Hardcoded directory name and filename
        config = create_sample_config(sample_config_path)
        logger.info("Please review and update the configuration as needed.")
    
    return False

if __name__ == "__main__":
    main()