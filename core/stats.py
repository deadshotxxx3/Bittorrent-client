import json
from datetime import date, timedelta
from pathlib import Path


class Stats:
    def __init__(self, path):
        self.path = Path(path)
        self.days: dict[str, list] = {}
        self.dirty = False
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.days = {k: [int(v[0]), int(v[1])] for k, v in data.get("days", {}).items()}
        except Exception:
            self.days = {}

    def save(self) -> None:
        if not self.dirty:
            return
        keep = sorted(self.days)[-800:]
        payload = {"days": {k: self.days[k] for k in keep}}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        self.dirty = False

    def add(self, down: float, up: float, today: date | None = None) -> None:
        if down <= 0 and up <= 0:
            return
        key = (today or date.today()).isoformat()
        entry = self.days.setdefault(key, [0, 0])
        entry[0] += int(down)
        entry[1] += int(up)
        self.dirty = True

    def totals(self, days: int | None = None, today: date | None = None) -> tuple:
        end = today or date.today()
        down = up = 0
        for key, (d, u) in self.days.items():
            if days is not None:
                age = (end - date.fromisoformat(key)).days
                if age < 0 or age >= days:
                    continue
            down += d
            up += u
        return down, up

    def series(self, count: int, today: date | None = None) -> list:
        end = today or date.today()
        result = []
        for offset in range(count - 1, -1, -1):
            day = end - timedelta(days=offset)
            d, u = self.days.get(day.isoformat(), [0, 0])
            result.append((day, d, u))
        return result
