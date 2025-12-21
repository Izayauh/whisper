# System Test Script for Whisper Dictation
# This script tests all components of the dictation system

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Whisper Dictation System Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$testsPassed = 0
$testsFailed = 0

# Test 1: Python Installation
Write-Host "[1/8] Testing Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
        $testsPassed++
    } else {
        Write-Host "  ✗ Python not found or not working" -ForegroundColor Red
        $testsFailed++
    }
} catch {
    Write-Host "  ✗ Python not found" -ForegroundColor Red
    $testsFailed++
}

# Test 2: Python Packages
Write-Host "[2/8] Testing Python packages..." -ForegroundColor Yellow
$requiredPackages = @("sounddevice", "soundfile", "keyboard", "pyperclip", "pyautogui", "tkinter", "pystray", "numpy")
$missingPackages = @()
foreach ($pkg in $requiredPackages) {
    python -c "import $pkg" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $missingPackages += $pkg
    }
}
if ($missingPackages.Count -eq 0) {
    Write-Host "  ✓ All required packages installed" -ForegroundColor Green
    $testsPassed++
} else {
    Write-Host "  ✗ Missing packages: $($missingPackages -join ', ')" -ForegroundColor Red
    Write-Host "  Run: python -m pip install $($missingPackages -join ' ')" -ForegroundColor Yellow
    $testsFailed++
}

# Test 3: Whisper Binary
Write-Host "[3/8] Testing Whisper binary..." -ForegroundColor Yellow
if (Test-Path "whisper-cli.exe") {
    Write-Host "  ✓ whisper-cli.exe found" -ForegroundColor Green
    $whisperBinary = "whisper-cli.exe"
    $testsPassed++
} elseif (Test-Path "main.exe") {
    Write-Host "  ✓ main.exe found" -ForegroundColor Green
    $whisperBinary = "main.exe"
    $testsPassed++
} else {
    Write-Host "  ✗ No Whisper binary found (whisper-cli.exe or main.exe)" -ForegroundColor Red
    $testsFailed++
    $whisperBinary = $null
}

# Test 4: DLL Files
Write-Host "[4/8] Testing required DLL files..." -ForegroundColor Yellow
$requiredDlls = @("ggml.dll", "ggml-cpu.dll")
$missingDlls = @()
foreach ($dll in $requiredDlls) {
    if (-not (Test-Path $dll)) {
        $missingDlls += $dll
    }
}
if ($missingDlls.Count -eq 0) {
    Write-Host "  ✓ All required DLLs found" -ForegroundColor Green
    $testsPassed++
} else {
    Write-Host "  ⚠ Missing DLLs: $($missingDlls -join ', ')" -ForegroundColor Yellow
    Write-Host "  (May affect performance but might still work)" -ForegroundColor Yellow
    $testsPassed++
}

# Test 5: CUDA Support
Write-Host "[5/8] Testing CUDA/GPU support..." -ForegroundColor Yellow
if (Test-Path "ggml-cuda.dll") {
    try {
        $nvidiaInfo = nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ CUDA available: $nvidiaInfo" -ForegroundColor Green
            $testsPassed++
        } else {
            Write-Host "  ⚠ ggml-cuda.dll found but nvidia-smi failed" -ForegroundColor Yellow
            Write-Host "  (Will fall back to CPU)" -ForegroundColor Yellow
            $testsPassed++
        }
    } catch {
        Write-Host "  ⚠ ggml-cuda.dll found but nvidia-smi not available" -ForegroundColor Yellow
        Write-Host "  (Install NVIDIA drivers for GPU acceleration)" -ForegroundColor Yellow
        $testsPassed++
    }
} else {
    Write-Host "  ⚠ No CUDA support (CPU only)" -ForegroundColor Yellow
    Write-Host "  (Transcription will be slower)" -ForegroundColor Yellow
    $testsPassed++
}

# Test 6: Model Files
Write-Host "[6/8] Testing model files..." -ForegroundColor Yellow
$modelFiles = @(
    @{Path="models\ggml-base.en.bin"; Name="base.en"; Size=142},
    @{Path="models\ggml-medium.en.bin"; Name="medium.en"; Size=1500},
    @{Path="models\ggml-large-v3.bin"; Name="large-v3"; Size=3100}
)
$foundModels = @()
foreach ($model in $modelFiles) {
    if (Test-Path $model.Path) {
        $sizeMB = [math]::Round((Get-Item $model.Path).Length / 1MB, 0)
        $foundModels += "$($model.Name) ($sizeMB MB)"
    }
}
if ($foundModels.Count -gt 0) {
    Write-Host "  ✓ Found models: $($foundModels -join ', ')" -ForegroundColor Green
    $testsPassed++
} else {
    Write-Host "  ✗ No model files found in models\ directory" -ForegroundColor Red
    Write-Host "  Download models from: https://huggingface.co/ggerganov/whisper.cpp" -ForegroundColor Yellow
    $testsFailed++
}

# Test 7: Audio Devices
Write-Host "[7/8] Testing audio input devices..." -ForegroundColor Yellow
try {
    $devices = python -c "import sounddevice as sd; devs = [d for d in sd.query_devices() if d['max_input_channels'] > 0]; print(f'{len(devs)} input devices found'); [print(f\"  - {d['name']}\") for d in devs[:3]]" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ $devices" -ForegroundColor Green
        $testsPassed++
    } else {
        Write-Host "  ⚠ Could not query audio devices" -ForegroundColor Yellow
        Write-Host "  (Check microphone connection)" -ForegroundColor Yellow
        $testsPassed++
    }
} catch {
    Write-Host "  ⚠ Could not test audio devices" -ForegroundColor Yellow
    $testsPassed++
}

# Test 8: Whisper Binary Functionality
Write-Host "[8/8] Testing Whisper binary functionality..." -ForegroundColor Yellow
if ($whisperBinary) {
    try {
        $help = & ".\$whisperBinary" --help 2>&1
        if ($help -match "usage:" -or $help -match "options:") {
            Write-Host "  ✓ Whisper binary is executable" -ForegroundColor Green
            $testsPassed++
        } else {
            Write-Host "  ⚠ Whisper binary ran but output unexpected" -ForegroundColor Yellow
            $testsPassed++
        }
    } catch {
        Write-Host "  ✗ Could not execute Whisper binary" -ForegroundColor Red
        $testsFailed++
    }
} else {
    Write-Host "  ⊘ Skipped (no binary found)" -ForegroundColor Gray
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Tests Passed: $testsPassed" -ForegroundColor Green
Write-Host "Tests Failed: $testsFailed" -ForegroundColor $(if ($testsFailed -gt 0) { "Red" } else { "Green" })
Write-Host ""

if ($testsFailed -eq 0) {
    Write-Host "✓ System is ready to use!" -ForegroundColor Green
    Write-Host "  Run: start_dictation.bat" -ForegroundColor Cyan
} elseif ($testsFailed -le 2) {
    Write-Host "⚠ System may work with some limitations" -ForegroundColor Yellow
    Write-Host "  Fix the failed tests for best experience" -ForegroundColor Yellow
} else {
    Write-Host "✗ System is not ready" -ForegroundColor Red
    Write-Host "  Please fix the failed tests before running" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Log files:" -ForegroundColor Gray
Write-Host "  - flow.log (application log)" -ForegroundColor Gray
Write-Host "  - gpu_last.log (GPU test log)" -ForegroundColor Gray
Write-Host ""

# Write results to file
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[Test Run: $timestamp]`nPassed: $testsPassed, Failed: $testsFailed" | Out-File -FilePath "test_results.log" -Append

Write-Output "__CURSOR_DONE__"

