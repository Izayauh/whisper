# Whisper Local Dictation Launcher (PowerShell)
# This script starts the dictation system with proper environment setup

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Whisper Local Dictation System" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "  Please install Python 3.8 or later" -ForegroundColor Yellow
    pause
    exit 1
}

# Check if required Python packages are installed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
$packagesCheck = python -c "import sounddevice, soundfile, keyboard, pyperclip, pyautogui, tkinter, pystray, numpy" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Installing required Python packages..." -ForegroundColor Yellow
    python -m pip install sounddevice soundfile keyboard pyperclip pyautogui pillow pystray numpy
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "✗ ERROR: Failed to install dependencies" -ForegroundColor Red
        pause
        exit 1
    }
}
Write-Host "✓ All dependencies installed" -ForegroundColor Green

# Check if model exists
$modelExists = $false
$modelFiles = @("models\ggml-large-v3.bin", "models\ggml-medium.en.bin", "models\ggml-base.en.bin")
foreach ($model in $modelFiles) {
    if (Test-Path $model) {
        Write-Host "✓ Model found: $model" -ForegroundColor Green
        $modelExists = $true
        break
    }
}
if (-not $modelExists) {
    Write-Host ""
    Write-Host "⚠ WARNING: No Whisper model found in models\ directory" -ForegroundColor Yellow
    Write-Host "  Please download a model file and place it in the models folder" -ForegroundColor Yellow
    Write-Host ""
    pause
}

# Check if Whisper binary exists
if (Test-Path "whisper-cli.exe") {
    Write-Host "✓ Whisper binary: whisper-cli.exe" -ForegroundColor Green
} elseif (Test-Path "main.exe") {
    Write-Host "✓ Whisper binary: main.exe" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ ERROR: Whisper binary not found" -ForegroundColor Red
    Write-Host "  Please ensure whisper-cli.exe or main.exe is in the current directory" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host ""
Write-Host "Starting dictation system..." -ForegroundColor Cyan
Write-Host ""

# Run the Python script
python flow_local_dictation.py; Write-Output "__CURSOR_DONE__"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "✗ ERROR: Dictation system exited with error code $LASTEXITCODE" -ForegroundColor Red
    pause
}

