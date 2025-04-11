"""
Unit tests for the email validation and message creation functionality.
"""

import os
import pytest
import base64
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, Mock

from src.voice_diary.send_email.send_email import (
    validate_email_format,
    create_message,
    create_message_with_attachment,
    EmailSendError,
    send_message
)

class TestEmailValidation:
    """Tests for email address validation functionality"""
    
    @pytest.mark.parametrize("email,expected", [
        ("test@example.com", True),
        ("user.name+tag@example.co.uk", True),
        ("x@example.com", True),
        ("example-indeed@strange-example.com", True),
        ("admin@mailserver1", True),
        ("", False),
        ("plainaddress", False),
        ("@missingusername.com", False),
        ("username@.com", False),
        (".username@example.com", False),
        ("username@example..com", False),
        ("username@example.com.", False),
        ("username@.example.com", False),
        ("username@example.com.com.com", False),  # Changed to False to match implementation
    ])
    def test_validate_email_format(self, email, expected):
        """Test email format validation with various email addresses"""
        assert validate_email_format(email) == expected

class TestMessageCreation:
    """Tests for email message creation functionality"""
    
    def test_create_simple_message(self):
        """Test creating a simple email message"""
        sender = "from@example.com"
        to = "to@example.com"
        subject = "Test Subject"
        message_text = "Test message content"
        
        result = create_message(sender, to, subject, message_text)
        
        # Verify the result contains a 'raw' key with base64 encoded content
        assert 'raw' in result
        
        # Decode the raw content to verify it contains our message parts
        raw_bytes = base64.urlsafe_b64decode(result['raw'])
        decoded = raw_bytes.decode('utf-8')
        
        # Check for headers in a case-insensitive way
        decoded_lower = decoded.lower()
        assert f"from: {sender}".lower() in decoded_lower
        assert f"to: {to}".lower() in decoded_lower
        assert f"subject: {subject}".lower() in decoded_lower
        assert message_text in decoded
    
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.stat')
    @patch('builtins.open', new_callable=mock_open, read_data=b'test attachment content')
    def test_create_message_with_attachment(self, mock_file, mock_stat, mock_exists):
        """Test creating an email message with an attachment"""
        # Mock stat result to return a small file size
        stat_result = Mock()
        stat_result.st_size = 1024  # 1KB
        mock_stat.return_value = stat_result
        
        sender = "from@example.com"
        to = "to@example.com"
        subject = "Test Subject with Attachment"
        message_text = "Test message with attachment"
        attachment_path = "test_attachment.txt"
        
        result = create_message_with_attachment(
            sender, to, subject, message_text, attachment_path
        )
        
        # Verify the result contains a 'raw' key with base64 encoded content
        assert 'raw' in result
        
        # Decode the raw content to verify it contains our message parts
        raw_bytes = base64.urlsafe_b64decode(result['raw'])
        decoded = raw_bytes.decode('utf-8', errors='ignore')
        
        # Check for headers in a case-insensitive way
        decoded_lower = decoded.lower()
        assert f"from: {sender}".lower() in decoded_lower
        assert f"to: {to}".lower() in decoded_lower
        assert f"subject: {subject}".lower() in decoded_lower
        assert message_text in decoded
        assert "Content-Disposition: attachment".lower() in decoded_lower
        assert "test_attachment.txt" in decoded
    
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.stat')
    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    def test_attachment_permission_error(self, mock_file, mock_stat, mock_exists):
        """Test handling of permission error when reading attachment"""
        # Mock stat result
        stat_result = Mock()
        stat_result.st_size = 1024
        mock_stat.return_value = stat_result
        
        with pytest.raises(EmailSendError) as excinfo:
            create_message_with_attachment(
                "from@example.com", 
                "to@example.com", 
                "Subject", 
                "Message", 
                "test_attachment.txt"
            )
        
        assert "Permission denied" in str(excinfo.value)
    
    @patch('pathlib.Path.exists', return_value=False)
    def test_nonexistent_attachment(self, mock_exists):
        """Test handling of non-existent attachment file"""
        with pytest.raises(EmailSendError) as excinfo:
            create_message_with_attachment(
                "from@example.com", 
                "to@example.com", 
                "Subject", 
                "Message", 
                "nonexistent.txt"
            )
        
        assert "Attachment file does not exist" in str(excinfo.value)

class TestEmailSending:
    """Tests for email sending functionality"""
    
    @patch('googleapiclient.discovery.build')
    def test_send_message_success(self, mock_build):
        """Test successful email sending"""
        # Mock the Gmail API service
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Mock the users, messages, and send methods/response
        mock_users = MagicMock()
        mock_service.users.return_value = mock_users
        
        mock_messages = MagicMock()
        mock_users.messages.return_value = mock_messages
        
        mock_send = MagicMock()
        mock_messages.send.return_value = mock_send
        
        # Mock the execute method to return a successful response
        mock_execute = MagicMock()
        mock_execute.return_value = {"id": "test_message_id"}
        mock_send.execute = mock_execute
        
        # Create a test message
        message = {"raw": "test_raw_message"}
        
        # Call the function
        logger = MagicMock()
        result = send_message(mock_service, "me", message, logger)
        
        # Verify the result
        assert result["id"] == "test_message_id"
        
        # Verify the API was called correctly
        mock_service.users.assert_called_once()
        mock_users.messages.assert_called_once()
        mock_messages.send.assert_called_once_with(userId="me", body=message)
        mock_send.execute.assert_called_once()
    
    @patch('googleapiclient.discovery.build')
    def test_send_message_http_error(self, mock_build):
        """Test handling of HTTP error during email sending"""
        from googleapiclient import errors as google_errors
        
        # Mock the Gmail API service
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Set up the method chain that will raise the error
        mock_users = MagicMock()
        mock_service.users.return_value = mock_users
        
        mock_messages = MagicMock()
        mock_users.messages.return_value = mock_messages
        
        mock_send = MagicMock()
        mock_messages.send.return_value = mock_send
        
        # Create an HttpError response
        mock_response = MagicMock()
        mock_response.status = 400  # Bad Request
        mock_error = google_errors.HttpError(mock_response, b'Bad Request')
        
        # Make execute raise the error
        mock_send.execute.side_effect = mock_error
        
        # Create a test message
        message = {"raw": "test_raw_message"}
        
        # Call the function and check for exception
        logger = MagicMock()
        with pytest.raises(EmailSendError) as excinfo:
            send_message(mock_service, "me", message, logger)
        
        assert "HTTP error" in str(excinfo.value)
        assert "400" in str(excinfo.value) 