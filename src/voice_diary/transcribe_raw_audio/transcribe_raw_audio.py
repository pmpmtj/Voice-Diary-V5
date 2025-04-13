#!/usr/bin/env python3
import json
import os
import sys
import time
import re
import shutil
import traceback
import subprocess
import webbrowser
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import pickle
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List, Union
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    
from voice_diary.logger_utils.logger_utils import setup_logger, ENCODING

# Try to import database utilities
try:
    from voice_diary.db_utils.db_manager import save_transcription as db_save_transcription, initialize_db
    DB_UTILS_AVAILABLE = True
except ImportError:
    DB_UTILS_AVAILABLE = False

# Initialize module directory path - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    MODULE_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    MODULE_DIR = Path(__file__).parent.absolute()

# Configurable fallback paths
DEFAULT_FALLBACK_CONFIG_PATH = "src/voice_diary/project_fallback_config/config_transcribe_raw_audio"
DEFAULT_FALLBACK_CONFIG_FILENAME = "config_transcribe_raw_audio.json"

# Set up logger
logger = setup_logger("transcribe_raw_audio")

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
    fallback_path = DEFAULT_FALLBACK_CONFIG_PATH
    fallback_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
    
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
    "transcriptions_dir": "transcriptions",
    "output_file": "diary_transcription.txt",
    "paths": {
      "downloads_dir": "../download_audio_files/downloaded",
      "output_dir": "transcriptions"
    },
    "downloads_path": {
      "_description": "Configuration for download directory location",
      "downloads_dir": "downloaded"
    },
    "models": {
      "whisper-1": {
        "enabled": "true",
        "description": "Original Whisper model, good general-purpose speech to text",
        "prompt": "Transcribe the given audio into english.",
        "supports_language_parameter": "true"
      },
      "gpt-4o-transcribe": {
        "enabled": "false",
        "description": "Advanced model with better accuracy but higher cost",
        "prompt": "Transcribe the given audio into english.",
        "supports_language_parameter": "false"
      },
      "gpt-4o-mini-transcribe": {
        "enabled": "false",
        "description": "Smaller model with good performance for shorter audio",
        "prompt": "Transcribe the given audio into english.",
        "supports_language_parameter": "false"
      }
    },
    "default_model": "whisper-1",
    "settings": {
      "language": "en",
      "prompt": "Transcribe the given audio into english.",
      "response_format": "json"
    },
    "cost_management": {
      "max_audio_duration_seconds": 300,
      "warn_on_large_files": "true"
    },
    "transcription": {
      "batch_processing": "true",
      "individual_files": "true",
      "batch_output_file": "batch_transcription.txt"
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

def get_openai_client():
    """
    Get the OpenAI client with API key from environment variable.
    
    Returns:
        OpenAI client instance or None if not available
    """
    if not OPENAI_AVAILABLE:
        logger.error("OpenAI Python library is not installed. Install with: pip install openai")
        return None
        
    try:
        # Get the API key from environment variable
        api_key = os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            logger.error("Please set the OPENAI_API_KEY environment variable with your OpenAI API key")
            return None
        
        # Log key validation (first 4 chars only for security)
        if len(api_key) > 4:
            logger.info(f"API key found starting with: {api_key[:4]}***")
        else:
            logger.info("API key found but is too short")
            
        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized")
        return client
        
    except Exception as e:
        logger.error(f"Error creating OpenAI client: {str(e)}")
        traceback.print_exc()
        return None

def calculate_duration(file_path):
    """
    Calculate the duration of an audio file using ffprobe.
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        Duration in seconds or None if not determined
    """
    try:
        # Use ffprobe to get the duration
        result = subprocess.run(
            [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                file_path
            ], 
            capture_output=True, 
            text=True
        )
        
        # Parse the output
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            return duration
        else:
            logger.warning(f"Unable to determine audio duration: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error calculating audio duration: {str(e)}")
        # Fallback: use file size as a very rough estimate (3MB ≈ 1 minute)
        try:
            file_size = os.path.getsize(file_path)
            return (file_size / (3 * 1024 * 1024)) * 60  # Convert to seconds
        except:
            return None

def get_downloads_dir(config):
    """
    Get downloads directory from configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Path to downloads directory
    """
    try:
        # Check first using the structure in download_audio_files config
        downloads_dir = config.get("downloads_path", {}).get("downloads_dir")
        
        # If not found, try the old path structure
        if not downloads_dir:
            downloads_dir = config.get("paths", {}).get("downloads_dir")
        
        if not downloads_dir:
            # Check if we can find it from download_audio_files module
            try:
                download_audio_module_path = MODULE_DIR.parent / "download_audio_files"
                if download_audio_module_path.exists():
                    # Try to load the download_audio_files config directly
                    try:
                        download_config_path = download_audio_module_path / "config" / "config.json"
                        if download_config_path.exists():
                            with open(download_config_path, "r", encoding=ENCODING) as f:
                                download_config = json.load(f)
                                downloads_dir = download_config.get("downloads_path", {}).get("downloads_dir")
                                if downloads_dir:
                                    # Make it relative to the download_audio_files module
                                    downloads_dir = str(download_audio_module_path / downloads_dir)
                                    logger.info(f"Using downloads directory from download_audio_files config: {downloads_dir}")
                    except Exception as e:
                        logger.warning(f"Error loading download_audio_files config: {str(e)}")
                    
                    # If still not found, use the default
                    if not downloads_dir:
                        downloads_dir = str(download_audio_module_path / "downloaded")
                        logger.info(f"Using downloads directory from download_audio_files module path: {downloads_dir}")
                else:
                    # Fallback to default location
                    downloads_dir = str(MODULE_DIR.parent / "downloaded")
                    logger.warning(f"Downloads directory not specified in config, using default: {downloads_dir}")
            except Exception as e:
                logger.warning(f"Error finding download_audio_files module: {str(e)}")
                # Fallback to default location
                downloads_dir = str(MODULE_DIR.parent / "downloaded")
                logger.warning(f"Downloads directory not specified in config, using default: {downloads_dir}")
            
        # Ensure the path exists
        downloads_path = Path(downloads_dir)
        if not downloads_path.exists():
            logger.warning(f"Downloads directory {downloads_dir} not found, creating it")
            downloads_path.mkdir(parents=True, exist_ok=True)
            
        return downloads_dir
    except Exception as e:
        logger.error(f"Error getting downloads directory: {str(e)}")
        # Return a default path
        default_path = str(MODULE_DIR.parent / "downloaded")
        return default_path

def get_transcription_model(config):
    """
    Get the appropriate transcription model based on configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        str: Model name to use for transcription
    """
    # Get available models from config
    models = config.get("models", {})
    default_model = config.get("default_model", "whisper-1")
    
    # Log available models
    logger.info(f"Configured transcription models:")
    for model_name, model_info in models.items():
        status = "enabled" if model_info.get("enabled", False) else "disabled"
        logger.info(f"  - {model_name}: {status} - {model_info.get('description', '')}")
    
    # Find enabled models
    enabled_models = [model_name for model_name, model_info in models.items() 
                     if model_info.get("enabled", False)]
    
    if not enabled_models:
        logger.warning(f"No enabled models found. Using default model: {default_model}")
        return default_model
    
    # If the default model is enabled, use it
    if default_model in enabled_models:
        logger.info(f"Using default model: {default_model}")
        return default_model
    
    # Otherwise use the first enabled model
    selected_model = enabled_models[0]
    logger.info(f"Default model not enabled. Using first enabled model: {selected_model}")
    return selected_model

def transcribe_file(client, file_path, config):
    """
    Transcribe a file using OpenAI's API.
    
    Args:
        client: OpenAI client instance
        file_path: Path to the audio file
        config: Configuration dictionary
        
    Returns:
        str: Transcription text or None if failed
    """
    if not client:
        logger.error("OpenAI client not available. Cannot transcribe file.")
        return None
        
    try:
        logger.info(f"Transcribing {file_path}")
        
        # Calculate estimated duration to log progress
        duration = calculate_duration(file_path)
        if duration:
            logger.info(f"Estimated duration: {duration:.2f} seconds")
            
            # Check file duration against maximum if configured
            max_duration = config.get("cost_management", {}).get("max_audio_duration_seconds")
            if max_duration and duration > max_duration:
                logger.warning(f"File duration ({duration}s) exceeds maximum allowed ({max_duration}s)")
                if config.get("cost_management", {}).get("warn_on_large_files", True):
                    logger.warning(f"Processing the file anyway, but this may result in higher costs")
        
        # Get transcription model and settings
        model = get_transcription_model(config)
        model_info = config.get("models", {}).get(model, {})
        settings = config.get("settings", {})
        language = settings.get("language")
        response_format = settings.get("response_format", "json")
        
        # Get prompt: first try model-specific prompt, then fall back to general settings prompt
        prompt = model_info.get("prompt") if "prompt" in model_info else settings.get("prompt")
        
        # Log the model being used
        logger.info(f"Using transcription model: {model}")
        logger.info(f"Using prompt: {prompt[:50]}..." if prompt and len(prompt) > 50 else f"Using prompt: {prompt}")
        
        start_time = time.time()
        
        # Open the file
        with open(file_path, "rb") as file:
            # Prepare API call parameters
            params = {
                "model": model,
                "file": file
            }
            
            # Add optional parameters if provided
            # Only add language parameter if the model supports it or we don't know
            supports_language = model_info.get("supports_language_parameter", True)
            if language and supports_language:
                params["language"] = language
                logger.info(f"Using language parameter: {language}")
            elif language and not supports_language:
                logger.info(f"Model {model} auto-detects language, not using language parameter")
                
            if prompt:
                params["prompt"] = prompt
                
            if response_format:
                params["response_format"] = response_format
            
            # Call the OpenAI API
            response = client.audio.transcriptions.create(**params)
        
        end_time = time.time()
        transcription_time = end_time - start_time
        
        # Extract the transcription text
        if response_format == "json":
            # Parse the JSON if needed
            if hasattr(response, 'text'):
                transcription = response.text
            else:
                # Newer models might return a different structure
                transcription = json.dumps(response.model_dump(), indent=2)
        else:
            transcription = response.text
        
        if duration:
            logger.info(f"Transcription completed in {transcription_time:.2f} seconds")
            logger.info(f"Transcription speed: {duration/transcription_time:.2f}x real-time")
        
        if transcription:
            logger.info(f"Transcription successful: {len(transcription)} characters")
        else:
            logger.warning("Transcription returned empty result")
            
        return transcription
    except Exception as e:
        logger.error(f"Error transcribing file: {str(e)}")
        traceback.print_exc()
        return None

def get_audio_files(directory):
    """
    Get all files from the specified directory and sort them chronologically.
    
    Args:
        directory: Path to directory containing audio files
        
    Returns:
        list: List of Path objects for audio files sorted chronologically
    """
    directory = Path(directory)
    
    if not directory.exists():
        logger.error(f"Directory {directory} does not exist")
        return []
        
    # Get all files in the directory without filtering by extension
    files = list(directory.glob("*"))
    
    # Filter out directories, only keep files
    files = [f for f in files if f.is_file()]
    
    if not files:
        return []
    
    # Function to extract timestamp from filename if present
    def get_timestamp_from_filename(filepath):
        filename = filepath.name
        # Try to extract timestamp in format YYYYMMDD_HHMMSS from filename
        timestamp_match = re.search(r'(\d{8}_\d{6})', filename)
        if timestamp_match:
            try:
                # If timestamp found in filename, use it
                timestamp_str = timestamp_match.group(1)
                return datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                pass
        
        # Fall back to file creation time if no timestamp in filename
        # or if timestamp couldn't be parsed
        return datetime.datetime.fromtimestamp(os.path.getctime(filepath))
    
    # Sort files by timestamp
    logger.info("Sorting files by creation time (chronological order)")
    sorted_files = sorted(files, key=get_timestamp_from_filename)
    
    # Log the sorted files
    if sorted_files:
        logger.info("Files will be processed in the following order:")
        for i, file in enumerate(sorted_files, 1):
            timestamp = get_timestamp_from_filename(file)
            logger.info(f"{i}. {file.name} (Created: {timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
    
    return sorted_files

def save_transcription(text, output_path, file_name):
    """
    Save the transcription to the output file.
    
    Args:
        text: Transcription text to save
        output_path: Directory path to save the file
        file_name: Name of the output file
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not text:
        logger.warning("No transcription text to save")
        return False
        
    try:
        # Convert the output_path to an absolute path if it's relative
        output_path = Path(output_path)
        if not output_path.is_absolute():
            # If path is relative, make it relative to the module directory
            output_path = MODULE_DIR / output_path
            
        # Create output directory if it doesn't exist
        if not output_path.exists():
            logger.info(f"Creating output directory: {output_path}")
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Use microsecond precision timestamp for unique filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_file = output_path / f"{timestamp}_{file_name}"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(text)
            
        logger.info(f"Transcription saved to {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving transcription: {str(e)}")
        traceback.print_exc()
        return False

def process_files(client, files, output_path, batch_output_path, config):
    """
    Process all files and save their transcriptions.
    
    Args:
        client: OpenAI client instance
        files: List of audio files to process
        output_path: Path to save individual transcriptions
        batch_output_path: Path to save batch transcription
        config: Configuration dictionary
        
    Returns:
        dict: Statistics about processed files
    """
    if not files:
        logger.warning("No files found")
        return {"successful": 0, "failed": 0, "total": 0}
        
    logger.info(f"Found {len(files)} file(s) to process")
    
    all_transcriptions = []
    failed_count = 0
    
    for file_path in files:
        logger.info(f"Processing {file_path}")
        
        # Transcribe the file
        transcription = transcribe_file(client, file_path, config)
        
        if transcription:
            # Save transcription to database if available
            if DB_UTILS_AVAILABLE:
                duration = calculate_duration(file_path)
                try:
                    logger.info(f"Attempting to save transcription to database for {file_path.name}")
                    logger.info(f"Transcription length: {len(transcription)} characters")
                    # Ensure initialize_db is called before saving
                    if initialize_db():
                        db_success = db_save_transcription(
                            content=transcription,
                            filename=file_path.name, 
                            audio_path=str(file_path),
                            duration_seconds=duration,
                            metadata={"transcribed_at": datetime.datetime.now().isoformat()}
                        )
                        if db_success:
                            logger.info(f"Successfully saved transcription to database for {file_path.name}")
                        else:
                            logger.error(f"Failed to save transcription to database for {file_path.name}")
                    else:
                        logger.error("Database initialization failed, cannot save transcription")
                except Exception as e:
                    logger.error(f"Exception while saving transcription to database: {str(e)}")
                    logger.error(traceback.format_exc())
            else:
                logger.warning("Database utilities not available. Transcription not saved to database.")
            
            # Add file name and timestamp to the transcription
            file_name = file_path.name
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_transcription = f"File: {file_name}\nTimestamp: {timestamp}\n\n{transcription}\n\n"
            
            # Save individual transcription file
            individual_saved = save_transcription(
                transcription, 
                output_path, 
                f"individual_{file_name}.txt"
            )
            
            if individual_saved:
                logger.info(f"Individual transcription saved for {file_name}")
            
            all_transcriptions.append(formatted_transcription)
        else:
            failed_count += 1
    
    # Combine all transcriptions and save them
    if all_transcriptions:
        combined_text = "\n".join(all_transcriptions)
        if batch_output_path:
            save_transcription(combined_text, output_path, batch_output_path.name)
        return {"successful": len(all_transcriptions), "failed": failed_count, "total": len(files)}
    
    return {"successful": 0, "failed": failed_count, "total": len(files)}

def ensure_env_file_exists():
    """
    Ensure the .env file exists for database configuration.
    This function looks for a .env file in several locations and copies it to
    the appropriate locations if needed.
    
    Returns:
        bool: True if .env file exists or was created, False otherwise
    """
    try:
        # Look for .env file in the current directory
        local_env_path = MODULE_DIR / '.env'
        
        # If not found, try parent directory
        if not local_env_path.exists():
            local_env_path = MODULE_DIR.parent / '.env'
            
            # If still not found, try one level up
            if not local_env_path.exists():
                local_env_path = MODULE_DIR.parent.parent / '.env'
        
        if local_env_path.exists():
            logger.info(f"Found .env file at {local_env_path}")
            return True
        else:
            # Create a default .env file
            default_env_path = MODULE_DIR / '.env'
            with open(default_env_path, 'w', encoding='utf-8') as f:
                f.write("DATABASE_URL=postgresql://postgres:password@localhost:5432/voice_diary\n")
                f.write("OPENAI_API_KEY=your_openai_api_key\n")
            
            logger.warning(f"Created default .env file at {default_env_path}")
            logger.warning("Please update the default .env file with your actual credentials")
            
            return True
    except Exception as e:
        logger.error(f"Error ensuring .env file exists: {e}")
        return False

def run_transcribe(config=None):
    """
    Run the transcription process.
    
    Args:
        config: Configuration dictionary (optional, will be loaded if not provided)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load config if not provided
        if config is None:
            config = load_config()
            if not config:
                logger.error("No configuration found. Cannot proceed with transcription.")
                return False
                
        # Ensure the .env file exists for database connection
        ensure_env_file_exists()
        
        # Initialize the database if available
        if DB_UTILS_AVAILABLE:
            logger.info("Initializing database connection for transcription")
            db_init_success = initialize_db()
            if db_init_success:
                logger.info("Database initialization successful for transcription")
            else:
                logger.error("Failed to initialize database connection for transcription")
        else:
            logger.warning("Database utilities not available. Transcriptions will not be saved to database.")
        
        # Initialize OpenAI client
        client = get_openai_client()
        if not client:
            logger.error("Failed to initialize OpenAI client. Cannot proceed with transcription.")
            return False
        
        # Get downloads directory from config or defaults
        downloads_dir = get_downloads_dir(config)
        
        # Get output directory from config
        output_dir = config.get("transcriptions_dir", "transcriptions")
        
        logger.info(f"Using downloads directory: {downloads_dir}")
        logger.info(f"Using output directory: {output_dir}")
        
        # Create paths if they don't exist
        downloads_path = Path(downloads_dir)
        output_path = Path(output_dir)
        
        if not downloads_path.exists():
            os.makedirs(downloads_path, exist_ok=True)
            logger.info(f"Created downloads directory: {downloads_path}")
        
        if not output_path.exists():
            os.makedirs(output_path, exist_ok=True)
            logger.info(f"Created output directory: {output_path}")
        
        # Get list of files from downloads directory
        files = get_audio_files(downloads_path)
        
        if not files:
            logger.info("No files found in downloads directory")
            return True

        # Get batch output configuration
        output_file = config.get("output_file", "diary_transcription.txt")
        batch_output_path = output_path / output_file
        
        # Process the files
        results = process_files(client, files, output_path, batch_output_path, config)
        
        # Log results
        total_files = results.get("total", 0)
        successful_files = results.get("successful", 0)
        failed_files = results.get("failed", 0)
        
        logger.info(f"Transcription complete: {successful_files} files successful, {failed_files} files failed out of {total_files} files")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in transcription process: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def main():
    """
    Main function to transcribe audio files.
    This function can be imported and called from other modules.
    """
    # Get fallback config paths from config if available
    fallback_config_path = DEFAULT_FALLBACK_CONFIG_PATH
    fallback_config_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
    
    config = load_config(fallback_config_path, fallback_config_filename)
    if config:
        logger.info("Configuration loaded successfully")
        # Run the transcription process with the loaded config
        success = run_transcribe(config)
        if success:
            logger.info("Transcription process completed successfully")
        else:
            logger.error("Transcription process failed")
    else:
        logger.warning("No configuration found. Creating sample configuration...")
        sample_config_path = MODULE_DIR / "config" / "config.json"  # Hardcoded directory name and filename
        config = create_sample_config(sample_config_path)
        logger.info("Please review and update the configuration as needed.")
        logger.info("Then run the script again to transcribe audio files.")

if __name__ == "__main__":
    main()