"""
=============================================================================
 GeneraExe.py — Compilatore per Tapo P110 Control Center (Windows 11)
 Genera l'eseguibile standalone .exe in cartella 'dist/' senza console.
 Autore: Alex Lignola - © 2026 Angolo Informatico
=============================================================================
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR / "Icona" / "icon.ico"
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
EXE_NAME = "Tapo P110 Control Center"

from core.version_manager import increment_version, get_version

def check_requirements():
    print("=" * 70)
    print("      COMPILAZIONE ESEGUIBILE: TAPO P110 CONTROL CENTER")
    print("=" * 70)
    
    # 1. Termina eventuali processi precedenti attivi che bloccano i file in dist/
    try:
        subprocess.run(["powershell", "-Command", "Get-Process | Where-Object { $_.ProcessName -like '*Tapo P110*' } | Stop-Process -Force -ErrorAction SilentlyContinue"], capture_output=True)
    except Exception:
        pass
    
    import time
    time.sleep(1)

    # 2. Cancella COMPLETAMENTE l'intero contenuto della cartella dist/
    if DIST_DIR.exists():
        print(f"[INFO] Pulizia completa contenuto cartella dist/ ({DIST_DIR})...")
        for item in DIST_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except Exception as e_del:
                print(f"[WARN] Impossibile eliminare {item.name}: {e_del}")
    else:
        DIST_DIR.mkdir(parents=True, exist_ok=True)
    print("[OK] Cartella dist/ pulita.")

    # 3. Pulisci anche la cartella build/
    if BUILD_DIR.exists():
        try:
            shutil.rmtree(BUILD_DIR, ignore_errors=True)
        except Exception:
            pass

    if not ICON_PATH.exists():
        print(f"[ERRORE] File icona non trovato in: {ICON_PATH}")
        sys.exit(1)
    print(f"[OK] Icona trovata: {ICON_PATH}")

def build_executable():
    new_v = increment_version()
    print(f"\n[INFO] Auto-incremento versione eseguito: v{new_v}")
    print("[INFO] Avvio compilazione con PyInstaller...")
    
    # Usa l'interprete dell'ambiente virtuale se presente per garantire la presenza di tutte le dipendenze
    py_exec = sys.executable
    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        py_exec = str(venv_py)
    
    # Argomenti PyInstaller
    cmd = [
        py_exec,
        "-m", "PyInstaller",
        "--name", EXE_NAME,
        "--noconsole",                # Nessuna finestra terminale all'avvio
        "--icon", str(ICON_PATH),     # Icona dell'applicazione
        "--clean",
        "--noconfirm",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        
        # Inclusione cartelle dati e risorse
        "--add-data", f"{BASE_DIR / 'static'};static",
        "--add-data", f"{BASE_DIR / 'core'};core",
        "--add-data", f"{BASE_DIR / 'Icona'};Icona",
        "--add-data", f"{BASE_DIR / 'version.json'};.",
        
        # Hidden imports e collezioni complete per FastAPI, Uvicorn, WebSockets, PyWebView e Kasa
        "--hidden-import", "uvicorn",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "websockets",
        "--hidden-import", "webview",
        "--collect-all", "webview",
        "--collect-all", "clr_loader",
        "--collect-all", "pythonnet",
        "--collect-all", "pystray",
        "--collect-all", "kasa",
        "--hidden-import", "mashumaro",
        "--hidden-import", "aiohttp",
        "--hidden-import", "asyncclick",
        "--hidden-import", "tapo",
        "--hidden-import", "PyP100",
        "--hidden-import", "sqlite3",
        "--hidden-import", "clr_loader",
        "--hidden-import", "pythonnet",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "winreg",
        
        # Script principale
        str(BASE_DIR / "main.py")
    ]
    
    print("[CMD] " + " ".join(cmd[:10]) + " ...")
    ret = subprocess.run(cmd)
    
    if ret.returncode == 0:
        exe_output_dir = DIST_DIR / EXE_NAME
        # In dist/data/settings.json genera una configurazione pulita senza credenziali e con demo_mode: True
        dist_data_dir = exe_output_dir / "data"
        dist_data_dir.mkdir(parents=True, exist_ok=True)
        clean_dist_config = {
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
        with open(dist_data_dir / "settings.json", "w", encoding="utf-8") as f:
            import json
            json.dump(clean_dist_config, f, indent=4)
        print(f"[OK] settings.json sicuro per GitHub generato in {dist_data_dir / 'settings.json'} (Demo Mode: True)")

        # Pulisci file db e log residui in dist
        for p in dist_data_dir.glob("*.db*"):
            try: p.unlink()
            except Exception: pass
        for p in dist_data_dir.glob("*.log"):
            try: p.unlink()
            except Exception: pass

        print("\n" + "=" * 70)
        print(f" [SUCCESSO] Eseguibile generato con successo!")
        print(f" Percorso file: {exe_output_dir / (EXE_NAME + '.exe')}")
        print("=" * 70)
    else:
        print(f"\n[ERRORE] Compilazione fallita con codice {ret.returncode}")
        sys.exit(ret.returncode)


if __name__ == "__main__":
    check_requirements()
    build_executable()
