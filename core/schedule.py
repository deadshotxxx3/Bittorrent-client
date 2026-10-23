import json
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Schedule:
    enabled: bool = False
    start: str = "08:00"
    end: str = "23:00"
    down: float = 2.0
    up: float = 1.0
    days: list = field(default_factory=lambda: list(range(7)))

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(text) -> "Schedule":
        try:
            data = json.loads(text)
            return Schedule(**{k: v for k, v in data.items() if k in Schedule.__dataclass_fields__})
        except Exception:
            return Schedule()


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def is_active(schedule: Schedule, now: datetime) -> bool:
    if not schedule.enabled:
        return False
    current = now.hour * 60 + now.minute
    start = _minutes(schedule.start)
    end = _minutes(schedule.end)
    if start == end:
        return now.weekday() in schedule.days
    if start < end:
        return start <= current < end and now.weekday() in schedule.days
    if current >= start:
        return now.weekday() in schedule.days
    if current < end:
        return (now.weekday() - 1) % 7 in schedule.days
    return False


def effective_limits(schedule: Schedule, base_down: float, base_up: float,
                     now: datetime) -> tuple[float, float]:
    if is_active(schedule, now):
        return schedule.down, schedule.up
    return base_down, base_up
