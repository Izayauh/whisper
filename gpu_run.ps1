param(
  [string]$Model = "C:\Users\isaia\Desktop\Orojects\Projects\Whisper\models\ggml-medium.en.bin",
  [string]$Input = "C:\Users\isaia\Desktop\Orojects\Projects\Whisper\flow_input.wav"
)
$env:GGML_CUDA_ENABLE="1"
$env:GGML_VERBOSE="1"
$env:WHISPER_PRINT_TIMINGS="1"
& "$PSScriptRoot\whisper-cli.exe" -m $Model $Input 2>&1 | Tee-Object "$PSScriptRoot\gpu_last.log"
if ($LASTEXITCODE -ne 0) { Write-Error "CUDA run failed. See gpu_last.log"; exit 1 }
$log = Get-Content "$PSScriptRoot\gpu_last.log" -Raw
if ($log -notmatch 'ggml_cuda_init: found\s+\d+\s+CUDA devices' -or $log -match 'ggml_cuda_init: found\s+0\s+CUDA devices') {
  Write-Error "GPU not used (no CUDA init detected). See gpu_last.log"; exit 1
}
