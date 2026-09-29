import os
import sys
import asyncio
import logging
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.config import load_config, save_config, BASE_DIR, DATA_DIR, set_start_with_windows
from core.database import (
    init_db, get_recent_samples, get_yearly_monthly_totals, get_days_for_month,
    export_history_data, import_history_data
)
from core.tapo_service import tapo_service

# Safe stream redirection for GUI / frozen executable mode
DATA_DIR.mkdir(parents=True, exist_ok=True)
log_file_path = DATA_DIR / "app.log"
log_handlers = [logging.FileHandler(str(log_file_path), encoding="utf-8")]

class SafeStreamWriter:
    def __init__(self, log_path):
        self.log_path = log_path
    def write(self, s):
        if not s:
            return
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(s)
        except Exception:
            pass
    def flush(self):
        pass
    def isatty(self):
        return False
    def fileno(self):
        return -1
    @property
    def encoding(self):
        return "utf-8"

if sys.stdout is not None:
    log_handlers.append(logging.StreamHandler(sys.stdout))
else:
    sys.stdout = SafeStreamWriter(log_file_path)
    sys.stderr = SafeStreamWriter(log_file_path)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers
)
logger = logging.getLogger("main")


# Background polling lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await tapo_service.initialize()
    poll_task = asyncio.create_task(tapo_service.start_polling_loop())
    yield
    tapo_service.stop_polling()
    poll_task.cancel()

app = FastAPI(title="Tapo P110 Control Center", lifespan=lifespan)

# Mount static files
static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

icon_dir = BASE_DIR / "Icona"
if icon_dir.exists():
    app.mount("/Icona", StaticFiles(directory=str(icon_dir)), name="icona")

@app.get("/favicon.ico")
async def favicon():
    icon_path = BASE_DIR / "Icona" / "icon.ico"
    if icon_path.exists():
        return FileResponse(str(icon_path))
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))

@app.get("/gadget")
async def gadget_view():
    gadget_path = static_dir / "gadget.html"
    if gadget_path.exists():
        return FileResponse(str(gadget_path))
    return FileResponse(str(static_dir / "index.html"))

_desktop_main_window = None
_desktop_gadget_window = None
_tray_instance = None

@app.post("/api/app/open-dashboard")
async def open_dashboard_endpoint():
    global _desktop_main_window, _desktop_gadget_window
    if _desktop_gadget_window:
        try:
            _desktop_gadget_window.hide()
        except Exception:
            pass
    if _desktop_main_window:
        try:
            _desktop_main_window.show()
            _desktop_main_window.restore()
        except Exception:
            pass
    return {"success": True}

@app.post("/api/app/minimize-dashboard")
async def minimize_dashboard_endpoint():
    global _desktop_main_window, _desktop_gadget_window
    cfg = load_config()
    if _desktop_main_window:
        try:
            _desktop_main_window.hide()
        except Exception:
            pass
    if _desktop_gadget_window and cfg.get("show_desktop_gadget", False):
        try:
            _desktop_gadget_window.show()
            _desktop_gadget_window.restore()
        except Exception:
            pass
    return {"success": True}

@app.post("/api/app/hide-gadget")
async def hide_gadget_endpoint():
    global _desktop_gadget_window
    cfg = load_config()
    cfg["show_desktop_gadget"] = False
    save_config(cfg)
    logger.info("Richiesta di nascondere il Desktop Gadget ricevuta")
    if _desktop_gadget_window:
        try:
            _desktop_gadget_window.hide()
            logger.info("Desktop Gadget nascosto con successo")
        except Exception as e:
            logger.error(f"Errore durante hide() del gadget: {e}")
    return {"success": True}

@app.post("/api/app/exit")
async def exit_app_endpoint():
    global _desktop_main_window, _desktop_gadget_window, _tray_instance
    logger.info("Richiesta di uscita totale dall'applicazione ricevuta")
    def _do_exit():
        import time, os
        time.sleep(0.1)
        if _tray_instance:
            try:
                _tray_instance.visible = False
                _tray_instance.stop()
            except Exception:
                pass
        try:
            if _desktop_gadget_window:
                _desktop_gadget_window.destroy()
        except Exception:
            pass
        try:
            if _desktop_main_window:
                _desktop_main_window.destroy()
        except Exception:
            pass
        os._exit(0)
    import threading
    threading.Thread(target=_do_exit, daemon=True).start()
    return {"success": True}

