import sqlite3
import datetime
from pathlib import Path
from core.config import DATA_DIR

DB_PATH = DATA_DIR / "energy_history.db"

def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            power_w REAL NOT NULL,
            voltage_v REAL NOT NULL,
            current_ma REAL NOT NULL,
            today_kwh REAL NOT NULL,
            is_on INTEGER NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(timestamp)
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_stats (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            day INTEGER NOT NULL,
            kwh REAL NOT NULL,
            PRIMARY KEY (year, month, day)
        )
    """)
    
    conn.commit()
    conn.close()

def save_sample(power_w: float, voltage_v: float, current_ma: float, today_kwh: float, is_on: bool):
    now = datetime.datetime.now()
    now_str = now.isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO samples (timestamp, power_w, voltage_v, current_ma, today_kwh, is_on)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_str, power_w, voltage_v, current_ma, today_kwh, 1 if is_on else 0))
    
    # Aggiorna il massimo kwh giornaliero registrato
    cursor.execute("""
        INSERT INTO monthly_stats (year, month, day, kwh)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(year, month, day) DO UPDATE SET
            kwh = MAX(monthly_stats.kwh, excluded.kwh)
    """, (now.year, now.month, now.day, today_kwh))
    
    conn.commit()
    conn.close()

def get_recent_samples(limit: int = 40):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, power_w, voltage_v, current_ma, today_kwh, is_on
        FROM samples
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    result = [dict(r) for r in reversed(rows)]
    return result

def get_yearly_monthly_totals(year: int = None):
    if year is None:
        year = datetime.datetime.now().year
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT month, COALESCE(SUM(kwh), 0.0) as total_kwh
        FROM monthly_stats
        WHERE year = ?
        GROUP BY month
        ORDER BY month ASC
    """, (year,))
    rows = {r["month"]: round(r["total_kwh"], 3) for r in cursor.fetchall()}
    conn.close()
    
    months_data = []
    month_names_it = [
        "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
    ]
    for m in range(1, 13):
        val = rows.get(m, 0.0)
        months_data.append({
            "month_num": m,
            "month": m,
            "month_name": month_names_it[m - 1],
            "kwh": val,
            "total_kwh": val
        })
    return months_data

def get_days_for_month(year: int, month: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT day, kwh
        FROM monthly_stats
        WHERE year = ? AND month = ?
        ORDER BY day ASC
    """, (year, month))
    rows = {r["day"]: round(r["kwh"], 3) for r in cursor.fetchall()}
    conn.close()
    
    # Calcola quanti giorni ha il mese
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    daily_list = []
    for d in range(1, days_in_month + 1):
        daily_list.append({
            "day": d,
            "kwh": rows.get(d, 0.0)
        })
    return daily_list

def export_history_data() -> dict:
    """Esporta la cronologia completa dei consumi per il salvataggio nel profilo."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT year, month, day, kwh FROM monthly_stats ORDER BY year, month, day")
    stats_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT timestamp, power_w, voltage_v, current_ma, today_kwh, is_on FROM samples ORDER BY id DESC LIMIT 120")
    sample_rows = [dict(r) for r in reversed(cursor.fetchall())]
    conn.close()

    return {
        "monthly_stats": stats_rows,
        "recent_samples": sample_rows
    }

def import_history_data(history: dict) -> bool:
    """Importa la cronologia dei consumi da un profilo caricato."""
    if not isinstance(history, dict):
        return False
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Importa statistiche mensili/giornaliere
        for item in history.get("monthly_stats", []):
            y = item.get("year")
            m = item.get("month")
            d = item.get("day")
            kwh = item.get("kwh", 0.0)
            if y and m and d:
                cursor.execute("""
                    INSERT INTO monthly_stats (year, month, day, kwh)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(year, month, day) DO UPDATE SET
                        kwh = excluded.kwh
                """, (y, m, d, kwh))

        # Importa campioni recenti
        for s in history.get("recent_samples", []):
            ts = s.get("timestamp")
            pw = s.get("power_w", 0.0)
            vv = s.get("voltage_v", 0.0)
            ma = s.get("current_ma", 0.0)
            tkwh = s.get("today_kwh", 0.0)
            ison = 1 if s.get("is_on") else 0
            if ts:
                cursor.execute("""
                    INSERT INTO samples (timestamp, power_w, voltage_v, current_ma, today_kwh, is_on)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (ts, pw, vv, ma, tkwh, ison))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False
