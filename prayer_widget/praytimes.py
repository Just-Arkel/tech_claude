"""Calcul hors-ligne des heures de prière.

Implémentation de l'algorithme astronomique de PrayTimes.org (position du
soleil, équation du temps, angles crépusculaires), sans dépendance externe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Dict, Optional

PRAYER_NAMES = ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]


@dataclass(frozen=True)
class Method:
    label: str
    fajr_angle: float
    isha_angle: Optional[float] = None    # en degrés sous l'horizon
    isha_minutes: Optional[float] = None  # ou minutes après le Maghrib
    maghrib_angle: Optional[float] = None  # None = coucher du soleil


METHODS: Dict[str, Method] = {
    "MWL": Method("Ligue Islamique Mondiale (18° / 17°)", 18, isha_angle=17),
    "ISNA": Method("ISNA - Amérique du Nord (15° / 15°)", 15, isha_angle=15),
    "Egypt": Method("Autorité égyptienne (19,5° / 17,5°)", 19.5, isha_angle=17.5),
    "Makkah": Method("Umm al-Qura, La Mecque (18,5° / 90 min)", 18.5, isha_minutes=90),
    "Karachi": Method("Université de Karachi (18° / 18°)", 18, isha_angle=18),
    "France": Method("UOIF / Musulmans de France (12° / 12°)", 12, isha_angle=12),
    "France15": Method("France 15° / 15°", 15, isha_angle=15),
    "France18": Method("France 18° / 17° (Grande Mosquée de Paris)", 18, isha_angle=17),
    "Morocco": Method("Maroc - Habous (19° / 17°)", 19, isha_angle=17),
    "Algeria": Method("Algérie (18° / 17°)", 18, isha_angle=17),
    "Tunisia": Method("Tunisie (18° / 18°)", 18, isha_angle=18),
    "Turkey": Method("Turquie - Diyanet (18° / 17°)", 18, isha_angle=17),
    "Gulf": Method("Région du Golfe (19,5° / 90 min)", 19.5, isha_minutes=90),
    "Tehran": Method("Institut de géophysique, Téhéran", 17.7, isha_angle=14, maghrib_angle=4.5),
}

HIGH_LAT_RULES = ("AngleBased", "NightMiddle", "OneSeventh", "None")


# --- trigonométrie en degrés -------------------------------------------------

def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))
def _tan(d): return math.tan(math.radians(d))
def _asin(x): return math.degrees(math.asin(x))
def _acos(x): return math.degrees(math.acos(x))
def _atan2(y, x): return math.degrees(math.atan2(y, x))
def _acot(x): return math.degrees(math.atan(1 / x))
def _fix(a, b): return a - b * math.floor(a / b)


def julian_date(year: int, month: int, day: int) -> float:
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    return (math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1))
            + day + b - 1524.5)


def sun_position(jd: float):
    """Retourne (déclinaison en degrés, équation du temps en heures)."""
    d = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * d, 360)
    q = _fix(280.459 + 0.98564736 * d, 360)
    lon = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * d
    ra = _fix(_atan2(_cos(e) * _sin(lon), _cos(lon)) / 15, 24)
    eqt = q / 15 - ra
    decl = _asin(_sin(e) * _sin(lon))
    return decl, eqt


class PrayerCalculator:
    def __init__(self, latitude: float, longitude: float, method: str = "MWL",
                 asr_factor: int = 1, high_lat_rule: str = "AngleBased",
                 elevation: float = 0.0, adjustments: Optional[Dict[str, float]] = None):
        if method not in METHODS:
            raise ValueError(f"Méthode inconnue : {method}")
        if high_lat_rule not in HIGH_LAT_RULES:
            raise ValueError(f"Règle haute latitude inconnue : {high_lat_rule}")
        self.lat = latitude
        self.lng = longitude
        self.method = METHODS[method]
        self.asr_factor = asr_factor
        self.high_lat_rule = high_lat_rule
        self.elevation = max(elevation, 0.0)
        self.adjustments = adjustments or {}

    # -- briques de calcul (temps en heures locales solaires) --

    def _mid_day(self, jd, t):
        _, eqt = sun_position(jd + t)
        return _fix(12 - eqt, 24)

    def _sun_angle_time(self, jd, angle, t, ccw=False):
        decl, _ = sun_position(jd + t)
        noon = self._mid_day(jd, t)
        cos_h = (-_sin(angle) - _sin(decl) * _sin(self.lat)) / (_cos(decl) * _cos(self.lat))
        if not -1 <= cos_h <= 1:
            return math.nan  # le soleil n'atteint pas cet angle (hautes latitudes)
        h = _acos(cos_h) / 15
        return noon - h if ccw else noon + h

    def _asr_time(self, jd, t):
        decl, _ = sun_position(jd + t)
        angle = -_acot(self.asr_factor + _tan(abs(self.lat - decl)))
        return self._sun_angle_time(jd, angle, t)

    def _raw_times(self, jd):
        m = self.method
        rise_angle = 0.833 + 0.0347 * math.sqrt(self.elevation)
        guess = {"fajr": 5, "sunrise": 6, "dhuhr": 12, "asr": 13,
                 "sunset": 18, "maghrib": 18, "isha": 18}
        times = dict(guess)
        for _ in range(2):  # deux itérations pour affiner
            # une valeur NaN (angle jamais atteint) repart de l'estimation par défaut
            p = {k: (guess[k] if math.isnan(v) else v) / 24 for k, v in times.items()}
            times = {
                "fajr": self._sun_angle_time(jd, m.fajr_angle, p["fajr"], ccw=True),
                "sunrise": self._sun_angle_time(jd, rise_angle, p["sunrise"], ccw=True),
                "dhuhr": self._mid_day(jd, p["dhuhr"]),
                "asr": self._asr_time(jd, p["asr"]),
                "sunset": self._sun_angle_time(jd, rise_angle, p["sunset"]),
                "maghrib": self._sun_angle_time(jd, m.maghrib_angle or rise_angle, p["maghrib"]),
                "isha": (self._sun_angle_time(jd, m.isha_angle, p["isha"])
                         if m.isha_angle is not None else guess["isha"]),
            }
        return times

    def _night_portion(self, angle, night):
        rule = self.high_lat_rule
        if rule == "AngleBased":
            return angle / 60 * night
        if rule == "OneSeventh":
            return night / 7
        return night / 2  # NightMiddle

    def _adjust_high_lats(self, t):
        m = self.method
        night = _fix(t["sunrise"] - t["sunset"], 24)

        portion = self._night_portion(m.fajr_angle, night)
        if math.isnan(t["fajr"]) or _fix(t["sunrise"] - t["fajr"], 24) > portion:
            t["fajr"] = t["sunrise"] - portion

        if m.isha_angle is not None:
            portion = self._night_portion(m.isha_angle, night)
            if math.isnan(t["isha"]) or _fix(t["isha"] - t["sunset"], 24) > portion:
                t["isha"] = t["sunset"] + portion

        if m.maghrib_angle:
            portion = self._night_portion(m.maghrib_angle, night)
            if math.isnan(t["maghrib"]) or _fix(t["maghrib"] - t["sunset"], 24) > portion:
                t["maghrib"] = t["sunset"] + portion

    def times_for(self, day: date, tz: Optional[tzinfo] = None) -> Dict[str, datetime]:
        """Heures de prière du jour `day`, en datetimes conscients du fuseau `tz`.

        Si `tz` est None, le fuseau local du système est utilisé.
        """
        jd = julian_date(day.year, day.month, day.day) - self.lng / (15 * 24)
        t = self._raw_times(jd)

        if self.method.isha_minutes is not None:
            t["isha"] = t["maghrib"] + self.method.isha_minutes / 60

        if self.high_lat_rule != "None":
            self._adjust_high_lats(t)

        # Heure solaire locale -> heures UTC depuis minuit UTC du jour
        utc_midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        result: Dict[str, datetime] = {}
        for name in PRAYER_NAMES:
            hours = t[name] - self.lng / 15 + self.adjustments.get(name, 0) / 60
            if math.isnan(hours):
                continue
            utc = utc_midnight + timedelta(hours=hours)
            result[name] = utc.astimezone(tz) if tz else utc.astimezone()
        return result


# --- Calendrier hégirien (algorithme arithmétique, ±1 jour) -----------------

HIJRI_MONTHS = ["Mouharram", "Safar", "Rabi' al-awwal", "Rabi' ath-thani",
                "Joumada al-oula", "Joumada ath-thania", "Rajab", "Cha'bane",
                "Ramadan", "Chawwal", "Dhou al-qi'da", "Dhou al-hijja"]


def to_hijri(day: date, offset_days: int = 0):
    """Convertit une date grégorienne en (année, mois, jour) hégiriens tabulaires."""
    jd = int(julian_date(day.year, day.month, day.day) + 0.5) + offset_days
    l = jd - 1948440 + 10632
    n = (l - 1) // 10631
    l = l - 10631 * n + 354
    j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
    l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    month = (24 * l) // 709
    d = l - (709 * month) // 24
    year = 30 * n + j - 30
    return year, month, d
