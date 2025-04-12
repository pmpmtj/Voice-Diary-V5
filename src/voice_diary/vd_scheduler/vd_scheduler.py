import logging
import json
import os
import sys
import time
import traceback
import threading
from datetime import datetime, timedelta
import shutil
from pathlib import Path

# Import voice diary components
try:
    from voice_diary.download_audio_files.download_audio_files import main as download_files_main
    from voice_diary.transcribe_raw_audio.transcribe_raw_audio import run_transcribe
    from voice_diary.agent_summarize_day.agent_summarize_day import summarize_day
    from voice_diary.send_email.send_email import main as send_email_main
    from voice_diary.db_utils.db_manager import get_latest_day_summaries, initialize_db
    from voice_diary.logger_utils.logger_utils import setup_logger
except ImportError as e:
    print(f"Error importing voice diary components: {e}")
    print("Please ensure all voice diary modules are installed correctly.")
    sys.exit(1)

# Initialize paths - handling both frozen (PyInstaller) and regular Python execution
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    SCRIPT_DIR = Path(sys._MEIPASS) / "voice_diary" / "vd_scheduler"
else:
    # Running as script
    SCRIPT_DIR = Path(__file__).parent.absolute()

# Define MODULE_DIR for consistency with other modules
MODULE_DIR = SCRIPT_DIR

# Create logs directory explicitly in the vd_scheduler module directory
LOGS_DIR = SCRIPT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Set up logger using the centralized logger utility with explicit log directory
# This ensures logs go to the vd_scheduler directory, not logger_utils
logger = setup_logger("vd_scheduler", log_dir=LOGS_DIR)

# === Constants ===
STATE_FILE = SCRIPT_DIR / 'pipeline_state.json'
CONFIG_FILE = SCRIPT_DIR / 'config' / 'config.json'

# === Config Handling ===
def create_sample_config(config_path):
    """
    Create a sample configuration file with default values.
    
    Args:
        config_path: Path where to save the sample config
        
    Returns:
        dict: Dictionary containing default configuration values
    """
    # Generate a default config template
    default_config = {
        "version": "1.0.0",
        "scheduler": {
            "runs_per_day": 12,
            "daily_task_hour": 23,
            "daily_task_minute": 55,
            "description": "Configuration for Voice Diary scheduler"
        },
        "logging": {
            "log_level": "INFO",
            "log_rotation_days": 7,
            "log_to_console": True
        },
        "pipeline": {
            "enable_notifications": False,
            "retry_on_failure": True,
            "max_retries": 3
        },
        "paths": {
            "output_directory": "output",
            "archive_directory": "archive"
        }
    }
    
    # Ensure the directory exists
    config_dir = Path(config_path).parent
    if not config_dir.exists():
        os.makedirs(config_dir, exist_ok=True)
        logger.info(f"Created config directory at: {config_dir}")
    
    # Write the configuration to the file
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, indent=2)
    
    logger.info(f"Created sample config file at: {config_path}")
    return default_config

