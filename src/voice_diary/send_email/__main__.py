#!/usr/bin/env python3
"""
Entry point for running the send_email module with python -m voice_diary.send_email.

This allows the module to be executed directly via:
python -m voice_diary.send_email [options]
"""

import sys
from pathlib import Path
from voice_diary.send_email.send_email import main, create_sample_config, SCRIPT_DIR

def run_module():
    """Execute the module functionality based on command-line arguments."""
    # Check for help option
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("Gmail API Email Sender for Voice Diary")
        print("\nUsage:")
        print("  python -m voice_diary.send_email [options]")
        print("\nOptions:")
        print("  --help, -h              Show this help message")
        print("  --create-config [path]  Create a sample configuration file at the specified path")
        print("                          If no path is provided, creates config at the default location")
        return 0
    
    # Check if user wants to create a sample config
    if len(sys.argv) > 1 and sys.argv[1] == "--create-config":
        config_path = None
        if len(sys.argv) > 2:
            config_path = Path(sys.argv[2])
        else:
            # Use default location
            config_path = SCRIPT_DIR / "config" / "conf_send_email.json"
        
        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
            
        print(f"Creating sample configuration file at: {config_path}")
        create_sample_config(config_path)
        print("Configuration file created successfully!")
        return 0
    
    # Run the main functionality
    if main():
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(run_module()) 