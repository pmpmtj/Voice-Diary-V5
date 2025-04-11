# Voice Diary Download Audio Files - Tests

This directory contains tests for the download_audio_files module. The tests are organized as follows:

```
tests/
  ├── conftest.py          # Common pytest fixtures
  ├── unit/                # Unit tests
  │   ├── test_config_functions.py      # Tests for configuration functions
  │   ├── test_credentials_functions.py # Tests for credential finding functions  
  │   └── test_main.py                  # Tests for the main function
```

## Requirements

To run the tests, you need to have `pytest` installed:

```bash
pip install pytest pytest-cov
```

## Running the Tests

You can run the tests from the project root directory using:

```bash
# Run all tests
python -m pytest src/voice_diary/download_audio_files/tests

# Run tests with coverage report
python -m pytest src/voice_diary/download_audio_files/tests --cov=voice_diary.download_audio_files

# Run a specific test file
python -m pytest src/voice_diary/download_audio_files/tests/unit/test_config_functions.py

# Run tests matching a specific name pattern
python -m pytest src/voice_diary/download_audio_files/tests -k "config"
```

## Notes

- The tests do not include actual authentication with Google or OAuth processes
- The tests use mocks to simulate file operations and external dependencies
- The tests are designed to be run in any environment without network access 