@app.get("/api/status")
async def get_status():
    return tapo_service.get_state_payload()

class PowerRequest(BaseModel):
    state: bool

@app.post("/api/power")
async def set_power(req: PowerRequest):
    success = await tapo_service.set_power(req.state)
    return {
        "success": success,
        "state": tapo_service.get_state_payload()
    }

@app.get("/api/history/recent")
async def get_recent_history():
    samples = get_recent_samples(limit=60)
    return {
        "samples": samples
    }

@app.get("/api/history/monthly")
async def get_monthly_history(year: int = 2026):
    data = get_yearly_monthly_totals(year)
    return {
        "year": year,
        "months": data
    }

@app.get("/api/history/days")
async def get_days_history(year: int = 2026, month: int = 9):
    data = get_days_for_month(year, month)
    return {
        "year": year,
        "month": month,
        "days": data
    }

class SettingsRequest(BaseModel):
    ip: str = ""
    email: str = ""
    password: str = ""
    demo_mode: bool = False
    device_name: str = "Tapo P110"
    minimize_to_tray: bool = False
    minimize_on_start: bool = False
    start_with_windows: bool = False
    show_desktop_gadget: bool = False

@app.get("/api/settings")
async def get_settings():
    cfg = load_config()
    safe_cfg = cfg.copy()
    if safe_cfg.get("password"):
        safe_cfg["password_set"] = True
        safe_cfg["password"] = "******"
    else:
        safe_cfg["password_set"] = False
    return JSONResponse(
        content=safe_cfg,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
    )

@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    cfg = load_config()
    cfg["ip"] = req.ip.strip()
    cfg["email"] = req.email.strip()
    if req.password == "":
        cfg["password"] = ""
    elif req.password and req.password != "******":
        cfg["password"] = req.password
    cfg["demo_mode"] = req.demo_mode
    if req.device_name:
        cfg["device_name"] = req.device_name.strip()
    
    cfg["minimize_to_tray"] = req.minimize_to_tray
    cfg["minimize_on_start"] = req.minimize_on_start
    cfg["start_with_windows"] = req.start_with_windows
    cfg["show_desktop_gadget"] = req.show_desktop_gadget
    save_config(cfg)

    # Configura avvio automatico con Windows nel Registro
    set_start_with_windows(req.start_with_windows)
    
    # Riconnetti se non in demo mode
    if not cfg["demo_mode"] and cfg["ip"] and cfg["email"]:
        await tapo_service.connect_device(cfg["ip"], cfg["email"], cfg.get("password", ""))
    elif cfg["demo_mode"]:
        await tapo_service.initialize()
        
    # Aggiorna istantaneamente lo stato del gadget desktop senza riavvio
    global _desktop_gadget_window
    if _desktop_gadget_window:
        if req.show_desktop_gadget:
            try:
                _desktop_gadget_window.show()
                _desktop_gadget_window.restore()
            except Exception:
                pass
        else:
            try:
                _desktop_gadget_window.hide()
            except Exception:
                pass

    return {
        "success": True,
        "state": tapo_service.get_state_payload(),
        "config": cfg
    }

def _ask_save_path_tk():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.asksaveasfilename(
            title="Salva Profilo Tapo",
            defaultextension=".json",
            filetypes=[("File JSON (*.json)", "*.json"), ("Tutti i file (*.*)", "*.*")],
            initialfile="settings.json"
        )
        root.destroy()
        return path if path else None
    except Exception as e:
        logger.error(f"Errore visualizzazione finestra salvataggio: {e}")
        return None

def _ask_open_path_tk():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Carica Profilo Tapo (settings.json)",
            filetypes=[("File JSON (*.json)", "*.json"), ("Tutti i file (*.*)", "*.*")]
        )
        root.destroy()
        return path if path else None
    except Exception as e:
        logger.error(f"Errore visualizzazione finestra apertura: {e}")
        return None

class ProfileSaveRequest(BaseModel):
    ip: str = ""
    email: str = ""
    password: str = ""
    device_name: str = "Tapo P110"
    demo_mode: bool = False
    theme: str = "cyber"
    minimize_to_tray: bool = False
    minimize_on_start: bool = False
    start_with_windows: bool = False
    show_desktop_gadget: bool = False

