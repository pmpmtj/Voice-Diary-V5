# Voice Diary

A comprehensive voice-based diary system that downloads audio recordings, transcribes them, summarizes your day using AI, and optionally sends email reports.

## Overview

Voice Diary is a modular Python application designed to help you maintain a personal diary using voice recordings. The system automatically:

1. Downloads your audio recordings from Google Drive
2. Transcribes the audio using OpenAI's transcription services
3. Stores the transcriptions in a database
4. Summarizes your day's entries using OpenAI's AI assistants
5. Optionally sends email reports of your diary entries

## Features

- **Google Drive Integration**: Automatically downloads audio files from specified Google Drive folders
- **Audio Transcription**: Transcribes audio recordings using OpenAI's Whisper and GPT models
- **Database Storage**: Securely stores all transcriptions in a PostgreSQL database
- **AI Summarization**: Uses OpenAI's assistants to create meaningful summaries of your diary entries
- **Email Reports**: Optionally sends diary summaries via email
- **Scheduled Operation**: Can run on a schedule using the built-in scheduler
- **Configuration-Driven**: All modules use JSON configuration files for flexible customization
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation

### Prerequisites

- Python 3.7 or higher
- PostgreSQL database (optional, for storage)

### Setup

1. Clone the repository:

```bash
git clone https://github.com/yourusername/voice-diary.git
cd voice-diary
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables:

Create a `.env` file in the `src/voice_diary` directory with the following:

```
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/voice_diary
```

## Configuration

Each module in Voice Diary has its own configuration file located in its respective directory. The primary configuration files are:

- `src/voice_diary/download_audio_files/config/config.json` - Google Drive download settings
- `src/voice_diary/transcribe_raw_audio/config/config.json` - Transcription settings
- `src/voice_diary/agent_summarize_day/config/config.json` - AI summarization settings
- `src/voice_diary/send_email/config/config.json` - Email notification settings
- `src/voice_diary/vd_scheduler/config/config.json` - Scheduler settings

Sample configuration files are automatically created if they don't exist.

### Google Drive Authentication

1. Create OAuth2 credentials in the Google Cloud Console
2. Download the credentials JSON file and place it in `src/voice_diary/download_audio_files/credentials/credentials.json`
3. The first time you run the application, it will prompt you to authorize access to your Google Drive

## Usage

### Running the Complete Workflow

Execute the main script to run the complete workflow:

```bash
python -m voice_diary.main
```

### Running Individual Modules

You can also run individual modules:

```bash
# Download audio files from Google Drive
python -m voice_diary.download_audio_files.download_audio_files

# Transcribe audio files
python -m voice_diary.transcribe_raw_audio.transcribe_raw_audio

# Generate daily summaries
python -m voice_diary.agent_summarize_day.agent_summarize_day

# Send email reports
python -m voice_diary.send_email.send_email
```

### Scheduling Tasks

The application includes a scheduler that can be configured to run tasks at specific times:

```bash
# Start the scheduler
python -m voice_diary.vd_scheduler.vd_scheduler
```

## Project Structure

```
voice_diary/
├── agent_summarize_day/       # AI summarization module
├── download_audio_files/      # Google Drive integration
├── db_utils/                  # Database utilities
├── file_utils/                # File handling utilities
├── logger_utils/              # Logging functionality
├── send_email/                # Email sending module
├── transcribe_raw_audio/      # Audio transcription
├── vd_scheduler/              # Task scheduler
└── project_fallback_config/   # Fallback configuration files
```

## Database Schema

The application uses a PostgreSQL database with the following main tables:

- `transcriptions` - Stores audio transcriptions
- `summaries` - Stores AI-generated summaries
- `email_logs` - Tracks sent emails

## Development

### Testing

Run the tests with pytest:

```bash
pytest
```

Generate a coverage report:

```bash
pytest --cov=src/voice_diary
```

### Building an Executable

You can build a standalone executable using PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "src/voice_diary/project_fallback_config:src/voice_diary/project_fallback_config" src/voice_diary/main.py
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [OpenAI](https://openai.com/) for the Whisper and GPT models
- [Google Drive API](https://developers.google.com/drive) for cloud storage integration 