## Whisper

Local Whisper ASR project using `whisper.cpp` plus helper scripts for dictation/workflows.

### Contents
- `whisper.cpp/`: Upstream sources for the Whisper inference engine
- `flow_local_dictation.py`: Local dictation/flow script
- `models/`: Place model binaries here (ignored by Git)

### Quick start
1) Download a Whisper model (e.g., `ggml-base.en.bin`) and put it in `models/`.
2) Build or use the provided Windows binaries as needed.
3) Run your desired executable or the Python flow script.

> Note: Large binaries, build outputs, and model files are ignored by Git via `.gitignore`.


