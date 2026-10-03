"""Logique « quelle est la prochaine prière ? », indépendante de l'interface."""

from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo
from typing import List, Optional, Tuple

from .praytimes import PrayerCalculator

# Le lever du soleil est affiché mais n'est pas une prière.
ALERT_PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha")


def local_today(tz: Optional[tzinfo]) -> date:
    return datetime.now(tz).date() if tz else datetime.now().astimezone().date()


def events_around(calc: PrayerCalculator, day: date, tz: Optional[tzinfo]
                  ) -> List[Tuple[str, datetime]]:
    """Prières de la veille, du jour et du lendemain, triées chronologiquement.

    La veille est incluse car l'Isha peut tomber après minuit en été.
    """
    events = []
    for offset in (-1, 0, 1):
        for name, when in calc.times_for(day + timedelta(days=offset), tz).items():
            if name in ALERT_PRAYERS:
                events.append((name, when))
    events.sort(key=lambda e: e[1])
    return events


def next_prayer(events: List[Tuple[str, datetime]], now: datetime
                ) -> Optional[Tuple[str, datetime]]:
    for name, when in events:
        if when > now:
            return name, when
    return None


def format_countdown(delta: timedelta) -> str:
    total = max(int(delta.total_seconds()), 0)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
