#!/usr/bin/env python3
"""
OpenAI Whisper API Transcription

This script transcribes audio files using OpenAI's API:
- whisper-1 API endpoint 

It processes audio files in the downloads directory in chronological order,
supporting both individual files and batch processing based on the configuration.
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from pathlib import Path
import traceback
import subprocess
import logging.handlers
import re
import shutil
from openai import OpenAI
from voice_diary.db_utils.db_manager import save_transcription as db_save_transcription, initialize_db


# Initialize paths - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    SCRIPT_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    SCRIPT_DIR = Path(__file__).parent.absolute()

# Create directories for application data
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Create config directory
CONFIG_DIR = SCRIPT_DIR / "config"
CONFIG_DIR.mkdir(exist_ok=True)

# Define log directory
LOGS_DIR = SCRIPT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Define configuration file paths
TRANSCRIBE_CONFIG_FILE = CONFIG_DIR / "transcribe_for_diary_config.json"
OPENAI_CONFIG_FILE = CONFIG_DIR / "openai_transcribe_config.json"
AUDIO_EXTENSIONS_CONFIG_FILE = CONFIG_DIR / "audio_extensions.json"

# Default configurations
DEFAULT_TRANSCRIBE_CONFIG = {
    "paths": {
        "downloads_dir": str(SCRIPT_DIR.parent / "download_audio_files" / "downloaded"),
        "output_dir": str(DATA_DIR / "transcriptions")
    },
    "transcription": {
        "batch_processing": True,
        "batch_output_file": "batch_transcription.txt",
        "individual_files": True
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(levelname)s - %(message)s",
        "log_file": "transcribe_audio_for_diary.log",
        "max_size_bytes": 1048576,
        "backup_count": 3
    }
}

DEFAULT_OPENAI_CONFIG = {
    "transcription": {
        "model": "whisper-1",
        "language": "en",
        "prompt": "This is a voice diary entry. The speaker is talking about their day, thoughts, or feelings.",
        "temperature": 0.0,
        "response_format": "text"
    }
}

DEFAULT_AUDIO_EXTENSIONS = {
    "audio_file_types": {
        "include": [".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"]
    }
}

# Load config function so we can get logging config
def load_config():
    """Load configuration from transcribe_config.json or create default if not exists."""
    try:
        if not TRANSCRIBE_CONFIG_FILE.exists():
            # Create default config
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(TRANSCRIBE_CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_TRANSCRIBE_CONFIG, f, indent=4)
            print(f"Created default configuration at {TRANSCRIBE_CONFIG_FILE}")
            
        with open(TRANSCRIBE_CONFIG_FILE, 'r') as f:
            config = json.load(f)

        return config
    except Exception as e:
        # Can't use logger here as it's not created yet
        print(f"Error loading configuration: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

# Load OpenAI transcription config
def load_openai_config():
    """Load OpenAI transcription configuration or create default if not exists."""
    try:
        if not OPENAI_CONFIG_FILE.exists():
            # Create default config
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(OPENAI_CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_OPENAI_CONFIG, f, indent=4)
            print(f"Created default OpenAI configuration at {OPENAI_CONFIG_FILE}")
            
        with open(OPENAI_CONFIG_FILE, 'r') as f:
            config = json.load(f)

        return config
    except Exception as e:
        # Can't use logger here as it's not created yet
        print(f"Error loading OpenAI configuration: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

# Load audio extensions config
def load_audio_extensions_config():
    """Load audio extensions configuration or create default if not exists."""
    try:
        if not AUDIO_EXTENSIONS_CONFIG_FILE.exists():
            # Create default config
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(AUDIO_EXTENSIONS_CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_AUDIO_EXTENSIONS, f, indent=4)
            print(f"Created default audio extensions configuration at {AUDIO_EXTENSIONS_CONFIG_FILE}")
            
        with open(AUDIO_EXTENSIONS_CONFIG_FILE, 'r') as f:
            config = json.load(f)

        return config
    except Exception as e:
        print(f"Error loading audio extensions configuration: {str(e)}")
        traceback.print_exc()
        return DEFAULT_AUDIO_EXTENSIONS

# Load configuration
config = load_config()
openai_config = load_openai_config()
audio_extensions_config = load_audio_extensions_config()

# Configure logging
logging_config = config.get("logging", {})
log_level = getattr(logging, logging_config.get("level", "INFO"))
log_format = logging_config.get("format", "%(asctime)s - %(levelname)s - %(message)s")
log_file = logging_config.get("log_file", "transcribe_audio_for_diary.log")
max_size = logging_config.get("max_size_bytes", 1048576)
backup_count = logging_config.get("backup_count", 3)

# Set up logger
logger = logging.getLogger("voice_diary.transcribe")
logger.setLevel(log_level)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(console_handler)

# File handler with rotation
log_path = LOGS_DIR / log_file
file_handler = logging.handlers.RotatingFileHandler(
    log_path, maxBytes=max_size, backupCount=backup_count
)
file_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(file_handler)

# Log initial information
logger.info("Voice Diary Transcription Service")
logger.info(f"Logging to {log_path}")


def get_openai_client():
    """Get the OpenAI client."""
    try:
        # Get the API key from environment variable
        api_key = os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            logger.error("Please set the OPENAI_API_KEY environment variable with your OpenAI API key")
            sys.exit(1)
            
        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized")
        return client
        
    except Exception as e:
        logger.error(f"Error creating OpenAI client: {str(e)}")
        traceback.print_exc()
        sys.exit(1)


def get_audio_extensions():
    """Get audio file extensions from configuration."""
    try:
        # Get audio file extensions
        audio_extensions = audio_extensions_config.get("audio_file_types", {}).get("include", [])
        
        if not audio_extensions:
            logger.warning("No audio file extensions found in config, using defaults")
            audio_extensions = DEFAULT_AUDIO_EXTENSIONS["audio_file_types"]["include"]
            
        return audio_extensions
    except Exception as e:
        logger.error(f"Error getting audio extensions: {str(e)}")
        return DEFAULT_AUDIO_EXTENSIONS["audio_file_types"]["include"]


def get_downloads_dir():
    """Get downloads directory from configuration."""
    try:
        # Get downloads directory from config
        downloads_dir = config.get("paths", {}).get("downloads_dir")
        
        if not downloads_dir:
            # Fallback to default location
            downloads_dir = str(SCRIPT_DIR.parent / "download_audio_files" / "downloaded")
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
        default_path = str(SCRIPT_DIR.parent / "download_audio_files" / "downloaded")
        return default_path


def calculate_duration(file_path):
    """Calculate the duration of an audio file using ffprobe."""
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
        file_size = os.path.getsize(file_path)
        return (file_size / (3 * 1024 * 1024)) * 60  # Convert to seconds


def get_transcription_model():
    """Get the appropriate transcription model based on configuration."""
    # Get available models from config
    models = openai_config.get("models", {})
    default_model = openai_config.get("default_model", "whisper-1")
    
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


def transcribe_audio_file(client, file_path):
    """Transcribe an audio file using OpenAI's API."""
    try:
        logger.info(f"Transcribing {file_path}")
        
        # Calculate estimated duration to log progress
        duration = calculate_duration(file_path)
        if duration:
            logger.info(f"Estimated duration: {duration:.2f} seconds")
            
            # Check file duration against maximum if configured
            max_duration = openai_config.get("cost_management", {}).get("max_audio_duration_seconds")
            if max_duration and duration > max_duration:
                logger.warning(f"Audio file duration ({duration}s) exceeds maximum allowed ({max_duration}s)")
                if openai_config.get("cost_management", {}).get("warn_on_large_files", True):
                    logger.warning(f"Processing the file anyway, but this may result in higher costs")
        
        # Get transcription model and settings
        model = get_transcription_model()
        model_info = openai_config.get("models", {}).get(model, {})
        settings = openai_config.get("settings", {})
        language = settings.get("language")
        response_format = settings.get("response_format", "json")
        
        # Get prompt: first try model-specific prompt, then fall back to general settings prompt
        prompt = model_info.get("prompt") if "prompt" in model_info else settings.get("prompt")
        
        # Log the model being used
        logger.info(f"Using transcription model: {model}")
        logger.info(f"Using prompt: {prompt[:50]}..." if prompt and len(prompt) > 50 else f"Using prompt: {prompt}")
        
        start_time = time.time()
        
        # Open the audio file
        with open(file_path, "rb") as audio_file:
            # Prepare API call parameters
            params = {
                "model": model,
                "file": audio_file
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
        logger.error(f"Error transcribing audio file: {str(e)}")
        traceback.print_exc()
        return None


def get_audio_files(directory):
    """Get all audio files from the specified directory and sort them chronologically."""
    directory = Path(directory)
    
    if not directory.exists():
        logger.error(f"Directory {directory} does not exist")
        return []
        
    # Get audio extensions from Google Drive config
    audio_extensions = get_audio_extensions()
    
    if not audio_extensions:
        logger.error("Could not load audio extensions from config")
        sys.exit(1)
    
    # Get all files with audio extensions
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(directory.glob(f"*{ext}"))
    
    if not audio_files:
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
                return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                pass
        
        # Fall back to file creation time if no timestamp in filename
        # or if timestamp couldn't be parsed
        return datetime.fromtimestamp(os.path.getctime(filepath))
    
    # Sort files by timestamp
    logger.info("Sorting audio files by creation time (chronological order)")
    sorted_files = sorted(audio_files, key=get_timestamp_from_filename)
    
    # Log the sorted files
    if sorted_files:
        logger.info("Files will be processed in the following order:")
        for i, file in enumerate(sorted_files, 1):
            timestamp = get_timestamp_from_filename(file)
            logger.info(f"{i}. {file.name} (Created: {timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
    
    return sorted_files


def save_transcription(text, output_path, file_name):
    """Save the transcription to the output file."""
    if not text:
        logger.warning("No transcription text to save")
        return False
        
    try:
        output_path = Path(output_path)
        
        # Create output directory if it doesn't exist
        if not output_path.exists():
            logger.info(f"Creating output directory: {output_path}")
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Use microsecond precision timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_file = output_path / f"{timestamp}_{file_name}"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(text)
            
        logger.info(f"Transcription saved to {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving transcription: {str(e)}")
        traceback.print_exc()
        return False


def process_audio_files(client, audio_files, output_path, batch_output_path):
    """Process all audio files and save their transcriptions."""
    if not audio_files:
        logger.warning("No audio files found")
        return False
        
    logger.info(f"Found {len(audio_files)} audio file(s) to process")
    
    all_transcriptions = []
    
    for file_path in audio_files:
        logger.info(f"Processing {file_path}")
        
        # Transcribe the audio file
        transcription = transcribe_audio_file(client, file_path)
        
        if transcription:
            # Save transcription to database
            duration = calculate_duration(file_path)
            try:
                db_success = db_save_transcription(
                    content=transcription,
                    filename=file_path.name, 
                    audio_path=str(file_path),
                    duration_seconds=duration,
                    metadata={"transcribed_at": datetime.now().isoformat()}
                )
                if db_success:
                    logger.info(f"Successfully saved transcription to database for {file_path.name}")
                else:
                    logger.error(f"Failed to save transcription to database for {file_path.name}")
            except Exception as e:
                logger.error(f"Exception while saving transcription to database: {str(e)}")
                logger.error(traceback.format_exc())
            
            # Add file name and timestamp to the transcription
            file_name = file_path.name
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_transcription = f"File: {file_name}\nTimestamp: {timestamp}\n\n{transcription}\n\n"
            
            all_transcriptions.append(formatted_transcription)
    
    # Combine all transcriptions and save them
    if all_transcriptions:
        combined_text = "\n".join(all_transcriptions)
        if batch_output_path:
            save_transcription(combined_text, output_path, batch_output_path.name)
        return {"successful": len(all_transcriptions), "failed": 0}
    
    return {"successful": 0, "failed": 0}


def ensure_env_file_exists():
    """
    Ensure the .env file exists for database configuration.
    This function looks for a .env file in several locations and copies it to
    the appropriate locations if needed.
    """
    try:
        # Look for .env file in the current directory
        local_env_path = SCRIPT_DIR / '.env'
        
        # If not found, try parent directory
        if not local_env_path.exists():
            local_env_path = SCRIPT_DIR.parent / '.env'
            
            # If still not found, try one level up
            if not local_env_path.exists():
                local_env_path = SCRIPT_DIR.parent.parent / '.env'
        
        if local_env_path.exists():
            logger.info(f"Found .env file at {local_env_path}")
            
            # Try to copy to package resources if possible
            try:
                import importlib.resources
                pkg_path = importlib.resources.files('voice_diary')
                pkg_env_path = pkg_path / '.env'
                
                if not pkg_env_path.exists() or (local_env_path.read_text() != pkg_env_path.read_text()):
                    shutil.copy2(local_env_path, pkg_env_path)
                    logger.info(f"Copied .env file to package resource location: {pkg_env_path}")
            except Exception as e:
                logger.warning(f"Could not copy .env file to package resources: {e}")
                
            return True
        else:
            # Create a default .env file
            default_env_path = SCRIPT_DIR / '.env'
            with open(default_env_path, 'w', encoding='utf-8') as f:
                f.write("DATABASE_URL=postgresql://postgres:password@localhost:5432/voice_diary\n")
                f.write("OPENAI_API_KEY=your_openai_api_key\n")
            
            logger.warning(f"Created default .env file at {default_env_path}")
            logger.warning("Please update the default .env file with your actual credentials")
            
            return True
    except Exception as e:
        logger.error(f"Error ensuring .env file exists: {e}")
        return False


def run_transcribe():
    """Run the transcription process."""
    try:
        # Ensure the .env file exists
        ensure_env_file_exists()
        
        # Initialize the database
        logger.info("Initializing database connection for transcription")
        db_init_success = initialize_db()
        if db_init_success:
            logger.info("Database initialization successful for transcription")
        else:
            logger.error("Failed to initialize database connection for transcription")
        
        # Get audio extensions from config
        audio_extensions = get_audio_extensions()
        
        if not audio_extensions:
            logger.error("Could not load audio extensions from config")
            audio_extensions = [".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"]
            logger.info(f"Using default audio extensions: {audio_extensions}")
        
        # Initialize OpenAI client
        client = get_openai_client()
        
        # Get downloads and output paths
        # Try to get downloads directory from config first
        downloads_dir = get_downloads_dir()
        
        if not downloads_dir:
            logger.error("Could not determine downloads directory")
            return False
        
        # Get output directory from config
        output_dir = config.get("paths", {}).get("output_dir")
        if not output_dir:
            # Create default output directory in data folder
            output_dir = str(DATA_DIR / "transcriptions")
            logger.info(f"Output directory not specified in config, using default: {output_dir}")
        
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
        
        # Get list of audio files from downloads directory
        audio_files = get_audio_files(downloads_path)
        
        if not audio_files:
            logger.info("No audio files found in downloads directory")
            return True

        # Process audio files
        batch_processing = config.get("transcription", {}).get("batch_processing", True)
        individual_files = config.get("transcription", {}).get("individual_files", True)
        batch_output_file = config.get("transcription", {}).get("batch_output_file", "batch_transcription.txt")
        
        # If batch processing is enabled, create a batch transcription file
        if batch_processing:
            batch_output_path = output_path / batch_output_file
            logger.info(f"Batch processing enabled, will save to: {batch_output_path}")
        else:
            batch_output_path = None
            logger.info("Batch processing disabled")
        
        # Process the audio files
        results = process_audio_files(client, audio_files, output_path, batch_output_path)
        
        # Log results
        total_files = len(audio_files)
        successful_files = results.get("successful", 0)
        failed_files = results.get("failed", 0)
        
        logger.info(f"Transcription complete: {successful_files} files successful, {failed_files} files failed out of {total_files} files")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in transcription process: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def main():
    """Entry point for the script when run directly."""
    run_transcribe()


if __name__ == "__main__":
    main()




