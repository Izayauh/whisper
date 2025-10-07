import os, subprocess, time, threading, queue, datetime, shlex
import sys, shutil, tempfile, uuid
import sounddevice as sd
import soundfile as sf
import keyboard
import pyperclip
import pyautogui
import tkinter as tk
from tkinter import Canvas
import ctypes
import numpy as np
from PIL import Image
import pystray
import re

# Enable CUDA by default unless explicitly disabled via environment
os.environ.setdefault("GGML_CUDA_ENABLE", "1")
os.environ.setdefault("FLOW_WHISPER_BIN", r"C:\\Users\\isaia\\whisper.cpp\\build\\bin\\Release\\main.exe")
os.environ.setdefault("WHISPER_BIN", os.environ["FLOW_WHISPER_BIN"])
os.environ.setdefault("FLOW_WHISPER_ARGS", "-ngl 99")

_bin = os.environ.get("FLOW_WHISPER_BIN")
if _bin and not os.path.isfile(_bin):
    raise FileNotFoundError(f"FLOW_WHISPER_BIN not found: {_bin}")

# Prefer winotify for reliable Windows 10/11 notifications; fall back gracefully if unavailable
try:
    from winotify import Notification, audio
except Exception:
    Notification = None
    audio = None

# --- Single-instance guard (Windows) ---
import tempfile, uuid, msvcrt

_SINGLETON_LOCK = None
def _acquire_single_instance():
    global _SINGLETON_LOCK
    lock_path = os.path.join(tempfile.gettempdir(), "flow_local_dictation.lock")
    _SINGLETON_LOCK = open(lock_path, "w")
    try:
        msvcrt.locking(_SINGLETON_LOCK.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("Already running. Exiting.")
        sys.exit(0)

_acquire_single_instance()

# --- Config ---
MODEL_PATH_REL = os.path.join("models", "ggml-large-v3.bin")  # upgraded model for better accuracy
WHISPER_BIN = os.environ.get("WHISPER_BIN") or os.path.join(".", "main.exe")
SAMPLE_RATE = 16000
CHANNELS = 1
WAV_TMP = "flow_input.wav"
TEXT_TMP_BASE = "flow_out"  # base name for whisper-cli text output
HOTKEY_HOLD = "windows+ctrl"    # hold to talk; release to transcribe
NOTIFY = True

# --- Text Post-Processing Modes ---
# Smart, offline-only post-processing toggles
MODE_FILLER = True
MODE_PUNCT = True
MODE_BULLET_NEXT = False  # one-shot list maker (also triggered by keywords)

# --- Advanced Config ---
# Optional input device override: integer index or substring of device name.
# Can also be set via env var FLOW_INPUT_DEVICE (e.g., "2" or "USB").
INPUT_DEVICE = os.environ.get("FLOW_INPUT_DEVICE", None)

# Timeout for whisper subprocess (seconds)
WHISPER_TIMEOUT_SEC = 120

# Silence detection during recording (on normalized float32 audio)
SILENCE_RMS_THRESHOLD = 0.008
MIN_SPOKEN_BLOCKS = 3

# Log file for diagnostics
LOG_FILE = "flow.log"

# Whisper binary detection candidates (prefer whisper-cli.exe)
WHISPER_CANDIDATES = [
    os.path.join(".", "whisper-cli.exe"),
    os.path.join("whisper.cpp", "build", "bin", "Release", "whisper-cli.exe"),
    os.path.join("whisper.cpp", "build", "bin", "Debug", "whisper-cli.exe"),
]

# Resolved at startup
resolved_whisper_bin = None

# Concurrency & debounce
STATE_LOCK = threading.Lock()
transcribing_flag = threading.Event()
last_edge_ts = 0.0
EDGE_COOLDOWN_MS = 150

# GUI config
BAR_WIDTH = 220
BAR_HEIGHT = 18
BAR_MARGIN = 6  # distance from taskbar edge

recording_flag = threading.Event()
rec_thread = None
ui_queue = queue.Queue()

# Resolved device (set at startup diagnostics)
selected_input_device_idx = None
selected_input_device_name = None

# --- GUI overlay ---
class StatusBar:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.wm_attributes("-toolwindow", True)
        except Exception:
            pass
        self.root.configure(bg="#000000")
        self.canvas = Canvas(self.root, width=BAR_WIDTH, height=BAR_HEIGHT, highlightthickness=0, bg="#000000")
        self.canvas.pack()
        self.bg = self.canvas.create_rectangle(0, 0, BAR_WIDTH, BAR_HEIGHT, fill="#2b2b2b", outline="")
        self.text = self.canvas.create_text(BAR_WIDTH//2, BAR_HEIGHT//2, text="Idle", fill="#d9d9d9", font=("Segoe UI", 9))
        self.position_near_taskbar()

    def position_near_taskbar(self):
        # Place centered near taskbar edge using SHAppBarMessage
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_int), ("top", ctypes.c_int), ("right", ctypes.c_int), ("bottom", ctypes.c_int)]
        class APPBARDATA(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("hWnd", ctypes.c_void_p), ("uCallbackMessage", ctypes.c_uint), ("uEdge", ctypes.c_uint), ("rc", RECT), ("lParam", ctypes.c_int)]

        ABM_GETTASKBARPOS = 0x00000005
        ABE_LEFT, ABE_TOP, ABE_RIGHT, ABE_BOTTOM = 0, 1, 2, 3
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        res = shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd))
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)

        x = (sw - BAR_WIDTH) // 2
        y = sh - BAR_HEIGHT - BAR_MARGIN
        if res:
            edge = abd.uEdge
            rc = abd.rc
            if edge == ABE_BOTTOM:
                y = rc.top - BAR_HEIGHT - BAR_MARGIN
                x = (sw - BAR_WIDTH) // 2
            elif edge == ABE_TOP:
                y = rc.bottom + BAR_MARGIN
                x = (sw - BAR_WIDTH) // 2
            elif edge == ABE_LEFT:
                x = rc.right + BAR_MARGIN
                y = sh - BAR_HEIGHT - BAR_MARGIN
            elif edge == ABE_RIGHT:
                x = rc.left - BAR_WIDTH - BAR_MARGIN
                y = sh - BAR_HEIGHT - BAR_MARGIN

        self.root.geometry(f"{BAR_WIDTH}x{BAR_HEIGHT}+{x}+{y}")

    def set_status(self, text, color_bg, color_fg="#ffffff"):
        self.canvas.itemconfig(self.bg, fill=color_bg)
        self.canvas.itemconfig(self.text, text=text, fill=color_fg)
        # brief alpha pulse on updates (optional)
        try:
            self.root.attributes("-alpha", 0.98)
            self.root.after(80, lambda: self.root.attributes("-alpha", 1.0))
        except Exception:
            pass

    def pump_queue(self):
        try:
            while True:
                fn, args = ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(30, self.pump_queue)

    # context menu: open settings
    def bind_context_menu(self, on_settings):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Microphone Settings...", command=on_settings)
        menu.add_separator()
        menu.add_command(label="Exit", command=self.root.destroy)
        def _popup(event):
            menu.tk_popup(event.x_root, event.y_root)
        self.root.bind("<Button-3>", _popup)


