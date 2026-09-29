import asyncio
import time
import math
import random
import logging
from typing import Optional, Dict, Any, List
from core.config import load_config
from core.database import save_sample

logger = logging.getLogger("tapo_service")
logging.basicConfig(level=logging.INFO)

class TapoService:
    def __init__(self):
        self.device = None
        self.client = None
        self.is_connected = False
        self.device_on = False
        self.connection_error = ""
        
        # Ultima lettura
        self.active_power_w = 0.0
        self.voltage_v = 0.0
        self.current_ma = 0.0
        self.today_kwh = 0.0
        self.month_kwh = 0.0
        self.device_nickname = "Tapo P110"
        self.last_update = 0.0
        
        # Demo simulation state
        self._sim_energy_today = 0.85
        self._sim_base_load = 135.0
        self._sim_step = 0
        
        # Polling task
        self._running = False
        self._poll_task = None
        self._subscribers: List[asyncio.Queue] = []

    async def initialize(self):
        cfg = load_config()
        if cfg.get("demo_mode") or not cfg.get("ip") or not cfg.get("email"):
            logger.info("Avvio in modalità SIMULAZIONE / DEMO (nessuna credenziale o demo_mode attivo)")
            self.is_connected = True
            self.device_on = True
            self.connection_error = ""
            return True
        
        return await self.connect_device(cfg["ip"], cfg["email"], cfg["password"])

    async def connect_device(self, ip: str, email: str, password: str) -> bool:
        if not ip or not email or not password:
            self.is_connected = False
            self.connection_error = "Credenziali o IP incompleti"
            return False
        
        # 1. Tentativo primario con python-kasa (permette lettura reale dei registri hardware V, A, W da get_emeter_data)
        try:
            from kasa import Discover, Credentials
            creds = Credentials(email, password)
            dev = await Discover.discover_single(ip, credentials=creds)
            await dev.update()
            self.device = dev
            self.device_on = dev.is_on
            self.device_nickname = getattr(dev, "alias", None) or "Tapo P110"
            self.is_connected = True
            self.connection_error = ""
            logger.info(f"Connesso con successo a Tapo P110 via python-kasa: {self.device_nickname} (Stato: {'ON' if self.device_on else 'OFF'})")
            return True
        except Exception as e_kasa:
            logger.warning(f"Connessione con python-kasa non riuscita ({e_kasa}), provo fallback con tapo SDK...")

        # 2. Fallback con tapo SDK
        try:
            from tapo import ApiClient
            self.client = ApiClient(email, password)
            self.device = await self.client.p110(ip)
            
            # Test lettura info
            info = await self.device.get_device_info()
            self.device_on = info.device_on
            self.device_nickname = info.nickname or "Tapo P110"
            self.is_connected = True
            self.connection_error = ""
            logger.info(f"Connesso con successo a Tapo P110: {self.device_nickname} (Stato: {'ON' if self.device_on else 'OFF'})")
            return True
        except Exception as e:
            err_msg = str(e)
            logger.warning(f"Errore connessione con tapo SDK: {err_msg}. Provo fallback...")
            
            # Se l'errore è FORBIDDEN da Tapo SDK, è dovuto a Third-Party Compatibility disabilitato
            is_forbidden = "FORBIDDEN" in err_msg or "Third-Party Compatibility" in err_msg
            
            try:
                # Fallback con PyP100
                from PyP100 import PyP110
                p110 = PyP110.P110(ip, email, password)
                p110.handshake()
                p110.login()
                info = p110.getDeviceInfo()
                self.device_on = info.get("device_on", False)
                self.device_nickname = info.get("nickname", "Tapo P110")
                self.device = p110
                self.is_connected = True
                self.connection_error = ""
                logger.info(f"Connesso via PyP100 a {self.device_nickname}")
                return True
            except Exception as e2:
                self.is_connected = False
                if is_forbidden:
                    self.connection_error = "Abilita 'Controllo terze parti' nell'app Tapo (Io > Servizi di terze parti)"
                else:
                    self.connection_error = f"Errore connessione: {err_msg if err_msg else e2}"
                logger.error(self.connection_error)
                return False

    async def set_power(self, turn_on: bool) -> bool:
        """
        Accende o spegne la presa.
        Se spenta, azzera istantaneamente le letture per evitare valori obsoleti a display.
        """
        cfg = load_config()
        is_demo = cfg.get("demo_mode") or not self.is_connected or self.device is None
        
        if is_demo:
            self.device_on = turn_on
            if not turn_on:
                self.instant_zero()
            else:
                self.voltage_v = 230.5
                self.active_power_w = self._sim_base_load
                self.current_ma = round((self.active_power_w / self.voltage_v) * 1000, 1)
            await self._broadcast_state()
            return True

        try:
            if hasattr(self.device, "turn_on") and hasattr(self.device, "turn_off"):
                if turn_on:
                    await self.device.turn_on()
                else:
                    await self.device.turn_off()
            elif hasattr(self.device, "on") and asyncio.iscoroutinefunction(self.device.on):
                if turn_on:
                    await self.device.on()
                else:
                    await self.device.off()
            elif hasattr(self.device, "setPowerState"):
                # PyP100 sincrono
                await asyncio.to_thread(self.device.setPowerState, turn_on)
            elif hasattr(self.device, "turnOn") and hasattr(self.device, "turnOff"):
                if turn_on:
                    await asyncio.to_thread(self.device.turnOn)
                else:
                    await asyncio.to_thread(self.device.turnOff)
            
            self.device_on = turn_on
            if not turn_on:
                # Regola fondamentale: azzeramento istantaneo
                self.instant_zero()
            
            await self._broadcast_state()
            return True
        except Exception as e:
            logger.error(f"Errore cambio stato presa: {e}")
            self.connection_error = f"Errore comando: {e}"
            return False

    def instant_zero(self):
        """Azzera istantaneamente le letture dinamiche per evitare valori obsoleti."""
        self.active_power_w = 0.0
        self.voltage_v = 0.0
        self.current_ma = 0.0
        # Salviamo nel database lo stato a 0W
        save_sample(
            power_w=0.0,
            voltage_v=0.0,
            current_ma=0.0,
            today_kwh=self.today_kwh,
            is_on=False
        )

    async def fetch_telemetry(self):
        """Interroga i registri ogni 2 secondi se la presa è accesa."""
        cfg = load_config()
        is_demo = cfg.get("demo_mode") or not self.is_connected or self.device is None
        
        if is_demo:
            if not self.device_on:
                self.active_power_w = 0.0
                self.voltage_v = 0.0
                self.current_ma = 0.0
            else:
                self._sim_step += 0.2
                fluctuation = math.sin(self._sim_step) * 15 + (random.random() * 6 - 3)
                v_fluct = (random.random() * 1.6 - 0.8)
                self.voltage_v = round(230.250 + v_fluct, 3)
                self.active_power_w = max(5.0, round(self._sim_base_load + fluctuation, 1))
                self.current_ma = round((self.active_power_w / self.voltage_v) * 1000, 1)
                interval = float(cfg.get("poll_interval", 4.0))
                self._sim_energy_today += (self.active_power_w / 3600.0 / 1000.0) * interval
                self.today_kwh = round(self._sim_energy_today, 3)
                self.month_kwh = round(34.2 + self.today_kwh, 2)
            
            self.last_update = time.time()
            save_sample(self.active_power_w, self.voltage_v, self.current_ma, self.today_kwh, self.device_on)
            return

        try:
            # Caso 1: Device connesso con python-kasa (registri hardware reali: V, A, W)
            if hasattr(self.device, "update") and hasattr(self.device, "features"):
                await self.device.update()
                self.device_on = self.device.is_on
                if hasattr(self.device, "alias") and self.device.alias:
                    self.device_nickname = self.device.alias

                if not self.device_on:
                    self.instant_zero()
                    self.last_update = time.time()
                    return

                # Tensione reale misurata dal convertitore interno ADC (in Volt con 3 decimali)
                if "voltage" in self.device.features and self.device.features["voltage"].value is not None:
                    self.voltage_v = round(float(self.device.features["voltage"].value), 3)
                else:
                    self.voltage_v = 230.000

                # Corrente reale RMS misurata dal sensore (in Ampere -> convertita in mA)
                if "current" in self.device.features and self.device.features["current"].value is not None:
                    self.current_ma = round(float(self.device.features["current"].value) * 1000.0, 1)
                elif self.voltage_v > 0 and self.active_power_w > 0:
                    self.current_ma = round((self.active_power_w / self.voltage_v) * 1000.0, 1)
                else:
                    self.current_ma = 0.0

                # Potenza attiva reale misurata dal chip (in Watt)
                if "current_consumption" in self.device.features and self.device.features["current_consumption"].value is not None:
                    self.active_power_w = round(float(self.device.features["current_consumption"].value), 1)
                elif "power" in self.device.features and self.device.features["power"].value is not None:
                    self.active_power_w = round(float(self.device.features["power"].value), 1)
                else:
                    self.active_power_w = 0.0

                # Energia odierna reale (kWh)
                if "consumption_today" in self.device.features and self.device.features["consumption_today"].value is not None:
                    self.today_kwh = round(float(self.device.features["consumption_today"].value), 3)

                # Energia mensile reale (kWh)
                if "consumption_this_month" in self.device.features and self.device.features["consumption_this_month"].value is not None:
                    self.month_kwh = round(float(self.device.features["consumption_this_month"].value), 2)

                self.last_update = time.time()
                self.connection_error = ""
                save_sample(self.active_power_w, self.voltage_v, self.current_ma, self.today_kwh, self.device_on)
                return

            # Caso 2: Fallback Tapo SDK reale
            if hasattr(self.device, "get_device_info"):
                info = await self.device.get_device_info()
                self.device_on = info.device_on
                if info.nickname:
                    self.device_nickname = info.nickname
            
            if not self.device_on:
                # Regola: se spenta azzera istantaneamente
                self.instant_zero()
                self.last_update = time.time()
                return

            # Presa accesa: leggiamo energia e potenza
            energy_usage = await self.device.get_energy_usage()
            p_val = getattr(energy_usage, "current_power", 0)
            if p_val > 500:
                p_watts = p_val / 1000.0
            else:
                p_watts = float(p_val)
            
            self.active_power_w = round(p_watts, 1)
            self.voltage_v = 230.0
            if self.active_power_w > 0 and self.voltage_v > 0:
                self.current_ma = round((self.active_power_w / self.voltage_v) * 1000.0, 1)
            else:
                self.current_ma = 0.0

            # today_energy in Wh -> converti in kWh
            today_wh = getattr(energy_usage, "today_energy", 0)
            month_wh = getattr(energy_usage, "month_energy", 0)
            self.today_kwh = round(today_wh / 1000.0, 3)
            self.month_kwh = round(month_wh / 1000.0, 2)
            self.last_update = time.time()
            self.connection_error = ""

            # Salva nel DB
            save_sample(self.active_power_w, self.voltage_v, self.current_ma, self.today_kwh, self.device_on)
        except Exception as e:
            logger.error(f"Errore lettura telemetria: {e}")
            self.connection_error = f"Errore lettura: {e}"

    def get_state_payload(self) -> Dict[str, Any]:
        cfg = load_config()
        from core.version_manager import get_version
        dev_ip = cfg.get("ip", "")
        if not dev_ip:
            dev_ip = "192.168.1.xxx" if not cfg.get("demo_mode") else "192.168.1.100 (Demo)"
            
        return {
            "device_on": self.device_on,
            "is_connected": self.is_connected,
            "demo_mode": cfg.get("demo_mode", False),
            "device_name": self.device_nickname,
            "device_ip": dev_ip,
            "version": get_version(),
            "active_power_w": self.active_power_w if self.device_on else 0.0,
            "voltage_v": self.voltage_v if self.device_on else 0.0,
            "current_ma": self.current_ma if self.device_on else 0.0,
            "today_kwh": self.today_kwh,
            "month_kwh": self.month_kwh,
            "error": self.connection_error,
            "timestamp": time.strftime("%H:%M:%S")
        }

    async def _broadcast_state(self):
        payload = self.get_state_payload()
        envelope = {"type": "telemetry", "payload": payload}
        for q in list(self._subscribers):
            try:
                await q.put(envelope)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def start_polling_loop(self):
        self._running = True
        cfg = load_config()
        interval = float(cfg.get("poll_interval", 4.0))
        logger.info(f"Loop di campionamento (ogni {interval}s) avviato.")
        while self._running:
            try:
                await self.fetch_telemetry()
                await self._broadcast_state()
            except Exception as e:
                logger.error(f"Eccezione nel loop: {e}")
            cfg = load_config()
            interval = float(cfg.get("poll_interval", 4.0))
            await asyncio.sleep(interval)

    def stop_polling(self):
        self._running = False

tapo_service = TapoService()
