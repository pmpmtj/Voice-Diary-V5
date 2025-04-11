"""
Pytest configuration file for Voice Diary Email Service tests.

This file contains shared fixtures and configuration for test modules.
"""

import os
import sys
import pytest
from pathlib import Path

# Define common fixtures for all tests
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Set up test environment variables and configuration.
    
    This fixture runs once per test session before any tests are executed.
    """
    # Save original environment
    original_env = os.environ.copy()
    
    # Set test-specific environment variables
    os.environ.update({
        # Set any environment variables needed for testing
        "EMAIL_SENDER_CONFIG": str(Path(__file__).parent / "test_data" / "conf_send_email.json"),
        "EMAIL_CREDENTIALS_DIR": str(Path(__file__).parent / "test_data" / "credentials")
    })
    
    # Create test data directories if they don't exist
    test_data_dir = Path(__file__).parent / "test_data"
    test_data_dir.mkdir(exist_ok=True)
    
    credentials_dir = test_data_dir / "credentials"
    credentials_dir.mkdir(exist_ok=True)
    
    logs_dir = test_data_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Run tests
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)

@pytest.fixture
def test_config_file():
    """
    Provide path to a test configuration file.
    
    This creates a temporary configuration file for testing.
    """
    config_dir = Path(__file__).parent / "test_data"
    config_file = config_dir / "conf_send_email.json"
    
    # Return the path without creating the file - individual tests should create
    # it with their specific test configuration
    return config_file 