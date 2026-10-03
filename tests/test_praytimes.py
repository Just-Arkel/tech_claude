import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from prayer_widget.config import DEFAULTS, load_config, save_config
from prayer_widget.praytimes import PrayerCalculator, to_hijri
from prayer_widget.schedule import events_around, format_countdown, next_prayer

# Références issues de l'algorithme solaire NOAA (bibliothèque astral),
# angles 18° (Fajr) et 17° (Isha), sans règle de hautes latitudes.
REFERENCES = [
    (48.8566, 2.3522, "Europe/Paris", date(2026, 3, 20),
     {"fajr": "05:06:50", "sunrise": "06:53:57", "dhuhr": "12:58:10",
      "maghrib": "19:03:00", "isha": "20:44:00"}),
    (33.5731, -7.5898, "Africa/Casablanca", date(2026, 10, 3),
     {"fajr": "06:03:20", "sunrise": "07:26:16", "dhuhr": "13:19:32",
      "maghrib": "19:11:59", "isha": "20:29:58"}),
    (-33.8688, 151.2093, "Australia/Sydney", date(2026, 1, 15),
     {"fajr": "04:19:04", "sunrise": "05:59:43", "dhuhr": "13:04:23",
      "maghrib": "20:08:45", "isha": "21:42:39"}),
]


class PrayerTimesTest(unittest.TestCase):
    def test_matches_reference_within_one_minute(self):
        for lat, lng, tz, day, expected in REFERENCES:
            zone = ZoneInfo(tz)
            times = PrayerCalculator(lat, lng, "MWL", high_lat_rule="None").times_for(day, zone)
            for name, hhmmss in expected.items():
                ref = datetime.combine(day, datetime.strptime(hhmmss, "%H:%M:%S").time(), zone)
                with self.subTest(tz=tz, prayer=name):
                    self.assertLess(abs((times[name] - ref).total_seconds()), 60)

    def test_order_and_asr(self):
        zone = ZoneInfo("Europe/Paris")
        std = PrayerCalculator(48.8566, 2.3522, "France").times_for(date(2026, 10, 3), zone)
        hanafi = PrayerCalculator(48.8566, 2.3522, "France", asr_factor=2).times_for(date(2026, 10, 3), zone)
        values = [std[k] for k in ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha")]
        self.assertEqual(values, sorted(values))
        self.assertGreater(hanafi["asr"], std["asr"])

    def test_isha_minutes_method(self):
        t = PrayerCalculator(21.4225, 39.8262, "Makkah").times_for(date(2026, 10, 3), ZoneInfo("Asia/Riyadh"))
        self.assertEqual(round((t["isha"] - t["maghrib"]).total_seconds() / 60), 90)

    def test_high_latitude_summer_has_all_times(self):
        # À Oslo en juin, le soleil ne descend jamais à 18° : la règle doit compenser.
        t = PrayerCalculator(59.91, 10.75, "MWL").times_for(date(2026, 6, 21), ZoneInfo("Europe/Oslo"))
        self.assertEqual(len(t), 6)
        self.assertLess(t["fajr"], t["sunrise"])
        self.assertGreater(t["isha"], t["maghrib"])

    def test_adjustments(self):
        zone = ZoneInfo("Europe/Paris")
        base = PrayerCalculator(48.8566, 2.3522).times_for(date(2026, 10, 3), zone)
        adj = PrayerCalculator(48.8566, 2.3522, adjustments={"dhuhr": 5}).times_for(date(2026, 10, 3), zone)
        self.assertEqual(adj["dhuhr"] - base["dhuhr"], timedelta(minutes=5))

    def test_hijri(self):
        self.assertEqual(to_hijri(date(2025, 3, 1)), (1446, 9, 1))  # 1er Ramadan 1446
        self.assertEqual(to_hijri(date(2025, 3, 1), offset_days=-1), (1446, 8, 29))


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneInfo("Europe/Paris")
        self.calc = PrayerCalculator(48.8566, 2.3522, "France18")

    def test_next_prayer_after_isha_is_tomorrow_fajr(self):
        day = date(2026, 10, 3)
        events = events_around(self.calc, day, self.zone)
        isha = self.calc.times_for(day, self.zone)["isha"]
        name, when = next_prayer(events, isha + timedelta(minutes=1))
        self.assertEqual(name, "fajr")
        self.assertEqual(when.date(), day + timedelta(days=1))

    def test_sunrise_is_not_a_next_prayer(self):
        day = date(2026, 10, 3)
        t = self.calc.times_for(day, self.zone)
        name, _ = next_prayer(events_around(self.calc, day, self.zone), t["fajr"] + timedelta(minutes=1))
        self.assertEqual(name, "dhuhr")

    def test_countdown(self):
        self.assertEqual(format_countdown(timedelta(hours=1, minutes=2, seconds=3)), "01:02:03")
        self.assertEqual(format_countdown(timedelta(seconds=-5)), "00:00:00")


class ConfigTest(unittest.TestCase):
    def test_roundtrip_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            self.assertEqual(load_config(path), DEFAULTS)
            cfg = load_config(path)
            cfg["city"] = "Lyon"
            cfg["adjustments"]["isha"] = 3
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded["city"], "Lyon")
            self.assertEqual(loaded["adjustments"]["isha"], 3)
            self.assertEqual(loaded["adjustments"]["fajr"], 0)


if __name__ == "__main__":
    unittest.main()
