# 🎤 Whisper Local Dictation System

**Privacy-focused, GPU-accelerated speech-to-text dictation for Windows**

Transform your voice into text instantly - completely offline, using OpenAI's Whisper AI running locally on your computer.

## ✨ Features

- 🔒 **100% Private** - All processing happens on your computer
- ⚡ **GPU Accelerated** - Fast transcription with NVIDIA CUDA
- 🌍 **System-wide** - Works in any application
- 🎯 **Simple Controls** - Just hold WIN + CTRL to dictate
- 🎨 **Clean UI** - Minimal status bar that stays out of your way
- 📝 **Smart Text Processing** - Automatic cleanup and formatting

## 🚀 Quick Start

**Just run:** `start_dictation.bat`

That's it! The launcher handles everything:
- Checks Python installation
- Installs required packages
- Verifies model files
- Starts the dictation system

## 📖 Usage

1. Position your cursor where you want text
2. **Hold WIN + CTRL** and speak
3. **Release** to transcribe and paste

See [`QUICK_START.md`](QUICK_START.md) for basic usage  
See [`USER_GUIDE.md`](USER_GUIDE.md) for detailed documentation

## 📋 Requirements

- Windows 10/11
- Python 3.8+
- (Optional) NVIDIA GPU with CUDA for faster transcription

## 🎯 Controls

| Action | Hotkey |
|--------|--------|
| Record & Dictate | Hold `WIN + CTRL` |
| Settings | `WIN + CTRL + S` |
| Exit | `ESC` |
| Self-Test | `F8` |

## 📁 Project Structure

```
Whisper/
├── start_dictation.bat        # Easy launcher (recommended)
├── start_dictation.ps1        # PowerShell launcher
├── flow_local_dictation.py   # Main application
├── whisper-cli.exe            # Whisper binary
├── models/                    # AI models
│   ├── ggml-base.en.bin
│   ├── ggml-medium.en.bin
│   └── ggml-large-v3.bin
├── QUICK_START.md             # Quick start guide
└── USER_GUIDE.md              # Full documentation
```

## 🔧 Troubleshooting

**Problem:** "No speech detected"  
**Solution:** Press `WIN + CTRL + S` for microphone settings, click Test

**Problem:** Slow transcription  
**Solution:** GPU acceleration is automatic - first run loads model (slower)

**Problem:** Python not found  
**Solution:** Install from [python.org](https://www.python.org/downloads/)

See [`USER_GUIDE.md`](USER_GUIDE.md) for detailed troubleshooting.

## 📊 Models

| Model | Speed | Accuracy | Size |
|-------|-------|----------|------|
| base.en | ⚡⚡⚡ | ⭐⭐ | 142 MB |
| medium.en | ⚡⚡ | ⭐⭐⭐ | 1.5 GB |
| large-v3 | ⚡ | ⭐⭐⭐⭐ | 3.1 GB |

Default: `large-v3` (best accuracy)

## 🔐 Privacy

- ✅ 100% local processing
- ✅ No internet required
- ✅ No data collection
- ✅ No cloud services
- ✅ Open source

## 📝 License

MIT License - Based on [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)

## 🆘 Support

1. Check `flow.log` for errors
2. Run self-test with `F8`
3. See [`USER_GUIDE.md`](USER_GUIDE.md) for help

---

**Made with ❤️ for privacy-conscious users**