@app.post("/api/profile/save-dialog")
async def save_profile_dialog(req: ProfileSaveRequest):
    import json
    cfg = load_config()
    real_password = req.password
    if not real_password or real_password == "******":
        real_password = cfg.get("password", "")

    file_path = await asyncio.to_thread(_ask_save_path_tk)
    if not file_path:
        return {"success": False, "cancelled": True}

    save_data = {
        "ip": req.ip.strip(),
        "email": req.email.strip(),
        "password": real_password,
        "device_name": req.device_name.strip() if req.device_name else "Tapo P110",
        "demo_mode": False,
        "poll_interval": cfg.get("poll_interval", 2.0),
        "host": cfg.get("host", "127.0.0.1"),
        "port": cfg.get("port", 8000),
        "theme": req.theme or cfg.get("theme", "cyber"),
        "minimize_to_tray": req.minimize_to_tray,
        "minimize_on_start": req.minimize_on_start,
        "start_with_windows": req.start_with_windows,
        "show_desktop_gadget": req.show_desktop_gadget,
        # CRITICO: Salvataggio cronologia completa consumi e grafici nel profilo
        "history": export_history_data()
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=4)
        return {"success": True, "path": file_path, "filename": Path(file_path).name}
    except Exception as e:
        logger.error(f"Errore salvataggio profilo in {file_path}: {e}")
        return {"success": False, "error": str(e)}

async def apply_loaded_profile(loaded_data: dict, file_name: str = "settings.json"):
    cfg = load_config()
    cfg["ip"] = loaded_data.get("ip", "").strip()
    cfg["email"] = loaded_data.get("email", "").strip()
    if "password" in loaded_data:
        cfg["password"] = loaded_data["password"]
    if "device_name" in loaded_data and loaded_data["device_name"]:
        cfg["device_name"] = loaded_data["device_name"].strip()
    
    # Tema salvato nel profilo
    if "theme" in loaded_data and loaded_data["theme"]:
        cfg["theme"] = loaded_data["theme"]
    
    # Opzioni aggiuntive
    for opt in ["minimize_to_tray", "minimize_on_start", "start_with_windows", "show_desktop_gadget"]:
        if opt in loaded_data:
            cfg[opt] = bool(loaded_data[opt])
    
    # CRITICO: la modalità demo DEVE essere disattivata quando si richiama il file
    cfg["demo_mode"] = False
    save_config(cfg)

    # Configura subito l'avvio con Windows
    set_start_with_windows(cfg.get("start_with_windows", False))

    # Ripristino cronologia grafici e consumi nel database SQLite
    if "history" in loaded_data and isinstance(loaded_data["history"], dict):
        import_history_data(loaded_data["history"])

    # Riconnetti subito la presa con le nuove credenziali
    if cfg["ip"] and cfg["email"]:
        await tapo_service.connect_device(cfg["ip"], cfg["email"], cfg.get("password", ""))
    else:
        await tapo_service.initialize()

    # Aggiorna istantaneamente lo stato del gadget desktop senza richiedere riavvio!
    global _desktop_gadget_window
    if _desktop_gadget_window:
        if cfg.get("show_desktop_gadget", False):
            try:
                _desktop_gadget_window.show()
                _desktop_gadget_window.restore()
            except Exception as eg:
                logger.warning(f"Errore visualizzazione gadget: {eg}")
        else:
            try:
                _desktop_gadget_window.hide()
            except Exception:
                pass

    return {
        "success": True,
        "filename": file_name,
        "config": {
            "ip": cfg.get("ip", ""),
            "email": cfg.get("email", ""),
            "password": cfg.get("password", ""),
            "device_name": cfg.get("device_name", "Tapo P110"),
            "theme": cfg.get("theme", "cyber"),
            "demo_mode": False,
            "minimize_to_tray": cfg.get("minimize_to_tray", False),
            "minimize_on_start": cfg.get("minimize_on_start", False),
            "start_with_windows": cfg.get("start_with_windows", False),
            "show_desktop_gadget": cfg.get("show_desktop_gadget", False)
        },
        "state": tapo_service.get_state_payload()
    }

@app.post("/api/profile/load-dialog")
async def load_profile_dialog():
    import json
    file_path = await asyncio.to_thread(_ask_open_path_tk)
    if not file_path:
        return {"success": False, "cancelled": True}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)

        return await apply_loaded_profile(loaded_data, Path(file_path).name)
    except Exception as e:
        logger.error(f"Errore lettura profilo da {file_path}: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/profile/load-data")
