import tempfile
import unittest
from datetime import date
from pathlib import Path

from core.stats import Stats


class StatsTests(unittest.TestCase):
    def test_accumulate_and_totals(self):
        with tempfile.TemporaryDirectory() as folder:
            stats = Stats(Path(folder) / "stats.json")
            today = date(2026, 10, 23)
            stats.add(100, 50, today)
            stats.add(100, 50, today)
            stats.add(10, 5, date(2026, 10, 10))
            self.assertEqual(stats.totals(1, today), (200, 100))
            self.assertEqual(stats.totals(7, today), (200, 100))
            self.assertEqual(stats.totals(30, today), (210, 105))
            self.assertEqual(stats.totals(None, today), (210, 105))

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stats.json"
            stats = Stats(path)
            stats.add(5, 6, date(2026, 1, 1))
            stats.save()
            self.assertEqual(Stats(path).days, {"2026-01-01": [5, 6]})

    def test_series_length(self):
        with tempfile.TemporaryDirectory() as folder:
            stats = Stats(Path(folder) / "s.json")
            series = stats.series(14, date(2026, 10, 23))
            self.assertEqual(len(series), 14)
            self.assertEqual(series[-1][0], date(2026, 10, 23))


if __name__ == "__main__":
    unittest.main()
