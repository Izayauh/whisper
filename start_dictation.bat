@echo off
REM Whisper Local Dictation Launcher
REM This script starts the dictation system with proper environment setup

echo ========================================
echo  Whisper Local Dictation System
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or later
    pause
    exit /b 1
)

REM Check if required Python packages are installed
echo Checking dependencies...
python -c "import sounddevice, soundfile, keyboard, pyperclip, pyautogui, tkinter, pystray, numpy" 2>nul
if errorlevel 1 (
    echo.
    echo Installing required Python packages...
    python -m pip install sounddevice soundfile keyboard pyperclip pyautogui pillow pystray numpy
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Check if model exists
if not exist "models\ggml-large-v3.bin" (
    if not exist "models\ggml-medium.en.bin" (
        if not exist "models\ggml-base.en.bin" (
            echo.
            echo WARNING: No Whisper model found in models\ directory
            echo Please download a model file and place it in the models folder
            echo.
            pause
        )
    )
)

REM Check if Whisper binary exists
if not exist "whisper-cli.exe" (
    if not exist "main.exe" (
        echo.
        echo ERROR: Whisper binary not found
        echo Please ensure whisper-cli.exe or main.exe is in the current directory
        pause
        exit /b 1
    )
)

echo.
echo Starting dictation system...
echo.

REM Set microphone to Audient iD14
set FLOW_INPUT_DEVICE=Analogue 1/2

REM Run the Python script
python flow_local_dictation.py

if errorlevel 1 (
    echo.
    echo ERROR: Dictation system exited with an error
    pause
)

