# Voice Diary Email Service Tests

This directory contains unit tests for the Voice Diary Email Service module.

## Test Structure

- `unit/` - Unit tests for individual components
  - `voice_diary/` - Tests organized by package name
    - `send_email/` - Tests for the email service module
      - `test_auth.py` - Tests for authentication functionality
      - `test_config.py` - Tests for configuration validation and loading
      - `test_email.py` - Tests for email message creation and sending
      - `test_main.py` - Tests for the main function flow
      - `test_utils.py` - Tests for utility functions

- `test_data/` - Contains test configuration files and other test data
- `conftest.py` - Common pytest fixtures and configuration
- `run_tests.py` - Script to run tests with coverage reporting

## Requirements

Make sure you have installed the test dependencies:

```bash
pip install pytest pytest-mock pytest-cov
```

## Running Tests

### Run all tests

```bash
python tests/run_tests.py
```

### Run with coverage report

```bash
python tests/run_tests.py --coverage
```

### Run with HTML coverage report

```bash
python tests/run_tests.py --coverage --html
```

### Run specific test module

```bash
python tests/run_tests.py --module send_email
```

### Run specific test file or test class

```bash
python tests/run_tests.py --select-tests test_config.py
python tests/run_tests.py --select-tests "test_config.py::TestConfigValidation"
```

### Run with verbose output

```bash
python tests/run_tests.py --verbose
```

## Test Data

The tests use configuration files in the `test_data/` directory. These are separate from the application's actual configuration to ensure tests don't interfere with the production environment.

## Environment Variables

The following environment variables are set during test execution:

- `EMAIL_SENDER_CONFIG` - Path to test configuration file
- `EMAIL_CREDENTIALS_DIR` - Path to test credentials directory

## Notes

- Tests are designed to run without actual Gmail API credentials by mocking the necessary components.
- The email sending functionality is tested in "dry run" mode to avoid sending actual emails. 