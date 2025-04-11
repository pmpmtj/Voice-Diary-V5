"""
Unit tests for utility functions in the send_email module.
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

from src.voice_diary.send_email.send_email import (
    ensure_directory_exists,
    update_config_value,
    restore_default_message,
    validate_file_path,
    ConfigError
)

class TestDirectoryUtils:
    """Tests for directory utility functions"""
    
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    def test_ensure_directory_exists_already_exists(self, mock_exists, mock_mkdir):
        """Test ensure_directory_exists when directory already exists"""
        mock_exists.return_value = True
        
        result = ensure_directory_exists("/fake/dir", "test directory")
        
        assert result is True
        mock_exists.assert_called_once()
        mock_mkdir.assert_not_called()
    
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    def test_ensure_directory_exists_create_success(self, mock_exists, mock_mkdir):
        """Test successful directory creation"""
        mock_exists.return_value = False
        
        # Mock logger
        logger = MagicMock()
        
        result = ensure_directory_exists("/fake/dir", "test directory", logger)
        
        assert result is True
        mock_exists.assert_called_once()
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        logger.info.assert_called_once()
    
    @patch('pathlib.Path.mkdir', side_effect=PermissionError("Permission denied"))
    @patch('pathlib.Path.exists')
    def test_ensure_directory_exists_permission_error(self, mock_exists, mock_mkdir):
        """Test handling of permission error during directory creation"""
        mock_exists.return_value = False
        
        # Mock logger
        logger = MagicMock()
        
        with pytest.raises(ConfigError) as excinfo:
            ensure_directory_exists("/fake/dir", "test directory", logger)
        
        assert "Permission denied" in str(excinfo.value)
        mock_exists.assert_called_once()
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        logger.error.assert_called_once()

class TestConfigUtils:
    """Tests for configuration utility functions"""
    
    def test_update_config_value(self):
        """Test updating a config value"""
        # Create test data
        test_config = {
            "email": {
                "message": "Original Message",
                "default_message": "Default Message"
            }
        }
        
        # Convert to JSON string
        config_json = json.dumps(test_config, indent=2)
        
        # Set up the mock file context manager
        mock_open_obj = mock_open(read_data=config_json)
        
        with patch('builtins.open', mock_open_obj):
            config_path = Path("/fake/config.json")
            key_path = ["email", "message"]
            new_value = "Updated Message"
            
            # Mock logger
            logger = MagicMock()
            
            # Call the function
            update_config_value(config_path, key_path, new_value, logger)
            
            # Verify file operations - check that open was called correctly for both read and write
            assert mock_open_obj.call_count == 2
            mock_open_obj.assert_any_call(config_path, 'r', encoding='utf-8')
            mock_open_obj.assert_any_call(config_path, 'w', encoding='utf-8')
            
            # Get the write handle and check what was written
            handle = mock_open_obj()
            handle.write.assert_called()
            
            # Get all written data and join it if multiple writes occurred
            written_data = ""
            for call in handle.write.call_args_list:
                args, _ = call
                if args and isinstance(args[0], str):
                    written_data += args[0]
            
            # Verify the written data contains our updated value
            assert new_value in written_data
            
            # If we can reliably parse it as JSON, do that too
            try:
                updated_config = json.loads(written_data)
                assert updated_config["email"]["message"] == new_value
            except json.JSONDecodeError:
                # If we can't parse it, at least check that the string contains what we expect
                assert f'"message": "{new_value}"' in written_data
    
    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    def test_update_config_value_permission_error(self, mock_file):
        """Test handling of permission error when updating config"""
        config_path = Path("/fake/config.json")
        key_path = ["email", "message"]
        new_value = "Updated Message"
        
        # Mock logger
        logger = MagicMock()
        
        with pytest.raises(ConfigError) as excinfo:
            update_config_value(config_path, key_path, new_value, logger)
        
        assert "Permission denied" in str(excinfo.value)
        logger.error.assert_called_once()
    
    @patch('src.voice_diary.send_email.send_email.CONFIG_FILE', Path('/fake/config.json'))
    @patch('src.voice_diary.send_email.send_email.update_config_value')
    def test_restore_default_message_when_different(self, mock_update):
        """Test restoring default message when current message differs"""
        # Mock config with different message
        mock_config = MagicMock()
        mock_config.email.message = "Current Message"
        mock_config.email.default_message = "Default Message"
        
        # Mock logger
        logger = MagicMock()
        
        # Call the function
        restore_default_message(mock_config, logger)
        
        # Verify update_config_value was called
        mock_update.assert_called_once_with(
            Path('/fake/config.json'), 
            ['email', 'message'], 
            "Default Message", 
            logger
        )
        
        # Verify in-memory config was updated
        assert mock_config.email.message == "Default Message"
    
    @patch('src.voice_diary.send_email.send_email.CONFIG_FILE', Path('/fake/config.json'))
    @patch('src.voice_diary.send_email.send_email.update_config_value')
    def test_restore_default_message_when_same(self, mock_update):
        """Test restoring default message when current message is already default"""
        # Mock config with same message as default
        mock_config = MagicMock()
        mock_config.email.message = "Default Message"
        mock_config.email.default_message = "Default Message"
        
        # Mock logger
        logger = MagicMock()
        
        # Call the function
        restore_default_message(mock_config, logger)
        
        # Verify update_config_value was not called
        mock_update.assert_not_called()

class TestPathValidation:
    """Tests for file path validation"""
    
    @pytest.mark.parametrize("path,expected", [
        ("/home/user/documents/attachment.txt", True),
        ("C:\\Users\\username\\Documents\\attachment.txt", True),
        ("/var/data/attachment.txt", True),
        ("/etc/passwd", True),
        ("/var/log/syslog", True),
        ("/proc/self/cmdline", True),
        ("/sys/kernel/debug", True),
        ("C:\\Windows\\System32\\config", True),
        ("C:\\Program Files\\Common Files\\secret.txt", True),
    ])
    def test_validate_file_path(self, path, expected):
        """Test file path validation with various paths"""
        with patch('pathlib.Path.resolve', return_value=Path(path)):
            result = validate_file_path(path)
            assert result is expected 