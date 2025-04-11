"""
Unit tests for the configuration functionality in the send_email module.
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
from src.voice_diary.send_email.send_email import (
    validate_config, 
    AppConfig, 
    ApiConfig, 
    AuthConfig, 
    EmailConfig, 
    LoggingConfig,
    ConfigError,
    load_config
)

@pytest.fixture
def valid_config():
    """Fixture providing a valid configuration object"""
    return AppConfig(
        send_email=True,
        validate_email=True,
        api=ApiConfig(
            scopes=["https://www.googleapis.com/auth/gmail.send", 
                    "https://www.googleapis.com/auth/gmail.readonly"]
        ),
        auth=AuthConfig(
            credentials_file="credentials_gmail.json",
            token_file="token_gmail.pickle",
            token_dir="credentials"
        ),
        email=EmailConfig(
            to="test@example.com",
            subject="Test Subject",
            message="Test Message",
            default_message="Default Test Message"
        ),
        logging=LoggingConfig()
    )

class TestConfigValidation:
    """Tests for configuration validation functionality"""
    
    def test_valid_config_passes_validation(self, valid_config):
        """Test that a valid configuration passes validation with no errors"""
        errors = validate_config(valid_config)
        assert errors == []
    
    def test_missing_email_recipient(self, valid_config):
        """Test validation catches missing email recipient"""
        valid_config.email.to = ""
        errors = validate_config(valid_config)
        assert any("Email recipient" in error for error in errors)
    
    def test_invalid_email_format(self, valid_config):
        """Test validation catches invalid email format"""
        valid_config.email.to = "invalid-email"
        errors = validate_config(valid_config)
        assert any("Invalid email format" in error for error in errors)
    
    def test_missing_subject(self, valid_config):
        """Test validation catches missing email subject"""
        valid_config.email.subject = ""
        errors = validate_config(valid_config)
        assert any("Email subject is missing" in error for error in errors)
    
    def test_missing_message(self, valid_config):
        """Test validation catches missing email message"""
        valid_config.email.message = ""
        valid_config.email.default_message = ""
        errors = validate_config(valid_config)
        assert any("Both email message and default message are missing" in error for error in errors)
    
    def test_nonexistent_attachment(self, valid_config, monkeypatch):
        """Test validation catches non-existent attachment file"""
        # Mock Path.exists to return False for our attachment
        original_path_exists = Path.exists
        
        def mock_exists(self):
            if str(self).endswith("nonexistent.txt"):
                return False
            return original_path_exists(self)
            
        monkeypatch.setattr(Path, "exists", mock_exists)
        
        valid_config.email.attachment = "nonexistent.txt"
        errors = validate_config(valid_config)
        assert any("Attachment file does not exist" in error for error in errors)
    
    def test_missing_api_scopes(self, valid_config):
        """Test validation catches missing API scopes"""
        valid_config.api.scopes = []
        errors = validate_config(valid_config)
        assert any("API scopes list is empty" in error for error in errors)
    
    def test_invalid_logging_level(self, valid_config):
        """Test validation catches invalid logging level"""
        valid_config.logging.file.level = "INVALID_LEVEL"
        errors = validate_config(valid_config)
        assert any("Invalid file logging level" in error for error in errors)
        
    def test_negative_backup_count(self, valid_config):
        """Test validation catches negative backup count"""
        valid_config.logging.file.backup_count = -1
        errors = validate_config(valid_config)
        assert any("Invalid backup_count" in error for error in errors)

@patch('builtins.open', new_callable=mock_open, read_data=json.dumps({
    "send_email": True,
    "validate_email": True,
    "api": {
        "scopes": ["https://www.googleapis.com/auth/gmail.send"]
    },
    "auth": {
        "credentials_file": "credentials_gmail.json",
        "token_file": "token_gmail.pickle",
        "token_dir": "credentials"
    },
    "email": {
        "to": "test@example.com",
        "subject": "Test Subject",
        "message": "Test Message",
        "default_message": "Default Test Message"
    },
    "logging": {
        "file": {
            "level": "INFO"
        },
        "console": {
            "level": "INFO"
        },
        "logs_dir": "logs"
    }
}))
@patch('pathlib.Path.exists', return_value=True)
@patch('pathlib.Path.resolve', return_value=Path('/fake/path'))
def test_load_config(mock_resolve, mock_exists, mock_file):
    """Test loading configuration from file"""
    with patch('src.voice_diary.send_email.send_email.CONFIG_FILE', Path('/fake/config.json')):
        config = load_config()
        assert config.send_email is True
        assert config.email.to == "test@example.com"
        assert config.auth.token_dir == "credentials"
        assert "https://www.googleapis.com/auth/gmail.send" in config.api.scopes

@patch('builtins.open', side_effect=json.JSONDecodeError("Expecting property name", "", 0))
@patch('pathlib.Path.exists', return_value=True)
def test_load_config_invalid_json(mock_exists, mock_file):
    """Test handling of invalid JSON in config file"""
    with patch('src.voice_diary.send_email.send_email.CONFIG_FILE', Path('/fake/config.json')):
        with pytest.raises(ConfigError) as excinfo:
            load_config()
        assert "Invalid JSON" in str(excinfo.value) 