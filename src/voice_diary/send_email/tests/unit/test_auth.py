"""
Unit tests for the authentication functionality in the send_email module.
"""

import os
import pickle
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, Mock

from src.voice_diary.send_email.send_email import (
    get_credentials_paths,
    check_credentials_file,
    encrypt_token,
    decrypt_token,
    authenticate_gmail,
    AuthenticationError,
    AppConfig,
    AuthConfig,
    ApiConfig,
    LoggingConfig
)

@pytest.fixture
def mock_config():
    """Fixture providing a mock configuration object"""
    config = MagicMock()
    config.auth = MagicMock()
    config.auth.credentials_file = "credentials_gmail.json"
    config.auth.token_file = "token_gmail.pickle"
    config.auth.token_dir = "credentials"
    config.api = MagicMock()
    config.api.scopes = ["https://www.googleapis.com/auth/gmail.send"]
    return config

class TestCredentialsPaths:
    """Tests for credential path resolution"""
    
    def test_get_credentials_paths_module_dir(self, mock_config):
        """Test getting credentials from module directory"""
        # Mock logger
        logger = MagicMock()
        
        # Mock script directory
        script_dir = Path('/fake/script/dir')
        
        # Create expected paths
        creds_dir = script_dir / "credentials"
        module_creds_path = creds_dir / "credentials_gmail.json"
        module_token_path = creds_dir / "token_gmail.pickle"
        
        # Setup mocks - only mock the specific paths we need to check
        with patch('src.voice_diary.send_email.send_email.SCRIPT_DIR', script_dir):
            with patch('pathlib.Path.exists') as mock_exists:
                # Mock that the module credentials file exists
                mock_exists.return_value = True
                
                # Call the function
                creds_path, token_path = get_credentials_paths(mock_config, logger)
                
                # Verify correct paths are returned
                assert creds_path == module_creds_path
                assert token_path == module_token_path

    def test_get_credentials_paths_env_var(self, mock_config):
        """Test getting credentials from environment variable
        
        Verifies that when the environment variable is set, it is properly used.
        """
        # Mock logger
        logger = MagicMock()
        
        # Set up environment variable
        env_path = "/env/credentials"
        
        # Setup function under test with patching
        with patch.dict(os.environ, {"EMAIL_CREDENTIALS_DIR": env_path}):
            with patch('src.voice_diary.send_email.send_email.get_config_path'):  # Avoid actual config dependency
                with patch('pathlib.Path.exists') as mock_exists:
                    # Make first path check fail (module dir) and second succeed (env dir)
                    # Path.exists is called at least twice in the function
                    mock_exists.side_effect = [False, True] + [True] * 10  # Default True for subsequent calls
                    
                    # Correctly mock Path.__truediv__ by creating a lambda that accepts self and other parameters
                    with patch('pathlib.Path.__truediv__', 
                              lambda self, other: Path(os.path.join(str(self), str(other)))):
                        
                        # Call function
                        creds_path, token_path = get_credentials_paths(mock_config, logger)
                        
                        # Test exact paths - env path should be used
                        expected_creds_path = Path(env_path) / mock_config.auth.credentials_file
                        expected_token_path = Path(env_path) / mock_config.auth.token_file
                        
                        assert str(creds_path) == str(expected_creds_path)
                        assert str(token_path) == str(expected_token_path)
                        
                        # Verify logger was called with appropriate messages
                        # This validates the function's behavior without being brittle to path changes
                        env_var_check = False
                        for call_args in logger.info.call_args_list:
                            if call_args and "environment variable" in str(call_args):
                                env_var_check = True
                                break
                        
                        assert env_var_check, "Environment variable path logging not found"

    def test_get_credentials_paths_absolute_config_path(self, mock_config):
        """Test getting credentials from absolute path in config
        
        This test verifies that absolute paths in configuration are correctly used in the
        credential path resolution process.
        """
        # Mock logger
        logger = MagicMock()
        
        # Set absolute path in config
        mock_config.auth.credentials_path = "/config/creds"
        
        # Setup function under test with patching
        with patch('src.voice_diary.send_email.send_email.get_config_path'):  # Avoid actual config dependency
            with patch('pathlib.Path.exists') as mock_exists:
                # Make first two path checks fail (module dir, env var) and third succeed (absolute path)
                # Path.exists is called at least three times in the function
                mock_exists.side_effect = [False, False, True] + [True] * 10  # Default True for subsequent calls
                
                # Correctly mock Path.__truediv__ by creating a lambda that accepts self and other parameters
                with patch('pathlib.Path.__truediv__', 
                           lambda self, other: Path(os.path.join(str(self), str(other)))):
                    
                    # Also mock Path.mkdir to avoid actual directory creation
                    with patch('pathlib.Path.mkdir'):
                        
                        # Call function
                        creds_path, token_path = get_credentials_paths(mock_config, logger)
                        
                        # Test exact paths - config absolute path should be used
                        expected_creds_path = Path(mock_config.auth.credentials_path) / mock_config.auth.credentials_file
                        expected_token_path = Path(mock_config.auth.credentials_path) / mock_config.auth.token_file
                        
                        assert str(creds_path) == str(expected_creds_path)
                        assert str(token_path) == str(expected_token_path)
                        
                        # Verify logger was called with appropriate messages
                        config_path_check = False
                        for args in logger.info.call_args_list:
                            if args and "absolute path" in str(args):
                                config_path_check = True
                                break
                        
                        # If we can't verify via logs, at least check mock calls were made as expected
                        if not config_path_check:
                            assert mock_exists.call_count >= 3, "Path existence not checked enough times"

