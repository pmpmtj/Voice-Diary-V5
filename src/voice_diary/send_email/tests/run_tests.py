#!/usr/bin/env python3
"""
Test Runner for Voice Diary Email Service

This script runs the unit tests for the Voice Diary Email Service,
generating coverage reports in both console and HTML formats.
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

def load_config():
    """Load test configuration from JSON file."""
    config_path = Path(__file__).parent / "test_config.json"
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Config file {config_path} not found. Using default configuration.")
        return {
            "test_paths": {
                "unit_tests_dir": "unit",
                "coverage": {
                    "module_path": "voice_diary.send_email"
                },
                "test_data": {
                    "dir": "test_data",
                    "credentials_dir": "credentials",
                    "logs_dir": "logs"
                }
            }
        }

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run Voice Diary Email Service tests")
    parser.add_argument("--coverage", action="store_true", 
                       help="Generate coverage report")
    parser.add_argument("--html", action="store_true", 
                       help="Generate HTML coverage report")
    parser.add_argument("--skip-tests", action="store_true", 
                       help="Skip running tests (useful with --coverage and existing .coverage file)")
    parser.add_argument("--module", type=str, default="send_email",
                       help="Specific module to test (default: send_email)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--select-tests", type=str, default=None,
                       help="Run specific tests using pytest selection (e.g. 'test_config.py::TestConfigValidation')")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to test configuration JSON file")
    return parser.parse_args()

def run_tests(args, config):
    """Run the tests with the specified options."""
    # Build the base command
    test_dir = Path(__file__).parent
    
    # Get paths from config
    unit_tests_dir = config["test_paths"]["unit_tests_dir"]
    module_path = config["test_paths"]["coverage"]["module_path"]
    
    # Determine test path based on module and select_tests arguments
    if args.select_tests:
        test_path = str(test_dir / unit_tests_dir / args.select_tests)
    else:
        test_path = str(test_dir / unit_tests_dir)
    
    # Set environment variables for testing
    # Use PYTHONPATH to help pytest find modules, avoid sys.path manipulation
    workspace_root = str(Path(__file__).resolve().parent.parent.parent.parent.parent)
    os.environ["PYTHONPATH"] = workspace_root
    
    # Prepare coverage command if needed
    if args.coverage:
        if args.skip_tests:
            print("Skipping tests, generating coverage report from existing data...")
            cmd = [
                "python", "-m", "coverage", "report", "--show-missing"
            ]
            if args.verbose:
                cmd.append("-v")
            
            subprocess.run(cmd)
            
            if args.html:
                print("Generating HTML coverage report...")
                html_cmd = [
                    "python", "-m", "coverage", "html"
                ]
                subprocess.run(html_cmd)
                print(f"HTML report generated at: {test_dir.parent}/htmlcov/index.html")
            
            return 0
        else:
            # Run tests with coverage
            cmd = [
                "python", "-m", "pytest", test_path,
                f"--cov={module_path}",
                "--cov-report=term-missing",
            ]
            
            if args.html:
                cmd.append("--cov-report=html")
    else:
        # Run tests without coverage
        cmd = ["python", "-m", "pytest", test_path]
    
    # Add verbosity if requested
    if args.verbose:
        cmd.append("-v")
    
    # Run the command
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    # Display HTML report path if needed
    if args.coverage and args.html and not args.skip_tests:
        print(f"HTML report generated at: {test_dir.parent}/htmlcov/index.html")
    
    return result.returncode

def ensure_test_directories(config):
    """Ensure test data directories exist."""
    test_dir = Path(__file__).parent
    
    # Get directory paths from config
    test_data_dir = test_dir / config["test_paths"]["test_data"]["dir"]
    test_data_dir.mkdir(exist_ok=True)
    
    credentials_dir = test_data_dir / config["test_paths"]["test_data"]["credentials_dir"]
    credentials_dir.mkdir(exist_ok=True)
    
    logs_dir = test_data_dir / config["test_paths"]["test_data"]["logs_dir"]
    logs_dir.mkdir(exist_ok=True)

def main():
    """Main function to run tests."""
    args = parse_args()
    
    # Load configuration
    if args.config:
        with open(args.config, "r") as f:
            config = json.load(f)
    else:
        config = load_config()
    
    # Ensure test directories exist
    ensure_test_directories(config)
    
    return run_tests(args, config)

if __name__ == "__main__":
    sys.exit(main()) 