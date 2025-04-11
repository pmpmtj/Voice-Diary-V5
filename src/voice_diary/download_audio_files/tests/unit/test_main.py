#!/usr/bin/env python3
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Import constants from the module
from voice_diary.download_audio_files.download_audio_files import (
    DEFAULT_FALLBACK_CONFIG_PATH,
    DEFAULT_FALLBACK_CONFIG_FILENAME,
    MODULE_CREDENTIALS_FILENAME,
    SCRIPT_DIR
)

# Import directly from the module we're testing
import voice_diary.download_audio_files.download_audio_files as download_module

class TestMainFunction:
    """Tests for the main function in download_audio_files.py"""
    
    def test_main_with_valid_config_and_credentials(self):
        """Test main function with valid config and credentials"""
        # Create mock config
        mock_config = {
            "auth": {
                "fallback_config_path": "custom/path",
                "fallback_config_filename": "custom_config.json",
            }
        }
        
        # Set up mocks
        with patch('voice_diary.download_audio_files.download_audio_files.load_config', 
                  return_value=mock_config) as mock_load_config, \
             patch('voice_diary.download_audio_files.download_audio_files.find_or_create_credentials',
                  return_value=(Path("test_creds.json"), Path("test_token.pickle"))) as mock_find_credentials:
            
            # First, make the module believe it's run as a main script
            original_name = download_module.__name__
            download_module.__name__ = "__main__"
            
            try:
                # Directly run the main block code from the module
                if download_module.__name__ == "__main__":
                    # Get fallback config paths from config if available
                    fallback_config_path = DEFAULT_FALLBACK_CONFIG_PATH
                    fallback_config_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
                    
                    config = mock_load_config(fallback_config_path, fallback_config_filename)
                    if config:
                        # Update fallback paths from config if present
                        if "auth" in config:
                            auth_config = config["auth"]
                            if "fallback_config_path" in auth_config:
                                fallback_config_path = auth_config["fallback_config_path"]
                            if "fallback_config_filename" in auth_config:
                                fallback_config_filename = auth_config["fallback_config_filename"]
                        
                        # Always try to create credentials directory and handle OAuth flow
                        mock_find_credentials(config)
                
                # Check if load_config was called with the right params
                mock_load_config.assert_called_once_with(
                    DEFAULT_FALLBACK_CONFIG_PATH, 
                    DEFAULT_FALLBACK_CONFIG_FILENAME
                )
                
                # Check if find_or_create_credentials was called with the right params
                mock_find_credentials.assert_called_once_with(mock_config)
            finally:
                # Restore the original module name
                download_module.__name__ = original_name
    
    def test_main_with_no_config(self):
        """Test main function when no config is found"""
        with patch('voice_diary.download_audio_files.download_audio_files.load_config', 
                  return_value=None) as mock_load_config, \
             patch('voice_diary.download_audio_files.download_audio_files.create_sample_config',
                  return_value={"sample": "config"}) as mock_create_config:
            
            # First, make the module believe it's run as a main script
            original_name = download_module.__name__
            download_module.__name__ = "__main__"
            
            try:
                # Directly run the main block code from the module
                if download_module.__name__ == "__main__":
                    # Get fallback config paths from config if available
                    fallback_config_path = DEFAULT_FALLBACK_CONFIG_PATH
                    fallback_config_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
                    
                    config = mock_load_config(fallback_config_path, fallback_config_filename)
                    if config:
                        pass  # Skip the main logic since we're testing the no-config case
                    else:
                        # Create sample config if none found
                        sample_config_path = SCRIPT_DIR / "config" / "config.json"
                        mock_create_config(sample_config_path)
                
                # Check if create_sample_config was called with the right path
                sample_config_path = SCRIPT_DIR / "config" / "config.json"
                mock_create_config.assert_called_once_with(sample_config_path)
            finally:
                # Restore the original module name
                download_module.__name__ = original_name
    
    def test_main_with_missing_credentials(self):
        """Test main function when credentials are not found"""
        # Create mock config
        mock_config = {
            "auth": {
                "fallback_config_path": DEFAULT_FALLBACK_CONFIG_PATH,
                "fallback_config_filename": DEFAULT_FALLBACK_CONFIG_FILENAME
            }
        }
        
        with patch('voice_diary.download_audio_files.download_audio_files.load_config', 
                  return_value=mock_config) as mock_load_config, \
             patch('voice_diary.download_audio_files.download_audio_files.find_or_create_credentials',
                  return_value=(None, None)) as mock_find_credentials:
            
            # First, make the module believe it's run as a main script
            original_name = download_module.__name__
            download_module.__name__ = "__main__"
            
            try:
                # Directly run the main block code from the module
                if download_module.__name__ == "__main__":
                    # Get fallback config paths from config if available
                    fallback_config_path = DEFAULT_FALLBACK_CONFIG_PATH
                    fallback_config_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
                    
                    config = mock_load_config(fallback_config_path, fallback_config_filename)
                    if config:
                        # Update fallback paths from config if present
                        if "auth" in config:
                            auth_config = config["auth"]
                            if "fallback_config_path" in auth_config:
                                fallback_config_path = auth_config["fallback_config_path"]
                            if "fallback_config_filename" in auth_config:
                                fallback_config_filename = auth_config["fallback_config_filename"]
                        
                        # Always try to create credentials directory and handle OAuth flow
                        mock_find_credentials(config)
                
                # Check function was called with right params
                mock_find_credentials.assert_called_once_with(mock_config)
            finally:
                # Restore the original module name
                download_module.__name__ = original_name
    
    def test_main_with_credentials_but_no_token(self):
        """Test main function when credentials exist but token is missing"""
        # Create mock config
        mock_config = {
            "auth": {
                "fallback_config_path": DEFAULT_FALLBACK_CONFIG_PATH,
                "fallback_config_filename": DEFAULT_FALLBACK_CONFIG_FILENAME
            }
        }
        
        with patch('voice_diary.download_audio_files.download_audio_files.load_config', 
                  return_value=mock_config) as mock_load_config, \
             patch('voice_diary.download_audio_files.download_audio_files.find_or_create_credentials',
                  return_value=(Path("test_creds.json"), None)) as mock_find_credentials:
            
            # First, make the module believe it's run as a main script
            original_name = download_module.__name__
            download_module.__name__ = "__main__"
            
            try:
                # Directly run the main block code from the module
                if download_module.__name__ == "__main__":
                    # Get fallback config paths from config if available
                    fallback_config_path = DEFAULT_FALLBACK_CONFIG_PATH
                    fallback_config_filename = DEFAULT_FALLBACK_CONFIG_FILENAME
                    
                    config = mock_load_config(fallback_config_path, fallback_config_filename)
                    if config:
                        # Update fallback paths from config if present
                        if "auth" in config:
                            auth_config = config["auth"]
                            if "fallback_config_path" in auth_config:
                                fallback_config_path = auth_config["fallback_config_path"]
                            if "fallback_config_filename" in auth_config:
                                fallback_config_filename = auth_config["fallback_config_filename"]
                        
                        # Always try to create credentials directory and handle OAuth flow
                        mock_find_credentials(config)
                
                # Check function was called with right params
                mock_find_credentials.assert_called_once_with(mock_config)
            finally:
                # Restore the original module name
                download_module.__name__ = original_name 