"""Chargement / sauvegarde de la configuration utilisateur (JSON)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
    "elevation": 0,
    "timezone": "",            # nom IANA (ex. "Europe/Paris") ; vide = fuseau du PC
    "method": "France18",
    "asr_factor": 1,           # 1 = Standard (Chafi'i, Maliki, Hanbali), 2 = Hanafi
    "high_lat_rule": "AngleBased",
    "adjustments": {"fajr": 0, "sunrise": 0, "dhuhr": 0, "asr": 0, "maghrib": 0, "isha": 0},
    "hijri_offset": 0,         # correction du calendrier hégirien en jours
    "alerts": True,            # notification + son à l'heure de chaque prière
    "reminder_minutes": 10,    # rappel avant la prière (0 = désactivé)
    "sound_file": "",          # fichier .wav optionnel (Windows) pour l'adhan
    "show_arabic": False,      # noms arabes (rendu dépendant du système)
    "always_on_top": True,
    "opacity": 0.93,
    "x": None,
    "y": None,
}

CITY_PRESETS = {
    "Paris": (48.8566, 2.3522, "Europe/Paris"),
    "Lyon": (45.7640, 4.8357, "Europe/Paris"),
    "Marseille": (43.2965, 5.3698, "Europe/Paris"),
    "Toulouse": (43.6047, 1.4442, "Europe/Paris"),
    "Lille": (50.6292, 3.0573, "Europe/Paris"),
    "Strasbourg": (48.5734, 7.7521, "Europe/Paris"),
    "Bordeaux": (44.8378, -0.5792, "Europe/Paris"),
    "Nice": (43.7102, 7.2620, "Europe/Paris"),
    "Bruxelles": (50.8503, 4.3517, "Europe/Brussels"),
    "Genève": (46.2044, 6.1432, "Europe/Zurich"),
    "Montréal": (45.5019, -73.5674, "America/Toronto"),
    "Casablanca": (33.5731, -7.5898, "Africa/Casablanca"),
    "Rabat": (34.0209, -6.8416, "Africa/Casablanca"),
    "Alger": (36.7538, 3.0588, "Africa/Algiers"),
    "Tunis": (36.8065, 10.1815, "Africa/Tunis"),
    "Dakar": (14.7167, -17.4677, "Africa/Dakar"),
    "Le Caire": (30.0444, 31.2357, "Africa/Cairo"),
    "Istanbul": (41.0082, 28.9784, "Europe/Istanbul"),
    "La Mecque": (21.4225, 39.8262, "Asia/Riyadh"),
    "Médine": (24.4672, 39.6111, "Asia/Riyadh"),
}


def config_path() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "PrayerWidget" / "config.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "prayer_widget" / "config.json"


def load_config(path: Path | None = None) -> dict:
    path = path or config_path()
    cfg = json.loads(json.dumps(DEFAULTS))  # copie profonde
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except (OSError, ValueError):
        return cfg
    adjustments = user.pop("adjustments", None)
    cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    if isinstance(adjustments, dict):
        cfg["adjustments"].update(adjustments)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