def load_config():
    """Load configuration from the config file, with fallback to project-wide defaults"""
    # Check primary config location
    if not CONFIG_FILE.exists():
        # Try fallback location
        fallback_config_dir = Path(__file__).parent.parent / "project_fallback_config" / "config_vd_scheduler"
        fallback_config_file = fallback_config_dir / "vd_scheduler_config.json"
        
        if fallback_config_file.exists():
            logger.info(f"Using fallback config file: {fallback_config_file}")
            try:
                with open(fallback_config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if "scheduler" not in config:
                    raise ValueError("Missing 'scheduler' section in config.json")
                return config
            except Exception as e:
                logger.error(f"Failed to load fallback configuration: {e}")
                sys.exit(1)
        else:
            logger.info(f"No config file found. Creating a sample configuration at: {CONFIG_FILE}")
            return create_sample_config(CONFIG_FILE)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if "scheduler" not in config:
            raise ValueError("Missing 'scheduler' section in config.json")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

def validate_config(config):
    """Validate the configuration has required fields with correct types"""
    scheduler = config.get("scheduler", {})
    
    # Validate runs_per_day
    if "runs_per_day" not in scheduler:
        raise ValueError("Missing 'runs_per_day' in scheduler section")
    if not isinstance(scheduler["runs_per_day"], (int, float)):
        raise ValueError("runs_per_day must be a number")
    
    # Validate daily task time settings if present
    if "daily_task_hour" in scheduler and not isinstance(scheduler["daily_task_hour"], int):
        raise ValueError("daily_task_hour must be an integer")
    if "daily_task_minute" in scheduler and not isinstance(scheduler["daily_task_minute"], int):
        raise ValueError("daily_task_minute must be an integer")
    
    # Validate logging settings if present
    logging_config = config.get("logging", {})
    if "log_level" in logging_config and not isinstance(logging_config["log_level"], str):
        raise ValueError("log_level must be a string")
    
    # Validate pipeline settings if present
    pipeline_config = config.get("pipeline", {})
    if "max_retries" in pipeline_config and not isinstance(pipeline_config["max_retries"], int):
        raise ValueError("max_retries must be an integer")
    
    # Validate path settings if present
    paths_config = config.get("paths", {})
    if "output_directory" in paths_config and not isinstance(paths_config["output_directory"], str):
        raise ValueError("output_directory must be a string")
    if "archive_directory" in paths_config and not isinstance(paths_config["archive_directory"], str):
        raise ValueError("archive_directory must be a string")
        
    logger.info("Configuration validation successful")

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
        download_files_main()
        logger.info("Completed file download from Google Drive")
        
        # Step 2: Transcribe downloaded audio files
        logger.info("Starting transcription of audio files")
        run_transcribe()
        logger.info("Completed transcription of audio files")
        
        # No need for Step 3 (moving files) as it's handled internally by the modules now
        
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
        # Step 1: Generate summary
        logger.info("Starting daily summary generation")
        summary_success = summarize_day()
        
        if summary_success:
            logger.info("Successfully generated daily summary")
            
            # Get the summary content - first try the database
            summary_content = None
            
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
                    # Try to find the summary file from the agent_summarize_day module
                    from importlib import import_module
                    try:
                        summary_module = import_module('voice_diary.agent_summarize_day.agent_summarize_day')
                        if hasattr(summary_module, 'CONFIG_PATH'):
                            summary_config_path = summary_module.CONFIG_PATH
                        else:
                            # Fallback to a common location
                            summary_config_path = Path(__file__).parent.parent / "project_fallback_config" / "config_agent_summarize_day" / "agent_summarize_day_config.json"
                    except ImportError:
                        # Fallback to a common location
                        summary_config_path = Path(__file__).parent.parent / "project_fallback_config" / "config_agent_summarize_day" / "agent_summarize_day_config.json"
                    
                    if not os.path.exists(summary_config_path):
                        logger.error(f"Summary config file not found at: {summary_config_path}")
                        raise FileNotFoundError(f"Summary config file not found at: {summary_config_path}")
                    
                    with open(summary_config_path, 'r', encoding='utf-8') as f:
                        summary_config = json.load(f)
                    
                    # Get the summary file path from the config - this is actually a file path, not a directory
                    summary_file_path = summary_config.get("paths", {}).get("summarized_file")
                    
                    if summary_file_path and os.path.exists(summary_file_path):
                        # This is a file path, not a directory - read directly from it
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
                    # Load the email config
                    email_config_path = MODULE_DIR.parent / "send_email" / "config" / "conf_send_email.json"
                    if not email_config_path.exists():
                        # Try fallback location
                        email_config_path = MODULE_DIR.parent / "project_fallback_config" / "config_send_email" / "conf_send_email.json"
                    
                    if not email_config_path.exists():
                        logger.error(f"Email config file not found at: {email_config_path}")
                        raise FileNotFoundError(f"Email config file not found at: {email_config_path}")
                    
                    with open(email_config_path, 'r', encoding='utf-8') as f:
                        email_config = json.load(f)
                    
                    # Update the email message with the summary content
                    if 'email' in email_config:
                        today = datetime.now().strftime("%Y-%m-%d")
                        email_config['email']['message'] = f"Voice Diary Summary for {today}:\n\n{summary_content}"
                        
                        # Save the updated config
                        with open(email_config_path, 'w', encoding='utf-8') as f:
                            json.dump(email_config, f, indent=2)
                        
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
def get_seconds_until_target_time(hour, minute):
    now = datetime.now()
    target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If it's already past the target time, schedule for tomorrow
    if now >= target_today:
        target_today = target_today + timedelta(days=1)
        
    return (target_today - now).total_seconds()

def end_of_day_scheduler(config):
    # Get daily task time from config or default to 23:55
    hour = config.get("scheduler", {}).get("daily_task_hour", 23)
    minute = config.get("scheduler", {}).get("daily_task_minute", 55)
    
    # Add debug logging to verify the configured time
    logger.info(f"End-of-day scheduler initialized with configured time: {hour:02d}:{minute:02d}")
    
    while True:
        sleep_time = get_seconds_until_target_time(hour, minute)
        logger.info(f"Next end-of-day task scheduled in {sleep_time:.0f} seconds (at {hour:02d}:{minute:02d}).")
        
        # Debug logging before sleep
        now = datetime.now()
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target_time:
            target_time = target_time + timedelta(days=1)
        logger.info(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}, Target time: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        time.sleep(sleep_time)
        
        logger.info("Starting end-of-day task")
        success = run_end_of_day_task()
        
        if success:
            logger.info("End-of-day task completed successfully")
        else:
            logger.error("End-of-day task failed")

# === Ensure Environment File Exists ===
def ensure_env_file_exists():
    """
    Ensure the .env file exists in both the source directory and the installed package location.
    This helps ensure the database configuration is properly loaded.
    """
    try:
        # Get the source .env file path
        src_env_path = Path(__file__).parent.parent / '.env'
        
        if src_env_path.exists():
            # Get the installed package location
            try:
                import importlib.resources
                pkg_path = importlib.resources.files('voice_diary')
                pkg_env_path = pkg_path / '.env'
                
                # Copy the .env file to the package location if it exists
                if not pkg_env_path.exists() or (src_env_path.read_text() != pkg_env_path.read_text()):
                    logger.info(f"Copying .env file from {src_env_path} to {pkg_env_path}")
                    shutil.copy2(src_env_path, pkg_env_path)
                    return True
                return True
            except Exception as e:
                logger.error(f"Error accessing package resources: {e}")
                return False
        else:
            logger.warning(f".env file not found at {src_env_path}")
            return False
    except Exception as e:
        logger.error(f"Error ensuring .env file exists: {e}")
        return False

# Helper function to handle exceptions in threads
def try_with_logging(func, args=(), kwargs=None, error_message="Thread error"):
    """Execute a function with exception handling and logging"""
    if kwargs is None:
        kwargs = {}
    try:
        func(*args, **kwargs)
    except Exception as e:
        logger.error(f"{error_message}: {e}")
        logger.error(traceback.format_exc())

# === Main Scheduler ===
def main():
    try:
        logger.info("Starting VD Scheduler")
        
        # Ensure the .env file exists for database configuration
        ensure_env_file_exists()
        
        # Load and validate configuration
        config = load_config()
        validate_config(config)
        
        interval = calculate_interval_seconds(config["scheduler"]["runs_per_day"])

        # Start end-of-day scheduler in parallel thread
        # Using a daemon thread with higher priority and explicitly handling exceptions
        end_of_day_thread = threading.Thread(
            target=lambda: 
                try_with_logging(
                    end_of_day_scheduler,
                    args=(config,),
                    error_message="End-of-day scheduler thread encountered an error"
                ),
            daemon=True,
            name="EndOfDayScheduler"
        )
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
                run_pipeline()
                next_run = calculate_next_run_time(interval)
                logger.info(f"Next main pipeline run at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
    finally:
        input("Press Enter to exit...")

if __name__ == "__main__":
    # Check for command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--create-config":
        # Just create the config file and exit
        config_path = CONFIG_FILE
        if len(sys.argv) > 2:
            config_path = Path(sys.argv[2])
        
        create_sample_config(config_path)
        print(f"Sample configuration created at: {config_path}")
        sys.exit(0)
    
    main()
