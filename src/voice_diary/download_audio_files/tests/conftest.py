#!/usr/bin/env python3
import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

@pytest.fixture
def temp_dir():
    """Fixture to create a temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_script_dir(temp_dir):
    """
    Fixture to mock the SCRIPT_DIR constant with a temporary directory
    and create the basic directory structure for tests
    """
    # Create necessary subdirectories
    config_dir = temp_dir / "config"
    credentials_dir = temp_dir / "credentials"
    logs_dir = temp_dir / "logs"
    
    for directory in [config_dir, credentials_dir, logs_dir]:
        directory.mkdir(exist_ok=True)
    
    # Return the temporary directory as the mocked SCRIPT_DIR
    return temp_dir

@pytest.fixture
def sample_config():
    """Fixture to provide a sample configuration for tests"""
    return {
        "version": "1.0.0",
        "api": {
            "scopes": ["https://www.googleapis.com/auth/drive"],
            "retry": {
                "max_retries": 3,
                "retry_delay": 2
            }
        },
        "auth": {
            "credentials_file": "test_credentials.json",
            "token_file": "test_token.pickle",
            "credentials_path": "credentials",
            "fallback_config_path": "custom/fallback/path",
            "fallback_config_filename": "fallback_config.json"
        },
        "folders": {
            "target_folders": [
                "test-folder-1",
                "test-folder-2"
            ]
        },
        "audio_file_types": {
            "include": [".mp3", ".wav", ".m4a"]
        },
        "download": {
            "add_timestamps": True,
            "timestamp_format": "%Y%m%d_%H%M%S",
            "dry_run": False,
            "delete_after_download": False
        },
        "downloads_path": {
            "downloads_dir": "test_downloads"
        }
    }

@pytest.fixture
def mock_json_file(sample_config):
    """Fixture to mock opening and reading a JSON config file"""
    return mock_open(read_data=json.dumps(sample_config))

@pytest.fixture
def mock_credentials_file():
    """Fixture to mock a credentials.json file"""
    mock_credentials = {
        "installed": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "project_id": "test-project-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "test-client-secret",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }
    return mock_open(read_data=json.dumps(mock_credentials))

@pytest.fixture
def mock_token_file():
    """Fixture to simulate a token.pickle file (not actual token data)"""
    # Just return a mock open function - we won't actually read this data
    # as it would be binary and would need special handling
    return mock_open(read_data=b"mock binary data") 