@patch('pathlib.Path.exists')
def test_check_credentials_file_exists(mock_exists, mock_config):
    """Test check_credentials_file when file exists"""
    mock_exists.return_value = True
    
    # Mock logger
    logger = MagicMock()
    
    with patch('src.voice_diary.send_email.send_email.get_credentials_paths') as mock_get_paths:
        mock_get_paths.return_value = (Path('/fake/path/credentials_gmail.json'), 
                                      Path('/fake/path/token_gmail.pickle'))
        
        result = check_credentials_file(mock_config, logger)
        assert result is True

@patch('pathlib.Path.exists')
def test_check_credentials_file_missing(mock_exists, mock_config):
    """Test check_credentials_file when file is missing"""
    mock_exists.return_value = False
    
    # Mock logger
    logger = MagicMock()
    
    with patch('src.voice_diary.send_email.send_email.get_credentials_paths') as mock_get_paths:
        mock_get_paths.return_value = (Path('/fake/path/credentials_gmail.json'), 
                                      Path('/fake/path/token_gmail.pickle'))
        
        result = check_credentials_file(mock_config, logger)
        assert result is False
        # Check that logger.error was called with appropriate message
        assert any("not found" in str(args[0]) for args, _ in logger.error.call_args_list)

class TestTokenEncryption:
    """Tests for token encryption and decryption"""
    
    @patch('builtins.open', new_callable=mock_open, read_data=b'test_key_data')
    @patch('pathlib.Path.exists')
    @patch('src.voice_diary.send_email.send_email.Fernet')
    def test_decrypt_token(self, mock_fernet, mock_exists, mock_file):
        """Test token decryption"""
        # Mock key file exists
        mock_exists.return_value = True
        
        # Mock Fernet
        mock_fernet_instance = MagicMock()
        mock_fernet_instance.decrypt.return_value = b'decrypted_data'
        mock_fernet.return_value = mock_fernet_instance
        
        # Create mock token file path
        token_file_path = Path('/fake/path/token_gmail.pickle')
        
        # Call the function
        result = decrypt_token(b'encrypted_data', token_file_path)
        
        # Verify result and that Fernet was used correctly
        assert result == b'decrypted_data'
        mock_fernet.assert_called_once_with(b'test_key_data')
        mock_fernet_instance.decrypt.assert_called_once_with(b'encrypted_data')
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    @patch('src.voice_diary.send_email.send_email.Fernet')
    @patch('src.voice_diary.send_email.send_email.ensure_directory_exists')
    def test_encrypt_token_new_key(self, mock_ensure_dir, mock_fernet, mock_exists, mock_file):
        """Test token encryption with new key generation"""
        # Mock key file doesn't exist
        mock_exists.return_value = False
        
        # Mock Fernet
        mock_fernet.generate_key.return_value = b'new_key_data'
        mock_fernet_instance = MagicMock()
        mock_fernet_instance.encrypt.return_value = b'encrypted_data'
        mock_fernet.return_value = mock_fernet_instance
        
        # Create mock token file path
        token_file_path = Path('/fake/path/token_gmail.pickle')
        
        # Call the function
        result = encrypt_token(b'token_data', token_file_path)
        
        # Verify result and that Fernet was used correctly
        assert result == b'encrypted_data'
        mock_fernet.generate_key.assert_called_once()
        mock_ensure_dir.assert_called_once()
        mock_fernet.assert_called_once_with(b'new_key_data')
        mock_fernet_instance.encrypt.assert_called_once_with(b'token_data')
        
        # Check file write operations
        mock_file.assert_called()
        handle = mock_file()
        handle.write.assert_called_once_with(b'new_key_data')

