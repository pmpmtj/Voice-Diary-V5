"""
Unit tests for the main functionality in the send_email module.
"""

import pytest
from unittest.mock import patch, MagicMock, call, ANY

from src.voice_diary.send_email.send_email import (
    main,
    AppConfig,
    ApiConfig,
    AuthConfig,
    EmailConfig,
    LoggingConfig,
    TestingConfig
)

@pytest.fixture
def mock_config():
    """Fixture providing a complete mock configuration object for main function"""
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
        logging=LoggingConfig(),
        testing=TestingConfig()
    )

@patch('src.voice_diary.send_email.send_email.load_config')
@patch('src.voice_diary.send_email.send_email.setup_logging')
@patch('src.voice_diary.send_email.send_email.check_email_config')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
@patch('src.voice_diary.send_email.send_email.authenticate_gmail')
@patch('src.voice_diary.send_email.send_email.create_message')
@patch('src.voice_diary.send_email.send_email.send_message')
@patch('src.voice_diary.send_email.send_email.restore_default_message')
def test_main_success_flow(mock_restore, mock_send, mock_create, mock_auth, 
                          mock_check_creds, mock_check_email, mock_setup_logging, 
                          mock_load_config, mock_config):
    """Test successful email sending flow"""
    # Configure mocks
    mock_load_config.return_value = mock_config
    mock_setup_logging.return_value = MagicMock()
    mock_check_email.return_value = True
    mock_check_creds.return_value = True
    
    # Mock service and user profile
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {"emailAddress": "sender@example.com"}
    mock_auth.return_value = mock_service
    
    # Mock message creation and sending
    mock_message = {"raw": "base64_encoded_message"}
    mock_create.return_value = mock_message
    mock_send.return_value = {"id": "test_message_id"}
    
    # Call main function
    result = main()
    
    # Verify successful result
    assert result is True
    
    # Verify correct function calls in sequence
    mock_load_config.assert_called_once()
    mock_setup_logging.assert_called_once_with(mock_config.logging)
    mock_check_email.assert_called_once_with(mock_config, mock_setup_logging.return_value)
    mock_check_creds.assert_called_once_with(mock_config, mock_setup_logging.return_value)
    mock_auth.assert_called_once_with(mock_config, mock_setup_logging.return_value)
    
    # Verify email creation and sending
    mock_create.assert_called_once_with(
        "sender@example.com", 
        mock_config.email.to, 
        mock_config.email.subject, 
        mock_config.email.message
    )
    mock_send.assert_called_once_with(
        mock_service, "me", mock_message, mock_setup_logging.return_value
    )
    
    # Verify default message restoration
    mock_restore.assert_called_once_with(mock_config, mock_setup_logging.return_value)

@patch('src.voice_diary.send_email.send_email.load_config')
@patch('src.voice_diary.send_email.send_email.setup_logging')
@patch('src.voice_diary.send_email.send_email.check_email_config')
def test_main_email_config_invalid(mock_check_email, mock_setup_logging, mock_load_config, mock_config):
    """Test main function when email configuration is invalid"""
    # Configure mocks
    mock_load_config.return_value = mock_config
    mock_setup_logging.return_value = MagicMock()
    mock_check_email.return_value = False
    
    # Call main function
    result = main()
    
    # Verify function failed
    assert result is False
    
    # Verify function calls
    mock_load_config.assert_called_once()
    mock_setup_logging.assert_called_once_with(mock_config.logging)
    mock_check_email.assert_called_once_with(mock_config, mock_setup_logging.return_value)

@patch('src.voice_diary.send_email.send_email.load_config')
@patch('src.voice_diary.send_email.send_email.setup_logging')
@patch('src.voice_diary.send_email.send_email.check_email_config')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
def test_main_credentials_missing(mock_check_creds, mock_check_email, 
                                 mock_setup_logging, mock_load_config, mock_config):
    """Test main function when credentials file is missing"""
    # Configure mocks
    mock_load_config.return_value = mock_config
    mock_setup_logging.return_value = MagicMock()
    mock_check_email.return_value = True
    mock_check_creds.return_value = False
    
    # Call main function
    result = main()
    
    # Verify function failed
    assert result is False
    
    # Verify function calls
    mock_load_config.assert_called_once()
    mock_setup_logging.assert_called_once_with(mock_config.logging)
    mock_check_email.assert_called_once_with(mock_config, mock_setup_logging.return_value)
    mock_check_creds.assert_called_once_with(mock_config, mock_setup_logging.return_value)

