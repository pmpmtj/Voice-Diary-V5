import logging
import logging.handlers
import json
import os
import sys
import time
import traceback
import threading
from datetime import datetime, timedelta
from pathlib import Path
import shutil

# Import voice diary components
from voice_diary.download_audio_files.download_audio_files import main as download_audio_files_main
from voice_diary.transcribe_raw_audio.transcribe_raw_audio import run_transcribe
from voice_diary.agent_summarize_day.agent_summarize_day import summarize_day
from voice_diary.send_email.send_email import main as send_email_main
from voice_diary.file_utils.mv_files import process_files, load_config as load_mv_files_config, setup_logging as setup_mv_files_logging
from voice_diary.db_utils.db_manager import get_latest_day_summaries, initialize_db

# === Constants ===
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

DOWNLOADS_DIR = DATA_DIR / "downloaded"
DOWNLOADS_DIR.mkdir(exist_ok=True)

PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(exist_ok=True)

TRANSCRIPTIONS_DIR = DATA_DIR / "transcriptions"
TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

SUMMARIES_DIR = DATA_DIR / "summaries"
SUMMARIES_DIR.mkdir(exist_ok=True)

# Create a default config directory if it doesn't exist
CONFIG_DIR = SCRIPT_DIR / "config"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "app_scheduler_config.json"
STATE_FILE = SCRIPT_DIR / 'pipeline_state.json'
LOG_DIR = SCRIPT_DIR / 'log'

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Initialize logger
logger = logging.getLogger(__name__)

# === Config Handling ===
def load_config():
    # First try to load from the script directory's config folder
    if CONFIG_FILE.exists():
        logger.info(f"Using configuration file at: {CONFIG_FILE}")
    else:
        # Create a default configuration
        logger.info(f"Configuration file not found, creating default at: {CONFIG_FILE}")
        create_default_config(CONFIG_FILE)
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if "scheduler" not in config:
            raise ValueError("Missing 'scheduler' section in config.json")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

