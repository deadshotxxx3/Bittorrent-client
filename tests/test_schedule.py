import unittest
from datetime import datetime

from core.schedule import Schedule, effective_limits, is_active


class ScheduleTests(unittest.TestCase):
    def test_disabled(self):
        self.assertFalse(is_active(Schedule(enabled=False), datetime(2026, 10, 23, 12, 0)))

    def test_day_window(self):
        schedule = Schedule(enabled=True, start="08:00", end="23:00")
        self.assertTrue(is_active(schedule, datetime(2026, 10, 23, 12, 0)))
        self.assertFalse(is_active(schedule, datetime(2026, 10, 23, 23, 30)))

    def test_overnight_window(self):
        schedule = Schedule(enabled=True, start="22:00", end="06:00", days=[4])
        self.assertTrue(is_active(schedule, datetime(2026, 10, 23, 23, 0)))
        self.assertTrue(is_active(schedule, datetime(2026, 10, 24, 3, 0)))
        self.assertFalse(is_active(schedule, datetime(2026, 10, 23, 12, 0)))
        self.assertFalse(is_active(schedule, datetime(2026, 10, 25, 3, 0)))

    def test_effective_limits(self):
        schedule = Schedule(enabled=True, start="08:00", end="23:00", down=2.0, up=1.0)
        self.assertEqual(effective_limits(schedule, 10.0, 5.0, datetime(2026, 10, 23, 12, 0)), (2.0, 1.0))
        self.assertEqual(effective_limits(schedule, 10.0, 5.0, datetime(2026, 10, 23, 3, 0)), (10.0, 5.0))

    def test_json_roundtrip(self):
        schedule = Schedule(enabled=True, start="01:00", end="02:00", days=[1, 2])
        self.assertEqual(Schedule.from_json(schedule.to_json()), schedule)
        self.assertEqual(Schedule.from_json("garbage"), Schedule())


if __name__ == "__main__":
    unittest.main()
