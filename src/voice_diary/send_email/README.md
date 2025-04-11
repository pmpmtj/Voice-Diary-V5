# Voice Diary Email Service

A Python module for sending emails via Gmail API with robust configuration management and error handling.

## Overview

This module provides reliable email sending capabilities for the Voice Diary application:
- Uses Gmail API for sending emails
- Supports plain text emails and attachments
- Securely stores authentication tokens with encryption
- Provides comprehensive logging
- Implements configuration management with fallbacks

## Requirements

- Python 3.6+
- Google API client libraries
- A Google Cloud Platform project with Gmail API enabled
- OAuth 2.0 credentials for Gmail API

## Installation

The module is part of the Voice Diary application. No separate installation is required.

## Configuration

### Configuration File

The module uses a JSON configuration file with the following structure:

```json
{
  "version": "1.0.0",
  "send_email": true,
  "validate_email": true,
  "api": {
    "scopes": [
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.compose",
      "https://www.googleapis.com/auth/gmail.modify",
      "https://mail.google.com/"
    ]
  },
  "auth": {
    "credentials_file": "credentials_gmail.json",
    "token_file": "token_gmail.pickle",
    "credentials_path": "credentials",
    "port": 0
  },
  "email": {
    "to": "",
    "subject": "Voice Diary Notification",
    "message": "=== THIS IS A TEST MESSAGE ===",
    "default_message": "=== THIS IS A TEST MESSAGE ==="
  },
  "logging": {
    "file": {
      "level": "INFO",
      "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
      "filename": "send_email.log",
      "max_size_bytes": 1048576,
      "backup_count": 3,
      "encoding": "utf-8"
    },
    "console": {
      "level": "INFO",
      "format": "%(asctime)s - %(levelname)s - %(message)s"
    },
    "logs_dir": "logs"
  }
}
```

### Configuration Search Order

The module searches for configuration in the following order of precedence:

1. **Module-specific config:** `[script_dir]/config/conf_send_email.json` (highest priority)
2. **Environment variable:** Path specified in `EMAIL_SENDER_CONFIG` environment variable
3. **Project-level config:** `[script_dir]/project_fallback_config/config_send_email/conf_send_email.json`
4. **Default module config:** `[script_dir]/conf_send_email.json`

If no configuration file is found, the module will attempt to create a default one at the highest priority location.

### Creating Configuration Files

You can create a sample configuration file in two ways:

#### Script Mode

```bash
python send_email.py --create-config [optional_path]
```

#### Module Mode

```bash
python -m voice_diary.send_email --create-config [optional_path]
```

**Important Notes:**
1. When using the module syntax, do not include the implementation filename in the path.
2. Do NOT add .py at the end of the module path.

Correct:
```bash
python -m voice_diary.send_email --create-config
```

Incorrect:
```bash
python -m voice_diary.send_email.send_email --create-config
python -m voice_diary.send_email.py --create-config  # Don't add .py
```

If no path is specified, it creates the config at the default location: `[script_dir]/config/conf_send_email.json`.

**Important:** When creating a configuration file in a custom location using `--create-config [custom_path]`, the module will not automatically use it for future runs. To make the module use your custom configuration:

1. Set the `EMAIL_SENDER_CONFIG` environment variable to point to your custom configuration file:
   ```bash
   # Windows
   set EMAIL_SENDER_CONFIG=C:/path/to/your/custom_config.json
   
   # Linux/Mac
   export EMAIL_SENDER_CONFIG=C:/path/to/your/custom_config.json
   ```

2. Or create your configuration in one of the standard search paths (preferably the highest priority path).

## Credentials Management

### Credential Search Order

The module searches for Gmail API credentials in the following order:

1. Module credentials directory: `[script_dir]/credentials/` (highest priority)
2. Environment variable: Path specified in `EMAIL_CREDENTIALS_DIR` environment variable
3. Absolute path in configuration: Value of `auth.credentials_path` if it's an absolute path
4. Relative path in configuration: Value of `auth.credentials_path` relative to `script_dir`
5. Default module directory: Falls back to `[script_dir]/credentials/`

### Setting Up Credentials

1. Create a Google Cloud Platform project
2. Enable the Gmail API
3. Create OAuth 2.0 credentials (Desktop application type)
4. Download the credentials JSON file
5. Rename it to match `auth.credentials_file` in your config (default: `credentials_gmail.json`)
6. Place it in one of the searched credential locations

## Command-Line Interface

The module supports the following command-line options:

### Script Mode

```bash
python send_email.py [options]
```

### Module Mode

```bash
python -m voice_diary.send_email [options]
```

Options:
- `--help`, `-h`: Show help message
- `--create-config [path]`: Create a sample configuration file at the specified path

## Logging

The module provides comprehensive logging capabilities:

- Console logging for immediate feedback
- File logging with rotation for persistent records
- Configurable log levels, formats, and locations

Log files are stored in the `logs` directory by default.

## Error Handling

The module implements robust error handling:
- Configuration validation errors
- Authentication and credential issues
- Email sending failures with automatic retries
- Attachment handling errors

## Security

- OAuth tokens are encrypted using Fernet symmetric encryption
- Encryption keys are stored in the token directory
- Email content is sent securely via Gmail API

## Usage Example

```python
from voice_diary.send_email.send_email import main

# Send an email using the configured settings
success = main()

if success:
    print("Email sent successfully")
else:
    print("Failed to send email")
``` 