"""Lancement automatique du widget à l'ouverture de session (Windows / Linux)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_DIR / "PrayerWidget.pyw"


def _target() -> Path | None:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                / "Startup" / "PrayerWidget.vbs")
    if sys.platform.startswith("linux"):
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "autostart" / "prayer-widget.desktop"
    return None


def supported() -> bool:
    return _target() is not None


def is_enabled() -> bool:
    target = _target()
    return bool(target and target.exists())


def _command() -> list[str]:
    if getattr(sys, "frozen", False):  # exécutable PyInstaller
        return [sys.executable]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if sys.platform.startswith("win") and pythonw.exists():
        exe = pythonw  # pas de console noire
    return [str(exe), str(LAUNCHER)]


def set_enabled(enabled: bool) -> None:
    target = _target()
    if target is None:
        raise OSError("Démarrage automatique non pris en charge sur ce système.")
    if not enabled:
        if target.exists():
            target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = _command()
    if sys.platform.startswith("win"):
        quoted = " ".join(f'""{c}""' for c in cmd)
        target.write_text(f'CreateObject("WScript.Shell").Run "{quoted}", 0, False\n',
                          encoding="utf-8")
    else:
        exec_line = " ".join(f'"{c}"' for c in cmd)
        target.write_text(
            "[Desktop Entry]\nType=Application\nName=Heures de prière\n"
            f"Exec={exec_line}\nX-GNOME-Autostart-enabled=true\n", encoding="utf-8")