# --- Helpers & Diagnostics ---
def res_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel)

# Resolve model path after res_path is defined
MODEL_PATH = res_path(os.path.join("models", "ggml-large-v3.bin"))
model_info_logged = False

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        msg = " ".join(str(a) for a in args)
        try:
            enc = sys.stdout.encoding or "utf-8"
        except Exception:
            enc = "utf-8"
        sys.stdout.write((msg + "\n").encode(enc, errors="replace").decode(errors="replace"))
def log_line(message):
    """Append a timestamped line to LOG_FILE and print it."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    safe_print(line)


def set_status_safe(text, bg, fg="#ffffff"):
    """Queue a status change without crashing on UI errors."""
    try:
        ui_queue.put((gui.set_status, (text, bg, fg)))
    except Exception:
        pass


def notify(msg):
    if NOTIFY:
        try:
            if Notification is not None:
                n = Notification(app_id="Flow (Local)", title="Flow (Local)", msg=msg)
                # Short non-looping sound for subtlety; ignored if audio is None
                if audio is not None:
                    n.set_audio(audio.SMS, loop=False)
                n.show()
        except Exception:
            pass
    log_line(msg)


def sanitize_transcript(text: str) -> str:
    """Remove banners, deprecation notices, and placeholder tokens from transcript."""
    if not text:
        return ""
    # Drop placeholder tokens
    text = text.replace("[BLANK_AUDIO]", "").replace("BLANK_AUDIO", "").strip()
    # Remove deprecation-warning banner lines if somehow present in text
    lines = []
    for ln in text.splitlines():
        lns = ln.strip()
        if not lns:
            continue
        low = lns.lower()
        if low.startswith("warning:"):
            continue
        if "deprecated" in low:
            continue
        if ("github.com/ggerganov/whisper.cpp" in low and "deprecation" in low) or ("see https://" in low and "deprecation" in low):
            continue
        # Explicitly drop the helper line of the banner
        if "please use" in low and "instead" in low:
            continue
        # Drop lines referencing the specific renamed binary suggestion
        if "whisper-cli.exe" in low or "binary 'main.exe'" in low:
            continue
        lines.append(lns)
    return "\n".join(lines).strip()


# --- Smart text post-processing helpers ---
FILLER_PATTERNS = [
    r"\b(?:um+|uh+)\b",
    r"\b(?:you know|ya know)\b",
    r"\b(?:i mean)\b",
    r"\b(?:kind of|kinda|sort of|sorta)\b",
    r"\b(?:like)\b(?!\s*(?:to|that|this|those|these|it|i|we|he|she|\d))",
]

def scrub_fillers(s: str) -> str:
    out = s
    for pat in FILLER_PATTERNS:
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out

COMMAND_REPLACERS = [
    (r"\bnew\s*line\b", "\n"),
    (r"\bnew\s*paragraph\b", "\n\n"),
    (r"\bcomma\b", ", "),
    (r"\bperiod\b", ". "),
    (r"\bexclamation\b", "! "),
    (r"\bquestion mark\b", "? "),
]

def apply_commands(s: str) -> str:
    out = s
    for pat, rep in COMMAND_REPLACERS:
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)
    return out

def autopunct_and_capitalize(s: str) -> str:
    parts = re.split(r"([.!?])", s)
    rebuilt = []
    for i in range(0, len(parts), 2):
        seg = parts[i].strip()
        if not seg:
            continue
        end = parts[i + 1] if i + 1 < len(parts) else ""
        if not end:
            end = "."
        seg = seg[0:1].upper() + seg[1:]
        rebuilt.append(seg + end + " ")
    return "".join(rebuilt).strip()

def to_bullets(s: str) -> str:
    if re.search(r"\b(bullets?|bullet\s*list|make\s+a\s+list|list:?)\b", s, re.IGNORECASE):
        s = re.sub(r"^\s*.*?(bullets?|list:?)\s*", "", s, flags=re.IGNORECASE)
    items = re.split(r",|\band\b", s)
    items = [it.strip(" .\t\r\n") for it in items if it.strip()]
    if len(items) <= 1:
        return s.strip()
    return "\n".join("- " + it for it in items)

def postprocess(text: str) -> str:
    return text  # no grammar, no filler, no bullets

def set_bullet_next():
    global MODE_BULLET_NEXT
    MODE_BULLET_NEXT = True
    notify("Bullet list on next paste")

def list_input_devices():
    """Return list of (index, name) for input-capable devices."""
    devices = []
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append((idx, dev.get("name", f"Device {idx}")))
    except Exception as e:
        notify(f"Device query error: {e}")
    return devices


def devices_summary_text():
    rows = []
    for idx, name in list_input_devices():
        mark = " (selected)" if idx == selected_input_device_idx else ""
        rows.append(f"[{idx}] {name}{mark}")
    return "\n".join(rows) if rows else "<no input devices>"


def device_index_and_names():
    """Return parallel lists of indices and labels for UI listbox/combobox."""
    pairs = list_input_devices()
    idxs = [p[0] for p in pairs]
    labels = [f"[{p[0]}] {p[1]}" for p in pairs]
    return idxs, labels


def resolve_input_device():
    """Resolve the input device index and validate settings. Sets globals."""
    global selected_input_device_idx, selected_input_device_name
    devices = list_input_devices()
    if not devices:
        notify("No input-capable audio devices found.")
        selected_input_device_idx = None
        selected_input_device_name = None
        return

    requested = INPUT_DEVICE
    idx = None
    name = None
    try:
        if requested is None or requested == "":
            # Use system default input device if available
            try:
                default_idx = None
                try:
                    default_idx = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
                except Exception:
                    default_idx = None
                if default_idx is not None and default_idx >= 0:
                    idx = int(default_idx)
                    name = sd.query_devices(idx).get("name", f"Device {idx}")
                else:
                    # fallback to first input device
                    idx, name = devices[0]
            except Exception:
                idx, name = devices[0]
        else:
            # Match by index or substring
            if isinstance(requested, str) and requested.isdigit():
                idx = int(requested)
                name = sd.query_devices(idx).get("name", f"Device {idx}")
            else:
                needle = str(requested).lower()
                for d_idx, d_name in devices:
                    if needle in str(d_name).lower():
                        idx, name = d_idx, d_name
                        break
                if idx is None:
                    # last resort: try int cast
                    try:
                        idx = int(requested)
                        name = sd.query_devices(idx).get("name", f"Device {idx}")
                    except Exception:
                        idx, name = devices[0]

        # Validate settings support
        sd.check_input_settings(device=idx, samplerate=SAMPLE_RATE, channels=CHANNELS)
        selected_input_device_idx = idx
        selected_input_device_name = name
        notify(f"Mic: {name}")
    except Exception as e:
        notify(f"Mic selection error: {e}")
        # Fallback to None to trigger later errors gracefully
        selected_input_device_idx = None
        selected_input_device_name = None


def startup_diagnostics():
    """Run preflight checks and print a concise summary."""
    issues = []
    # Files
    if not os.path.exists(MODEL_PATH):
        issues.append(f"Missing model at {MODEL_PATH}")
    # Resolve whisper binary
    global resolved_whisper_bin
    resolved_whisper_bin = None
    for candidate in WHISPER_CANDIDATES:
        if os.path.exists(candidate):
            resolved_whisper_bin = candidate
            break
    if resolved_whisper_bin is None:
        issues.append("Missing whisper binary (checked multiple locations)")
    else:
        log_line(f"Whisper bin: {resolved_whisper_bin}")

    # PortAudio / devices
    try:
        pa_ver = sd.get_portaudio_version()
        log_line(f"PortAudio: {pa_ver}")
    except Exception as e:
        issues.append(f"PortAudio error: {e}")

    # Resolve device and validate
    resolve_input_device()
    if selected_input_device_idx is None:
        issues.append("No working input device")
    else:
        try:
            sd.check_input_settings(device=selected_input_device_idx, samplerate=SAMPLE_RATE, channels=CHANNELS)
        except Exception as e:
            issues.append(f"Device unsupported @ {SAMPLE_RATE} Hz / {CHANNELS}ch: {e}")

    if issues:
        set_status_safe("Issues detected", "#faad14")
        for it in issues:
            log_line(f"DIAG: {it}")
            notify(it)
        # Also log available devices for quick troubleshooting
        log_line("Available input devices:\n" + devices_summary_text())
    else:
        msg = f"Ready (Mic: {selected_input_device_name})"
        set_status_safe(msg, "#2b2b2b", "#d9d9d9")
        log_line("Diagnostics OK")
        log_line("Available input devices:\n" + devices_summary_text())


def _resolve_whisper_exe(bin_path: str) -> str:
    """Resolve path to whisper binary, preferring env, then given path, then PATH, then known locations."""
    for key in ("FLOW_WHISPER_BIN", "WHISPER_BIN"):
        p = os.getenv(key)
        if p and os.path.isfile(p):
            return p
    # Accept explicit path (absolute or relative)
    if bin_path and os.path.isfile(bin_path):
        return bin_path
    w = shutil.which("main.exe") or shutil.which("whisper-cli.exe")
    if w:
        return w
    for p in (
        r"C:\\Users\\isaia\\whisper.cpp\\build\\bin\\Release\\main.exe",
        r"C:\\Users\\isaia\\whisper.cpp\\build\\bin\\Release\\whisper-cli.exe",
    ):
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Whisper binary not found (env, PATH, or known locations).")

def build_whisper_cmd(exe, model_path, wav_path, base_args=None):
    base_args = base_args or []
    extra_args = shlex.split(os.getenv("FLOW_WHISPER_ARGS", ""))

    # The legacy whisper-cli.exe does not accept GPU layer args like -ngl
    if os.path.basename(exe).lower() == "whisper-cli.exe":
        extra_args = [a for a in extra_args if a not in ("-ngl", "--n-gpu-layers")]
        return [exe, "-m", model_path, *base_args, *extra_args, wav_path]

    # main.exe accepts -f <wav>
    return [exe, "-m", model_path, "-f", wav_path, *base_args, *extra_args]

MIN_SEC = 0.4           # require at least 0.4s of voiced audio
RMS_THRESH = 0.005      # adjust to taste
PREROLL_SEC  = 2.0      # reserved: pre-roll buffer window (if trimming logic is added)
POSTROLL_SEC = 0.4      # keep recording briefly after release

def record_loop():
    """Record while recording_flag is set; write to WAV on stop with RMS gate."""
    log_line("[rec] start")
    notify("Listening...")
    data = []
    voiced_samples = 0
    block_dur = 0.1

    if selected_input_device_idx is None:
        set_status_safe("Mic not ready", "#fa541c")
        return

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", device=selected_input_device_idx) as stream:
            while recording_flag.is_set():
                try:
                    block, _ = stream.read(int(SAMPLE_RATE * block_dur))
                except Exception as e:
                    log_line(f"Audio read error: {e}")
                    set_status_safe("Audio read error", "#fa541c")
                    break
                data.append(block.copy())
                rms = float(np.sqrt(np.mean(block * block) + 1e-12))
                if rms > RMS_THRESH:
                    voiced_samples += block.shape[0]
    except Exception as e:
        log_line(f"Mic open error: {e}")
        set_status_safe("Mic open error", "#fa541c")
        return

    # If no audio or not enough voiced content, treat as silence
    if not data or (voiced_samples / SAMPLE_RATE) < MIN_SEC:
        safe_print("[rec] stop, no speech detected")
        try:
            if os.path.exists(WAV_TMP):
                os.remove(WAV_TMP)
        except Exception:
            pass
        set_status_safe("No speech", "#faad14")
        return

    try:
        audio = np.concatenate(data, axis=0)
        sf.write(WAV_TMP, audio, SAMPLE_RATE)
        safe_print(f"[rec] stop, saved: {WAV_TMP}")
    except Exception as e:
        log_line(f"WAV write error: {e}")
        set_status_safe("WAV write error", "#fa541c")


def open_settings_window(parent):
    win = tk.Toplevel(parent)
    win.title("Flow Microphone Settings")
    win.attributes("-topmost", True)
    try:
        win.wm_attributes("-toolwindow", True)
    except Exception:
        pass
    win.geometry("520x360")

    tk.Label(win, text="Select input device:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

    idxs, labels = device_index_and_names()
    var = tk.StringVar(value=labels)
    listbox = tk.Listbox(win, listvariable=var, height=10)
    listbox.pack(fill="both", expand=True, padx=10)

    # pre-select current if visible
    try:
        if selected_input_device_idx is not None:
            cur = f"[{selected_input_device_idx}]"
            for i, lab in enumerate(labels):
                if lab.startswith(cur):
                    listbox.selection_set(i)
                    listbox.see(i)
                    break
    except Exception:
        pass

    status = tk.Label(win, text="", fg="#888")
    status.pack(anchor="w", padx=10, pady=6)

    def do_refresh():
        nonlocal idxs, labels
        idxs, labels = device_index_and_names()
        var.set(labels)
        status.config(text="Device list refreshed")

    def do_apply():
        sel = listbox.curselection()
        if not sel:
            status.config(text="Select a device first")
            return
        idx = idxs[sel[0]]
        # override env and re-resolve
        os.environ["FLOW_INPUT_DEVICE"] = str(idx)
        resolve_input_device()
        if selected_input_device_idx == idx:
            status.config(text=f"Selected mic: {selected_input_device_name}")
        else:
            status.config(text="Failed to select device (see log)")

    def do_test():
        # quick 1s capture to check RMS
        if selected_input_device_idx is None:
            status.config(text="No device selected")
            return
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", device=selected_input_device_idx) as stream:
                block, _ = stream.read(int(SAMPLE_RATE * 0.5))
                block_f = block.astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(block_f * block_f) + 1e-12))
                status.config(text=f"RMS: {rms:.4f} (threshold {SILENCE_RMS_THRESHOLD})")
        except Exception as e:
            status.config(text=f"Test error: {e}")

    btns = tk.Frame(win)
    btns.pack(fill="x", padx=10, pady=8)
    tk.Button(btns, text="Refresh", command=do_refresh).pack(side="left")
    tk.Button(btns, text="Apply", command=do_apply).pack(side="left", padx=6)
    tk.Button(btns, text="Test", command=do_test).pack(side="left")
    tk.Button(btns, text="Close", command=win.destroy).pack(side="right")

def start_recording():
    global rec_thread
    with STATE_LOCK:
        if recording_flag.is_set() or transcribing_flag.is_set():
            return
        # remove stale wav
        try:
            if os.path.exists(WAV_TMP):
                os.remove(WAV_TMP)
        except Exception:
            pass
        recording_flag.set()
    set_status_safe("Listening...", "#d4380d")
    rec_thread = threading.Thread(target=record_loop, daemon=True)
    rec_thread.start()

def run_whisper(filename, bin_path):
    # Resolve executable and ensure DLLs are found by running in its directory
    exe = os.path.abspath(_resolve_whisper_exe(bin_path))
    workdir = os.path.dirname(exe) or "."

    # Output transcript file in temp directory
    out_txt = os.path.join(tempfile.gettempdir(), f"flow_out_{uuid.uuid4().hex}.txt")

    # Clean any stale file before run
    try:
        if os.path.exists(out_txt):
            os.remove(out_txt)
    except Exception:
        pass

    # Build command: write a .txt and specify output file (without extension)
    global model_info_logged
    if not model_info_logged:
        safe_print(f"MODEL_PATH -> {MODEL_PATH}")
        try:
            sz = os.path.getsize(MODEL_PATH)
            safe_print(f"MODEL_SIZE -> {sz/1_000_000:.1f} MB")
        except Exception:
            pass
        model_info_logged = True

    # Threading and optional accuracy mode for long dictations
    num_threads = str(os.cpu_count() or 4)
    cmd = build_whisper_cmd(
        exe,
        MODEL_PATH,
        filename,
        base_args=[
            "-l", "en",
            "-nt",
            "-mc", "0",
            "-bs", "5",
            "-t", num_threads,
            "-nfa",
            "-otxt", "-of", out_txt[:-4],
        ],
    )

    # Optional accuracy mode for long dictations (>15s)
    try:
        duration_sec = None
        try:
            info = sf.info(filename)
            if getattr(info, "samplerate", 0) and getattr(info, "frames", 0):
                duration_sec = info.frames / float(info.samplerate)
        except Exception:
            duration_sec = None
        if duration_sec is not None and duration_sec >= 15:
            cmd[cmd.index("-bs")+1] = "10"   # bs -> 10
            cmd.extend(["-bo", "10"])        # best-of -> 10
            safe_print("[whisper] accuracy mode: bs=10, bo=10")
    except Exception:
        pass

    env = os.environ.copy()
    env["GGML_CUDA_FORCE_CUBLAS"] = "1"   # avoid flash-attn kernel assert on RTX 20-series
    log_line(f"DEBUG exe = {exe}")
    log_line(f"DEBUG wav_path = {filename}")
    log_line(f"DEBUG cmd = {cmd}")

    res = subprocess.run(
        cmd,
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def _looks_cuda_assert(s: str) -> bool:
        return ("GGML_ASSERT" in (s or "")) or ("Incorrect KV cache padding" in (s or ""))

    if res.returncode != 0 or _looks_cuda_assert(res.stderr):
        safe_print("[whisper] CUDA failed; retrying on CPU")
        cmd_cpu = build_whisper_cmd(
            exe,
            MODEL_PATH,
            filename,
            base_args=["-l", "en", "-nt", "-mc", "0", "-bs", "5", "-otxt", "-of", out_txt[:-4], "--no-gpu"],
        )
        res = subprocess.run(
            cmd_cpu,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    safe_print(f"[whisper] exit={res.returncode} stdout={len(res.stdout)}B stderr={len(res.stderr)}B out='{out_txt}'")

    # Prefer reading from file; fallback to stdout, then log stderr head if still empty
    text = ""
    try:
        if os.path.exists(out_txt):
            with open(out_txt, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
    except Exception as e:
        safe_print(f"[whisper] read file error: {e}")

    if not text:
        text = (res.stdout or "").strip()

    # Defensive retry on usage/arg errors (prevents empty pastes)
    def _looks_bad(s: str) -> bool:
        s = (s or "").lower()
        return "usage:" in s or "unknown argument" in s

    if not text and _looks_bad(res.stderr):
        safe_print("[whisper] bad-args fallback")
        cmd_fallback = build_whisper_cmd(
            exe,
            MODEL_PATH,
            filename,
            base_args=["-l", "en", "-nt", "-bs", "5", "-otxt", "-of", out_txt[:-4]],
        )
        res = subprocess.run(
            cmd_fallback,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            if os.path.exists(out_txt):
                with open(out_txt, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
        except Exception:
            pass
        if not text:
            text = (res.stdout or "").strip()

    if not text:
        safe_print("[whisper] empty transcript; stderr head:")
        safe_print((res.stderr or "")[:500])

    return res.returncode, text, (res.stderr or "").strip()


def _transcribe_and_paste(wav_path):
    safe_print("[whisper] running...")
    bin_path = (resolved_whisper_bin or WHISPER_BIN)
    rc, out, err = run_whisper(wav_path, bin_path)

    # Bail on failure
    if rc != 0:
        notify("Transcription failed")
        safe_print(f"[whisper] exit={rc} stderr={err[:400]}")
        return

    # Sanitize output
    raw = (out or "").strip()
    text = sanitize_transcript(raw)

    def _dedupe_lines(s: str) -> str:
        seen = []
        for ln in s.splitlines():
            if not seen or seen[-1] != ln:
                seen.append(ln)
        return "\n".join(seen)

    text = _dedupe_lines(text)

    banned = {"[ Silence ]", "[silence]", ""}
    if text in banned or len(text.replace("\n","" ).strip()) == 0:
        notify("Nothing to paste (empty transcript)")

    try:
        # Smart offline post-processing right before copy/paste
        text = postprocess(text)
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        notify("Pasted OK")
        safe_print("Pasted OK")
    except Exception as e:
        safe_print(f"Paste error: {e}")
        notify("Copy/Paste error")


def stop_recording_and_transcribe():
    with STATE_LOCK:
        if not recording_flag.is_set() or transcribing_flag.is_set():
            return
        # mark transcribing first so we don't allow a new recording to start
        transcribing_flag.set()

    # Post-roll: keep capturing briefly after key release before we stop
    try:
        time.sleep(POSTROLL_SEC)
    except Exception:
        pass

    with STATE_LOCK:
        recording_flag.clear()

    if rec_thread:
        rec_thread.join()

    # If file missing or too small, treat as silence
    if not os.path.exists(WAV_TMP) or os.path.getsize(WAV_TMP) < 1024:
        try:
            if os.path.exists(WAV_TMP):
                os.remove(WAV_TMP)
        except Exception:
            pass
        notify("No speech detected")
        with STATE_LOCK:
            transcribing_flag.clear()
        return

    _transcribe_and_paste(WAV_TMP)

    with STATE_LOCK:
        transcribing_flag.clear()

def on_hotkey_press(e):
    # Debounce: only start if not already recording
    if not recording_flag.is_set():
        start_recording()

def on_hotkey_release(e):
    # Only stop if we are recording
    if recording_flag.is_set():
        stop_recording_and_transcribe()


# --- Diagnostics: self-test and debug probe (non-F-key capable) ---
def self_test_jfk():
    sample = os.path.join("whisper.cpp", "samples", "jfk.wav")
    if not os.path.exists(sample):
        notify("Self-test sample not found: whisper.cpp/samples/jfk.wav")
        return
    if resolved_whisper_bin is None and not os.path.exists(WHISPER_BIN):
        notify("No whisper binary available for self-test")
        return
    exe = os.path.abspath(_resolve_whisper_exe(resolved_whisper_bin or WHISPER_BIN))
    cmd = build_whisper_cmd(exe, MODEL_PATH, sample, base_args=["-nt"]) 
    log_line("[self-test] running: " + " ".join(cmd))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=WHISPER_TIMEOUT_SEC)
        out = (res.stdout or "").strip() or (res.stderr or "").strip()
        if out:
            notify("Self-test OK (see log)")
            log_line("[self-test-output]\n" + out)
        else:
            notify("Self-test produced no output")
    except Exception as e:
        notify(f"Self-test error: {e}")


def run_debug_probe():
    sample = os.path.join("whisper.cpp", "samples", "jfk.wav")
    if not os.path.exists(sample):
        notify("Debug: sample not found whisper.cpp/samples/jfk.wav")
        return
    candidates = []
    if os.path.exists(os.path.join(".", "main.exe")):
        candidates.append(os.path.join(".", "main.exe"))
    if os.path.exists(os.path.join(".", "whisper-cli.exe")):
        candidates.append(os.path.join(".", "whisper-cli.exe"))
    if not candidates:
        notify("Debug: no local main.exe or whisper-cli.exe found")
        return
    os.makedirs("debug", exist_ok=True)
    for bin_path in candidates:
        name = os.path.basename(bin_path)
        exe = os.path.abspath(_resolve_whisper_exe(bin_path))
        cmd = build_whisper_cmd(exe, MODEL_PATH, sample, base_args=["-nt"]) 
        log_line(f"[debug] running: {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=WHISPER_TIMEOUT_SEC)
            raw = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
            san = sanitize_transcript(raw)
            with open(os.path.join("debug", f"flow_debug_{name}_raw.txt"), "w", encoding="utf-8") as f:
                f.write(raw)
            with open(os.path.join("debug", f"flow_debug_{name}_sanitized.txt"), "w", encoding="utf-8") as f:
                f.write(san)
            banner_present = ("deprecated" in raw.lower()) or ("please use" in raw.lower())
            log_line(f"[debug] {name}: rc={res.returncode} banner={'yes' if banner_present else 'no'}; files in ./debug/")
        except Exception as e:
            log_line(f"[debug] error running {name}: {e}")
    notify("Debug probe complete (see ./debug and log)")

tray_icon = None
listening_enabled = True

def _tray_update(title="Flow Local", text="Idle"):
    try:
        if tray_icon:
            tray_icon.title = f"{title} — {text}"
    except Exception:
        pass

def _tray_toggle(_=None):
    global listening_enabled
    listening_enabled = not listening_enabled
    _tray_update(text=("Listening" if listening_enabled else "Paused"))

def _tray_selftest(_=None):
    try:
        self_test_jfk()
    except Exception as e:
        safe_print(f"Self-test error: {e}")

def _tray_debug(_=None):
    try:
        run_debug_probe()
    except Exception as e:
        safe_print(f"Debug error: {e}")

def _tray_quit(_=None):
    try:
        if recording_flag.is_set():
            stop_recording_and_transcribe()
    finally:
        os._exit(0)

def start_tray():
    global tray_icon
    icon_path = res_path("whisper.ico")
    try:
        img = Image.open(icon_path)
    except Exception:
        img = Image.new("RGBA", (16,16), (0,0,0,0))
    tray_icon = pystray.Icon(
        "Flow Local",
        img,
        "Flow Local",
        menu=pystray.Menu(
            pystray.MenuItem("Toggle Listening", _tray_toggle, default=True),
            pystray.MenuItem("Self-test (JFK)", _tray_selftest),
            pystray.MenuItem("Run Debug Probe", _tray_debug),
            pystray.MenuItem("Quit", _tray_quit)
        )
    )
    tray_icon.run_detached()
    _tray_update(text="Listening")

def main():
    safe_print("Flow-style local dictation running.")
    safe_print("Hold CTRL + WIN to talk; release to paste.")
    safe_print("Press ESC to exit.")
    # Init GUI and polling loop in the Tk main thread
    global gui
    gui = StatusBar()
    gui.set_status("Idle", "#2b2b2b", "#d9d9d9")
    gui.bind_context_menu(lambda: open_settings_window(gui.root))

    # Run diagnostics after UI ready so we can display status
    startup_diagnostics()
    # Show a brief summary to the user
    try:
        device_lines = devices_summary_text()
        notify("Startup OK. Press and hold Win+Ctrl to speak.")
        log_line("Startup devices:\n" + device_lines)
    except Exception:
        pass

    was_down = False

    # Hotkeys: F-keys and non-F-key alternates
    keyboard.on_press_key("f8", lambda e: threading.Thread(target=self_test_jfk, daemon=True).start())
    keyboard.on_press_key("f9", lambda e: threading.Thread(target=run_debug_probe, daemon=True).start())
    keyboard.add_hotkey("ctrl+alt+j", lambda: threading.Thread(target=self_test_jfk, daemon=True).start())
    keyboard.add_hotkey("ctrl+alt+d", lambda: threading.Thread(target=run_debug_probe, daemon=True).start())
    keyboard.add_hotkey("ctrl+alt+b", lambda: set_bullet_next())

    def poll_hotkey():
        nonlocal was_down
        global last_edge_ts
        try:
            down = listening_enabled and keyboard.is_pressed("windows") and keyboard.is_pressed("ctrl")
        except Exception:
            down = False
        # Open settings with Win+Ctrl+S
        try:
            if (keyboard.is_pressed("windows") and keyboard.is_pressed("ctrl") and keyboard.is_pressed("s")):
                open_settings_window(gui.root)
        except Exception:
            pass
        now = time.time()
        if down and not was_down and (now - last_edge_ts) * 1000 > EDGE_COOLDOWN_MS:
            last_edge_ts = now
            on_hotkey_press(None)
        if (not down) and was_down and (now - last_edge_ts) * 1000 > EDGE_COOLDOWN_MS:
            last_edge_ts = now
            # offload stop+transcribe so UI stays responsive
            threading.Thread(target=stop_recording_and_transcribe, daemon=True).start()
        was_down = down
        # ESC to exit
        try:
            if keyboard.is_pressed("esc"):
                gui.root.destroy()
                return
        except Exception:
            pass
        gui.root.after(10, poll_hotkey)

    gui.pump_queue()
    gui.root.after(10, poll_hotkey)
    gui.root.mainloop()
    # cleanup after GUI closes
    if recording_flag.is_set():
        stop_recording_and_transcribe()
    safe_print("Bye.")

if __name__ == "__main__":
    start_tray()
    main()


