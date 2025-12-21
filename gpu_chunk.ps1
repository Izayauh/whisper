param(
  [string]$Model = "C:\Users\isaia\Desktop\Orojects\Projects\Whisper\models\ggml-medium.en.bin",
  [string]$Input = "C:\Users\isaia\Desktop\Orojects\Projects\Whisper\flow_input.wav",
  [int]$ChunkSec = 25,
  [int]$OverlapSec = 2
)
$env:GGML_CUDA_ENABLE="1"; $env:GGML_VERBOSE="1"; $env:WHISPER_PRINT_TIMINGS="1"

# A) split
Remove-Item chunk_*.wav, out.txt -ErrorAction SilentlyContinue
ffmpeg -y -i $Input -f segment -segment_time $ChunkSec -af "asetpts=N/SR/TB,aresample=16000" -segment_overlap $OverlapSec -c:a pcm_s16le "chunk_%03d.wav"

# B) transcribe each
Get-ChildItem . -Filter "chunk_*.wav" | Sort-Object Name | ForEach-Object {
  & "$PSScriptRoot\whisper-cli.exe" -m $Model $_.FullName -otxt -of "$($_.BaseName)" 2>&1 | Tee-Object "$($_.BaseName).log"
  if ($LASTEXITCODE -ne 0) { Write-Error "CUDA failed on $($_.Name). See log."; exit 1 }
  $log = Get-Content "$($_.BaseName).log" -Raw
  if ($log -notmatch 'ggml_cuda_init: found\s+\d+\s+CUDA devices' -or $log -match 'ggml_cuda_init: found\s+0\s+CUDA devices') { Write-Error "GPU not used on $($_.Name). See $($_.BaseName).log"; exit 1 }
  Get-Content "$($_.BaseName).txt" | Add-Content out.txt
}
Write-Host "Done. Combined text in out.txt"
