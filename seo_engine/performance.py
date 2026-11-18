"""Content performance report over Search Console-shaped CSV (date,page,query,clicks,impressions,position).

Works on any export with those columns. In this repo the file is synthetic.
"""
from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

# Rough expected CTR by whole position. An assumed benchmark curve, NOT measured
# data; override via expected_ctr= if you have your own.
EXPECTED_CTR = {1: .28, 2: .15, 3: .10, 4: .07, 5: .055, 6: .04, 7: .03, 8: .025, 9: .02, 10: .017}


@dataclass
class PageStats:
    page: str
    clicks: int = 0
    impressions: int = 0
    pos_weighted: float = 0.0

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def position(self) -> float:
        return self.pos_weighted / self.impressions if self.impressions else 0.0


def load_gsc(path: str) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["date"] = dt.date.fromisoformat(r["date"])
        r["clicks"], r["impressions"] = int(r["clicks"]), int(r["impressions"])
        r["position"] = float(r["position"])
    return rows


def aggregate(rows: list[dict]) -> dict[str, PageStats]:
    out: dict[str, PageStats] = {}
    for r in rows:
        s = out.setdefault(r["page"], PageStats(r["page"]))
        s.clicks += r["clicks"]
        s.impressions += r["impressions"]
        s.pos_weighted += r["position"] * r["impressions"]
    return out


def split_periods(rows: list[dict], days: int = 28):
    end = max(r["date"] for r in rows)
    cur_start = end - dt.timedelta(days=days - 1)
    prev_start = cur_start - dt.timedelta(days=days)
    cur = [r for r in rows if r["date"] >= cur_start]
    prev = [r for r in rows if prev_start <= r["date"] < cur_start]
    return cur, prev, (prev_start, cur_start, end)


def analyse(rows: list[dict], days: int = 28, min_impr: int = 300, expected_ctr=EXPECTED_CTR) -> dict:
    cur, prev, bounds = split_periods(rows, days)
    c, p = aggregate(cur), aggregate(prev)
    pages = []
    for page, s in c.items():
        old = p.get(page, PageStats(page))
        change = (s.clicks - old.clicks) / old.clicks if old.clicks else None
        flags = []
        if change is not None and change <= -0.20 and old.clicks >= 30:
            flags.append("decaying")
        if change is not None and change >= 0.20 and s.clicks >= 30:
            flags.append("growing")
        if 8 <= s.position <= 20 and s.impressions >= min_impr:
            flags.append("striking-distance")
        exp = expected_ctr.get(max(1, min(10, round(s.position))))
        if exp and s.impressions >= min_impr and s.ctr < 0.6 * exp:
            flags.append("low-ctr-for-position")
        pages.append({"page": page, "clicks": s.clicks, "impressions": s.impressions,
                      "ctr": round(s.ctr, 4), "position": round(s.position, 1),
                      "prev_clicks": old.clicks, "click_change": None if change is None else round(change, 3),
                      "flags": flags})
    pages.sort(key=lambda r: -r["clicks"])
    # query level: top queries in current period
    q: dict[str, PageStats] = {}
    for r in cur:
        s = q.setdefault(r["query"], PageStats(r["query"]))
        s.clicks += r["clicks"]; s.impressions += r["impressions"]; s.pos_weighted += r["position"] * r["impressions"]
    top_q = sorted(q.values(), key=lambda s: -s.clicks)[:5]
    return {"bounds": bounds, "pages": pages,
            "totals": {"clicks": sum(x["clicks"] for x in pages), "impressions": sum(x["impressions"] for x in pages),
                       "prev_clicks": sum(x["prev_clicks"] for x in pages)},
            "top_queries": [(s.page, s.clicks, s.impressions) for s in top_q]}


ACTIONS = {
    "decaying": "Refresh content, check for new competing results, re-link from fresh pages.",
    "striking-distance": "Add depth/internal links; page is close to page one.",
    "low-ctr-for-position": "Rewrite title and meta description; ranking is fine, the snippet is not earning clicks.",
    "growing": "Protect: do not rewrite; build supporting links.",
}


def report_markdown(a: dict) -> str:
    ps, cs, end = a["bounds"]
    t = a["totals"]
    chg = (t["clicks"] - t["prev_clicks"]) / t["prev_clicks"] * 100 if t["prev_clicks"] else 0
    out = ["# Content performance report (synthetic Search Console data)", "",
           f"Current period: {cs} to {end}. Compared with {ps} to {cs - dt.timedelta(days=1)}.", "",
           f"Clicks: **{t['clicks']}** ({chg:+.1f}% vs previous), impressions: **{t['impressions']}**.", "",
           "| Page | Clicks | Impr. | CTR | Avg pos | Click change | Flags |", "|---|---|---|---|---|---|---|"]
    for r in a["pages"]:
        ch = "n/a" if r["click_change"] is None else f"{r['click_change']*100:+.0f}%"
        out.append(f"| {r['page']} | {r['clicks']} | {r['impressions']} | {r['ctr']*100:.1f}% | {r['position']} | {ch} | {', '.join(r['flags']) or '-'} |")
    out += ["", "## Recommended actions", ""]
    any_flag = False
    for r in a["pages"]:
        for f in r["flags"]:
            any_flag = True
            out.append(f"- `{r['page']}` ({f}): {ACTIONS[f]}")
    if not any_flag:
        out.append("- No flagged pages.")
    out += ["", "## Top queries (current period)", ""]
    out += [f"- {q}: {c} clicks / {i} impressions" for q, c, i in a["top_queries"]]
    out += ["", "_CTR expectations are an assumed benchmark curve, not measured data._"]
    return "\n".join(out) + "\n"