@patch('src.voice_diary.send_email.send_email.load_config')
@patch('src.voice_diary.send_email.send_email.setup_logging')
@patch('src.voice_diary.send_email.send_email.check_email_config')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
@patch('src.voice_diary.send_email.send_email.authenticate_gmail')
@patch('src.voice_diary.send_email.send_email.create_message_with_attachment')
@patch('src.voice_diary.send_email.send_email.send_message')
@patch('src.voice_diary.send_email.send_email.restore_default_message')
def test_main_with_attachment(mock_restore, mock_send, mock_create_with_attach, 
                             mock_auth, mock_check_creds, mock_check_email, 
                             mock_setup_logging, mock_load_config, mock_config):
    """Test email sending with attachment"""
    # Set attachment in config
    mock_config.email.attachment = "test_attachment.txt"
    
    # Configure mocks
    mock_load_config.return_value = mock_config
    mock_setup_logging.return_value = MagicMock()
    mock_check_email.return_value = True
    mock_check_creds.return_value = True
    
    # Mock service and user profile
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {"emailAddress": "sender@example.com"}
    mock_auth.return_value = mock_service
    
    # Mock message creation and sending
    mock_message = {"raw": "base64_encoded_message_with_attachment"}
    mock_create_with_attach.return_value = mock_message
    mock_send.return_value = {"id": "test_message_id"}
    
    # Call main function
    result = main()
    
    # Verify successful result
    assert result is True
    
    # Verify email creation with attachment
    mock_create_with_attach.assert_called_once_with(
        "sender@example.com", 
        mock_config.email.to, 
        mock_config.email.subject, 
        mock_config.email.message,
        mock_config.email.attachment,
        mock_setup_logging.return_value
    )
    
    # Verify email sending
    mock_send.assert_called_once_with(
        mock_service, "me", mock_message, mock_setup_logging.return_value
    )

@patch('src.voice_diary.send_email.send_email.setup_logging')
@patch('src.voice_diary.send_email.send_email.load_config')
@patch('src.voice_diary.send_email.send_email.check_email_config')
@patch('src.voice_diary.send_email.send_email.get_credentials_paths')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
@patch('src.voice_diary.send_email.send_email.restore_default_message')
def test_main_dry_run_mode(mock_restore_default, mock_check_creds, mock_get_creds, 
                           mock_check_config, mock_load_config, mock_setup_logging):
    """Test the main function in dry run mode
    
    Verifies the main function works properly in dry run mode.
    """
    # Setup mock config with dry run enabled
    mock_config = MagicMock()
    mock_config.dry_run = True
    mock_config.email.to = "test@example.com"
    mock_config.email.subject = "Test Subject"
    mock_config.email.message = "Test Message"
    mock_config.email.attachment = None
    
    # Setup mocks
    mock_load_config.return_value = mock_config
    mock_check_creds.return_value = True
    logger = MagicMock()
    mock_setup_logging.return_value = logger
    
    # Test
    with patch('builtins.print') as mock_print:
        result = main()
        
        # Assert successful dry run
        assert result is True
        
        # Verify dry run message was logged
        logger.info.assert_any_call(ANY)  # Check that logger.info was called
        dry_run_logged = False
        for call_args in logger.info.call_args_list:
            if call_args and "dry run" in str(call_args).lower():
                dry_run_logged = True
                break
        assert dry_run_logged, "Dry run message not logged"
        
        # Check that dry run message was printed
        mock_print.assert_any_call(ANY)  # Check that print was called
        dry_run_printed = False
        for call_args in mock_print.call_args_list:
            if call_args and "dry run" in str(call_args).lower():
                dry_run_printed = True
                break
        assert dry_run_printed, "Dry run message not printed"
        
        # Verify default message is restored in dry run
        mock_restore_default.assert_called_once()

@patch('src.voice_diary.send_email.send_email.load_config')
@patch('src.voice_diary.send_email.send_email.setup_logging')
@patch('src.voice_diary.send_email.send_email.check_email_config')
@patch('src.voice_diary.send_email.send_email.check_credentials_file')
@patch('src.voice_diary.send_email.send_email.authenticate_gmail')
@patch('src.voice_diary.send_email.send_email.create_message')
@patch('src.voice_diary.send_email.send_email.send_message')
def test_main_send_error(mock_send, mock_create, mock_auth, mock_check_creds, 
                        mock_check_email, mock_setup_logging, mock_load_config, mock_config):
    """Test main function handling send error"""
    # Configure mocks
    mock_load_config.return_value = mock_config
    mock_setup_logging.return_value = MagicMock()
    mock_check_email.return_value = True
    mock_check_creds.return_value = True
    
    # Mock service and user profile
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {"emailAddress": "sender@example.com"}
    mock_auth.return_value = mock_service
    
    # Mock message creation
    mock_message = {"raw": "base64_encoded_message"}
    mock_create.return_value = mock_message
    
    # Make send_message raise an exception
    from src.voice_diary.send_email.send_email import EmailSendError
    mock_send.side_effect = EmailSendError("Send error test")
    
    # Call main function
    result = main()
    
    # Verify function failed
    assert result is False
    
    # Verify error was logged
    logger = mock_setup_logging.return_value
    logger.error.assert_any_call("Failed to send email: Send error test") 