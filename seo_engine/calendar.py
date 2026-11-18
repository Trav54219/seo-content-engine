"""Editorial calendar: pillars first, then supporting pages by opportunity."""
from __future__ import annotations

import csv
import datetime as dt

from .briefs import make_brief
from .keywords import Pillar

FIELDS = ["publish_date", "slug", "type", "primary_keyword", "intent", "theme", "target_words",
          "pillar", "owner", "status"]


def next_weekday(d: dt.date, weekday: int) -> dt.date:
    return d + dt.timedelta(days=(weekday - d.weekday()) % 7)


def build_calendar(pillars: list[Pillar], start: dt.date, per_week: int = 2, weekdays=(1, 3)) -> list[dict]:
    """Publish days default to Tue/Thu. A theme's pillar is scheduled before its
    supporting pages; themes are ordered by pillar volume; navigational clusters are skipped
    (they are not editorial content)."""
    assert per_week == len(weekdays), "per_week must match number of publish weekdays"
    queue: list[dict] = []
    for p in pillars:
        briefs = [make_brief(c, p) for c in p.clusters if c.intent != "navigational"]
        briefs.sort(key=lambda b: (not b["is_pillar"], -b["total_volume"]))
        # ensure the pillar page exists even if its keyword sits inside a supporting cluster
        queue += briefs
    # pillar-first globally: all pillars, then supporting content interleaved by theme volume
    pillars_first = [b for b in queue if b["is_pillar"]]
    rest = [b for b in queue if not b["is_pillar"]]
    ordered = pillars_first + rest
    rows, day_idx, week0 = [], 0, next_weekday(start, weekdays[0])
    base_monday = week0 - dt.timedelta(days=week0.weekday())
    for b in ordered:
        week, slot = divmod(day_idx, per_week)
        d = base_monday + dt.timedelta(weeks=week, days=weekdays[slot])
        rows.append({
            "publish_date": d.isoformat(), "slug": b["slug"], "type": "pillar" if b["is_pillar"] else "supporting",
            "primary_keyword": b["primary_keyword"], "intent": b["intent"], "theme": b["theme"],
            "target_words": b["target_words"], "pillar": b["pillar_keyword"], "owner": "unassigned", "status": "planned",
        })
        day_idx += 1
    return rows


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