async def load_profile_data(data: dict):
    try:
        return await apply_loaded_profile(data, "settings.json")
    except Exception as e:
        logger.error(f"Errore elaborazione profilo da dati: {e}")
        return {"success": False, "error": str(e)}

@app.websocket("/ws")
async def websocket_telemetry(ws: WebSocket):
    await ws.accept()
    q = tapo_service.subscribe()
    # Invia subito lo stato corrente nel formato atteso dal frontend
    await ws.send_json({"type": "telemetry", "payload": tapo_service.get_state_payload()})
    try:
        while True:
            # Attendiamo il prossimo campionamento (ogni 2 sec)
            data = await q.get()
            await ws.send_json(data)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        tapo_service.unsubscribe(q)

def find_free_port(start_port: int = 8000, max_port: int = 8150, host: str = "127.0.0.1") -> int:
    import socket
    for p in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    # Fallback SO
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]

def run_uvicorn_server(host: str, port: int):
    import uvicorn
    class CustomUvicornServer(uvicorn.Server):
        def install_signal_handlers(self):
            # Avoid signal errors in secondary threads and Windows GUI processes
            pass

    try:
        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None  # Critical: disables color loggers that fail on missing console TTY
        )
        server = CustomUvicornServer(config=config)
        server.run()
    except Exception as e:
        logger.error(f"Errore fatale server HTTP su {host}:{port}: {e}")
        try:
            with open(DATA_DIR / "crash.log", "a", encoding="utf-8") as f:
                import traceback
                f.write(f"\n--- UVICORN SERVER CRASH su {host}:{port} ---\n")
                traceback.print_exc(file=f)
        except Exception:
            pass

def wait_for_server(host: str, port: int, timeout: float = 25.0) -> bool:
    import socket
    import time
    start_time = time.time()
    logger.info(f"In attesa che il server HTTP sia pronto su {host}:{port}...")
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                logger.info(f"Server pronto e connessione stabilita in {time.time() - start_time:.2f}s!")
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.15)
    logger.error(f"Timeout attesa server ({timeout}s) scaduto!")
    return False