def create_default_config(config_path):
    """Create a default configuration file if none exists"""
    default_config = {
        "scheduler": {
            "runs_per_day": 4,
            "daily_task_hour": 23,
            "daily_task_minute": 55
        }
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to create default configuration: {e}")
        return False

def validate_config(config):
    scheduler = config.get("scheduler", {})
    if "runs_per_day" not in scheduler:
        raise ValueError("Missing 'runs_per_day' in scheduler section")
    if not isinstance(scheduler["runs_per_day"], (int, float)):
        raise ValueError("runs_per_day must be a number")

# === Interval Calculation ===
def calculate_interval_seconds(runs_per_day):
    return 0 if runs_per_day == 0 else int(86400 / runs_per_day)

def calculate_next_run_time(interval_seconds):
    now = datetime.now()
    return now + timedelta(seconds=interval_seconds)

# === State Saving ===
def update_pipeline_state(state_file, updates):
    try:
        with open(state_file, 'w') as f:
            json.dump(updates, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to update state file: {e}")
        raise

# === Main Pipeline Implementation ===
def run_pipeline():
    """
    Run the main Voice Diary pipeline:
    1. Download audio files from Google Drive
    2. Transcribe the downloaded audio files
    3. Move files to appropriate directories to prevent duplication
    """
    state = {"last_run_time": datetime.now().isoformat()}
    
    try:
        # Initialize database before pipeline execution
        logger.info("Initializing database connection")
        db_init_success = initialize_db()
        if not db_init_success:
            logger.error("Failed to initialize database connection")
        else:
            logger.info("Database initialization successful")
        
        # Step 1: Download files from Google Drive
        logger.info("Starting file download from Google Drive")
        download_audio_files_main()
        logger.info("Completed file download from Google Drive")
        
        # Step 2: Transcribe downloaded audio files
        logger.info("Starting transcription of audio files")
        run_transcribe()
        logger.info("Completed transcription of audio files")
        
        # Step 3: Move the downloaded files to appropriate directories
        # to prevent duplicate processing in future runs
        logger.info("Starting file organization to prevent duplication")
        try:
            # Create a local mv_files configuration path
            mv_files_config_path = SCRIPT_DIR / "config" / "file_utils_config.json"
            if not mv_files_config_path.exists():
                # Create directory if needed
                mv_files_config_path.parent.mkdir(exist_ok=True)
                # Create a default configuration
                default_mv_files_config = {
                    "paths": {
                        "source_dir": str(DOWNLOADS_DIR),
                        "target_dir": str(PROCESSED_DIR)
                    },
                    "logging": {
                        "log_file": "file_utils.log",
                        "log_level": "INFO"
                    }
                }
                with open(mv_files_config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_mv_files_config, f, indent=4)
            
            # Load mv_files configuration and set up its logger
            mv_files_config = load_mv_files_config(mv_files_config_path)
            mv_files_logger = setup_mv_files_logging(mv_files_config)
            
            # Process and move the files
            files_processed, files_failed = process_files(mv_files_config, mv_files_logger)
            logger.info(f"File organization completed: {files_processed} files processed, {files_failed} files failed")
        except Exception as e:
            logger.error(f"Error organizing files: {str(e)}")
            logger.error(traceback.format_exc())
        
        state["last_run_status"] = "success"
        logger.info("Pipeline execution completed successfully")
    except Exception as e:
        state["last_run_status"] = "failed"
        state["error"] = str(e)
        logger.error(f"Pipeline execution failed: {e}")
        logger.error(traceback.format_exc())
    
    # Update state file
    update_pipeline_state(STATE_FILE, state)
    return state["last_run_status"] == "success"

# === End of Day Task ===
def run_end_of_day_task():
    """
    Run the end-of-day tasks:
    1. Generate daily summary
    2. Send email with summary
    """
    try:
        # Ensure the .env file exists before initializing the database
        ensure_env_file_exists()
        
        # Step 1: Generate summary
        logger.info("Starting daily summary generation")
        summary_success = summarize_day()
        
        if summary_success:
            logger.info("Successfully generated daily summary")
            
            summary_content = None
            
            # First try to get the summary from the database
            try:
                logger.info("Attempting to get summary from database")
                initialize_db()
                summaries = get_latest_day_summaries(limit=1)
                
                if summaries and len(summaries) > 0:
                    latest_summary = summaries[0]
                    summary_content = latest_summary.get('content', '')
                    logger.info(f"Found latest summary in database from {latest_summary.get('summary_date')}")
            except Exception as e:
                logger.error(f"Error retrieving summary from database: {e}")
                logger.error(traceback.format_exc())
            
            # If database retrieval failed, try to read from file
            if not summary_content:
                logger.info("No summary found in database, trying to read from file")
                try:
                    # Create local agent_summarize_day config if it doesn't exist
                    summary_config_path = SCRIPT_DIR / "config" / "agent_summarize_day_config.json"
                    if not summary_config_path.exists():
                        # Create default config
                        default_summary_config = {
                            "paths": {
                                "transcriptions_dir": str(TRANSCRIPTIONS_DIR),
                                "summarized_file": str(SUMMARIES_DIR / "daily_summary.txt")
                            },
                            "openai": {
                                "api_key_env_var": "OPENAI_API_KEY",
                                "model": "gpt-3.5-turbo"
                            }
                        }
                        # Create directory if needed
                        summary_config_path.parent.mkdir(exist_ok=True)
                        with open(summary_config_path, 'w', encoding='utf-8') as f:
                            json.dump(default_summary_config, f, indent=4)
                    
                    with open(summary_config_path, 'r', encoding='utf-8') as f:
                        summary_config = json.load(f)
                    
                    # Get the summary file path from the config
                    summary_file_path = summary_config.get("paths", {}).get("summarized_file")
                    
                    if summary_file_path and os.path.exists(summary_file_path):
                        # Read directly from the file
                        logger.info(f"Reading summary from file: {summary_file_path}")
                        with open(summary_file_path, 'r', encoding='utf-8') as f:
                            summary_content = f.read()
                        logger.info(f"Successfully read summary content from file ({len(summary_content)} characters)")
                    else:
                        logger.warning(f"Summary file not found at path: {summary_file_path}")
                except Exception as e:
                    logger.error(f"Error reading summary from file: {e}")
                    logger.error(traceback.format_exc())
            
            # If we have summary content, update the email config
            if summary_content:
                try:
                    # Create or load the email config
                    email_config_path = SCRIPT_DIR / "config" / "email_config.json"
                    if not email_config_path.exists():
                        # Create default email config
                        default_email_config = {
                            "email": {
                                "sender": "your-email@example.com",
                                "recipient": "your-email@example.com",
                                "subject": "Voice Diary Daily Summary",
                                "message": "Your daily voice diary summary will appear here.",
                                "smtp": {
                                    "server": "smtp.example.com",
                                    "port": 587,
                                    "use_tls": True,
                                    "username": "your-email@example.com",
                                    "password_env_var": "EMAIL_PASSWORD"
                                }
                            }
                        }
                        # Create directory if needed
                        email_config_path.parent.mkdir(exist_ok=True)
                        with open(email_config_path, 'w', encoding='utf-8') as f:
                            json.dump(default_email_config, f, indent=4)

                    # Load the email config
                    with open(email_config_path, 'r', encoding='utf-8') as f:
                        email_config = json.load(f)
                    
                    # Update the email message with the summary content
                    if 'email' in email_config:
                        today = datetime.now().strftime("%Y-%m-%d")
                        email_config['email']['message'] = f"Voice Diary Summary for {today}:\n\n{summary_content}"
                        
                        # Save the updated config
                        with open(email_config_path, 'w', encoding='utf-8') as f:
                            json.dump(email_config, f, indent=4)
                        
                        logger.info(f"Updated email message with summary content ({len(summary_content)} characters)")
                    else:
                        logger.warning("Email configuration doesn't contain 'email' section")
                except Exception as e:
                    logger.error(f"Error updating email config: {e}")
                    logger.error(traceback.format_exc())
                
                # Step 2: Send email
                logger.info("Starting email sending process")
                send_email_main()
                logger.info("Completed email sending process")
            else:
                logger.warning("No summary content found, skipping email")
        else:
            logger.warning("Daily summary generation did not produce results, skipping email")
            
        return True
    except Exception as e:
        logger.error(f"End of day task failed: {e}")
        logger.error(traceback.format_exc())
        return False

# === End of Day Scheduler ===
def calculate_seconds_until_daily_task():
    """Calculate seconds until the configured daily task time."""
    now = datetime.now()
    
    # Get time from config, or use fallback values if not found
    config = load_config()
    scheduler_config = config.get("scheduler", {})
    hour = scheduler_config.get("daily_task_hour", 23)
    minute = scheduler_config.get("daily_task_minute", 55)
    
    target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If it's already past the target time, schedule for tomorrow
    if now >= target_today:
        target_today = target_today + timedelta(days=1)
        
    seconds_until_target = (target_today - now).total_seconds()
    return seconds_until_target

def end_of_day_scheduler():
    """
    Runs the end-of-day task at the scheduled time each day.
    This function runs in an infinite loop in a separate thread.
    It calculates the time until the next scheduled run, sleeps until then,
    and executes the daily summary and email tasks.
    """
    while True:
        sleep_time = calculate_seconds_until_daily_task()
        next_run_time = datetime.now() + timedelta(seconds=sleep_time)
        logger.info(f"Next end-of-day task scheduled in {sleep_time:.0f} seconds (at {next_run_time.strftime('%Y-%m-%d %H:%M:%S')})")
        
        time.sleep(sleep_time)
        logger.info("Starting end-of-day task")
        success = run_end_of_day_task()
        
        if success:
            logger.info("End-of-day task completed successfully")
        else:
            logger.error("End-of-day task failed")

# === Setup Logging ===
def setup_logging():
    log_file = LOG_DIR / 'app_scheduler.log'
    
    # Create handlers
    console_handler = logging.StreamHandler()
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=1024*1024,  # 1MB
        backupCount=5
    )
    
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # Set logger level
    logger.setLevel(logging.INFO)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f"Logging to: {log_file}")

# === Main Scheduler ===
def main():
    # Setup logging
    setup_logging()
    logger.info("Voice Diary Scheduler starting up")

    try:
        # Log the configuration path being used
        logger.info(f"Using configuration file at: {CONFIG_FILE}")
        
        # Load and validate configuration
        config = load_config()
        validate_config(config)
        interval = calculate_interval_seconds(config["scheduler"]["runs_per_day"])
        
        # Log configuration
        runs_per_day = config["scheduler"]["runs_per_day"]
        logger.info(f"Configuration loaded: {runs_per_day} runs per day (every {interval//60} minutes)")

        # Start end-of-day scheduler in parallel thread
        end_of_day_thread = threading.Thread(target=end_of_day_scheduler, daemon=True)
        end_of_day_thread.start()
        
        # Log with the actual configured time
        hour = config["scheduler"].get("daily_task_hour", 23)
        minute = config["scheduler"].get("daily_task_minute", 55)
        logger.info(f"Started end-of-day scheduler thread (runs at {hour:02d}:{minute:02d} daily)")

        if interval == 0:
            # Run once mode
            logger.info("Main pipeline: Running once and exiting")
            run_pipeline()
        else:
            # Main loop for recurring execution
            logger.info("Main pipeline: Running in continuous mode")
            while True:
                logger.info("Starting main pipeline execution")
                run_pipeline()
                next_run = calculate_next_run_time(interval)
                logger.info(f"Next main pipeline run at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())

def ensure_env_file_exists():
    """
    Ensure the .env file exists in both the source directory and the installed package location.
    This helps ensure the database configuration is properly loaded.
    """
    try:
        # Look for .env file in the voice_diary module directory
        src_env_path = SCRIPT_DIR / '.env'
        
        # If not found, try parent directory
        if not src_env_path.exists():
            src_env_path = SCRIPT_DIR.parent / '.env'
            
            # If still not found, try one level up
            if not src_env_path.exists():
                src_env_path = SCRIPT_DIR.parent.parent / '.env'
        
        if src_env_path.exists():
            # Get the installed package location
            import importlib.resources
            pkg_path = importlib.resources.files('voice_diary')
            pkg_env_path = pkg_path / '.env'
            
            # Copy the .env file to the package location if it exists
            if not pkg_env_path.exists() or (src_env_path.read_text() != pkg_env_path.read_text()):
                logger.info(f"Copying .env file from {src_env_path} to {pkg_env_path}")
                shutil.copy2(src_env_path, pkg_env_path)
                return True
            return True
        else:
            # Create a local .env file with default values
            env_file = SCRIPT_DIR / '.env'
            if not env_file.exists():
                with open(env_file, 'w', encoding='utf-8') as f:
                    f.write("DATABASE_URL=postgresql://postgres:password@localhost:5432/voice_diary\n")
                    f.write("OPENAI_API_KEY=your_openai_api_key\n")
                logger.info(f"Created default .env file at {env_file}")
            
            logger.warning(f"No source .env file found, using local default")
            return True
    except Exception as e:
        logger.error(f"Error ensuring .env file exists: {e}")
        return False

if __name__ == "__main__":
    main()
