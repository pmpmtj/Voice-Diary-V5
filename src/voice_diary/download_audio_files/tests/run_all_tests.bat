@echo off
:: Script to run all unit tests for the voice_diary.download_audio_files module sequentially
echo Running all tests for voice_diary.download_audio_files module...
echo.

:: Run the Python script
python src/voice_diary/download_audio_files/tests/run_all_tests.py

:: Exit with the same exit code as the Python script
exit /b %ERRORLEVEL% 