def start_desktop_app():
    cfg = load_config()
    host = cfg.get("host", "127.0.0.1")
    desired_port = int(cfg.get("port", 8000))
    actual_port = find_free_port(start_port=desired_port, host=host)
    if actual_port != desired_port:
        logger.info(f"Porta {desired_port} occupata. Passaggio automatico alla porta libera {actual_port}")
    
    url = f"http://{host}:{actual_port}"
    
    # Avvia il server FastAPI in un thread background
    server_thread = threading.Thread(target=run_uvicorn_server, args=(host, actual_port), daemon=True)
    server_thread.start()
    
    # Attendi che il server sia effettivamente attivo e in ascolto sul socket
    server_ready = wait_for_server(host, actual_port, timeout=25.0)
    if not server_ready:
        logger.error("Impossibile contattare il server locale FastAPI.")
    
    # Finestra nativa Windows 11 centrata sullo schermo & Gadget Desktop
    try:
        import webview
        logger.info(f"Apertura finestra Windows 11 su {url}")
        
        win_w = 1240
        win_h = 740
        win_x = None
        win_y = None
        screens = None
        try:
            screens = webview.screens
            if screens:
                primary = screens[0]
                win_x = max(0, int((primary.width - win_w) / 2))
                win_y = max(0, int((primary.height - win_h) / 2))
        except Exception:
            pass

        window = webview.create_window(
            title="Tapo P110 Control Center — Windows 11",
            url=url,
            width=win_w,
            height=win_h,
            x=win_x,
            y=win_y,
            min_size=(900, 600),
            background_color="#070a12"
        )

        # Il gadget desktop viene SEMPRE pre-creato (hidden=True),
        # così è disponibile istantaneamente al caricamento del profilo o toggle impostazioni senza riavvio!
        gadget_w = 250
        gadget_h = 345
        gx = None
        gy = None
        try:
            if screens:
                primary = screens[0]
                gx = max(0, primary.width - gadget_w - 24)
                gy = max(0, primary.height - gadget_h - 48)
        except Exception:
            pass

        gadget_window = webview.create_window(
            title="Tapo P110 Gadget",
            url=f"{url}/gadget",
            width=gadget_w,
            height=gadget_h,
            x=gx,
            y=gy,
            frameless=True,
            on_top=False,
            hidden=True,
            background_color="#0a0f1d"
        )

        global _desktop_main_window, _desktop_gadget_window
        _desktop_main_window = window
        _desktop_gadget_window = gadget_window

        tray_instance = None
        def init_system_tray():
            nonlocal tray_instance
            global _tray_instance
            try:
                import pystray
                from PIL import Image
                icon_path = BASE_DIR / "Icona" / "icon.ico"
                if icon_path.exists():
                    tray_img = Image.open(icon_path)
                else:
                    tray_img = Image.new('RGB', (32, 32), color=(14, 165, 233))

                def act_show_main(icon, item):
                    try:
                        if gadget_window:
                            gadget_window.hide()
                        window.show()
                        window.restore()
                    except Exception:
                        pass

                def act_show_gadget(icon, item):
                    if gadget_window:
                        try:
                            gadget_window.show()
                            gadget_window.restore()
                        except Exception:
                            pass

                def act_exit(icon, item):
                    icon.stop()
                    if gadget_window:
                        try:
                            gadget_window.destroy()
                        except Exception:
                            pass
                    try:
                        window.destroy()
                    except Exception:
                        pass

                menu_items = [
                    pystray.MenuItem("Apri Tapo Control Center", act_show_main, default=True),
                ]
                if gadget_window:
                    menu_items.append(pystray.MenuItem("Mostra Gadget Desktop", act_show_gadget))
                menu_items.extend([
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Esci", act_exit)
                ])

                tray_instance = pystray.Icon(
                    "tapo_p110_app",
                    tray_img,
                    "Tapo P110 Control Center",
                    pystray.Menu(*menu_items)
                )
                _tray_instance = tray_instance
                tray_thread = threading.Thread(target=tray_instance.run, daemon=True)
                tray_thread.start()
            except Exception as ex_tray:
                logger.warning(f"Inizializzazione system tray non riuscita: {ex_tray}")

        def on_closing():
            current_cfg = load_config()
            if current_cfg.get("minimize_to_tray", False):
                try:
                    window.hide()
                    if gadget_window and current_cfg.get("show_desktop_gadget", False):
                        gadget_window.show()
                        gadget_window.restore()
                    return False
                except Exception:
                    pass
            if tray_instance:
                try:
                    tray_instance.stop()
                except Exception:
                    pass
            return True

        def on_minimized():
            current_cfg = load_config()
            if gadget_window and current_cfg.get("show_desktop_gadget", False):
                try:
                    gadget_window.show()
                    gadget_window.restore()
                except Exception:
                    pass

        def on_restored():
            # Quando la dashboard viene ingrandita o ripristinata, chiudi il gadget
            if gadget_window:
                try:
                    gadget_window.hide()
                except Exception:
                    pass

        def on_loaded():
            init_system_tray()
            current_cfg = load_config()
            if current_cfg.get("minimize_on_start", False):
                try:
                    window.hide()
                    if gadget_window and current_cfg.get("show_desktop_gadget", False):
                        gadget_window.show()
                        gadget_window.restore()
                except Exception:
                    pass
            else:
                if gadget_window:
                    if current_cfg.get("show_desktop_gadget", False):
                        try:
                            gadget_window.show()
                            gadget_window.restore()
                        except Exception:
                            pass
                    else:
                        try:
                            gadget_window.hide()
                        except Exception:
                            pass

        window.events.closing += on_closing
        window.events.minimized += on_minimized
        window.events.restored += on_restored
        window.events.loaded += on_loaded

        webview.start()
    except Exception as e:
        import traceback
        err_details = traceback.format_exc()
        logger.warning(f"PyWebView non avviato ({e}). Dettagli:\n{err_details}\nFallback su browser predefinito...")
        try:
            with open(DATA_DIR / "webview_error.log", "w", encoding="utf-8") as f_err:
                f_err.write(err_details)
        except Exception:
            pass
        webbrowser.open(url)
        server_thread.join()

if __name__ == "__main__":
    try:
        if "--server" in sys.argv:
            cfg = load_config()
            h = cfg.get("host", "127.0.0.1")
            dp = int(cfg.get("port", 8000))
            ap = find_free_port(start_port=dp, host=h)
            if ap != dp:
                logger.info(f"Porta {dp} occupata. Avvio server su porta libera {ap}")
            run_uvicorn_server(h, ap)
        else:
            start_desktop_app()
    except Exception:
        import traceback
        try:
            with open(DATA_DIR / "crash.log", "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass


