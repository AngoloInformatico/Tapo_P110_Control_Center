import json
import re
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = BASE_DIR / "version.json"
README_FILE = BASE_DIR / "README.md"

def get_version_info() -> dict:
    if not VERSION_FILE.exists():
        default_v = {
            "major": 1,
            "minor": 0,
            "build": 1,
            "version": "1.0.1",
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(default_v, f, indent=4)
        return default_v

    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"major": 1, "minor": 0, "build": 1, "version": "1.0.1"}

def get_version() -> str:
    info = get_version_info()
    return info.get("version", "1.0.1")

def increment_version(bump_type: str = "build") -> str:
    """
    Incrementa automaticamente la versione e aggiorna version.json e README.md
    """
    info = get_version_info()
    major = info.get("major", 1)
    minor = info.get("minor", 0)
    build = info.get("build", 1) + 1

    if bump_type == "minor":
        minor += 1
        build = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        build = 0

    new_version = f"{major}.{minor}.{build}"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info["major"] = major
    info["minor"] = minor
    info["build"] = build
    info["version"] = new_version
    info["last_updated"] = now_str

    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=4)
    except Exception:
        pass

    # Aggiorna README.md se presente
    if README_FILE.exists():
        try:
            content = README_FILE.read_text(encoding="utf-8")
            # Aggiorna badge versione: Release-vX.X.X-orange
            updated_content = re.sub(
                r"Release-v[0-9]+\.[0-9]+\.[0-9]+-orange",
                f"Release-v{new_version}-orange",
                content
            )
            README_FILE.write_text(updated_content, encoding="utf-8")
        except Exception:
            pass

    return new_version

if __name__ == "__main__":
    v = increment_version()
    print(f"Versione incrementata a: v{v}")
