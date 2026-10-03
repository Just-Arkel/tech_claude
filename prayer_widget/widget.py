"""Widget de bureau (Tkinter) affichant les heures de prière.

Clic gauche + glisser : déplacer le widget.
Clic droit : menu (paramètres, premier plan, démarrage auto, quitter).
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from . import autostart
from .config import CITY_PRESETS, load_config, save_config
from .praytimes import HIGH_LAT_RULES, HIJRI_MONTHS, METHODS, PrayerCalculator, to_hijri
from .schedule import events_around, format_countdown, local_today, next_prayer

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python < 3.9
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

LABELS = {
    "fajr": ("Fajr", "الفجر"),
    "sunrise": ("Chourouk", "الشروق"),
    "dhuhr": ("Dhuhr", "الظهر"),
    "asr": ("Asr", "العصر"),
    "maghrib": ("Maghrib", "المغرب"),
    "isha": ("Isha", "العشاء"),
}
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]

BG = "#0f2a24"
BG_ROW = "#163a32"
BG_NEXT = "#c9a227"
FG = "#f2efe6"
FG_DIM = "#9fb8ad"
FG_NEXT = "#0f2a24"
ACCENT = "#e3c565"

FONT = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"


def resolve_tz(name: str):
    if not name or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None  # sous Windows, installer « tzdata » (pip install tzdata)


class PrayerWidget:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.fired = set()
        self._drag = (0, 0)
        self._day = None

        root.title("Heures de prière")
        root.overrideredirect(True)
        root.configure(bg=BG)
        self._apply_window_options()

        self._build_ui()
        self._build_menu()
        self._recompute()
        self._place_window()
        self._tick()

    # ---------------------------------------------------------------- UI

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG, padx=14, pady=10,
                         highlightthickness=1, highlightbackground=ACCENT)
        outer.pack(fill="both", expand=True)

        top = tk.Frame(outer, bg=BG)
        top.pack(fill="x")
        self.city_lbl = tk.Label(top, bg=BG, fg=ACCENT, font=(FONT, 12, "bold"), anchor="w")
        self.city_lbl.pack(side="left")
        close = tk.Label(top, text="✕", bg=BG, fg=FG_DIM, font=(FONT, 10), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.quit())

        self.clock_lbl = tk.Label(outer, bg=BG, fg=FG, font=(FONT, 22, "bold"))
        self.clock_lbl.pack(pady=(2, 0))
        self.date_lbl = tk.Label(outer, bg=BG, fg=FG_DIM, font=(FONT, 9))
        self.date_lbl.pack()
        self.hijri_lbl = tk.Label(outer, bg=BG, fg=FG_DIM, font=(FONT, 9))
        self.hijri_lbl.pack(pady=(0, 6))

        self.rows = {}
        for name in LABELS:
            row = tk.Frame(outer, bg=BG_ROW, padx=10, pady=3)
            row.pack(fill="x", pady=1)
            fr, ar = LABELS[name]
            lbls = (
                tk.Label(row, text=fr, bg=BG_ROW, fg=FG, font=(FONT, 11), width=9, anchor="w"),
                tk.Label(row, text=ar, bg=BG_ROW, fg=FG_DIM, font=(FONT, 10), width=6),
                tk.Label(row, text="--:--", bg=BG_ROW, fg=FG, font=(FONT, 11, "bold"), anchor="e"),
            )
            lbls[0].pack(side="left")
            if self.cfg.get("show_arabic"):
                lbls[1].pack(side="left")
            lbls[2].pack(side="right")
            self.rows[name] = (row, lbls)

        self.next_lbl = tk.Label(outer, bg=BG, fg=ACCENT, font=(FONT, 10, "bold"))
        self.next_lbl.pack(pady=(8, 0))

        # Déplacement et menu sur toutes les zones du widget
        for w in self._all_widgets(self.root):
            if w is not close:
                w.bind("<ButtonPress-1>", self._start_drag)
                w.bind("<B1-Motion>", self._on_drag)
                w.bind("<ButtonRelease-1>", lambda e: self._save_position())
                w.bind("<Button-3>", self._show_menu)
                w.bind("<Button-2>", self._show_menu)  # macOS

    def _all_widgets(self, w):
        yield w
        for c in w.winfo_children():
            yield from self._all_widgets(c)

    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.var_top = tk.BooleanVar(value=self.cfg["always_on_top"])
        self.var_alerts = tk.BooleanVar(value=self.cfg["alerts"])
        self.var_autostart = tk.BooleanVar(value=autostart.is_enabled())
        self.menu.add_command(label="Paramètres…", command=self.open_settings)
        self.menu.add_checkbutton(label="Toujours au premier plan", variable=self.var_top,
                                  command=self._toggle_top)
        self.menu.add_checkbutton(label="Notifications", variable=self.var_alerts,
                                  command=self._toggle_alerts)
        if autostart.supported():
            self.menu.add_checkbutton(label="Lancer au démarrage", variable=self.var_autostart,
                                      command=self._toggle_autostart)
        self.menu.add_separator()
        self.menu.add_command(label="Tester la notification",
                              command=lambda: self.notify("Test", "La notification fonctionne."))
        self.menu.add_separator()
        self.menu.add_command(label="Quitter", command=self.quit)

    def _show_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    # --------------------------------------------------------- fenêtre

    def _apply_window_options(self):
        self.root.attributes("-topmost", bool(self.cfg["always_on_top"]))
        try:
            self.root.attributes("-alpha", float(self.cfg["opacity"]))
        except tk.TclError:
            pass

    def _place_window(self):
        self.root.update_idletasks()
        x, y = self.cfg.get("x"), self.cfg.get("y")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if x is None or y is None or not (0 <= x < sw - 40 and 0 <= y < sh - 40):
            x, y = sw - w - 30, 60  # coin supérieur droit par défaut
        self.root.geometry(f"+{x}+{y}")

    def _start_drag(self, event):
        self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        self.root.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _save_position(self):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)

    def _toggle_top(self):
        self.cfg["always_on_top"] = self.var_top.get()
        self._apply_window_options()
        save_config(self.cfg)

    def _toggle_alerts(self):
        self.cfg["alerts"] = self.var_alerts.get()
        save_config(self.cfg)

    def _toggle_autostart(self):
        try:
            autostart.set_enabled(self.var_autostart.get())
        except OSError as exc:
            self.var_autostart.set(autostart.is_enabled())
            messagebox.showerror("Démarrage automatique", str(exc), parent=self.root)

    # ---------------------------------------------------------- calcul

    def _recompute(self):
        c = self.cfg
        self.tz = resolve_tz(c["timezone"])
        self.calc = PrayerCalculator(
            float(c["latitude"]), float(c["longitude"]), c["method"],
            asr_factor=int(c["asr_factor"]), high_lat_rule=c["high_lat_rule"],
            elevation=float(c.get("elevation") or 0), adjustments=c["adjustments"])
        self._day = local_today(self.tz)
        self.today = self.calc.times_for(self._day, self.tz)
        self.events = events_around(self.calc, self._day, self.tz)

        self.city_lbl.config(text=c["city"] or "Ma position")
        d = self._day
        self.date_lbl.config(text=f"{DAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1]} {d.year}")
        hy, hm, hd = to_hijri(d, int(c.get("hijri_offset") or 0))
        self.hijri_lbl.config(text=f"{hd} {HIJRI_MONTHS[hm - 1]} {hy} H")
        for name, (_, lbls) in self.rows.items():
            t = self.today.get(name)
            lbls[2].config(text=t.strftime("%H:%M") if t else "--:--")

    def _now(self) -> datetime:
        return datetime.now(self.tz) if self.tz else datetime.now().astimezone()

    def _tick(self):
        now = self._now()
        if now.date() != self._day:
            self._recompute()

        self.clock_lbl.config(text=now.strftime("%H:%M:%S"))
        nxt = next_prayer(self.events, now)
        highlighted = None
        if nxt:
            name, when = nxt
            label = LABELS[name][0]
            suffix = " (demain)" if when.date() > self._day and name != "isha" else ""
            self.next_lbl.config(text=f"{label}{suffix} dans {format_countdown(when - now)}")
            highlighted = name
        for name, (row, lbls) in self.rows.items():
            on = name == highlighted
            bg, fg = (BG_NEXT, FG_NEXT) if on else (BG_ROW, FG)
            row.config(bg=bg)
            lbls[0].config(bg=bg, fg=fg)
            lbls[1].config(bg=bg, fg=fg if on else FG_DIM)
            lbls[2].config(bg=bg, fg=fg)

        self._check_alerts(now)
        self.root.after(1000 - now.microsecond // 1000, self._tick)

    def _check_alerts(self, now: datetime):
        if not self.cfg["alerts"]:
            return
        reminder = int(self.cfg.get("reminder_minutes") or 0)
        for name, when in self.events:
            label = LABELS[name][0]
            key = (name, when.isoformat())
            if key not in self.fired and timedelta(0) <= now - when < timedelta(minutes=1):
                self.fired.add(key)
                self.notify(f"{label} — {LABELS[name][1]}" if self.cfg.get("show_arabic") else label,
                            f"C'est l'heure de la prière de {label} ({when:%H:%M}).", sound=True)
            if reminder > 0:
                rkey = ("rappel",) + key
                at = when - timedelta(minutes=reminder)
                if rkey not in self.fired and timedelta(0) <= now - at < timedelta(minutes=1):
                    self.fired.add(rkey)
                    self.notify(f"{label} dans {reminder} min",
                                f"La prière de {label} est à {when:%H:%M}.")

    # ---------------------------------------------------- notifications

    def notify(self, title: str, message: str, sound: bool = False):
        self._play_sound(sound)
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=ACCENT)
        body = tk.Frame(toast, bg=BG, padx=16, pady=12)
        body.pack(padx=2, pady=2)
        tk.Label(body, text=title, bg=BG, fg=ACCENT, font=(FONT, 12, "bold")).pack(anchor="w")
        tk.Label(body, text=message, bg=BG, fg=FG, font=(FONT, 10)).pack(anchor="w", pady=(4, 0))
        tk.Label(body, text="Cliquer pour fermer", bg=BG, fg=FG_DIM, font=(FONT, 8)).pack(anchor="e", pady=(6, 0))
        toast.update_idletasks()
        sw, sh = toast.winfo_screenwidth(), toast.winfo_screenheight()
        toast.geometry(f"+{sw - toast.winfo_width() - 24}+{sh - toast.winfo_height() - 64}")
        for w in self._all_widgets(toast):
            w.bind("<Button-1>", lambda e: toast.destroy())
        toast.after(60_000, lambda: toast.winfo_exists() and toast.destroy())

    def _play_sound(self, adhan: bool):
        sound_file = self.cfg.get("sound_file") or ""
        if sys.platform.startswith("win"):
            import winsound
            if adhan and sound_file and os.path.isfile(sound_file):
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        else:
            self.root.bell()

    # ---------------------------------------------------- paramètres

    def open_settings(self):
        SettingsDialog(self.root, self.cfg, self._on_settings_saved)

    def _on_settings_saved(self, new_cfg: dict):
        arabic_changed = bool(new_cfg.get("show_arabic")) != bool(self.cfg.get("show_arabic"))
        self.cfg.update(new_cfg)
        save_config(self.cfg)
        self.var_alerts.set(self.cfg["alerts"])
        self.fired.clear()
        if arabic_changed:
            for _, lbls in self.rows.values():
                if self.cfg["show_arabic"]:
                    lbls[1].pack(side="left", after=lbls[0])
                else:
                    lbls[1].pack_forget()
        self._recompute()

    def quit(self):
        self._save_position()
        self.root.destroy()


class SettingsDialog:
    def __init__(self, parent: tk.Tk, cfg: dict, on_save):
        self.cfg = cfg
        self.on_save = on_save
        self.win = win = tk.Toplevel(parent)
        win.title("Paramètres — Heures de prière")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        r = 0

        def row(label, widget):
            nonlocal r
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            widget.grid(row=r, column=1, sticky="ew", pady=3)
            r += 1

        self.v_preset = tk.StringVar()
        preset = ttk.Combobox(frm, textvariable=self.v_preset, values=list(CITY_PRESETS),
                              state="readonly", width=34)
        preset.bind("<<ComboboxSelected>>", self._apply_preset)
        row("Ville prédéfinie", preset)

        self.v_city = tk.StringVar(value=cfg["city"])
        row("Nom affiché", ttk.Entry(frm, textvariable=self.v_city))
        self.v_lat = tk.StringVar(value=str(cfg["latitude"]))
        row("Latitude", ttk.Entry(frm, textvariable=self.v_lat))
        self.v_lng = tk.StringVar(value=str(cfg["longitude"]))
        row("Longitude", ttk.Entry(frm, textvariable=self.v_lng))
        self.v_tz = tk.StringVar(value=cfg["timezone"])
        row("Fuseau (vide = PC)", ttk.Entry(frm, textvariable=self.v_tz))

        self.method_keys = list(METHODS)
        self.v_method = tk.StringVar(value=METHODS[cfg["method"]].label)
        row("Méthode de calcul", ttk.Combobox(frm, textvariable=self.v_method, state="readonly",
                                              values=[METHODS[k].label for k in self.method_keys]))
        self.asr_labels = ["Standard (Chafi'i, Maliki, Hanbali)", "Hanafi"]
        self.v_asr = tk.StringVar(value=self.asr_labels[int(cfg["asr_factor"]) - 1])
        row("Calcul de l'Asr", ttk.Combobox(frm, textvariable=self.v_asr, state="readonly",
                                           values=self.asr_labels))
        self.v_high = tk.StringVar(value=cfg["high_lat_rule"])
        row("Hautes latitudes", ttk.Combobox(frm, textvariable=self.v_high, state="readonly",
                                            values=list(HIGH_LAT_RULES)))
        self.v_hijri = tk.StringVar(value=str(cfg.get("hijri_offset", 0)))
        row("Correction hégirienne (j)", ttk.Spinbox(frm, from_=-2, to=2, textvariable=self.v_hijri, width=5))

        self.v_arabic = tk.BooleanVar(value=cfg.get("show_arabic", False))
        row("Noms en arabe", ttk.Checkbutton(frm, variable=self.v_arabic))
        self.v_alerts = tk.BooleanVar(value=cfg["alerts"])
        row("Notifications", ttk.Checkbutton(frm, variable=self.v_alerts))
        self.v_rem = tk.StringVar(value=str(cfg.get("reminder_minutes", 0)))
        row("Rappel avant (min, 0 = non)", ttk.Spinbox(frm, from_=0, to=60, textvariable=self.v_rem, width=5))
        self.v_sound = tk.StringVar(value=cfg.get("sound_file", ""))
        row("Son de l'adhan (.wav)", ttk.Entry(frm, textvariable=self.v_sound))

        adj = ttk.Frame(frm)
        self.v_adj = {}
        for i, name in enumerate(LABELS):
            ttk.Label(adj, text=LABELS[name][0]).grid(row=0, column=i, padx=2)
            v = tk.StringVar(value=str(cfg["adjustments"].get(name, 0)))
            ttk.Spinbox(adj, from_=-30, to=30, textvariable=v, width=4).grid(row=1, column=i, padx=2)
            self.v_adj[name] = v
        row("Ajustements (min)", adj)

        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Annuler", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Enregistrer", command=self._save).pack(side="right", padx=6)

    def _apply_preset(self, _event=None):
        name = self.v_preset.get()
        lat, lng, tz = CITY_PRESETS[name]
        self.v_city.set(name)
        self.v_lat.set(str(lat))
        self.v_lng.set(str(lng))
        self.v_tz.set(tz)

    def _save(self):
        try:
            lat = float(self.v_lat.get().replace(",", "."))
            lng = float(self.v_lng.get().replace(",", "."))
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
            adjustments = {k: int(v.get()) for k, v in self.v_adj.items()}
            reminder = int(self.v_rem.get())
            hijri = int(self.v_hijri.get())
        except ValueError:
            messagebox.showerror("Paramètres", "Valeurs numériques invalides.", parent=self.win)
            return
        tz = self.v_tz.get().strip()
        if tz and resolve_tz(tz) is None:
            messagebox.showerror(
                "Paramètres",
                f"Fuseau horaire inconnu : {tz}\nExemple : Europe/Paris.\n"
                "Sous Windows, installez le paquet tzdata (pip install tzdata), "
                "ou laissez vide pour utiliser l'heure du PC.", parent=self.win)
            return
        method = self.method_keys[[METHODS[k].label for k in self.method_keys].index(self.v_method.get())]
        self.on_save({
            "city": self.v_city.get().strip(),
            "latitude": lat,
            "longitude": lng,
            "timezone": tz,
            "method": method,
            "asr_factor": self.asr_labels.index(self.v_asr.get()) + 1,
            "high_lat_rule": self.v_high.get(),
            "hijri_offset": hijri,
            "show_arabic": self.v_arabic.get(),
            "alerts": self.v_alerts.get(),
            "reminder_minutes": reminder,
            "sound_file": self.v_sound.get().strip(),
            "adjustments": adjustments,
        })
        self.win.destroy()


def main():
    root = tk.Tk()
    PrayerWidget(root)
    root.mainloop()


if __name__ == "__main__":
    main()