@patch('src.voice_diary.send_email.send_email.get_credentials_paths')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
@patch('src.voice_diary.send_email.send_email.Path.exists')
@patch('builtins.open', new_callable=mock_open, read_data=b'encrypted_token_data')
@patch('src.voice_diary.send_email.send_email.decrypt_token')
@patch('src.voice_diary.send_email.send_email.pickle.loads')
@patch('src.voice_diary.send_email.send_email.build')
def test_authenticate_gmail_with_valid_token(mock_build, mock_pickle_loads, mock_decrypt, 
                                            mock_file, mock_exists, mock_check_creds, 
                                            mock_get_paths, mock_config):
    """Test authentication with valid token"""
    # Mock logger
    logger = MagicMock()
    
    # Setup credential paths
    creds_path = Path('/fake/path/credentials_gmail.json')
    token_path = Path('/fake/path/token_gmail.pickle')
    mock_get_paths.return_value = (creds_path, token_path)
    
    # Mock token exists
    mock_exists.return_value = True
    
    # Mock token decryption and deserialization
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_decrypt.return_value = b'decrypted_token'
    mock_pickle_loads.return_value = mock_creds
    
    # Mock API service
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    # Call function
    result = authenticate_gmail(mock_config, logger)
    
    # Verify interactions
    mock_get_paths.assert_called_once_with(mock_config, logger)
    mock_decrypt.assert_called_once_with(b'encrypted_token_data', token_path)
    mock_pickle_loads.assert_called_once_with(b'decrypted_token')
    mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
    assert result == mock_service
    
    # Logging calls
    assert any('credentials' in str(args) for args, _ in logger.info.call_args_list)
    assert any('token' in str(args) for args, _ in logger.info.call_args_list)

@patch('src.voice_diary.send_email.send_email.get_credentials_paths')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
@patch('src.voice_diary.send_email.send_email.Path.exists')
@patch('src.voice_diary.send_email.send_email.InstalledAppFlow')
@patch('src.voice_diary.send_email.send_email.pickle.dumps')
@patch('src.voice_diary.send_email.send_email.encrypt_token')
@patch('builtins.open', new_callable=mock_open)
@patch('src.voice_diary.send_email.send_email.build')
@patch('src.voice_diary.send_email.send_email.ensure_directory_exists')
def test_authenticate_gmail_with_new_flow(mock_ensure_dir, mock_build, mock_file, 
                                         mock_encrypt, mock_pickle_dumps,
                                         mock_flow, mock_exists, mock_check_creds, 
                                         mock_get_paths, mock_config):
    """Test authentication with new OAuth flow"""
    # Mock logger
    logger = MagicMock()
    
    # Setup credential paths
    creds_path = Path('/fake/path/credentials_gmail.json')
    token_path = Path('/fake/path/token_gmail.pickle')
    mock_get_paths.return_value = (creds_path, token_path)
    
    # Mock token doesn't exist, then credentials check passes
    mock_exists.side_effect = [False, True]
    mock_check_creds.return_value = True
    
    # Mock OAuth flow
    mock_creds = MagicMock()
    mock_flow_instance = MagicMock()
    mock_flow_instance.run_local_server.return_value = mock_creds
    mock_flow.from_client_secrets_file.return_value = mock_flow_instance
    
    # Mock token serialization and encryption
    mock_pickle_dumps.return_value = b'serialized_token'
    mock_encrypt.return_value = b'encrypted_token'
    
    # Mock API service
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    # Call function
    result = authenticate_gmail(mock_config, logger)
    
    # Verify interactions
    mock_get_paths.assert_called_once_with(mock_config, logger)
    mock_check_creds.assert_called_once_with(mock_config, logger)
    mock_flow.from_client_secrets_file.assert_called_once_with(
        str(creds_path), mock_config.api.scopes)
    mock_pickle_dumps.assert_called_once_with(mock_creds)
    mock_encrypt.assert_called_once_with(b'serialized_token', token_path)
    mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
    assert result == mock_service
    
    # Verify directory creation
    mock_ensure_dir.assert_called_once()
    
    # Verify OAuth flow was created and run
    mock_flow_instance.run_local_server.assert_called_once_with(port=mock_config.auth.port)
    
    # Verify token was saved
    mock_pickle_dumps.assert_called_once_with(mock_creds)
    mock_encrypt.assert_called_once_with(b'serialized_token', token_path)
    
    # Verify the correct service was built
    mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds) 