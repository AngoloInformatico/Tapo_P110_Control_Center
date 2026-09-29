import sys
import os
import json
from pathlib import Path

exe_dir = Path(os.path.dirname(sys.executable)) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

if getattr(sys, "frozen", False):
    # PyInstaller temporary bundle directory for read-only assets
    BASE_DIR = Path(sys._MEIPASS)
    # Persistent writable data folder next to the .exe
    DATA_DIR = exe_dir / "data"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"

from core.version_manager import get_version

# Search for Codex_Work/settings.json in multiple likely locations:
possible_codex_paths = [
    exe_dir / "Codex_Work" / "settings.json",
    exe_dir.parent.parent / "Codex_Work" / "settings.json",
    Path(__file__).resolve().parent.parent / "Codex_Work" / "settings.json",
    BASE_DIR / "Codex_Work" / "settings.json"
]

CODEX_SETTINGS = None
for p in possible_codex_paths:
    if p.exists():
        CODEX_SETTINGS = p
        break

CONFIG_FILE = DATA_DIR / "settings.json"


DEFAULT_CONFIG = {
    "ip": "",
    "email": "",
    "password": "",
    "device_name": "Tapo P110",
    "demo_mode": True,
    "poll_interval": 4.0,
    "host": "127.0.0.1",
    "port": 8000,
    "theme": "cyber",
    "minimize_to_tray": False,
    "minimize_on_start": False,
    "start_with_windows": False,
    "show_desktop_gadget": False
}

def set_start_with_windows(enable: bool) -> bool:
    """Configura l'avvio automatico con Windows nel Registro di sistema."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "TapoP110ControlCenter"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}"'
                else:
                    cmd = f'"{sys.executable}" "{Path(__file__).resolve().parent.parent / "main.py"}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        return False

def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Se esiste un settings.json in DATA_DIR, carichiamo
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass

    # 2. Se in ambiente di sviluppo (sorgenti), fallback su CODEX_SETTINGS
    if not getattr(sys, "frozen", False) and CODEX_SETTINGS and CODEX_SETTINGS.exists():
        try:
            with open(CODEX_SETTINGS, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass

    # 3. Fallback sul file di default
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    # Se presente Codex_Work, mantieni sincronizzato anche lì
    if CODEX_SETTINGS and CODEX_SETTINGS.exists():
        try:
            with open(CODEX_SETTINGS, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
        except Exception:
            pass

